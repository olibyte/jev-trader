import math
import random
from datetime import date, timedelta

import polars as pl
import pytest

from jevtrader.states import (
    ALL_STATES,
    DIMENSIONS,
    STATE_VERSION,
    VOTE_REVERT,
    VOTE_TREND,
    State,
    labels,
    levels,
    state_key,
    state_rows,
    vote,
)

FIRST_DEFINED = 264  # ATR from row 13, then a full 252-value window for its rank


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


@pytest.mark.parametrize("seed", [0, 1, 2])
def test_levels_at_t_match_on_bars_truncated_at_t(seed):
    bars = random_walk(seed)
    full = levels(bars)

    assert full.drop_nulls()["date"][0] == bars["date"][FIRST_DEFINED]
    for t in range(bars.height):
        assert levels(bars.head(t + 1)).row(-1) == full.row(t), f"row {t} sees the future"


def test_levels_of_a_steady_rise():
    close = [100.0 + i for i in range(280)]
    bars = pl.DataFrame(
        {
            "date": [date(2005, 1, 3) + timedelta(days=i) for i in range(280)],
            "open": [c - 0.5 for c in close],
            "high": [c + 0.5 for c in close],
            "low": [c - 1.0 for c in close],
            "close": close,
        }
    )

    assert levels(bars).row(-1) == (
        date(2005, 10, 9),
        "OVERBOUGHT",  # no down day, so RSI is 100
        "ABOVE",
        "ABOVE",
        "POS_FALLING",  # MACD climbs toward its steady state and the signal line closes in
        "UPPER_HALF",  # close is 9.5 above the 20-day mean, under the band at 11.5
        "LOW",  # true range is a constant 1.5, so ATR as a share of price keeps falling
    )


def test_split_follows_the_split_table():
    days = [date(2007, 12, 31), date(2008, 1, 2), date(2014, 12, 31), date(2015, 1, 2)]
    days += [date(2018, 12, 31), date(2019, 1, 2)]
    bars = pl.DataFrame({"date": days, "open": [1.0] * len(days)})

    assert labels(bars)["split"].to_list() == [
        "warmup",
        "fit",
        "fit",
        "validate",
        "validate",
        "holdout",
    ]


def test_labels_enter_next_open_and_purge_across_a_split_boundary():
    days = [date(2014, 12, 1) + timedelta(days=i) for i in range(60)]
    opens = [100.0] * 60
    opens[21] = 125.0  # exit for t=0
    opens[30] = 80.0  # exit for t=9, on 2014-12-31
    bars = pl.DataFrame({"date": days, "open": opens})

    rows = labels(bars)

    assert rows.row(0) == (date(2014, 12, 1), "fit", 0.25, True)
    assert rows.row(9)[:2] == (date(2014, 12, 10), "fit")
    assert rows.row(9)[2] == pytest.approx(-0.2)
    assert rows.row(9)[3] is False
    assert rows.row(10) == (date(2014, 12, 11), "fit", None, None), "exit 2015-01-01 is validate"
    assert rows.row(30) == (date(2014, 12, 31), "fit", None, None)
    assert rows.row(31) == (date(2015, 1, 1), "validate", 0.0, False)
    assert rows.row(38) == (date(2015, 1, 8), "validate", 0.0, False)
    assert rows.row(39) == (date(2015, 1, 9), "validate", None, None), "exit is past the last bar"


def test_state_rows_keep_defined_sessions_only():
    bars = random_walk(0)

    rows = state_rows("SPY", bars)

    assert rows.columns == [
        "symbol",
        "date",
        "split",
        "state_key",
        "state_version",
        "fwd_ret_20",
        "up_20",
    ]
    assert rows.height == 700 - FIRST_DEFINED
    assert rows["date"][0] == date(2005, 9, 24)
    assert rows.row(0)[:5] == (
        "SPY",
        date(2005, 9, 24),
        "warmup",
        state_key(State(*levels(bars).row(FIRST_DEFINED)[1:])),
        STATE_VERSION,
    )
    assert rows["fwd_ret_20"].null_count() == 21, "the last 21 sessions have no exit open"


def test_state_space():
    keys = {state_key(s) for s in ALL_STATES}

    assert len(ALL_STATES) == 960
    assert len(keys) == 960
    assert (
        state_key(ALL_STATES[0])
        == "e712d8cb5343ce1fce81f837d62e6807cc4c2af29bea329dfa734e852a28b91f"
    ), "sha256 of the canonical JSON of the first State"


def test_vote_tables_cover_every_level():
    for table in (VOTE_TREND, VOTE_REVERT):
        assert {name: tuple(levels) for name, levels in table.items()} == DIMENSIONS


def test_vote_sums_one_vote_per_dimension():
    hot = State("OVERBOUGHT", "ABOVE", "ABOVE", "POS_RISING", "ABOVE_UPPER", "HIGH")
    washed_out = State("OVERSOLD", "BELOW", "BELOW", "NEG_RISING", "BELOW_LOWER", "LOW")

    assert (vote(VOTE_TREND, hot), vote(VOTE_REVERT, hot)) == (5, -2)
    assert (vote(VOTE_TREND, washed_out), vote(VOTE_REVERT, washed_out)) == (-4, 3)
