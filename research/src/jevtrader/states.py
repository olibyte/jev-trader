"""Indicator levels, the versioned State, and forward labels for each session."""

from __future__ import annotations

import hashlib
import io
import itertools
import json
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from typing import Literal, get_args, get_type_hints

import polars as pl

from jevtrader.data import UNIVERSE, atomic_write, forward_return

STATE_VERSION = "states/v1"
HORIZON = 20
ATR_WINDOW = 252
CASH = "BIL"
STUDY = tuple(s for s in UNIVERSE if s != CASH)

Split = Literal["warmup", "fit", "validate", "holdout"]
SPLIT_STARTS: tuple[tuple[Split, date], ...] = (
    ("fit", date(2008, 1, 1)),
    ("validate", date(2015, 1, 1)),
    ("holdout", date(2019, 1, 1)),
)


@dataclass(frozen=True)
class State:
    rsi14: Literal["OVERSOLD", "WEAK", "NEUTRAL", "STRONG", "OVERBOUGHT"]
    vs_sma200: Literal["ABOVE", "BELOW"]
    sma50_vs_sma200: Literal["ABOVE", "BELOW"]
    macd_hist: Literal["POS_RISING", "POS_FALLING", "NEG_RISING", "NEG_FALLING"]
    bollinger: Literal["BELOW_LOWER", "LOWER_HALF", "UPPER_HALF", "ABOVE_UPPER"]
    atr_regime: Literal["LOW", "NORMAL", "HIGH"]


DIMENSIONS: dict[str, tuple[str, ...]] = {
    name: get_args(hint) for name, hint in get_type_hints(State).items()
}
ALL_STATES = tuple(State(*levels) for levels in itertools.product(*DIMENSIONS.values()))

VoteTable = Mapping[str, Mapping[str, int]]

VOTE_TREND: VoteTable = {
    "rsi14": {"OVERSOLD": -1, "WEAK": -1, "NEUTRAL": 0, "STRONG": 1, "OVERBOUGHT": 1},
    "vs_sma200": {"ABOVE": 1, "BELOW": -1},
    "sma50_vs_sma200": {"ABOVE": 1, "BELOW": -1},
    "macd_hist": {"POS_RISING": 1, "POS_FALLING": 0, "NEG_RISING": 0, "NEG_FALLING": -1},
    "bollinger": {"BELOW_LOWER": -1, "LOWER_HALF": 0, "UPPER_HALF": 0, "ABOVE_UPPER": 1},
    "atr_regime": {"LOW": 0, "NORMAL": 0, "HIGH": 0},
}

VOTE_REVERT: VoteTable = {
    "rsi14": {"OVERSOLD": 1, "WEAK": 0, "NEUTRAL": 0, "STRONG": 0, "OVERBOUGHT": -1},
    "vs_sma200": {"ABOVE": 0, "BELOW": 0},
    "sma50_vs_sma200": {"ABOVE": 0, "BELOW": 0},
    "macd_hist": {"POS_RISING": 0, "POS_FALLING": -1, "NEG_RISING": 1, "NEG_FALLING": 0},
    "bollinger": {"BELOW_LOWER": 1, "LOWER_HALF": 0, "UPPER_HALF": 0, "ABOVE_UPPER": -1},
    "atr_regime": {"LOW": 0, "NORMAL": 0, "HIGH": 0},
}


def state_key(state: State) -> str:
    """sha256 of the canonical State JSON."""
    text = json.dumps(asdict(state), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode()).hexdigest()


def state_table() -> pl.DataFrame:
    """One row per State: the six level columns and state_key."""
    schema = {name: pl.Enum(levels) for name, levels in DIMENSIONS.items()}
    return pl.DataFrame(
        [{**asdict(s), "state_key": state_key(s)} for s in ALL_STATES],
        schema={**schema, "state_key": pl.String},
        orient="row",
    )


def vote(table: VoteTable, state: State) -> int:
    return sum(table[name][level] for name, level in asdict(state).items())


def _wilder(x: pl.Expr) -> pl.Expr:
    return x.ewm_mean(alpha=1 / 14, adjust=False, min_samples=14)


def _ema(x: pl.Expr, span: int) -> pl.Expr:
    return x.ewm_mean(span=span, adjust=False, min_samples=span)


def sma(n: int) -> pl.Expr:
    return pl.col("close").rolling_mean(n)


def macd_hist() -> pl.Expr:
    macd = _ema(pl.col("close"), 12) - _ema(pl.col("close"), 26)
    return macd - _ema(macd, 9)


def bollinger() -> tuple[pl.Expr, pl.Expr]:
    """The 20-session mean of the close and the band offset, 2 population standard deviations."""
    return sma(20), 2 * pl.col("close").rolling_std(20, ddof=0)


