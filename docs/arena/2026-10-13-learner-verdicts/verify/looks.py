"""Power of one rule's 8-pair verdict under three look schedules, known-variance Gaussian model.

nightly-plain: the single-look 95% critical value, checked every session from session 60.
nightly-held: a critical value that holds 5% over every nightly look to 5 years, then freezes.
yearly: a verdict only on each anniversary of the save (5 looks), critical value held at 5%.
"""

import numpy as np

YEAR, N, FIRST = 252, 5 * 252, 60
NIGHTS = np.arange(FIRST, N + 1)
YEARS = np.arange(1, 6) * YEAR


def paths(reps: int, rng: np.random.Generator) -> np.ndarray:
    """Standardised cumulative sums of L - Ck for 8 pairs: reps x N x 8, unit variance per session."""
    e = rng.standard_normal((reps, N, 9), dtype=np.float32)
    diff = (e[:, :, :1] - e[:, :, 1:]) / np.sqrt(2)
    return np.cumsum(diff, axis=1)


def z(cum: np.ndarray, looks: np.ndarray, drift: float) -> np.ndarray:
    t = looks[None, :, None].astype(float)
    shift = np.zeros(8)
    shift[0] = drift  # the rule's edge over buy and hold only, per session in noise units
    return (cum[:, looks - 1, :] + shift * t) / np.sqrt(t)


def main() -> None:
    rng = np.random.default_rng(0)
    null = np.concatenate([paths(500, rng) for _ in range(8)])
    single = np.quantile(np.abs(z(null, np.array([N]), 0)).max(axis=(1, 2)), 0.95)
    held = np.quantile(np.abs(z(null, NIGHTS, 0)).max(axis=(1, 2)), 0.95)
    yearly = np.quantile(np.abs(z(null, YEARS, 0)).max(axis=(1, 2)), 0.95)
    plain_ever = (np.abs(z(null, NIGHTS, 0)).max(axis=(1, 2)) > single).mean()
    print(f"critical values: single {single:.2f}, nightly-held {held:.2f}, yearly {yearly:.2f}")
    print(f"null rule, any verdict on some night with the single-look value: {plain_ever:.3f}")
    alt = np.concatenate([paths(500, rng) for _ in range(4)])
    for rho in (0.75, 0.25):
        for d in (0.3, 0.5, 1.0):
            drift = d / np.sqrt(YEAR) / np.sqrt(2 * (1 - rho))
            row = []
            for looks, c in ((NIGHTS, single), (NIGHTS, held), (YEARS, yearly)):
                zz = z(alt, looks, drift)[:, :, 0]
                for horizon in (3, 5):
                    keep = looks <= horizon * YEAR
                    row.append((zz[:, keep] > c).any(axis=1).mean())
            print(
                f"rho {rho} d {d}: win vs buy and hold by 3y/5y  "
                f"nightly-plain {row[0]:.2f}/{row[1]:.2f}  "
                f"nightly-held {row[2]:.2f}/{row[3]:.2f}  yearly {row[4]:.2f}/{row[5]:.2f}"
            )


if __name__ == "__main__":
    main()
