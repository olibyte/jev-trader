"""Staggered saves with the look-adjusted critical value and a verdict that freezes at 5 years.

Same staggered model as sitewide.py: M null rules saved on uniform random days over 5 years,
the site looked at nightly for 10 years, known sd. Each rule's verdict is recomputed nightly from
60 sessions to 5 live years, then freezes. The cutoff each night is the 5-year look-adjusted
critical value for the number of rules with 60 sessions. Measured. Writes results/sitewide_look.md.
"""

import json
from pathlib import Path

import numpy as np

from common import MIN_SESSIONS, N_CATALOG, YEAR, crit_table_lookup

OUT = Path(__file__).parent / "results"
SITE = json.loads((OUT / "sitewide.json").read_text())
LOOK = {int(m): r["5"]["crit_look"] for m, r in SITE["cohort"].items()}
PLAIN = {int(m): r["crit"] for m, r in SITE["cohort"].items()}


def run(m: int, runs: int, table: dict[int, float], cap: int | None, rng: np.random.Generator) -> tuple[float, float]:
    """(chance of any false win, the scale on the table that would make that chance 5%)."""
    span = 10 * YEAR
    save = np.sort(rng.integers(0, 5 * YEAR, size=m))
    t = np.arange(span + 1)
    age = t[None, :] - save[:, None]
    eligible = (age >= MIN_SESSIONS).sum(0)
    looks = (age >= MIN_SESSIONS) & (age <= (cap if cap else span))
    crit = np.array([crit_table_lookup(table, int(e)) if e else np.inf for e in eligible])
    ratio = []
    scale = np.sqrt(2 * np.maximum(age, 1))
    for _ in range(runs):
        w = np.concatenate([np.zeros((m, 1)), rng.standard_normal((m, span)).cumsum(1)], 1)
        c = np.concatenate([np.zeros((N_CATALOG, 1)), rng.standard_normal((N_CATALOG, span)).cumsum(1)], 1)
        dw = w - w[np.arange(m), save][:, None]
        worst = np.zeros(span + 1)
        for k in range(N_CATALOG):
            dc = c[k][None, :] - c[k][save][:, None]
            worst = np.maximum(worst, np.where(looks, np.abs(dw - dc) / scale, 0.0).max(0))
        ratio.append((worst / crit).max())
    ratio = np.array(ratio)
    return float((ratio > 1).mean()), float(np.quantile(ratio, 0.95))


def main() -> None:
    rng = np.random.default_rng(29)
    lines = [
        "Staggered saves over 5 years, site looked at nightly for 10 years, known sd (measured)",
        "",
        "| M | runs | per-look crit, no freeze | per-look crit, freeze at 5y | cohort look-adjusted crit, freeze at 5y | scale on that crit for 5% |",
        "|---|---|---|---|---|---|",
    ]
    for m, runs in ((100, 1_000), (1_000, 300)):
        a = run(m, runs, PLAIN, None, rng)
        b = run(m, runs, PLAIN, 5 * YEAR, rng)
        c = run(m, runs, LOOK, 5 * YEAR, rng)
        lines.append(f"| {m:,} | {runs:,} | {a[0]:.1%} | {b[0]:.1%} | {c[0]:.1%} | {c[1]:.3f} |")
        print(lines[-1], flush=True)
    (OUT / "sitewide_look.md").write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
