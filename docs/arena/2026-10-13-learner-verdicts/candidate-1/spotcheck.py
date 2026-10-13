"""Spot-check the Gaussian max-|z| critical value against the real block bootstrap.

Uses jevtrader.evaluate.block_bootstrap and sharpe and jevtrader.catalog.critical_value
unchanged, on synthetic daily excess returns from the shared factor model. Measured.
"""

import math
from pathlib import Path

import numpy as np

from jevtrader.catalog import critical_value
from jevtrader.evaluate import block_bootstrap, sharpe

from common import LEVEL, N_CATALOG, YEAR

OUT = Path(__file__).parent / "results"
OUT.mkdir(exist_ok=True)
S, RHO, SR = 0.01, 0.75, 0.6


def gaussian_crit(m: int, reps: int = 50_000) -> float:
    rng = np.random.default_rng(3)
    e = rng.standard_normal((reps, m))
    c = rng.standard_normal((reps, N_CATALOG))
    hi = np.maximum(e.max(1) - c.min(1), c.max(1) - e.min(1)) / math.sqrt(2)
    return float(np.quantile(hi, LEVEL))


def bootstrap_crit(m: int, days: int, seed: int) -> float:
    rng = np.random.default_rng(100 + seed)
    f = rng.standard_normal(days)
    mu = SR / math.sqrt(YEAR) * S
    x = mu + S * (math.sqrt(RHO) * f + math.sqrt(1 - RHO) * rng.standard_normal((N_CATALOG + m, days)))
    dates = np.arange(days)
    draws, points = [], []
    for j in range(N_CATALOG, N_CATALOG + m):
        for k in range(N_CATALOG):
            xa, xb = x[j], x[k]
            stat = lambda w, xa=xa, xb=xb: sharpe(xa, w) - sharpe(xb, w)  # noqa: E731
            draws.append(block_bootstrap(dates, stat))
            points.append(stat(np.ones(days)))
    return critical_value(np.array(draws), np.array(points))


def main() -> None:
    lines = [
        "Block bootstrap (real code, 2,000 reps) against Gaussian max-|z|, rule-vs-catalog pairs",
        "",
        "| rules | pairs | sessions | blocks | bootstrap crit, 5 data seeds | mean | Gaussian |",
        "|---|---|---|---|---|---|---|",
    ]
    for m in (2, 10):
        g = gaussian_crit(m)
        for days in (60, 252, 1260):
            cs = [bootstrap_crit(m, days, s) for s in range(5)]
            lines.append(
                f"| {m} | {m * N_CATALOG} | {days} | {days // 20} | "
                + ", ".join(f"{c:.2f}" for c in cs)
                + f" | {np.mean(cs):.2f} | {g:.2f} |"
            )
            print(lines[-1], flush=True)
    (OUT / "spotcheck.md").write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
