import json
from datetime import date, timedelta

import numpy as np
import polars as pl
import pytest

from jevtrader.catalog import (
    CATALOG,
    Strategy,
    critical_value,
    decisions,
    entry,
    fingerprint,
    random_walk,
    reconcile,
    refusals,
)
from jevtrader.evaluate import ARMS, HOLDOUT_PATH, holdout_result, render_json
from jevtrader.states import ALL_STATES, CASH, STUDY, labels, state_key

END = date(2019, 6, 30)
DAYS = 5300  # 2005-01-03 to 2019-07-07 in calendar days, so bars run past END


def first_peek(strategy: Strategy, bars: pl.DataFrame) -> int | None:
    """The first row t whose position on bars.head(t + 1) differs from the full frame's."""
    full = strategy.positions(bars).to_list()
    for t in range(bars.height):
        if strategy.positions(bars.head(t + 1))[-1] != full[t]:
            return t
    return None


def _oracle(bars: pl.DataFrame) -> pl.Series:
    long = (pl.col("fwd_ret_20") > ARMS["oracle"].threshold).fill_null(False)
    return labels(bars).select(long.cast(pl.Int8).alias("position")).to_series()


ORACLE = Strategy("oracle", 1, "Oracle", "Reads fwd_ret_20.", "None.", "control", _oracle)


@pytest.mark.parametrize("seed", [0, 1, 2])
@pytest.mark.parametrize("strategy", CATALOG.values(), ids=list(CATALOG))
def test_positions_at_t_match_on_bars_truncated_at_t(strategy, seed):
    assert first_peek(strategy, random_walk(seed)) is None


def test_the_oracle_fails_the_truncation_check():
    assert {seed: first_peek(ORACLE, random_walk(seed)) for seed in range(3)} == {0: 0, 1: 0, 2: 7}


def test_tripling_prices_after_a_cut_changes_no_position_before_it():
    bars = random_walk(0)
    cut = 400
    prices = ("open", "high", "low", "close")
    later = pl.col("date") > bars["date"][cut]
    tripled = bars.with_columns(
        pl.when(later).then(pl.col(c) * 3).otherwise(pl.col(c)).alias(c) for c in prices
    )

    changed = {}
    for strategy in CATALOG.values():
        before, after = strategy.positions(bars), strategy.positions(tripled)
        assert after[: cut + 1].to_list() == before[: cut + 1].to_list(), strategy.id
        changed[strategy.id] = int((after[cut + 1 :] != before[cut + 1 :]).sum())
    assert changed == {"buy_hold": 0, "golden_cross": 33, "macd_cross": 11, "bollinger_bounce": 0}


def test_bollinger_bounce_enters_below_the_lower_band_and_exits_at_the_middle():
    closes = [100.0] * 20 + [90.0, 95.0, 100.0, 99.0, 80.0, 99.0, 97.0]
    days = [date(2005, 1, 3) + timedelta(days=i) for i in range(len(closes))]
    bars = pl.DataFrame({"date": days, "close": closes})

    positions = CATALOG["bollinger_bounce"].positions(bars).to_list()

    assert positions[:20] == [0] * 20, "flat until the band exists, and 100 is not below it"
    assert positions[20:] == [1, 1, 0, 0, 1, 0, 0]


def test_fingerprints():
    assert {i: fingerprint(s) for i, s in CATALOG.items()} == {
        "buy_hold": "ef8e09363081b03701cb1c135944501402b3e3d7f70cc6a0d4e945b0b4ff215a",
        "golden_cross": "208804d03ec4ddba87a381f48b531fabb74857914ba5518cf74bd32ae88638e5",
        "macd_cross": "d9ce2e036327ac78f688a83d382c10720cfc0a644db15d916c288db90c634ed4",
        "bollinger_bounce": "9b9c73a801c944c36896505507ed677c95f3efd4d96eaed77f98fde0b1ab2a1e",
    }


