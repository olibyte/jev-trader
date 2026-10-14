"""Independent check of the Q1 arena numbers, from daily returns, not from a closed form.

One learner rule L against the 8 catalog entries C0..C7 (C0 is buy and hold). Daily excess returns
r_i = mu_i + s * (sqrt(rho) * f + sqrt(1 - rho) * e_i). The verdict reads the 8 pairs L - Ci with a
max-|z| critical value for a family of P pairs, where P stands in for the family a candidate uses.
"""

import sys

import numpy as np

YEAR = 252
S = 0.01


def crit(n_pairs: int, corr: float, rng: np.random.Generator, reps: int = 200_000) -> float:
    if n_pairs == 1:
        return 1.959964
    # Equicorrelated pairs as a stand-in for the bootstrap's max-|z| quantile.
    common = rng.standard_normal((reps, 1))
    own = rng.standard_normal((reps, n_pairs)) if n_pairs <= 2000 else None
    if own is None:
        # Large families: Bonferroni-Sidak bound, close to max-|z| for weakly correlated pairs.
        from statistics import NormalDist

        return NormalDist().inv_cdf(1 - (1 - 0.95 ** (1 / n_pairs)) / 2)
    z = np.sqrt(corr) * common + np.sqrt(1 - corr) * own
    return float(np.quantile(np.abs(z).max(axis=1), 0.95))


def run(rho: float, d: float, years: int, c: float, runs: int, rng: np.random.Generator):
    n = years * YEAR
    sr_bh = 0.5
    mu = np.full(9, sr_bh / np.sqrt(YEAR) * S)
    mu[0] += d / np.sqrt(YEAR) * S  # index 0 is the learner rule, with advantage d over every Ci
    first_look = 60
    looks = np.arange(first_look, n + 1, 1) - 1
    final_win = 0
    ever_win = 0
    ever_any = 0
    for _ in range(runs):
        f = rng.standard_normal((n, 1))
        e = rng.standard_normal((n, 9))
        r = mu + S * (np.sqrt(rho) * f + np.sqrt(1 - rho) * e)
        diff = r[:, :1] - r[:, 1:]  # n x 8, L minus Ci in daily returns
        cs = np.cumsum(r, axis=0)
        cs2 = np.cumsum(r * r, axis=0)
        t = np.arange(1, n + 1)[:, None]
        mean = cs / t
        sd = np.sqrt(np.maximum(cs2 / t - mean**2, 1e-30))
        sr = mean / sd * np.sqrt(YEAR)
        srd = sr[:, :1] - sr[:, 1:]
        dcs = np.cumsum(diff, axis=0)
        dcs2 = np.cumsum(diff * diff, axis=0)
        dmean = dcs / t
        dvar = np.maximum(dcs2 / t - dmean**2, 1e-30)
        se = np.sqrt(dvar / t) / sd[:, 1:] * np.sqrt(YEAR)  # delta-method SE of the Sharpe difference
        z = srd / se
        win = (z > c).any(axis=1)
        final_win += bool(win[-1])
        ever_win += bool(win[looks].any())
        ever_any += bool((np.abs(z[looks]) > c).any())
    return final_win / runs, ever_win / runs, ever_any / runs


def main() -> None:
    rng = np.random.default_rng(0)
    runs = int(sys.argv[1]) if len(sys.argv) > 1 else 400
    print("critical values, pairs corr 0.5 within a rule (equicorrelated stand-in)")
    for p in (1, 8, 80, 800, 8000, 80000):
        print(f"  family {p:>6} pairs: {crit(p, 0.5 if p <= 8 else 0.1, rng):.2f}")
    for family, label in ((8, "one rule's 8 pairs"), (800, "100 rules"), (8000, "1,000 rules")):
        c = crit(family, 0.5 if family <= 8 else 0.1, rng)
        for rho in (0.75, 0.25):
            for d in (0.0, 0.5, 1.0):
                for years in (1, 3, 5):
                    fw, ew, ea = run(rho, d, years, c, runs, rng)
                    print(
                        f"{label:>18} c={c:.2f} rho={rho} d={d} {years}y "
                        f"rule-wins single-look {fw:.3f} ever {ew:.3f} any-verdict ever {ea:.3f}"
                    )


if __name__ == "__main__":
    main()
