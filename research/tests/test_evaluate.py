import math
import random
import tomllib
from datetime import date, timedelta

import numpy as np
import polars as pl
import pytest

from jevtrader.catalog import random_walk
from jevtrader.evaluate import (
    ARMS,
    Power,
    arm_reports,
    auc,
    backtest,
    block_bootstrap_auc,
    brier_skill,
    calibration,
    decisions,
    empirical_table,
    holdout_blocks,
    matched_cut,
    open_returns,
    power,
    render_prereg,
    write_prereg,
)
from jevtrader.states import ALL_STATES, CASH, SPLIT_STARTS, state_key, state_rows

A, B, C = (state_key(s) for s in ALL_STATES[:3])


def test_empirical_table_shrinks_toward_the_base_rate():
    rows = pl.DataFrame(
        {
            "state_key": [A, A, A, A, A, B, B],
            "up_20": [True, True, True, False, None, False, False],
        }
    )

    table = empirical_table(rows, k=2)

    by_key = {key: (p, n) for key, p, n in table.iter_rows()}
    assert table.height == 960
    assert by_key[A] == (pytest.approx(4 / 6), 4), "(3 + 1) / (4 + 2)"
    assert by_key[B] == (0.25, 2), "(0 + 1) / (2 + 2)"
    assert by_key[C] == (0.5, 0), "an unseen state scores the base rate"


def test_auc_counts_correctly_ordered_pairs():
    assert auc(np.array([0.1, 0.4, 0.35, 0.8]), np.array([0, 0, 1, 1])) == 0.75


def test_auc_counts_a_tie_as_half():
    assert auc(np.array([0.2, 0.5, 0.5, 0.9]), np.array([0, 0, 1, 1])) == 0.875
    assert auc(np.array([0.5, 0.5, 0.5, 0.5]), np.array([0, 1, 0, 1])) == 0.5


def test_auc_weight_counts_a_row_that_many_times():
    score, up = np.array([0.1, 0.4, 0.35, 0.8]), np.array([0, 0, 1, 1])

    weighted = auc(score, up, np.array([1, 2, 3, 1]))
    repeated = auc(np.repeat(score, [1, 2, 3, 1]), np.repeat(up, [1, 2, 3, 1]))

    assert weighted == repeated == 0.5


def informative(n_dates: int = 200, symbols: int = 3) -> tuple[np.ndarray, ...]:
    rng = random.Random(0)
    dates, score, up = [], [], []
    for d in range(n_dates):
        for _ in range(symbols):
            s = rng.random()
            dates.append(date(2015, 1, 1) + timedelta(days=d))
            score.append(s)
            up.append(s + rng.gauss(0, 0.3) > 0.5)
    return np.array(dates), np.array(score), np.array(up)


def test_block_bootstrap_is_fixed_by_its_seed():
    dates, score, up = informative()

    first = block_bootstrap_auc(dates, score, up, reps=200, seed=0)

    assert block_bootstrap_auc(dates, score, up, reps=200, seed=0) == first
    assert block_bootstrap_auc(dates, score, up, reps=200, seed=1) != first
    point, lo, hi = first
    assert point == auc(score, up)
    assert 0.5 < lo < point < hi < 1, "an informative score has a CI above 0.5 around its AUC"


def test_block_bootstrap_with_one_block_has_no_spread():
    dates = np.array([date(2015, 1, 2)] * 2 + [date(2015, 1, 5)] * 2)

    result = block_bootstrap_auc(
        dates, np.array([0.1, 0.4, 0.35, 0.8]), np.array([0, 0, 1, 1]), block=2, reps=50
    )

    assert result == (0.75, 0.75, 0.75), "both dates fall in one block, drawn once every rep"


def test_matched_cut_picks_the_exposure_closest_to_the_target():
    score = np.array([0.1, 0.2, 0.2, 0.3, 0.4, np.nan])

    assert matched_cut(score, 0.7) == 0.1, "exposures 5/6, 4/6, 2/6, 1/6, 0: 4/6 is closest"
    assert matched_cut(score, 0.9) == pytest.approx(-0.9), "below the minimum, long on every score"
    assert matched_cut(score, 0.0) == 0.4


