"""Site-wide chance of any false win, with a known standard deviation (Gaussian oracle).

Cohort: all M null rules saved the same day, every one compared with 8 null catalog entries,
looked at every night from 60 sessions to the horizon. Staggered: M null rules saved on
uniform random days over 5 years and looked at every night for 10 years, with the critical
value of the rules that have 60 sessions that night. Writes results/sitewide.json and .md.
Measured.
"""

import json
import math
from pathlib import Path

import numpy as np

from common import HORIZONS, LEVEL, MIN_SESSIONS, MS, N_CATALOG, YEAR, crit_table_lookup

HERE = Path(__file__).parent
OUT = HERE / "results"
CRIT = json.loads((OUT / "crit.json").read_text())
TABLE = {int(k): v for k, v in CRIT["rule_vs_catalog"].items()}
TABLE[1] = CRIT["one_rule_8_pairs"]
RUNS = {10: 4_000, 100: 4_000, 1_000: 1_000, 10_000: 300}


def cohort(m: int, runs: int, rng: np.random.Generator) -> dict:
    days = max(HORIZONS) * YEAR
    n = np.arange(1, days + 1)
    zmax = np.empty((runs, days), dtype=np.float32)
    for r in range(runs):
        hi = np.full(days, -np.inf, dtype=np.float32)
        lo = np.full(days, np.inf, dtype=np.float32)
        for start in range(0, m, 2_500):
            w = rng.standard_normal((min(2_500, m - start), days), dtype=np.float32).cumsum(1)
            hi = np.maximum(hi, w.max(0))
            lo = np.minimum(lo, w.min(0))
        c = rng.standard_normal((N_CATALOG, days)).cumsum(1)
        zmax[r] = np.maximum(hi - c.min(0), c.max(0) - lo) / np.sqrt(2 * n)
    crit = TABLE[m]
    out = {"crit": crit}
    for h in HORIZONS:
        last = h * YEAR
        ever = zmax[:, MIN_SESSIONS - 1 : last].max(1)
        out[h] = {
            "single": float((zmax[:, last - 1] > crit).mean()),
            "ever": float((ever > crit).mean()),
            "crit_look": float(np.quantile(ever, LEVEL)),
        }
    return out


def staggered(m: int, runs: int, rng: np.random.Generator) -> dict:
    span = 10 * YEAR
    save = np.sort(rng.integers(0, 5 * YEAR, size=m))
    t = np.arange(span + 1)
    age = t[None, :] - save[:, None]  # sessions since save, per rule and night
    live = age >= MIN_SESSIONS
    eligible = live.sum(0)
    crit = np.array([crit_table_lookup(TABLE, int(e)) for e in eligible])
    crit[eligible == 0] = np.inf
    single = ever = 0
    for _ in range(runs):
        w = np.concatenate([np.zeros((m, 1)), rng.standard_normal((m, span)).cumsum(1)], 1)
        c = np.concatenate([np.zeros((N_CATALOG, 1)), rng.standard_normal((N_CATALOG, span)).cumsum(1)], 1)
        dw = w - w[np.arange(m), save][:, None]
        scale = np.sqrt(2 * np.maximum(age, 1))
        worst = np.zeros(span + 1)
        for k in range(N_CATALOG):
            dc = c[k][None, :] - c[k][save][:, None]
            z = np.where(live, np.abs(dw - dc) / scale, 0.0)
            worst = np.maximum(worst, z.max(0))
        hit = worst > crit
        single += bool(hit[-1])
        ever += bool(hit.any())
    return {"single_last_night": single / runs, "ever_10y": ever / runs}


def main() -> None:
    rng = np.random.default_rng(11)
    res = {"cohort": {}, "staggered": {}}
    for m in MS:
        res["cohort"][m] = cohort(m, RUNS[m], rng)
        print(m, res["cohort"][m], flush=True)
    for m in (100, 1_000):
        res["staggered"][m] = staggered(m, 400 if m == 1_000 else 1_000, rng)
        print("staggered", m, res["staggered"][m], flush=True)
    (OUT / "sitewide.json").write_text(json.dumps(res, indent=2))
    lines = [
        "Site-wide chance of at least one false win among M null rules (known sd, measured)",
        "",
        "| M | runs | crit | 1y single | 1y ever | 3y single | 3y ever | 5y single | 5y ever | look-adjusted crit 1y / 3y / 5y |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for m in MS:
        r = res["cohort"][m]
        cells = " | ".join(f"{r[h]['single']:.1%} | {r[h]['ever']:.1%}" for h in HORIZONS)
        look = " / ".join(f"{r[h]['crit_look']:.2f}" for h in HORIZONS)
        lines.append(f"| {m:,} | {RUNS[m]:,} | {r['crit']:.2f} | {cells} | {look} |")
    lines += ["", "Staggered saves over 5 years, looked at nightly for 10 years", "", "| M | last night | ever |", "|---|---|---|"]
    for m, r in res["staggered"].items():
        lines.append(f"| {m:,} | {r['single_last_night']:.1%} | {r['ever_10y']:.1%} |")
    (OUT / "sitewide.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
