"""Time one night's family-wide critical value for M saved rules, vectorized.

One weight matrix of 2,000 reps of 20-session block counts on the global live calendar serves
every pair, as block_bootstrap does with one seed. Each rule's Sharpe reads its own sessions,
and each catalog entry's Sharpe is cut to the same sessions by suffix sums. Measured on this
machine. Writes results/timing.md.
"""

import time
from pathlib import Path

import numpy as np

from common import BLOCK, MIN_SESSIONS, N_CATALOG, YEAR

OUT = Path(__file__).parent / "results"
REPS = 2_000


def sharpe(s1, s2, n):
    mean = s1 / n
    var = (s2 - n * mean**2) / (n - 1)
    return mean / np.sqrt(var) * np.sqrt(YEAR)


def night(m: int, days: int, rng: np.random.Generator) -> float:
    blocks = np.arange(days) // BLOCK
    nb = blocks.max() + 1
    counts = np.stack([np.bincount(rng.integers(nb, size=nb), minlength=nb) for _ in range(REPS)])
    w = counts[:, blocks].astype(np.float32)  # reps x days
    save = rng.integers(0, days - MIN_SESSIONS, size=m)
    x = (rng.standard_normal((days, m)) * 0.01).astype(np.float32)
    x[np.arange(days)[:, None] < save[None, :]] = 0
    cat = (rng.standard_normal((days, N_CATALOG)) * 0.01).astype(np.float32)
    t0 = time.perf_counter()
    suffix_w = np.flip(np.flip(w, 1).cumsum(1), 1)  # weight from each day to tonight
    n_rule = suffix_w[:, save]
    rule = sharpe(w @ x, w @ (x * x), n_rule)  # reps x m
    ones = np.ones(days, np.float32)
    rule_pt = sharpe(ones @ x, ones @ (x * x), days - save)
    worst = np.zeros(REPS, np.float32)
    for k in range(N_CATALOG):
        c1 = np.flip(np.flip(w * cat[:, k], 1).cumsum(1), 1)[:, save]
        c2 = np.flip(np.flip(w * cat[:, k] ** 2, 1).cumsum(1), 1)[:, save]
        draws = rule - sharpe(c1, c2, n_rule)
        p1 = np.flip(np.flip(cat[:, k]).cumsum())[save]
        p2 = np.flip(np.flip(cat[:, k] ** 2).cumsum())[save]
        point = rule_pt - sharpe(p1, p2, days - save)
        ratio = np.abs(draws - point) / draws.std(0, ddof=1)
        worst = np.maximum(worst, ratio.max(1))
    np.quantile(worst, 0.95)
    return time.perf_counter() - t0


def main() -> None:
    rng = np.random.default_rng(5)
    lines = ["One night's critical value over every saved rule's 8 catalog pairs, 2,000 reps (measured on this laptop with numpy, BLAS threads unpinned)", "", "| rules | live sessions | seconds |", "|---|---|---|"]
    for m in (1_000, 10_000):
        for years in (5, 10):
            s = night(m, years * YEAR, rng)
            lines.append(f"| {m:,} | {years * YEAR:,} | {s:.1f} |")
            print(lines[-1], flush=True)
    (OUT / "timing.md").write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
