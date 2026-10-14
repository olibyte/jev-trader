"""Spot-check the Gaussian max-|z| critical value against the repo's block bootstrap.

One learner rule against 8 catalog entries, daily excess returns from the shared setup,
evaluate.block_bootstrap (seed 0, 2,000 reps, 20-session blocks) and catalog.critical_value.
Also times the bootstrap for the per-night cost estimate. Run with python -B so nothing is
written into the repo.
"""

import math
import time

import numpy as np

from jevtrader.catalog import critical_value
from jevtrader.evaluate import block_bootstrap, sharpe

import sim

S = 0.16 / math.sqrt(252)
MU = 0.6 / math.sqrt(252) * S  # buy and hold excess Sharpe 0.6


def dataset(rng, n, rho):
    f = rng.standard_normal(n)
    e = rng.standard_normal((9, n))
    return MU + S * (math.sqrt(rho) * f + math.sqrt(1 - rho) * e)  # row 0 is the rule


def family(x, dates):
    draws, points = [], []
    for k in range(1, 9):
        stat = lambda w, a=x[0], b=x[k]: sharpe(a, w) - sharpe(b, w)  # noqa: E731
        draws.append(block_bootstrap(dates, stat, seed=0))
        points.append(stat(np.ones(len(dates))))
    return np.array(draws), np.array(points)


def main():
    gauss = sim.crit(0.05, sim.LOGP2)
    print(f"Gaussian two-sided 95% critical value, 8 pairs at correlation 0.5: {gauss:.3f}")
    for years, rho, n_sets in ((3, 0.75, 20), (3, 0.25, 10), (1, 0.75, 10), (5, 0.75, 5)):
        n = 252 * years
        dates = np.arange(n)
        rng = np.random.default_rng(years * 100 + int(rho * 100))
        cs, sds, cors = [], [], []
        t0 = time.time()
        for _ in range(n_sets):
            draws, points = family(dataset(rng, n, rho), dates)
            cs.append(critical_value(draws, points))
            sds.append(draws.std(axis=1, ddof=1).mean())
            c = np.corrcoef(draws)
            cors.append(c[np.triu_indices(8, 1)].mean())
        per = (time.time() - t0) / n_sets
        analytic = math.sqrt(2 * (1 - rho) * 252 / n)
        print(
            f"{years}y rho={rho}: bootstrap c mean {np.mean(cs):.3f} (range {min(cs):.3f} to"
            f" {max(cs):.3f}, {n_sets} sets); pair sd {np.mean(sds):.3f} vs analytic"
            f" {analytic:.3f}; draw correlation {np.mean(cors):.2f}; {per:.2f}s per rule"
        )
    # cost: a vectorized bootstrap of one rule's 9 series with one weight matrix
    n = 1260
    rng = np.random.default_rng(0)
    x = dataset(rng, n, 0.75)
    blocks = np.arange(n) // 20
    count = blocks.max() + 1
    t0 = time.time()
    for _ in range(20):
        drawn = rng.integers(count, size=(2000, count))
        w = np.stack([np.bincount(d, minlength=count) for d in drawn])[:, blocks].astype(float)
        nw = w.sum(1, keepdims=True)
        m = w @ x.T / nw
        v = (w @ (x.T**2) - nw * m**2) / (nw - 1)
        _ = m / np.sqrt(v) * math.sqrt(252)
    print(f"vectorized 2,000-rep bootstrap of 9 series over 5 years: {(time.time() - t0) / 20:.3f}s")


if __name__ == "__main__":
    main()
