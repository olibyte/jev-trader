"""How often a null pair's |point| / bootstrap sd passes each critical value, with the real code.

This checks the per-pair tail that perrule.py models with the linear bootstrap sd. It uses
jevtrader.evaluate.block_bootstrap and sharpe unchanged on null pairs from the factor model
(rho = 0.75). Measured. Writes results/tails.md.
"""

import math
from pathlib import Path

import numpy as np

from jevtrader.evaluate import block_bootstrap, sharpe

from common import YEAR, norm_sf, t_cutoff

OUT = Path(__file__).parent / "results"
S, RHO, SR, PAIRS = 0.01, 0.75, 0.6, 2_000
CUTS = (2.66, 3.33, 4.35, 4.76)


def ratios(days: int) -> np.ndarray:
    rng = np.random.default_rng(days)
    dates = np.arange(days)
    mu = SR / math.sqrt(YEAR) * S
    out = np.empty(PAIRS)
    for i in range(PAIRS):
        f = rng.standard_normal(days)
        xa, xb = (mu + S * (math.sqrt(RHO) * f + math.sqrt(1 - RHO) * rng.standard_normal(days)) for _ in range(2))
        stat = lambda w: sharpe(xa, w) - sharpe(xb, w)  # noqa: E731
        draws = block_bootstrap(dates, stat, seed=i)
        out[i] = abs(stat(np.ones(days))) / draws.std(ddof=1)
    return out


def main() -> None:
    lines = [
        f"Share of {PAIRS:,} null pairs whose |point| / bootstrap sd passes a cutoff (real bootstrap, measured), with the normal and t(blocks - 1) references (arithmetic)",
        "",
        "| sessions | blocks | cutoff | real bootstrap | normal | t reference | t-corrected cutoff |",
        "|---|---|---|---|---|---|---|",
    ]
    for days in (60, 252):
        r = ratios(days)
        b = days // 20
        for c in CUTS:
            tc = t_cutoff(c, b)
            # t reference: P(|T_{b-1}| * sqrt(b/(b-1)) > c)
            from common import t_sf

            tref = 2 * t_sf(c / math.sqrt(b / (b - 1)), b - 1)
            lines.append(
                f"| {days} | {b} | {c:.2f} | {(r > c).mean():.2%} | {2 * norm_sf(c):.5%} | {tref:.2%} | {tc:.1f} |"
            )
        print("\n".join(lines[-4:]), flush=True)
    (OUT / "tails.md").write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
