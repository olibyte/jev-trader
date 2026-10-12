"""Arm scores and metrics: the shrunk empirical table, AUC, and the joint-date block bootstrap."""

from __future__ import annotations

from collections.abc import Callable
from typing import NamedTuple

import numpy as np
import polars as pl

from jevtrader.states import state_table

SHRINK_K = 50
BLOCK = 20
REPS = 2000
LEVEL = 0.95


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


class Interval(NamedTuple):
    point: float
    lo: float
    hi: float


def n_blocks(dates: np.ndarray, block: int = BLOCK) -> int:
    return -(-len(np.unique(dates)) // block)


def block_bootstrap(
    dates: np.ndarray,
    statistic: Callable[[np.ndarray], float],
    *,
    block: int = BLOCK,
    reps: int = REPS,
    seed: int = 0,
    draws: int | None = None,
) -> np.ndarray:
    """`reps` draws of statistic(weights), one weight per row.

    The sorted distinct dates split into consecutive `block`-session blocks. Each rep draws
    `draws` blocks (default: as many as there are), with replacement, and weights a row by its
    block's draw count. Every symbol on a date shares the date's block, so the resample keeps
    cross-symbol correlation.
    """
    _, day = np.unique(dates, return_inverse=True)
    blocks = day // block
    count = int(blocks.max()) + 1
    rng = np.random.default_rng(seed)
    out = np.empty(reps)
    for i in range(reps):
        drawn = rng.integers(count, size=count if draws is None else draws)
        out[i] = statistic(np.bincount(drawn, minlength=count)[blocks])
    return out


def bootstrap_interval(
    dates: np.ndarray,
    statistic: Callable[[np.ndarray], float],
    block: int = BLOCK,
    reps: int = REPS,
    seed: int = 0,
    level: float = LEVEL,
) -> Interval:
    """statistic at unit weights and the percentile CI of its block bootstrap draws."""
    draws = block_bootstrap(dates, statistic, block=block, reps=reps, seed=seed)
    lo, hi = np.quantile(draws, [(1 - level) / 2, (1 + level) / 2])
    return Interval(float(statistic(np.ones(len(dates)))), float(lo), float(hi))


def block_bootstrap_auc(
    dates: np.ndarray,
    score: np.ndarray,
    up: np.ndarray,
    block: int = BLOCK,
    reps: int = REPS,
    seed: int = 0,
    level: float = LEVEL,
) -> Interval:
    """Point AUC and its joint-date block bootstrap CI."""
    return bootstrap_interval(dates, lambda w: auc(score, up, w), block, reps, seed, level)
