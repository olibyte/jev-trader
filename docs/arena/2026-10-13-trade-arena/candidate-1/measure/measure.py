"""Scratch: sizes and timings for a precomputed catalog. Reads local data only."""
import itertools, json, sys, time
from datetime import date, timedelta
from pathlib import Path
import numpy as np, polars as pl
sys.path.insert(0, "research/src")
from jevtrader import evaluate as ev
from jevtrader.states import STUDY, CASH

DATA = Path("data/market")
END = date(2026, 10, 9)
H0 = date(2019, 1, 1)
t0 = time.perf_counter()
market = {s: pl.read_parquet(DATA / f"{s}.parquet").filter(pl.col("date") <= END) for s in (*STUDY, CASH)}

def positions(b):
    c = pl.col("close")
    ema = lambda x, n: x.ewm_mean(span=n, adjust=False, min_samples=n)
    macd = ema(c, 12) - ema(c, 26)
    df = b.select("date", "close",
        (c.rolling_mean(50) > c.rolling_mean(200)).alias("sma"),
        (macd > ema(macd, 9)).alias("macd"),
        (c.rolling_mean(20) - 2 * c.rolling_std(20, ddof=0)).alias("lo"),
        c.rolling_mean(20).alias("mid"))
    close, lo, mid = (df[k].to_numpy() for k in ("close", "lo", "mid"))
    pos, held = np.zeros(len(close), dtype=np.int8), 0
    for i in range(len(close)):  # stateful: enter below lower band, exit at or above the mid
        if np.isnan(lo[i]): held = 0
        elif not held and close[i] < lo[i]: held = 1
        elif held and close[i] >= mid[i]: held = 0
        pos[i] = held
    return df.select("date",
        pl.lit(1, pl.Int8).alias("buy_hold"),
        pl.col("sma").fill_null(False).cast(pl.Int8).alias("sma_filter"),
        pl.col("macd").fill_null(False).cast(pl.Int8).alias("macd_cross"),
        pl.Series("bollinger_bounce", pos))

dec = pl.concat(
    positions(b).filter(pl.col("date") >= H0).unpivot(index="date", variable_name="arm", value_name="position").with_columns(pl.lit(s).alias("symbol"))
    for s, b in market.items() if s != CASH)
returns = ev.open_returns(market, END + timedelta(days=1))
t1 = time.perf_counter()
sleeves = ev.backtest(dec, returns, ev.COST_BPS)
port = ev.portfolio(sleeves)
t2 = time.perf_counter()
arms = sorted(port["arm"].unique())
ex = {a: port.filter(pl.col("arm") == a).with_columns((pl.col("ret") - pl.col("r_cash")).alias("x")) for a in arms}
dates = ex[arms[0]]["date"].to_numpy()
for a in arms:
    i = ev.bootstrap_interval(dates, lambda w, x=ex[a]["x"].to_numpy(): ev.sharpe(x, w))
    s = sleeves.filter(pl.col("arm") == a)
    print(f"{a:18s} sharpe {i.point:.2f} [{i.lo:.2f}, {i.hi:.2f}] exposure {s['position'].cast(float).mean():.2f} switches/yr {s['switch'].sum()/(s.height/252):.1f}")
t3 = time.perf_counter()
pairs = list(itertools.combinations(arms, 2))
pt, draws = {}, {}
for a, b in pairs:
    xa, xb = ex[a]["x"].to_numpy(), ex[b]["x"].to_numpy()
    f = lambda w: ev.sharpe(xa, w) - ev.sharpe(xb, w)
    pt[(a, b)] = f(np.ones(len(dates)))
    draws[(a, b)] = ev.block_bootstrap(dates, f)  # same seed -> same block draws in every call
t4 = time.perf_counter()
D = np.array([draws[p] for p in pairs]); P = np.array([pt[p] for p in pairs])
se = D.std(axis=1, ddof=1)
crit = np.quantile(np.max(np.abs(D - D.mean(axis=1, keepdims=True)) / se[:, None], axis=0), 0.95)
print(f"pairs {len(pairs)}, max-t critical value {crit:.2f} (vs 1.96 per pair)")
for p, pp, s, d in zip(pairs, P, se, D):
    lo, hi = np.quantile(d, [0.025, 0.975])
    print(f"{p[0]:>16s} - {p[1]:16s} {pp:+.2f} 95% [{lo:+.2f}, {hi:+.2f}] simultaneous [{pp-crit*s:+.2f}, {pp+crit*s:+.2f}]")
curve = port.filter(pl.col("arm") == arms[0])
blob = json.dumps({"equity": [round(v, 6) for v in (1 + curve["ret"]).cum_prod().to_list()]}, separators=(",", ":"))
print(f"days {len(dates)}, blocks {ev.n_blocks(dates)}; one compact equity curve {len(blob)} bytes")
print(f"timing: load+signals {t1-t0:.1f}s, backtest {t2-t1:.2f}s, 4 single CIs {t3-t2:.1f}s, {len(pairs)} pair bootstraps {t4-t3:.1f}s")
