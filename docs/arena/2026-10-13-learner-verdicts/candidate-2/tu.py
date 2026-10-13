"""Candidate 2: what a time-uniform interval would cost (Gaussian rule, rejected alternative).

Finds the one critical value k such that a null rule shows any win on any night from 60 to
1,260 sessions in 5% of runs, then measures power over buy and hold at k.
Run: uv run python tu.py
"""

import numpy as np

import sim

np.seterr(invalid="ignore", divide="ignore")


def zpaths(rho, reps, chunk=250, seed=99):
    rng = np.random.default_rng(seed)
    S = np.r_[np.full(sim.N_CAT, sim.BASE), sim.BASE + np.array(sim.DS)]
    mu, H, F, NC = S / np.sqrt(sim.YEAR), sim.H, sim.FIRST, sim.N_CAT
    n = np.arange(1, H + 1, dtype=float)[F - 1 :]
    maxabs, zbh = [], []
    for a in range(0, reps, chunk):
        B = min(chunk, reps - a)
        r = mu[None, :, None] + np.sqrt(rho) * rng.standard_normal((B, 1, H)) + np.sqrt(
            1 - rho) * rng.standard_normal((B, len(S), H))
        c1 = np.cumsum(r, -1)[..., F - 1 :]
        c2 = np.cumsum(r * r, -1)[..., F - 1 :]
        cp = np.cumsum(r[:, NC:, None, :] * r[:, None, :NC, :], -1)[..., F - 1 :]
        m = c1 / n
        sd = np.sqrt((c2 - n * m * m) / (n - 1))
        sh = m / sd
        hL, hC = sh[:, NC:, None], sh[:, None, :NC]
        rh = (cp - n * m[:, NC:, None] * m[:, None, :NC]) / (n - 1) / (sd[:, NC:, None] * sd[:, None, :NC])
        z = (hL - hC) / np.sqrt((2 - 2 * rh + 0.5 * (hL**2 + hC**2 - 2 * hL * hC * rh**2)) / n)
        maxabs.append(np.abs(z[:, 0]).max(1).max(-1))  # null rule, max over pairs and nights
        zbh.append(z[:, :, 0, :])
    return np.concatenate(maxabs), np.concatenate(zbh)


for rho in sim.RHOS:
    mx, zbh = zpaths(rho, 10_000)
    k = np.quantile(mx, 0.95)
    cells = "; ".join(f"d={d}: " + ", ".join(
        f"{100*(zbh[:, j, n - sim.FIRST] > k).mean():.1f}" for n in sim.HORIZONS.values())
        for j, d in enumerate(sim.DS) if d > 0)
    print(f"rho {rho}: time-uniform critical value {k:.2f} (per-night {2.654:.2f}). "
          f"Power over buy and hold at 1y, 3y, 5y: {cells}")
