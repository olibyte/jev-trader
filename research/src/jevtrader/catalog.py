"""The arena catalog: strategies as causal position rules, and the comparisons between them."""

from __future__ import annotations

import hashlib
import itertools
import math
import random
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date, timedelta
from statistics import NormalDist
from typing import Literal, NamedTuple, TypedDict

import numpy as np
import polars as pl

from jevtrader.evaluate import (
    COST_BPS,
    COSTS_BPS,
    LEVEL,
    POWER,
    YEAR,
    Interval,
    backtest,
    block_bootstrap,
    bootstrap_interval,
    max_drawdown,
    n_blocks,
    open_returns,
    portfolio,
    sharpe,
)
from jevtrader.states import SPLIT_STARTS, STUDY, bollinger, macd_hist, sma

CATALOG_VERSION = 1
BACKTEST_START = dict(SPLIT_STARTS)["fit"]
BACKTEST_ENDS = {1: date(2026, 10, 9)}
BACKTEST_END = BACKTEST_ENDS[CATALOG_VERSION]
Period = Literal["backtest", "live"]
Kind = Literal["benchmark", "indicator", "candlestick", "ml", "jev", "control"]
Verdict = Literal["a_ahead", "b_ahead", "no_difference", "too_early"]


@dataclass(frozen=True)
class Strategy:
    id: str
    version: int
    title: str
    plain: str
    rule: str
    citation: str
    kind: Kind
    positions: Callable[[pl.DataFrame], pl.Series]  # bars -> Int8 0/1 per bar, decided at close t


def _buy_hold(bars: pl.DataFrame) -> pl.Series:
    return pl.repeat(1, bars.height, dtype=pl.Int8, eager=True).alias("position")


def _long_when(bars: pl.DataFrame, condition: pl.Expr) -> pl.Series:
    return bars.select(condition.fill_null(False).cast(pl.Int8).alias("position")).to_series()


def _golden_cross(bars: pl.DataFrame) -> pl.Series:
    return _long_when(bars, sma(50) > sma(200))


def _macd_cross(bars: pl.DataFrame) -> pl.Series:
    return _long_when(bars, macd_hist() > 0)


def _bollinger_bounce(bars: pl.DataFrame) -> pl.Series:
    mid, band = bollinger()
    frame = bars.select("close", mid.alias("mid"), band.alias("band"))
    held, out = False, []
    for close, middle, offset in frame.iter_rows():
        if offset is None:
            held = False
        elif held:
            held = close < middle
        else:
            held = close < middle - offset
        out.append(held)
    return pl.Series("position", out, dtype=pl.Int8)


CATALOG: dict[str, Strategy] = {
    s.id: s
    for s in (
        Strategy(
            "buy_hold",
            1,
            "Buy and hold",
            "Put the money in on day one and never take it out.",
            "Always long.",
            "No parameters.",
            "benchmark",
            _buy_hold,
        ),
        Strategy(
            "golden_cross",
            1,
            "Golden cross",
            "Stay in while prices are on a long climb. Move to cash when the climb ends.",
            "Long when the 50-day average is above the 200-day average.",
            "Murphy, J. J. (1999). Technical Analysis of the Financial Markets."
            " New York Institute of Finance.",
            "indicator",
            _golden_cross,
        ),
        Strategy(
            "macd_cross",
            1,
            "MACD crossover",
            "Stay in while prices are speeding up. Move to cash when they slow down.",
            "Long when MACD(12, 26) is above its 9-day signal line.",
            "Appel, G. (2005). Technical Analysis: Power Tools for Active Investors."
            " FT Prentice Hall.",
            "indicator",
            _macd_cross,
        ),
        Strategy(
            "bollinger_bounce",
            1,
            "Bollinger bounce",
            "Jump in after an unusually sharp drop. Get out once the price is back to normal.",
            "Enter when the close falls below the lower band (20 days, 2 standard deviations)."
            " Exit when the close reaches the middle band.",
            "Bollinger, J. (2001). Bollinger on Bollinger Bands. McGraw-Hill.",
            "indicator",
            _bollinger_bounce,
        ),
    )
}
HOLDOUT_ARMS = {"buy_hold": "buy_hold", "golden_cross": "sma_filter"}
SCOPES = ("portfolio", *STUDY)
# Each range button's calendar offset back from the last curve date, as a polars duration.
RANGES: dict[str, str | None] = {
    "1W": "-1w",
    "1M": "-1mo",
    "3M": "-3mo",
    "1Y": "-1y",
    "5Y": "-5y",
    "All": None,
}