def days(n: int) -> list[date]:
    return [date(2015, 1, 5) + timedelta(days=i) for i in range(n)]


def market(spy: list[float], cash: list[float]) -> dict[str, pl.DataFrame]:
    return {
        "SPY": pl.DataFrame({"date": days(len(spy)), "open": spy}),
        CASH: pl.DataFrame({"date": days(len(cash)), "open": cash}),
    }


def equity(sleeves: pl.DataFrame) -> float:
    return float((1 + sleeves["ret"]).product())


def test_always_long_equals_buy_and_hold():
    opens = market(
        [100.0, 101.0, 103.0, 102.0, 105.0, 104.0, 99.0], [50.0, 50.1, 50.2] + [50.3] * 4
    )
    rows = pl.DataFrame(
        {
            "symbol": ["SPY"] * 4,
            "date": days(4),
            "state_key": [A] * 4,
            "fwd_ret_20": [0.1, -0.1, 0.2, 0.3],
            "up_20": [True, False, True, True],
        }
    )
    policy = pl.DataFrame({"state_key": [A], "p_up": [0.4]})
    made = decisions(rows, rows, policy).filter(pl.col("arm") == "buy_hold")
    returns = open_returns(opens, date(2015, 1, 11))

    assert returns["date"].to_list() == days(4), "the last two sessions before the end drop out"
    assert equity(backtest(made, returns, 0)) == pytest.approx(1.0297029703), "104 / 101"
    assert equity(backtest(made, returns, 5)) == pytest.approx(1.0291881188), "0.9995 * 104 / 101"


def test_a_switch_charges_entry_and_exit_and_flat_earns_cash():
    opens = market([100.0, 100.0, 100.0, 120.0, 120.0, 120.0], [50.0, 50.0] + [55.0] * 4)
    made = pl.DataFrame(
        {
            "symbol": ["SPY"] * 4,
            "date": days(4),
            "arm": ["x"] * 4,
            "score": [0.0, 1.0, 1.0, 0.0],
            "position": [0, 1, 1, 0],
        },
        schema_overrides={"position": pl.Int8},
    )

    sleeves = backtest(made, open_returns(opens, date(2015, 1, 11)), 5)

    assert sleeves["switch"].to_list() == [False, True, False, True]
    assert sleeves["ret"].to_list() == pytest.approx([0.1, 0.9995 * 1.2 - 1, 0.0, 0.9995 - 1])
    assert equity(sleeves) == pytest.approx(1.1 * 1.2 * 0.9995**2)


def test_brier_skill_of_the_base_rate_is_zero():
    up = np.array([True, False, False, True, True])

    assert brier_skill(np.full(5, 0.6), up, 0.6) == 0.0
    assert brier_skill(up.astype(float), up, 0.6) == 1.0


def test_calibration_bins_by_fixed_width():
    p, up = np.array([0.05, 0.55, 0.58, 1.0]), np.array([False, True, False, True])

    assert calibration(p, up) == [
        (0.0, 1, 0.05, 0.0),
        (0.5, 2, pytest.approx(0.565), 0.5),
        (0.9, 1, 1.0, 1.0),
    ]


def drift(n: int) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "date": [date(2005, 1, 3) + timedelta(days=i) for i in range(n)],
            "open": [50 * math.exp(0.00005 * i) for i in range(n)],
        }
    )


@pytest.fixture(scope="module")
def synthetic():
    n = 4100
    bars = {s: random_walk(seed, n) for seed, s in enumerate(("SPY", "QQQ", "IWM"))}
    rows = pl.concat(state_rows(s, b) for s, b in bars.items())
    policy = pl.DataFrame(
        {
            "state_key": [state_key(s) for s in ALL_STATES],
            "p_up": np.random.default_rng(1).random(len(ALL_STATES)),
        }
    )
    returns = open_returns({**bars, CASH: drift(n)}, dict(SPLIT_STARTS)["holdout"])
    split = pl.col("split")
    return rows.filter(split == "validate"), rows.filter(split == "fit"), policy, returns


