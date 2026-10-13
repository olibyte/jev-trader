"""How false wins arrive under BH: in bursts on the nights a shared catalog entry ran unlucky.

Reads sim.run at one configuration per line and reports, at the horizon look:
P(any win shown), E[FDP | any win shown], P(FDP > 0.5 | any win shown), mean FDP (the FDR).
"""

import numpy as np

import sim

print("rho | d | M | H | method | reps | P(any win) | FDR | E[FDP given a win shown] | P(FDP>0.5 given a win shown) | mean wins on nights with a false win")
for rho, d, M, reps in ((0.75, 0.5, 1000, 600), (0.75, 1.0, 1000, 600), (0.75, 0.5, 100, 4000), (0.75, 1.0, 10000, 60)):
    out = sim.run(M, rho, 0.02, d, reps=reps, seed=12345 + M)
    for name in ("own95", "bh", "by"):
        for hy in (3, 5):
            rows = out[name][hy]
            R = np.array([r["R"] for r in rows])
            V = np.array([r["V"] for r in rows])
            fdp = np.where(R > 0, V / np.maximum(R, 1), 0.0)
            shown = R > 0
            bad = V > 0
            print(
                f"{rho} | {d} | {M} | {hy}y | {name} | {reps} | {shown.mean():.3f} | {fdp.mean():.3f} |"
                f" {fdp[shown].mean() if shown.any() else float('nan'):.3f} |"
                f" {(fdp[shown] > 0.5).mean() if shown.any() else float('nan'):.3f} |"
                f" {R[bad].mean() if bad.any() else float('nan'):.1f}",
                flush=True,
            )