class CatalogEntry(TypedDict):
    id: str
    version: int
    title: str
    plain: str
    rule: str
    citation: str
    kind: Kind
    fingerprint: str


class PairRecord(TypedDict):
    a: str
    b: str
    scope: str
    period: Period
    blocks: int
    diff: dict[str, float]
    simultaneous: dict[str, float]
    family: int
    mde: float
    verdict: Verdict | None


class StrategyRecord(TypedDict):
    id: str
    scope: str
    period: Period
    blocks: int
    excessSharpe: dict[str, float]
    excessSharpeByCost: list[dict[str, float]]
    maxDrawdown: float
    switchesPerYear: float
    exposure: float


class WindowStats(TypedDict):
    growth: float
    exposure: float
    maxDrawdown: float


class WindowRecord(TypedDict):  # export/arena/v1/windows.json, one per RANGES entry
    range: str
    base: str | None  # the curve date the window grows from, None for All
    strategies: dict[str, WindowStats]


class Trades(TypedDict):  # export/arena/v1/funds/{symbol}.json, one per strategy
    buy: list[str]
    sell: list[str]


class ScopeResult(NamedTuple):
    strategies: list[StrategyRecord]
    pairs: list[PairRecord]
    equity: pl.DataFrame


def random_walk(seed: int, n: int = 700) -> pl.DataFrame:
    """OHLC bars whose volatility drifts, so the ATR regime moves through all three levels."""
    rng = random.Random(seed)
    rows, close = [], 100.0
    for i in range(n):
        sigma = 0.01 * (1 + 0.6 * math.sin(i / 40))
        open_ = close * math.exp(rng.gauss(0, sigma / 3))
        close = open_ * math.exp(rng.gauss(0, sigma))
        high = max(open_, close) * (1 + abs(rng.gauss(0, sigma / 2)))
        low = min(open_, close) * (1 - abs(rng.gauss(0, sigma / 2)))
        rows.append((date(2005, 1, 3) + timedelta(days=i), open_, high, low, close, 1000))
    return pl.DataFrame(
        rows, schema=["date", "open", "high", "low", "close", "volume"], orient="row"
    )


def fingerprint(strategy: Strategy) -> str:
    """sha256 of the positions on random_walk(0), (1), and (2), one line of 0s and 1s each."""
    lines = ("".join(map(str, strategy.positions(random_walk(seed)))) for seed in range(3))
    return hashlib.sha256("\n".join(lines).encode()).hexdigest()


def entry(strategy: Strategy) -> CatalogEntry:
    return {
        "id": strategy.id,
        "version": strategy.version,
        "title": strategy.title,
        "plain": strategy.plain,
        "rule": strategy.rule,
        "citation": strategy.citation,
        "kind": strategy.kind,
        "fingerprint": fingerprint(strategy),
    }


def decisions(
    market: Mapping[str, pl.DataFrame], start: date = BACKTEST_START, end: date = BACKTEST_END
) -> pl.DataFrame:
    """symbol, date, arm, position for every CATALOG strategy on every STUDY symbol.

    Bars after `end` are dropped before any position is decided, so no position reads them. The
    column is `arm` because evaluate.backtest groups by it.
    """
    frames = []
    for symbol in STUDY:
        bars = market[symbol].filter(pl.col("date") <= end)
        for strategy in CATALOG.values():
            frames.append(
                bars.select(
                    pl.lit(symbol).alias("symbol"), "date", pl.lit(strategy.id).alias("arm")
                ).with_columns(strategy.positions(bars))
            )
    return pl.concat(frames).filter(pl.col("date") >= start)


def _excess(days: pl.DataFrame) -> np.ndarray:
    return (days["ret"] - days["r_cash"]).to_numpy()


def _sharpe_interval(days: pl.DataFrame) -> dict[str, float]:
    excess = _excess(days)
    return bootstrap_interval(days["date"].to_numpy(), lambda w: sharpe(excess, w))._asdict()


