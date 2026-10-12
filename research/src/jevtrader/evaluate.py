"""Arm scores and metrics: the shrunk empirical table, AUC, and the joint-date block bootstrap."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import date
from typing import NamedTuple

import numpy as np
import polars as pl

from jevtrader.data import forward_return
from jevtrader.states import ALL_STATES, CASH, VOTE_REVERT, VOTE_TREND, state_key, state_table, vote

SHRINK_K = 50
BLOCK = 20
REPS = 2000
LEVEL = 0.95
COST_BPS = 5
COSTS_BPS = (0, 5, 10, 20)
YEAR = 252


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


def open_returns(market: Mapping[str, pl.DataFrame], end: date) -> pl.DataFrame:
    """symbol, date, r, r_cash from bars dated before `end`: r = open[t+2] / open[t+1] - 1.

    market maps each symbol, CASH included, to its bars. CASH gives r_cash, joined on date. A
    row without both returns is dropped, so the last two sessions before `end` fall away.
    """

    def r(bars: pl.DataFrame) -> pl.DataFrame:
        return bars.filter(pl.col("date") < end).select("date", forward_return(1).alias("r"))

    cash = r(market[CASH]).rename({"r": "r_cash"})
    return (
        pl.concat(
            r(bars).select(pl.lit(s).alias("symbol"), "date", "r")
            for s, bars in market.items()
            if s != CASH
        )
        .join(cash, on="date", maintain_order="left")
        .drop_nulls(["r", "r_cash"])
    )


def backtest(decisions: pl.DataFrame, returns: pl.DataFrame, cost_bps: float) -> pl.DataFrame:
    """Sleeve rows: decisions joined to open_returns plus `switch` and the net sleeve return `ret`.

    A position at t earns r over the open of t+1 to the open of t+2, and cash earns r_cash when
    flat. Each (arm, symbol) sleeve starts flat, and a switch costs cost_bps of the sleeve.
    """
    pos = pl.col("position").cast(pl.Float64)
    switch = pl.col("position") != pl.col("position").shift(1, fill_value=0).over("arm", "symbol")
    growth = (1 - cost_bps / 1e4 * pl.col("switch")) * (
        1 + pos * pl.col("r") + (1 - pos) * pl.col("r_cash")
    )
    return (
        decisions.join(returns, on=["symbol", "date"])
        .sort("arm", "symbol", "date")
        .with_columns(switch.alias("switch"))
        .with_columns((growth - 1).alias("ret"))
    )


def portfolio(sleeves: pl.DataFrame) -> pl.DataFrame:
    """arm, date, ret, r_cash: the equal-weight mean of the sleeve returns on each date."""
    return (
        sleeves.group_by("arm", "date")
        .agg(pl.col("ret").mean(), pl.col("r_cash").first())
        .sort("arm", "date")
    )


def sharpe(excess: np.ndarray, weight: np.ndarray | None = None) -> float:
    """Annualized mean / sd (ddof 1) of daily excess returns. A weight of w counts a day w times."""
    weight = np.ones(len(excess)) if weight is None else np.asarray(weight, dtype=float)
    n = weight.sum()
    mean = (weight * excess).sum() / n
    var = (weight * (excess - mean) ** 2).sum() / (n - 1)
    return float(mean / np.sqrt(var) * np.sqrt(YEAR))


def brier_skill(
    p: np.ndarray, up: np.ndarray, base: float, weight: np.ndarray | None = None
) -> float:
    """1 - Brier(p) / Brier(base). A weight of w counts a row w times."""
    weight = np.ones(len(p)) if weight is None else np.asarray(weight, dtype=float)
    up = np.asarray(up, dtype=float)
    return float(1 - (weight * (p - up) ** 2).sum() / (weight * (base - up) ** 2).sum())


def calibration(
    p: np.ndarray, up: np.ndarray, bins: int = 10
) -> list[tuple[float, int, float, float]]:
    """(bin low edge, n, mean p, up rate) for each nonempty fixed-width bin on [0, 1]."""
    which = np.minimum((p * bins).astype(int), bins - 1)
    out = []
    for b in np.unique(which):
        hit = which == b
        out.append((b / bins, int(hit.sum()), float(p[hit].mean()), float(up[hit].mean())))
    return out


def max_drawdown(ret: np.ndarray) -> float:
    """Largest fall of the equity curve from its running peak, the starting 1.0 included."""
    equity = np.cumprod(1 + ret)
    peak = np.maximum.accumulate(np.concatenate([[1.0], equity]))[1:]
    return float((1 - equity / peak).max())


class ArmReport(NamedTuple):
    auc: Interval
    brier_skill: Interval | None
    sharpe: Interval  # excess over cash at COST_BPS
    sharpe_by_cost: dict[int, float]
    exposure: float
    turnover: float  # switches per sleeve per year
    max_drawdown: float
    calibration: list[tuple[float, int, float, float]] | None


def arm_reports(
    rows: pl.DataFrame, fit: pl.DataFrame, policy: pl.DataFrame, returns: pl.DataFrame
) -> dict[str, ArmReport]:
    """Every arm fitted on `fit` and measured on `rows`. returns comes from open_returns."""
    made = decisions(rows, fit, policy)
    labelled = made.join(rows.select("symbol", "date", "up_20"), on=["symbol", "date"]).filter(
        pl.col("up_20").is_not_null()
    )
    sleeves = {bps: backtest(made, returns, bps) for bps in COSTS_BPS}
    base = float(fit["up_20"].drop_nulls().mean())
    return {
        name: _report(
            arm,
            labelled.filter(pl.col("arm") == name),
            {bps: s.filter(pl.col("arm") == name) for bps, s in sleeves.items()},
            base,
        )
        for name, arm in ARMS.items()
    }


def _report(
    arm: Arm, labelled: pl.DataFrame, sleeves: dict[int, pl.DataFrame], base: float
) -> ArmReport:
    dates, score = labelled["date"].to_numpy(), labelled["score"].to_numpy()
    up = labelled["up_20"].to_numpy()
    days = {bps: portfolio(s) for bps, s in sleeves.items()}
    excess = {bps: (d["ret"] - d["r_cash"]).to_numpy() for bps, d in days.items()}
    sleeve, day = sleeves[COST_BPS], days[COST_BPS]
    return ArmReport(
        auc=bootstrap_interval(dates, lambda w: auc(score, up, w)),
        brier_skill=bootstrap_interval(dates, lambda w: brier_skill(score, up, base, w))
        if arm.probability
        else None,
        sharpe=bootstrap_interval(day["date"].to_numpy(), lambda w: sharpe(excess[COST_BPS], w)),
        sharpe_by_cost={bps: sharpe(x) for bps, x in excess.items()},
        exposure=float(sleeve["position"].cast(pl.Float64).mean()),
        turnover=float(sleeve["switch"].sum() / (sleeve.height / YEAR)),
        max_drawdown=max_drawdown(day["ret"].to_numpy()),
        calibration=calibration(score, up) if arm.probability else None,
    )
