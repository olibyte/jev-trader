import random
from datetime import date, timedelta

import numpy as np
import polars as pl
import pytest

from jevtrader.evaluate import auc, block_bootstrap_auc, empirical_table
from jevtrader.states import ALL_STATES, state_key

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
