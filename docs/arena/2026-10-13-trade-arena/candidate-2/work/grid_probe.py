"""Development-only probe: time a parameter grid and measure the multiplicity penalty.

Reads no holdout bar: every frame is cut before 2019-01-01.
"""
import itertools, sys, time
from datetime import date
from pathlib import Path

sys.path.insert(0, "research/src")
import numpy as np
import polars as pl
from jevtrader.evaluate import backtest, portfolio, open_returns, sharpe, BLOCK, REPS
from jevtrader.states import STUDY, CASH

DATA = Path("data/market")
END = date(2019, 1, 1)
START = date(2008, 1, 1)
market = {s: pl.read_parquet(DATA / f"{s}.parquet").filter(pl.col("date") < END) for s in (*STUDY, CASH)}
returns = open_returns(market, END)

c = pl.col("close")
def ema(x, n): return x.ewm_mean(span=n, adjust=False, min_samples=n)
def wilder(x, n): return x.ewm_mean(alpha=1/n, adjust=False, min_samples=n)
def hold(enter, exit_):
    # 1 on entry, 0 on exit, carry otherwise. Causal: forward fill only.
    return pl.when(enter).then(1).when(exit_).then(0).otherwise(None).forward_fill().fill_null(0)
def rsi(n):
    ch = c.diff(); g = wilder(ch.clip(lower_bound=0), n); l = wilder((-ch).clip(lower_bound=0), n)
    return pl.when(l == 0).then(100.0).otherwise(100 - 100 / (1 + g / l))

grid = {}
for w, k, ex in itertools.product((10, 20, 50), (1.5, 2.0, 2.5), ("mid", "upper")):
    mid, sd = c.rolling_mean(w), c.rolling_std(w, ddof=0)
    grid[f"bollinger_bounce/w{w}_k{k}_{ex}"] = hold(c < mid - k * sd, c > (mid if ex == "mid" else mid + k * sd))
for (f, s), sig, filt in itertools.product(((8, 17), (12, 26), (19, 39)), (5, 9, 12), (False, True)):
    m = ema(c, f) - ema(c, s); rule = m > ema(m, sig)
    if filt: rule = rule & (c > c.rolling_mean(200))
    grid[f"macd_cross/{f}_{s}_{sig}_{'sma200' if filt else 'none'}"] = rule.cast(pl.Int8)
for f, s in itertools.product((10, 20, 50), (100, 150, 200)):
    grid[f"sma_cross/{f}_{s}"] = (c.rolling_mean(f) > c.rolling_mean(s)).cast(pl.Int8)
for n, lo, hi in itertools.product((2, 14), (10, 20, 30), (50, 70)):
    grid[f"rsi_revert/{n}_{lo}_{hi}"] = hold(rsi(n) < lo, rsi(n) > hi)
grid["buy_hold"] = pl.lit(1)

t0 = time.perf_counter()
frames = []
for sym in STUDY:
    b = market[sym]
    frames.append(b.select("date", *(e.fill_null(0).cast(pl.Int8).alias(n) for n, e in grid.items()))
                  .filter(pl.col("date") >= START).with_columns(symbol=pl.lit(sym)))
wide = pl.concat(frames)
dec = wide.unpivot(index=["symbol", "date"], variable_name="arm", value_name="position").with_columns(score=pl.lit(None, pl.Float64))
t1 = time.perf_counter()
days = portfolio(backtest(dec, returns, 5))
t2 = time.perf_counter()
piv = days.with_columns(x=pl.col("ret") - pl.col("r_cash")).pivot(on="arm", index="date", values="x").sort("date")
names = [n for n in grid]
X = piv.select(names).to_numpy()
dates = piv["date"].to_numpy()
point = np.array([sharpe(X[:, j]) for j in range(X.shape[1])])