def _first_level_or_null(*cases: tuple[pl.Expr, str]) -> pl.Expr:
    (first, level), *rest = cases
    expr = pl.when(first).then(pl.lit(level))
    for condition, level in rest:
        expr = expr.when(condition).then(pl.lit(level))
    return expr


def levels(bars: pl.DataFrame) -> pl.DataFrame:
    """Date plus the six level columns, null until an indicator has its history.

    Causal: row t reads bars[: t + 1] only.
    """
    close, high, low = pl.col("close"), pl.col("high"), pl.col("low")
    prev_close = close.shift(1)

    change = close.diff()
    gain = _wilder(change.clip(lower_bound=0))
    loss = _wilder((-change).clip(lower_bound=0))
    rsi = pl.when(loss == 0).then(100.0).otherwise(100 - 100 / (1 + gain / loss))

    sma50, sma200 = sma(50), sma(200)

    hist = macd_hist()
    prev_hist = hist.shift(1)

    mid, band = bollinger()

    true_range = pl.max_horizontal(high - low, (high - prev_close).abs(), (low - prev_close).abs())
    # Count of the trailing ATR_WINDOW values (t included) that are <= today's. Null until full.
    rank = (_wilder(true_range) / close).rolling_rank(ATR_WINDOW, method="max")

    columns = {
        "rsi14": _first_level_or_null(
            (rsi < 30, "OVERSOLD"),
            (rsi < 45, "WEAK"),
            (rsi <= 55, "NEUTRAL"),
            (rsi < 70, "STRONG"),
            (rsi >= 70, "OVERBOUGHT"),
        ),
        "vs_sma200": _first_level_or_null((close > sma200, "ABOVE"), (close <= sma200, "BELOW")),
        "sma50_vs_sma200": _first_level_or_null(
            (sma50 > sma200, "ABOVE"), (sma50 <= sma200, "BELOW")
        ),
        "macd_hist": pl.concat_str(
            _first_level_or_null((hist > 0, "POS"), (hist <= 0, "NEG")),
            _first_level_or_null((hist > prev_hist, "RISING"), (hist <= prev_hist, "FALLING")),
            separator="_",
        ),
        "bollinger": _first_level_or_null(
            (close < mid - band, "BELOW_LOWER"),
            (close < mid, "LOWER_HALF"),
            (close <= mid + band, "UPPER_HALF"),
            (close > mid + band, "ABOVE_UPPER"),
        ),
        "atr_regime": _first_level_or_null(
            (rank * 3 <= ATR_WINDOW, "LOW"),
            (rank * 3 <= 2 * ATR_WINDOW, "NORMAL"),
            (rank * 3 > 2 * ATR_WINDOW, "HIGH"),
        ),
    }
    return bars.select(
        "date",
        *(expr.cast(pl.Enum(DIMENSIONS[name])).alias(name) for name, expr in columns.items()),
    )


def _split(day: pl.Expr) -> pl.Expr:
    split = pl.when(day.is_not_null()).then(pl.lit("warmup"))
    for name, start in SPLIT_STARTS:
        split = pl.when(day >= start).then(pl.lit(name)).otherwise(split)
    return split


def labels(bars: pl.DataFrame) -> pl.DataFrame:
    """Date, split, fwd_ret_20, up_20.

    The label is null when the exit open falls in a later split than t, so no fit label reads
    validate prices and no validate label reads holdout prices.
    """
    day = pl.col("date")
    exit_day = day.shift(-(HORIZON + 1))
    fwd = pl.when(_split(exit_day) == _split(day)).then(forward_return(HORIZON))
    return bars.select(
        "date",
        _split(day).alias("split"),
        fwd.alias("fwd_ret_20"),
        (fwd > 0).alias("up_20"),
    )


def state_rows(symbol: str, bars: pl.DataFrame) -> pl.DataFrame:
    """StateRow frame. Drops a session whose state is undefined."""
    return (
        levels(bars)
        .join(state_table(), on=list(DIMENSIONS), maintain_order="left")
        .join(labels(bars), on="date", maintain_order="left")
        .select(
            pl.lit(symbol).alias("symbol"),
            "date",
            "split",
            "state_key",
            pl.lit(STATE_VERSION).alias("state_version"),
            "fwd_ret_20",
            "up_20",
        )
    )


def write_states(symbol: str, data_dir: Path) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Read data/market/{symbol}.parquet, write data/states/{symbol}.parquet. Returns both."""
    bars = pl.read_parquet(data_dir / "market" / f"{symbol}.parquet")
    rows = state_rows(symbol, bars)
    buffer = io.BytesIO()
    rows.write_parquet(buffer)
    atomic_write(data_dir / "states" / f"{symbol}.parquet", buffer.getvalue())
    return bars, rows
