"""Candidate 2: the real procedure, every night, on synthetic data.

sim.py uses a Gaussian max-|z| rule. Its spot check showed that the real block bootstrap is far
less calibrated with few blocks. This script runs the real procedure instead: the draws of
evaluate.block_bootstrap (seed 0, 2,000 reps, 20-session blocks, reproduced exactly by one
weight matrix, checked in sim.py to 5e-15) and catalog.critical_value over the rule's 8 pairs,
recomputed on every night from session 60 to 1,260.

The block draws depend only on the number of blocks and the seed, so one weight matrix per
night serves every synthetic dataset.

Run: uv run python real.py [rho] [datasets]
"""

import sys
import time

import numpy as np

from jevtrader.catalog import critical_value

np.seterr(invalid="ignore", divide="ignore")
YEAR, BLOCK, REPS, FIRST, H, N_CAT, BASE = 252, 20, 2000, 60, 1260, 8, 0.6
DS = [0.0, 0.3, 0.5, 1.0]
HORIZONS = {"1y": 252, "3y": 756, "5y": 1260}


def weights(n):
    blocks = np.arange(n) // BLOCK
    count = int(blocks.max()) + 1
    rng = np.random.default_rng(0)
    W = np.empty((REPS, count))
    for i in range(REPS):
        W[i] = np.bincount(rng.integers(count, size=count), minlength=count)
    return W[:, blocks]


def main(rho, D, seed):
    t0 = time.perf_counter()
    rng = np.random.default_rng(seed)
    K = len(DS)
    S = np.r_[np.full(N_CAT, BASE), BASE + np.array(DS)]
    r = S[None, :, None] / np.sqrt(YEAR) + np.sqrt(rho) * rng.standard_normal((D, 1, H)) + \
        np.sqrt(1 - rho) * rng.standard_normal((D, N_CAT + K, H))
    X = r.transpose(2, 0, 1).reshape(H, D * (N_CAT + K))
    nights = range(FIRST, H + 1)
    snap = {k: np.zeros((len(nights), D, K), bool) for k in ("any", "fav", "bh")}
    T = {k: np.zeros((len(nights), D, K)) for k in ("abs", "fav", "bh")}
    for j, n in enumerate(nights):
        Wd = weights(n)
        Xn = X[:n]
        nw = Wd.sum(1, keepdims=True)
        m = Wd @ Xn / nw
        sh = (m / np.sqrt((Wd @ (Xn * Xn) - nw * m * m) / (nw - 1))).reshape(REPS, D, -1)
        m1 = Xn.mean(0)
        pt = (m1 / Xn.std(0, ddof=1)).reshape(D, -1)
        draws = sh[:, :, N_CAT:, None] - sh[:, :, None, :N_CAT]  # (REPS, D, K, 8)
        points = pt[:, N_CAT:, None] - pt[:, None, :N_CAT]  # (D, K, 8)
        sd = draws.std(0, ddof=1)
        # catalog.critical_value per rule: same formula, vectorised over rules
        cv = np.quantile(np.abs((draws - points) / sd).max(-1), 0.95, axis=0)  # (D, K)
        hw = cv[..., None] * sd
        snap["any"][j] = (np.abs(points) > hw).any(-1)
        snap["fav"][j] = (points > hw).any(-1)
        snap["bh"][j] = points[..., 0] > hw[..., 0]
        T["abs"][j] = (np.abs(points) / sd).max(-1)
        T["fav"][j] = (points / sd).max(-1)
        T["bh"][j] = points[..., 0] / sd[..., 0]
        if j == 0:  # check the vectorised critical value against catalog.critical_value
            ref = critical_value(np.moveaxis(draws[:, 0, 0, :], 0, 1) * 1.0, points[0, 0])
            assert abs(ref - cv[0, 0]) < 1e-9, (ref, cv[0, 0])
    ever = {k: np.logical_or.accumulate(v, 0) for k, v in snap.items()}
    print(f"\n### Real procedure, rho = {rho}, {D} datasets, every night 60..1260")
    print("\nNull rule, percent of rules:\n")
    print("| Horizon | Any win, single look | Rule wins, single look | Any win, ever | "
          "Rule wins, ever |")
    print("|---|---|---|---|---|")
    for h, n in HORIZONS.items():
        i = n - FIRST
        print(f"| {h} | {100*snap['any'][i,:,0].mean():.1f} | {100*snap['fav'][i,:,0].mean():.1f} "
              f"| {100*ever['any'][i,:,0].mean():.1f} | {100*ever['fav'][i,:,0].mean():.1f} |")
    print("\nNull 'any win' single-look rate by night (blocks):")
    print(", ".join(f"{n} ({-(-n // BLOCK)}): {100*snap['any'][n-FIRST,:,0].mean():.0f}%"
                    for n in (60, 80, 100, 140, 200, 252, 378, 504, 756, 1008, 1260)))
    print("\nPower over buy and hold, single look (ever):\n")
    print("| d | 1y | 3y | 5y |")
    print("|---|---|---|---|")
    for k, d in enumerate(DS[1:], 1):
        print(f"| {d} | " + " | ".join(
            f"{100*snap['bh'][n-FIRST,:,k].mean():.1f} ({100*ever['bh'][n-FIRST,:,k].mean():.1f})"
            for n in HORIZONS.values()) + " |")
    # Ever, counting only looks from a later first night (what a stricter "Too early" buys)
    print("\nNull 'rule wins, ever' to 5y if the first verdict waited for B blocks:")
    for b in (3, 6, 13, 25):
        i0 = b * BLOCK - FIRST
        e = snap["fav"][i0:, :, 0].any(0).mean()
        s = snap["any"][i0, :, 0].mean()
        print(f"- B = {b}: ever {100*e:.1f}%, any-win single look at the first night {100*s:.1f}%")
    # Calibrated critical value: per night, the 95th percentile over null datasets of the
    # rule's max |point| / bootstrap sd. In-sample on these datasets, so slightly optimistic.
    c_n = np.quantile(T["abs"][:, :, 0], 0.95, axis=1)  # (nights,)
    print("\nCalibrated critical value by night (blocks): " + ", ".join(
        f"{n} ({-(-n // BLOCK)}): {c_n[n-FIRST]:.2f}" for n in (60, 100, 140, 252, 504, 1260)))
    cal = {k: T[k] > c_n[:, None, None] for k in T}
    cal_ever = {k: np.logical_or.accumulate(v, 0) for k, v in cal.items()}
    print("\nCalibrated, null rule 'rule wins': single look (ever) at 1y, 3y, 5y: " + ", ".join(
        f"{100*cal['fav'][n-FIRST,:,0].mean():.1f} ({100*cal_ever['fav'][n-FIRST,:,0].mean():.1f})"
        for n in HORIZONS.values()))
    print("\nCalibrated power over buy and hold, single look (ever):\n")
    print("| d | 1y | 3y | 5y |")
    print("|---|---|---|---|")
    for k, d in enumerate(DS[1:], 1):
        print(f"| {d} | " + " | ".join(
            f"{100*cal['bh'][n-FIRST,:,k].mean():.1f} ({100*cal_ever['bh'][n-FIRST,:,k].mean():.1f})"
            for n in HORIZONS.values()) + " |")
    print(f"\n({time.perf_counter()-t0:.0f} s)")


if __name__ == "__main__":
    main(float(sys.argv[1]) if len(sys.argv) > 1 else 0.75,
         int(sys.argv[2]) if len(sys.argv) > 2 else 200,
         int(sys.argv[3]) if len(sys.argv) > 3 else 7)