_, day = np.unique(dates, return_inverse=True); blocks = day // BLOCK; nb = blocks.max() + 1
rng = np.random.default_rng(0)
boot = np.empty((REPS, len(names)))
def wsharpe(X, w):
    n = w.sum(); m = (w[:, None] * X).sum(0) / n
    v = (w[:, None] * (X - m) ** 2).sum(0) / (n - 1)
    return m / np.sqrt(v) * np.sqrt(252)
for i in range(REPS):
    w = np.bincount(rng.integers(nb, size=nb), minlength=nb)[blocks].astype(float)
    boot[i] = wsharpe(X, w)
t3 = time.perf_counter()
print("never long or nan:", [names[j] for j in range(len(names)) if not np.isfinite(point[j])])
ok=np.isfinite(point)&np.isfinite(boot).all(0)
names=[n for j,n in enumerate(names) if ok[j]]; boot=boot[:,ok]; point=point[ok]; X=X[:,ok]
dev = boot - point
single = np.quantile(np.abs(dev), 0.95, axis=0)
grid_names = [n for n in names if n != "buy_hold"]
gi = [names.index(n) for n in grid_names]
simul = np.quantile(np.abs(dev[:, gi]).max(axis=1), 0.95)
bh = names.index("buy_hold")
diff = boot[:, gi] - boot[:, [bh]]
dpoint = point[gi] - point[bh]
dsingle = np.quantile(np.abs(diff - dpoint), 0.95, axis=0)
dsimul = np.quantile(np.abs(diff - dpoint).max(axis=1), 0.95)

print(f"variants={len(grid_names)} plus buy_hold; dev dates={len(dates)} blocks={nb}")
print(f"signals {t1-t0:.1f}s, backtest {t2-t1:.1f}s, bootstrap {REPS} reps all variants {t3-t2:.1f}s")
print(f"decision rows={dec.height:,}")
print("exposure median", float(np.median([dec.filter(pl.col("arm")==n)["position"].mean() for n in names])))
print(f"buy_hold dev Sharpe {point[bh]:.2f}")
ps = point[gi]; print(f"grid dev Sharpe: min {ps.min():.2f} median {np.median(ps):.2f} max {ps.max():.2f}  best={grid_names[int(ps.argmax())]}")
print(f"Sharpe CI half-width: single median {np.median(single[gi]):.2f}; simultaneous over grid {simul:.2f}")
print(f"Sharpe minus buy_hold half-width: single median {np.median(dsingle):.2f}; simultaneous {dsimul:.2f}")
print(f"best minus buy_hold: {dpoint.max():.2f}; variants whose single CI excludes 0: {(np.abs(dpoint) > dsingle).sum()}; simultaneous: {(np.abs(dpoint) > dsimul).sum()}")
sig = np.abs(dpoint) > dsingle
print("single-CI exclusions:", [(grid_names[i], round(float(dpoint[i]), 2)) for i in np.where(sig)[0]])
# Pairwise: all pairs share one weight draw, so a pair CI is a quantile of a difference of columns.
G = boot[:, gi]; P = point[gi]
iu = np.triu_indices(len(gi), 1)
pd = (G[:, iu[0]] - G[:, iu[1]]) - (P[iu[0]] - P[iu[1]])
print(f"pairs={len(iu[0])}; pair half-width median {np.median(np.quantile(np.abs(pd), 0.95, axis=0)):.2f}; simultaneous over all pairs {np.quantile(np.abs(pd).max(1), 0.95):.2f}")
r = np.random.default_rng(1)
D = np.abs(diff - dpoint)
for k in (1, 5, 10, 20, 36, len(gi)):
    hw = [np.quantile(D[:, r.choice(len(gi), k, replace=False)].max(1), 0.95) for _ in range(50)]
    print(f"N={k}: simultaneous half-width vs buy_hold {np.mean(hw):.2f}")
sw = dec.sort("arm","symbol","date").with_columns(s=(pl.col("position")!=pl.col("position").shift(1,fill_value=0).over("arm","symbol")).cast(pl.Int32)).group_by("arm").agg(pl.col("s").sum()/13/11)
print("switches/sleeve/yr median", sw["s"].median(), "max", sw["s"].max())
