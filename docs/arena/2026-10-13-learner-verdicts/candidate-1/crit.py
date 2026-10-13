"""Gaussian max-|z| critical values for each family, and the staggered-start check.

Writes results/crit.json and results/crit.md. Every number here is measured by Monte Carlo.
"""

import json
import math
from pathlib import Path

import numpy as np

from common import LEVEL, MS, N_CATALOG, YEAR, MIN_SESSIONS

OUT = Path(__file__).parent / "results"
OUT.mkdir(exist_ok=True)
RNG = np.random.default_rng(1)
REPS = 20_000
CHUNK = 500


def q(x: np.ndarray) -> float:
    return float(np.quantile(x, LEVEL))


def rule_vs_catalog(m: int) -> float:
    """Every saved rule's pairs with the catalog, equal windows."""
    out = []
    for _ in range(REPS // CHUNK):
        e = RNG.standard_normal((CHUNK, m))
        c = RNG.standard_normal((CHUNK, N_CATALOG))
        hi = np.maximum(e.max(1) - c.min(1), c.max(1) - e.min(1))
        out.append(hi / math.sqrt(2))
    return q(np.concatenate(out))


def all_pairs(n: int) -> float:
    """Every pair among n equally precise strategies (Tukey range)."""
    out = []
    for _ in range(REPS // CHUNK):
        e = RNG.standard_normal((CHUNK, n))
        out.append((e.max(1) - e.min(1)) / math.sqrt(2))
    return q(np.concatenate(out))


def staggered(m: int, days: int, reps: int) -> tuple[float, float]:
    """Rules saved on different days, all looked at tonight. Each pair reads only its rule's
    sessions, and the catalog is cut to the same sessions. Returns (staggered, equal) critical
    values from the same draws of the catalog path."""
    rng = np.random.default_rng(7)
    n = rng.integers(MIN_SESSIONS, days + 1, size=m)  # live sessions of each rule tonight
    stag, eq = [], []
    for _ in range(reps):
        walk = np.concatenate([np.zeros((N_CATALOG, 1)), rng.standard_normal((N_CATALOG, days)).cumsum(1)], 1)
        cbar = (walk[:, -1:] - walk[:, days - n]) / n  # catalog mean over each rule's window
        ebar = rng.standard_normal(m) / np.sqrt(n)
        z = (ebar - cbar) / np.sqrt(2 / n)
        stag.append(np.abs(z).max())
        cbar_eq = walk[:, -1] / days
        e_eq = rng.standard_normal(m) / math.sqrt(days)
        z_eq = (e_eq[None, :] - cbar_eq[:, None]) / math.sqrt(2 / days)
        eq.append(np.abs(z_eq).max())
    return q(np.array(stag)), q(np.array(eq))


def main() -> None:
    res = {
        "one_rule_8_pairs": rule_vs_catalog(1),
        "catalog_6_pairs": all_pairs(4),
        "catalog_28_pairs": all_pairs(N_CATALOG),
        "rule_vs_catalog": {m: rule_vs_catalog(m) for m in MS},
        "with_rule_vs_rule": {m: all_pairs(m + N_CATALOG) for m in MS},
    }
    res["staggered"] = {m: staggered(m, 5 * YEAR, 4_000) for m in (100, 1_000)}
    (OUT / "crit.json").write_text(json.dumps(res, indent=2))
    lines = [
        "Gaussian max-|z| critical values (measured, 20,000 reps; staggered 4,000 reps)",
        "",
        f"- one rule's 8 pairs with the catalog: {res['one_rule_8_pairs']:.2f}",
        f"- catalog only, 6 pairs (M7 bootstrap gave 2.53): {res['catalog_6_pairs']:.2f}",
        f"- catalog only, 28 pairs: {res['catalog_28_pairs']:.2f}",
        "",
        "| saved rules M | pairs (rule vs catalog) | crit | pairs incl. rule vs rule | crit |",
        "|---|---|---|---|---|",
    ]
    for m in MS:
        rr = m * N_CATALOG + m * (m - 1) // 2 + 28
        lines.append(
            f"| {m:,} | {m * N_CATALOG:,} | {res['rule_vs_catalog'][m]:.2f} | {rr:,} | {res['with_rule_vs_rule'][m]:.2f} |"
        )
    lines += ["", "| M | staggered windows (60 to 1,260 sessions) | equal windows (1,260) |", "|---|---|---|"]
    for m, (s, e) in res["staggered"].items():
        lines.append(f"| {m:,} | {s:.2f} | {e:.2f} |")
    (OUT / "crit.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