def test_decisions_run_from_start_through_end_for_every_strategy_and_symbol():
    market = {s: random_walk(seed) for seed, s in enumerate(STUDY)}

    made = decisions(market, start=date(2005, 3, 1), end=date(2005, 6, 1))

    spans = made.group_by("arm", "symbol").agg(
        pl.col("date").min().alias("first"), pl.col("date").max().alias("last"), pl.len()
    )
    assert spans.height == len(CATALOG) * len(STUDY)
    assert set(spans.select("first", "last", "len").iter_rows()) == {
        (date(2005, 3, 1), date(2005, 6, 1), 93)
    }


@pytest.fixture(scope="module")
def made():
    market = {s: random_walk(seed) for seed, s in enumerate(STUDY)}
    return decisions(market, start=date(2005, 1, 1))


def committed(**changes: dict) -> list:
    entries = [entry(s) for s in CATALOG.values()]
    return [{**e, **changes.get(e["id"], {})} for e in entries]


@pytest.mark.parametrize(
    ("catalog", "flat", "expected"),
    [
        (committed(), None, []),
        (None, None, []),
        (
            [*committed(), {**entry(CATALOG["buy_hold"]), "id": "old_rule"}],
            None,
            ["catalog.json has old_rule, which CATALOG drops"],
        ),
        (
            committed(macd_cross={"fingerprint": "0" * 64}),
            None,
            [
                "macd_cross version 1 has fingerprint"
                " d9ce2e036327ac78f688a83d382c10720cfc0a644db15d916c288db90c634ed4,"
                f" not {'0' * 64} as in catalog.json. A changed rule needs a new version"
            ],
        ),
        (committed(macd_cross={"version": 0, "fingerprint": "0" * 64}), None, []),
        (None, "bollinger_bounce", ["bollinger_bounce is never long in the backtest period"]),
    ],
    ids=["clean", "first run", "dropped id", "changed rule", "new version", "never long"],
)
def test_refusals(made, catalog, flat, expected):
    if flat is not None:
        made = made.with_columns(
            pl.when(pl.col("arm") == flat).then(0).otherwise("position").alias("position")
        )

    assert refusals(catalog, made) == expected


def test_critical_value_scales_each_pair_by_its_spread_around_its_point():
    draws = np.array([[0.0, 2.0, 4.0], [1.0, 1.0, 4.0]])
    points = np.array([2.0, 1.0])

    assert critical_value(draws, points) == pytest.approx(1 + 0.9 * (3**0.5 - 1))


@pytest.fixture(scope="module")
def template(tmp_path_factory):
    """A repo with a holdout.json from synthetic bars, and a data dir of those bars."""
    root = tmp_path_factory.mktemp("template")
    repo, data = root / "repo", root / "data"
    (repo / "research").mkdir(parents=True)
    (data / "market").mkdir(parents=True)
    market = {s: random_walk(seed, DAYS) for seed, s in enumerate((*STUDY, CASH))}
    for s, bars in market.items():
        bars.write_parquet(data / "market" / f"{s}.parquet")
    policy = pl.DataFrame(
        {
            "state_key": [state_key(s) for s in ALL_STATES],
            "p_up": np.random.default_rng(1).random(len(ALL_STATES)),
        }
    )
    (repo / HOLDOUT_PATH).write_text(render_json(holdout_result(market, policy, END)))
    return root


def test_reconcile_reproduces_the_holdout_sharpe_intervals_exactly(template):
    holdout = json.loads((template / "repo" / HOLDOUT_PATH).read_text())
    market = {
        s: pl.read_parquet(template / "data" / "market" / f"{s}.parquet") for s in (*STUDY, CASH)
    }
    made = decisions(market)

    assert reconcile(made, market, holdout) == []

    holdout["arms"]["sma_filter"]["excess_sharpe"]["lo"] = -2.25
    assert reconcile(made, market, holdout) == [
        "golden_cross excess Sharpe"
        " {'point': 0.8061769532882747, 'lo': -2.2881494329069016, 'hi': 4.137028667561658}"
        " is not {'point': 0.8061769532882747, 'lo': -2.25, 'hi': 4.137028667561658},"
        " the sma_filter arm in holdout.json"
    ]
