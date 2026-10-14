"""How often today's live verdict code calls a null pair, by block count.

Reproduces evaluate.block_bootstrap's draws exactly (same seed, same rng calls) in matrix form,
then applies catalog.critical_value and the verdict rule to one rule's 8 pairs with the catalog.
"""

import sys

import numpy as np

from jevtrader.catalog import critical_value  # noqa: E402
from jevtrader.evaluate import BLOCK, REPS, YEAR, block_bootstrap, sharpe  # noqa: E402


def weights(n: int, seed: int = 0) -> np.ndarray:
    blocks = np.arange(n) // BLOCK
    count = int(blocks.max()) + 1
    rng = np.random.default_rng(seed)
    drawn = np.stack([np.bincount(rng.integers(count, size=count), minlength=count) for _ in range(REPS)])
    return drawn[:, blocks].astype(float)


def wsharpe(x: np.ndarray, w: np.ndarray) -> np.ndarray:
    n = w.sum(axis=1, keepdims=True)
    mean = (w @ x) / n
    var = (w @ x**2 - n * mean**2) / (n - 1)
    return mean / np.sqrt(var) * np.sqrt(YEAR)


def main() -> None:
    rho, s = 0.75, 0.01
    data = np.random.default_rng(1)
    datasets = int(sys.argv[1]) if len(sys.argv) > 1 else 1500
    for nb in (3, 6, 13, 26, 63, 236):
        n = nb * BLOCK
        w = weights(n)
        called = 0
        for _ in range(datasets):
            r = 0.5 / np.sqrt(YEAR) * s + s * (
                np.sqrt(rho) * data.standard_normal((n, 1)) + np.sqrt(1 - rho) * data.standard_normal((n, 9))
            )
            sr = wsharpe(r, w)  # REPS x 9
            draws = (sr[:, :1] - sr[:, 1:]).T  # 8 pairs x REPS
            points = np.array([sharpe(r[:, 0]) - sharpe(r[:, j]) for j in range(1, 9)])
            c = critical_value(draws, points)
            sd = draws.std(axis=1, ddof=1)
            called += bool(((points - c * sd > 0) | (points + c * sd < 0)).any())
        print(f"{nb:>3} blocks: null rule gets a verdict other than Too close to call in {called / datasets:.3f}")
    x = data.standard_normal(60)
    ref = block_bootstrap(np.arange(60), lambda wt: sharpe(x, wt))
    print("matrix draws equal block_bootstrap:", np.allclose(wsharpe(x[:, None], weights(60))[:, 0], ref))


if __name__ == "__main__":
    main()
