"""Arm scores and metrics: the shrunk empirical table, AUC, and the joint-date block bootstrap."""

from __future__ import annotations

import numpy as np
import polars as pl

from jevtrader.states import state_table

SHRINK_K = 50  # pseudo-observations at the base rate
BLOCK = 20
REPS = 2000


def empirical_table(rows: pl.DataFrame, k: float = SHRINK_K) -> pl.DataFrame:
    """One row per State: empirical_p = (ups + k * base) / (n_dev + k).

    base is the up rate over the labelled rows. A state with no labelled rows scores base.
    """
    labelled = rows.filter(pl.col("up_20").is_not_null())
    base = labelled["up_20"].mean()
    counts = labelled.group_by("state_key").agg(
        pl.len().alias("n_dev"), pl.col("up_20").sum().alias("ups")
    )
    n, ups = pl.col("n_dev").fill_null(0), pl.col("ups").fill_null(0)
    return (
        state_table()
        .select("state_key")
        .join(counts, on="state_key", how="left", maintain_order="left")
        .select("state_key", ((ups + k * base) / (n + k)).alias("empirical_p"), n.alias("n_dev"))
    )


def auc(score: np.ndarray, up: np.ndarray, weight: np.ndarray | None = None) -> float:
    """Mann-Whitney AUC with ties counted as 1/2. A weight of w counts a row w times."""
    weight = np.ones(len(score)) if weight is None else np.asarray(weight, dtype=float)
    up = np.asarray(up, dtype=bool)
    groups, codes = np.unique(score, return_inverse=True)
    pos = np.bincount(codes, weights=np.where(up, weight, 0), minlength=len(groups))
    neg = np.bincount(codes, weights=np.where(up, 0, weight), minlength=len(groups))
    below = np.cumsum(neg) - neg
    return float((pos * (below + neg / 2)).sum() / (pos.sum() * neg.sum()))


def block_bootstrap_auc(
    dates: np.ndarray,
    score: np.ndarray,
    up: np.ndarray,
    block: int = BLOCK,
    reps: int = REPS,
    seed: int = 0,
    level: float = 0.95,
) -> tuple[float, float, float]:
    """Point AUC and percentile CI.

    The sorted distinct dates split into consecutive `block`-session blocks. Each rep draws as
    many blocks as there are, with replacement, and weights a row by its block's draw count.
    Every symbol on a date shares the date's block, so the resample keeps cross-symbol
    correlation.
    """
    _, day = np.unique(dates, return_inverse=True)
    blocks = day // block
    n_blocks = int(blocks.max()) + 1
    rng = np.random.default_rng(seed)
    draws = []
    for _ in range(reps):
        counts = np.bincount(rng.integers(n_blocks, size=n_blocks), minlength=n_blocks)
        draws.append(auc(score, up, counts[blocks]))
    lo, hi = np.quantile(draws, [(1 - level) / 2, (1 + level) / 2])
    return auc(score, up), float(lo), float(hi)