def test_the_oracle_beats_every_other_arm(synthetic):
    reports = arm_reports(*synthetic)

    oracle = reports.pop("oracle")
    assert set(reports) == set(ARMS) - {"oracle"}
    assert oracle.auc == (1.0, 1.0, 1.0)
    for name, report in reports.items():
        assert oracle.excess_sharpe.point > report.excess_sharpe.point, name


def test_holdout_blocks_leave_out_the_unlabelled_tail():
    dates = pl.Series([date(2019, 1, 1) + timedelta(days=i // 2) for i in range(2 * 62)])

    assert holdout_blocks(dates) == 3, "62 dates, 21 without an exit open, 41 in blocks of 20"


def test_mde_scales_with_the_holdout_block_count(synthetic):
    rows, fit, policy, _ = synthetic

    small, large = power(rows, fit, policy, 20), power(rows, fit, policy, 80)

    assert small.mde == pytest.approx(2.8015852 * small.se), "z(0.975) + z(0.8)"
    assert small.se / large.se == pytest.approx(2, rel=0.1), "4x the blocks halves the SE"
    assert (small.eval_blocks, small.holdout_blocks) == (22, 20), "429 labelled dates"


PREREG = {
    "model_served": "typesafe/jev-1.13",
    "policy_sha256": "ab" * 32,
    "market_sha256": {"SPY": "cd" * 32, "BIL": "ef" * 32},
    "holdout_end": date(2026, 10, 9),
    "power": Power(se=0.0125, mde=0.035, eval_blocks=50, holdout_blocks=97),
}


def test_prereg_round_trips_through_toml():
    prereg = tomllib.loads(render_prereg(**PREREG))

    assert prereg["study"] == {
        "state_version": "states/v1",
        "prompt_version": "descriptive/v1",
        "model_served": "typesafe/jev-1.13",
        "policy_sha256": "ab" * 32,
        "market_sha256": {"SPY": "cd" * 32, "BIL": "ef" * 32},
    }
    assert prereg["holdout"] == {
        "start": date(2019, 1, 1),
        "end": date(2026, 10, 9),
        "fit_on": ["fit", "validate"],
    }
    assert prereg["primary"] == {
        "metric": "auc(jev) - auc(empirical_table)",
        "level": 0.95,
        "block": 20,
        "reps": 2000,
        "seed": 0,
        "outcome": {
            "jev_better": "ci_low > 0",
            "jev_worse": "ci_high < 0",
            "inconclusive": "otherwise",
        },
    }
    assert prereg["power"] == {
        "alpha": 0.05,
        "power": 0.8,
        "dev_se": 0.0125,
        "mde": 0.035,
        "validate_blocks": 50,
        "holdout_blocks": 97,
    }
    assert list(prereg["arms"]) == list(ARMS)
    assert prereg["arms"]["jev"] == "p_up > 0.5"
    assert prereg["arms"]["vote_trend"] == "vote_trend > -0.5"
    assert prereg["arms"]["random_matched"] == (
        "uniform_seed0 > the cut whose exposure on the fit rows is closest to the mean exposure"
        " of jev"
    )
    assert prereg["settings"] == {"shrink_k": 50, "cost_bps": 5, "costs_bps": [0, 5, 10, 20]}


def test_write_prereg_never_replaces_a_different_file(tmp_path):
    path, text = tmp_path / "prereg.toml", render_prereg(**PREREG)
    other = render_prereg(**{**PREREG, "holdout_end": date(2026, 10, 12)})

    assert write_prereg(path, text) == "missing"
    assert path.read_text() == text
    assert write_prereg(path, text) == "matches"
    assert write_prereg(path, other) == "differs"
    assert path.read_text() == text
