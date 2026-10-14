"""Per-rule false wins and power with an estimated standard deviation, looked at every night.

Each simulated rule has its own 8 catalog series cut to its own live window (a rule's view of the
catalog is 8 independent noise series, whatever other rules do). A pair's interval is
point +/- cutoff * sd, where sd is the block bootstrap sd of the mean difference in its linear
form, sum_i (S_i - L_i * mean)^2 / N^2 over the rule's 20-session blocks, the partial block
included. Measured. Writes results/perrule.json and .md.

Variants:
- oracle: the sd is known, cutoff c(M).
- plain: the bootstrap sd, cutoff c(M). This is what the current code would do.
- t: the bootstrap sd, cutoff c(M) moved to the same tail probability of t(blocks - 1).
- look+t: as t, from the look-adjusted critical value for the horizon.
"""

import json
import math
from pathlib import Path

import numpy as np

from common import BLOCK, DS, HORIZONS, MIN_SESSIONS, MS, N_CATALOG, RHOS, YEAR, delta, t_cutoff

HERE = Path(__file__).parent
OUT = HERE / "results"
CRIT = json.loads((OUT / "crit.json").read_text())
SITE = json.loads((OUT / "sitewide.json").read_text())
R = 100_000
DAYS = max(HORIZONS) * YEAR
VARIANTS = ("oracle", "plain", "t", "look+t")


def cutoffs(m: int) -> dict[str, np.ndarray]:
    """cutoff[variant][h][n] for every night n (index n - 1) and horizon h."""
    c = CRIT["rule_vs_catalog"][str(m)]
    blocks = np.arange(1, DAYS + 1) // BLOCK
    out = {}
    tc = {b: t_cutoff(c, b) for b in range(3, blocks.max() + 1)}
    for h in HORIZONS:
        cl = SITE["cohort"][str(m)][str(h)]["crit_look"]
        tl = {b: t_cutoff(cl, b) for b in range(3, blocks.max() + 1)}
        out[h] = {
            "oracle": np.full(DAYS, c),
            "plain": np.full(DAYS, c),
            "t": np.array([tc.get(b, np.inf) for b in blocks]),
            "look+t": np.array([tl.get(b, np.inf) for b in blocks]),
        }
    return out


def main() -> None:
    rng = np.random.default_rng(23)
    cuts = {m: cutoffs(m) for m in MS}
    print("cutoffs ready", flush=True)
    shape = (R, N_CATALOG)
    total = np.zeros(shape)
    q_done = np.zeros(shape)  # sum of completed block sums squared
    x_done = np.zeros(shape)  # sum of completed block sums
    part = np.zeros(shape)  # current partial block sum
    nb = 0
    # null flags: ever[m][h][variant] per rule, single at horizon likewise; power at horizon
    ever = {m: {h: {v: np.zeros(R, bool) for v in VARIANTS} for h in HORIZONS} for m in MS}
    single = {m: {h: {} for h in HORIZONS} for m in MS}
    power = {m: {h: {} for h in HORIZONS} for m in MS}
    pair_single = {m: {h: {} for h in HORIZONS} for m in MS}
    for n in range(1, DAYS + 1):
        x = rng.standard_normal(R)[:, None] - rng.standard_normal(shape)
        total += x
        part += x
        lp = n - nb * BLOCK
        if lp == BLOCK:
            q_done += part**2
            x_done += part
            part[:] = 0
            nb += 1
            lp = 0
        if n < MIN_SESSIONS:
            continue
        mean = total / n
        var = (q_done + part**2 - 2 * mean * (BLOCK * x_done + lp * part) + mean**2 * (BLOCK**2 * nb + lp**2)) / n**2
        sd = {"oracle": math.sqrt(2 / n), "est": np.sqrt(var)}
        z = {"oracle": np.abs(mean) / sd["oracle"], "est": np.abs(mean) / sd["est"]}
        for m in MS:
            for h in HORIZONS:
                if n > h * YEAR:
                    continue
                for v in VARIANTS:
                    cut = cuts[m][h][v][n - 1]
                    zz = z["oracle"] if v == "oracle" else z["est"]
                    hit = zz > cut
                    any_hit = hit.any(1)
                    ever[m][h][v] |= any_hit
                    if n == h * YEAR:
                        single[m][h][v] = float(any_hit.mean())
                        pair_single[m][h][v] = float(hit[:, 0].mean())
                        sdv = sd["oracle"] if v == "oracle" else sd["est"][:, 0]
                        power[m][h][v] = {
                            f"{rho}/{d}": float(((mean[:, 0] + delta(d, rho)) / sdv > cut).mean())
                            for rho in RHOS
                            for d in DS
                        }
        if n % 252 == 0:
            print("night", n, flush=True)
    res = {
        "rules": R,
        "single": single,
        "pair_single": pair_single,
        "ever": {m: {h: {v: float(a.mean()) for v, a in vv.items()} for h, vv in hh.items()} for m, hh in ever.items()},
        "power": power,
    }
    (OUT / "perrule.json").write_text(json.dumps(res, indent=2))
    lines = [f"Per null rule: chance of a false win against any of 8 catalog entries ({R:,} simulated rules, measured)", ""]
    lines += ["| M | variant | 1y single | 1y ever | 3y single | 3y ever | 5y single | 5y ever |", "|---|---|---|---|---|---|---|---|"]
    for m in MS:
        for v in VARIANTS:
            cells = " | ".join(f"{single[m][h][v]:.4%} | {res['ever'][m][h][v]:.4%}" for h in HORIZONS)
            lines.append(f"| {m:,} | {v} | {cells} |")
    lines += ["", "Power: chance that a rule with true advantage d over buy and hold reads 'A wins' against buy and hold at the horizon (single look, measured)", ""]
    lines += ["| M | variant | rho | d | 1y | 3y | 5y |", "|---|---|---|---|---|---|---|"]
    for m in MS:
        for v in VARIANTS:
            for rho in RHOS:
                for d in DS:
                    cells = " | ".join(f"{power[m][h][v][f'{rho}/{d}']:.1%}" for h in HORIZONS)
                    lines.append(f"| {m:,} | {v} | {rho} | {d} | {cells} |")
    (OUT / "perrule.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines[:22]))


if __name__ == "__main__":
    main()
