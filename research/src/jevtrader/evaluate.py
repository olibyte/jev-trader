"""Arm scores and metrics: the shrunk empirical table, AUC, and the joint-date block bootstrap."""

from __future__ import annotations

from collections.abc import Callable
from typing import NamedTuple

import numpy as np
import polars as pl

from jevtrader.states import ALL_STATES, VOTE_REVERT, VOTE_TREND, state_key, state_table, vote

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


class Arm(NamedTuple):
    score: str
    threshold: (
        float | tuple[str, ...]
    )  # a fixed cut, or the arms whose mean fit exposure it matches
    probability: bool


ARMS: dict[str, Arm] = {
    "jev": Arm("p_up", 0.5, True),
    "jev_matched": Arm("p_up", ("vote_trend", "vote_revert"), True),
    "empirical_table": Arm("empirical_p", 0.5, True),
    "vote_trend": Arm("vote_trend", -0.5, False),
    "vote_revert": Arm("vote_revert", -0.5, False),
    "sma_filter": Arm("sma50_above_sma200", 0.5, False),
    "buy_hold": Arm("constant_1", 0.0, False),
    "random_matched": Arm("uniform_seed0", ("jev",), False),
    "oracle": Arm("fwd_ret_20", 0.0, False),  # look-ahead check, not a strategy
}


def scored(rows: pl.DataFrame, fit: pl.DataFrame, policy: pl.DataFrame) -> pl.DataFrame:
    """rows plus every arm's score column. empirical_p is fitted on `fit`."""
    per_state = pl.DataFrame(
        {
            "state_key": [state_key(s) for s in ALL_STATES],
            "vote_trend": [float(vote(VOTE_TREND, s)) for s in ALL_STATES],
            "vote_revert": [float(vote(VOTE_REVERT, s)) for s in ALL_STATES],
            "sma50_above_sma200": [float(s.sma50_vs_sma200 == "ABOVE") for s in ALL_STATES],
            "uniform_seed0": np.random.default_rng(0).random(len(ALL_STATES)),
        }
    )
    for table in (
        per_state,
        policy.select("state_key", "p_up"),
        empirical_table(fit).select("state_key", "empirical_p"),
    ):
        rows = rows.join(table, on="state_key", how="left", maintain_order="left")
    return rows.with_columns(constant_1=pl.lit(1.0))


def _long(score: str, cut: float) -> pl.Expr:
    return (pl.col(score) > cut).fill_null(False)


def matched_cut(score: np.ndarray, target: float) -> float:
    """The cut whose exposure mean(score > cut) is closest to `target`, a tie to the lower cut.

    The candidates are each distinct score and one below the minimum. A NaN score is flat.
    """
    values, counts = np.unique(score[~np.isnan(score)], return_counts=True)
    cuts = np.concatenate([[values[0] - 1], values])
    exposure = (counts.sum() - np.concatenate([[0], np.cumsum(counts)])) / len(score)
    return float(cuts[np.argmin(np.abs(exposure - target))])


def thresholds(fit: pl.DataFrame) -> dict[str, float]:
    """Each arm's cut on scored fit rows. Fixed cuts resolve first, matched cuts after."""
    cuts = {n: a.threshold for n, a in ARMS.items() if not isinstance(a.threshold, tuple)}
    for name, arm in ARMS.items():
        if isinstance(arm.threshold, tuple):
            exposures = [
                fit.select(_long(ARMS[a].score, cuts[a]).mean()).item() for a in arm.threshold
            ]
            cuts[name] = matched_cut(fit[arm.score].to_numpy(), float(np.mean(exposures)))
    return cuts


def decisions(rows: pl.DataFrame, fit: pl.DataFrame, policy: pl.DataFrame) -> pl.DataFrame:
    """Decision frame (symbol, date, arm, score, position) for every arm on `rows`.

    empirical_table and the matched thresholds are fitted on `fit`. A null score is flat.
    Never stored.
    """
    rows, cuts = scored(rows, fit, policy), thresholds(scored(fit, fit, policy))
    return pl.concat(
        rows.select(
            "symbol",
            "date",
            pl.lit(name).alias("arm"),
            pl.col(arm.score).alias("score"),
            _long(arm.score, cuts[name]).cast(pl.Int8).alias("position"),
        )
        for name, arm in ARMS.items()
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