def reconcile(made: pl.DataFrame, market: Mapping[str, pl.DataFrame], holdout: dict) -> list[str]:
    """Each HOLDOUT_ARMS strategy whose excess Sharpe interval differs from its holdout.json arm.

    An empty list passes.
    """
    first, last = (date.fromisoformat(holdout[k]) for k in ("first", "last"))
    returns = open_returns(market, last + timedelta(days=1))
    failures = []
    for strategy_id, arm in HOLDOUT_ARMS.items():
        window = made.filter(pl.col("arm") == strategy_id, pl.col("date").is_between(first, last))
        found = _sharpe_interval(portfolio(backtest(window, returns, COST_BPS)))
        recorded = holdout["arms"][arm]["excess_sharpe"]
        if found != recorded:
            failures.append(
                f"{strategy_id} excess Sharpe {found} is not {recorded}, the {arm} arm in"
                " holdout.json"
            )
    return failures


def refusals(committed: list[CatalogEntry] | None, made: pl.DataFrame) -> list[str]:
    """The reasons `jt arena` refuses this catalog. An empty list passes.

    committed is the catalog.json of the last run, None before the first run.
    """
    entries = {s.id: entry(s) for s in CATALOG.values()}
    failures = []
    for old in committed or []:
        new = entries.get(old["id"])
        if new is None:
            failures.append(f"catalog.json has {old['id']}, which CATALOG drops")
        elif new["version"] == old["version"] and new["fingerprint"] != old["fingerprint"]:
            failures.append(
                f"{old['id']} version {old['version']} has fingerprint {new['fingerprint']},"
                f" not {old['fingerprint']} as in catalog.json. A changed rule needs a new version"
            )
    long = set(made.filter(pl.col("position") == 1)["arm"].unique())
    failures += [f"{i} is never long in the backtest period" for i in CATALOG if i not in long]
    return failures


def critical_value(draws: np.ndarray, points: np.ndarray) -> float:
    """The LEVEL quantile over reps of the family's largest |draw - point| / sd.

    draws holds one row of bootstrap draws for each pair, all drawn with the same blocks, and
    points holds each pair's point value. sd is the standard deviation of the pair's draws.
    """
    ratio = (draws - points[:, None]) / draws.std(axis=1, ddof=1)[:, None]
    return float(np.quantile(np.abs(ratio).max(axis=0), LEVEL))


def _difference(xa: np.ndarray, xb: np.ndarray) -> Callable[[np.ndarray], float]:
    return lambda w: sharpe(xa, w) - sharpe(xb, w)


def _interval(point: float, lo: float, hi: float) -> dict[str, float]:
    return Interval(float(point), float(lo), float(hi))._asdict()


def _verdict(scope: str, simultaneous: dict[str, float]) -> Verdict | None:
    if scope != "portfolio":
        return None
    if simultaneous["lo"] > 0:
        return "a_ahead"
    if simultaneous["hi"] < 0:
        return "b_ahead"
    return "no_difference"


