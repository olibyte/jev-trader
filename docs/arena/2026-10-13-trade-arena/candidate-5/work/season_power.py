"""Read-only: how wide is a pairwise excess-Sharpe CI over a season of L sessions?"""
import sys, time
from datetime import date, timedelta
from pathlib import Path
import numpy as np
import polars as pl
from jevtrader.states import STUDY, CASH, state_rows
from jevtrader.evaluate import decisions, open_returns, backtest, portfolio, sharpe, block_bootstrap, auc

data = Path(sys.argv[1])
END = date(2026, 10, 9)
t0 = time.time()
market = {s: pl.read_parquet(data / "market" / f"{s}.parquet").filter(pl.col("date") <= END) for s in (*STUDY, CASH)}
rows = pl.concat(state_rows(s, b) for s, b in market.items() if s != CASH)
policy = pl.read_parquet(data / "policy" / "jev.parquet")
fit = rows.filter(pl.col("split").is_in(["fit", "validate"]))
test = rows.filter(pl.col("split") == "holdout")
t1 = time.time()
made = decisions(test, fit, policy)
rets = open_returns(market, END + timedelta(days=1))
port = portfolio(backtest(made, rets, 5))
t2 = time.time()
print(f"load+states {t1-t0:.1f}s, 9-arm decisions+backtest on holdout {t2-t1:.1f}s, rows {test.height}")
wide = port.with_columns((pl.col("ret") - pl.col("r_cash")).alias("x")).pivot("arm", index="date", values="x").sort("date").drop_nulls()
dates = wide["date"].to_numpy()
print("holdout traded dates", len(dates))
pairs = [("sma_filter", "buy_hold"), ("vote_revert", "vote_trend"), ("empirical_table", "jev")]
for L in (63, 126, 252, 504, len(dates)):
    for a, b in pairs:
        ses, diffs = [], []
        for start in range(0, len(dates) - L + 1, L):
            xa, xb = wide[a].to_numpy()[start:start+L], wide[b].to_numpy()[start:start+L]
            d = dates[start:start+L]
            draws = block_bootstrap(d, lambda w: sharpe(xa, w) - sharpe(xb, w), reps=400)
            ses.append(np.std(draws, ddof=1)); diffs.append(sharpe(xa) - sharpe(xb))
        full = sharpe(wide[a].to_numpy()) - sharpe(wide[b].to_numpy())
        flips = sum(np.sign(x) != np.sign(full) for x in diffs)
        print(f"L={L:5d} {a:>16} - {b:<10} seasons={len(ses):2d} mean SE={np.mean(ses):.2f} -> 95% half-width ~{1.96*np.mean(ses):.2f}; season diffs {[round(x,2) for x in diffs] if len(diffs)<=8 else ''} sign flips vs full={flips}/{len(diffs)}")