def scope_records(
    sleeves: Mapping[int, pl.DataFrame], scope: str, period: Period = "backtest"
) -> ScopeResult:
    """Every strategy's figures and every pair's comparison on one scope.

    sleeves maps each cost in COSTS_BPS to evaluate.backtest rows of every CATALOG strategy.
    The "portfolio" scope reads every symbol's sleeves and a symbol scope reads its own.
    """
    if scope != "portfolio":
        sleeves = {bps: s.filter(pl.col("symbol") == scope) for bps, s in sleeves.items()}
    days = {bps: portfolio(s) for bps, s in sleeves.items()}
    per = {i: {bps: d.filter(pl.col("arm") == i) for bps, d in days.items()} for i in CATALOG}
    dates = days[COST_BPS]["date"].unique(maintain_order=True).to_numpy()
    blocks = n_blocks(dates)

    strategies: list[StrategyRecord] = []
    for i, by_cost in per.items():
        sleeve = sleeves[COST_BPS].filter(pl.col("arm") == i)
        strategies.append(
            {
                "id": i,
                "scope": scope,
                "period": period,
                "blocks": blocks,
                "excessSharpe": _sharpe_interval(by_cost[COST_BPS]),
                "excessSharpeByCost": [
                    {"costBps": bps, "value": sharpe(_excess(by_cost[bps]))} for bps in COSTS_BPS
                ],
                "maxDrawdown": max_drawdown(by_cost[COST_BPS]["ret"].to_numpy()),
                "switchesPerYear": float(sleeve["switch"].sum() / (sleeve.height / YEAR)),
                "exposure": float(sleeve["position"].cast(pl.Float64).mean()),
            }
        )

    excess = {i: _excess(by_cost[COST_BPS]) for i, by_cost in per.items()}
    pairs = list(itertools.combinations(CATALOG, 2))
    statistics = [_difference(excess[a], excess[b]) for a, b in pairs]
    points = np.array([f(np.ones(len(dates))) for f in statistics])
    draws = np.array([block_bootstrap(dates, f) for f in statistics])
    crit, sd = critical_value(draws, points), draws.std(axis=1, ddof=1)
    lo, hi = np.quantile(draws, [(1 - LEVEL) / 2, (1 + LEVEL) / 2], axis=1)
    mde = (crit + NormalDist().inv_cdf(POWER)) * sd
    records: list[PairRecord] = []
    for k, (a, b) in enumerate(pairs):
        simultaneous = _interval(points[k], points[k] - crit * sd[k], points[k] + crit * sd[k])
        records.append(
            {
                "a": a,
                "b": b,
                "scope": scope,
                "period": period,
                "blocks": blocks,
                "diff": _interval(points[k], lo[k], hi[k]),
                "simultaneous": simultaneous,
                "family": len(pairs),
                "mde": float(mde[k]),
                "verdict": _verdict(scope, simultaneous),
            }
        )

    return ScopeResult(strategies, records, _equity(days[COST_BPS]))


def _equity(days: pl.DataFrame) -> pl.DataFrame:
    """date, then each CATALOG strategy's growth of 1 over evaluate.portfolio rows."""
    return (
        days.with_columns((1 + pl.col("ret")).cum_prod().over("arm").alias("equity"))
        .pivot("arm", index="date", values="equity")
        .select("date", *CATALOG)
    )


def windows(sleeves: pl.DataFrame) -> list[WindowRecord]:
    """Each RANGES window's growth, exposure, and max drawdown on the portfolio scope.

    sleeves holds the COST_BPS evaluate.backtest rows of every CATALOG strategy on every symbol.
    A window holds the curve dates after its base through the last date, and `base` is the last
    curve date on or before the offset cutoff.
    """
    days = portfolio(sleeves)
    equity = _equity(days)
    dates = equity["date"]
    last = dates[-1]
    records: list[WindowRecord] = []
    for label, offset in RANGES.items():
        if offset is None:
            base, kept, start = None, pl.lit(True), dict.fromkeys(CATALOG, 1.0)
        else:
            cutoff = pl.Series([last]).dt.offset_by(offset)[0]
            base = dates.filter(dates <= cutoff)[-1]
            kept = pl.col("date") > base
            start = equity.row(by_predicate=pl.col("date") == base, named=True)
        strategies: dict[str, WindowStats] = {}
        for i in CATALOG:
            ret = days.filter(pl.col("arm") == i, kept)["ret"].to_numpy()
            position = sleeves.filter(pl.col("arm") == i, kept)["position"]
            strategies[i] = {
                "growth": round(equity[i][-1] / start[i], 6),
                "exposure": float(position.cast(pl.Float64).mean()),
                "maxDrawdown": max_drawdown(ret),
            }
        records.append(
            {
                "range": label,
                "base": None if base is None else base.isoformat(),
                "strategies": strategies,
            }
        )
    return records


def trades(sleeves: pl.DataFrame, bars: pl.DataFrame) -> dict[str, Trades]:
    """Each CATALOG strategy's buy and sell dates on one symbol.

    sleeves holds that symbol's evaluate.backtest rows. A switch decided at the close of t
    trades at the next open, so its date is the bar after t in `bars`.
    """
    after = bars.select("date", pl.col("date").shift(-1).alias("trade"))
    switched = sleeves.filter(pl.col("switch")).join(after, on="date", how="left").sort("date")

    def on(i: str, position: int) -> list[str]:
        mine = switched.filter(pl.col("arm") == i, pl.col("position") == position)
        return [d.isoformat() for d in mine["trade"]]

    return {i: {"buy": on(i, 1), "sell": on(i, 0)} for i in CATALOG}
