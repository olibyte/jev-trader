import hashlib
import json
import shutil
import subprocess
from datetime import date

import numpy as np
import polars as pl
import pytest

from jevtrader import cli, evaluate
from jevtrader.catalog import random_walk
from jevtrader.evaluate import (
    ARMS,
    HOLDOUT_PATH,
    HOLDOUT_RUN_PATH,
    PREREG_PATH,
    Interval,
    Power,
    holdout_result,
    outcome,
    render_prereg,
)
from jevtrader.jev import POLICY_PATH
from jevtrader.states import ALL_STATES, CASH, STUDY, state_key

END = date(2019, 6, 30)
DAYS = 5300  # 2005-01-03 to 2019-07-07 in calendar days, so bars run past END


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def git(repo, *args):
    return subprocess.run(
        ["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t", *args],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


@pytest.fixture(scope="module")
def inputs(tmp_path_factory):
    """A data dir of synthetic bars and a policy, and a prereg that matches it."""
    data = tmp_path_factory.mktemp("data")
    market = {s: random_walk(seed, DAYS) for seed, s in enumerate((*STUDY, CASH))}
    for s, bars in market.items():
        (data / "market").mkdir(exist_ok=True)
        bars.write_parquet(data / "market" / f"{s}.parquet")
    policy = pl.DataFrame(
        {
            "state_key": [state_key(s) for s in ALL_STATES],
            "p_up": np.random.default_rng(1).random(len(ALL_STATES)),
        }
    )
    (data / POLICY_PATH).parent.mkdir()
    policy.write_parquet(data / POLICY_PATH)
    prereg = render_prereg(
        model_served="typesafe/jev-1.13-20260917",
        policy_sha256=sha256((data / POLICY_PATH).read_bytes()),
        market_sha256={s: sha256((data / "market" / f"{s}.parquet").read_bytes()) for s in market},
        holdout_end=END,
        power=Power(se=0.0116, mde=0.0324, eval_blocks=50, holdout_blocks=97),
    )
    return data, prereg


@pytest.fixture
def study(tmp_path, inputs, monkeypatch):
    """A git repo with the prereg committed, and a private copy of the data dir."""
    data, prereg = inputs
    repo = tmp_path / "repo"
    (repo / PREREG_PATH).parent.mkdir(parents=True)
    (repo / PREREG_PATH).write_text(prereg)
    git(repo, "init", "-q")
    git(repo, "add", ".")
    git(repo, "commit", "-q", "--no-gpg-sign", "-m", "prereg")
    shutil.copytree(data, tmp_path / "data")
    monkeypatch.setattr(cli, "REPO_ROOT", repo)
    monkeypatch.setattr(cli, "DATA_DIR", tmp_path / "data")
    return repo, tmp_path / "data"


def outputs(repo):
    return [p for p in (repo / HOLDOUT_PATH, repo / HOLDOUT_RUN_PATH) if p.exists()]


def test_holdout_refuses_an_uncommitted_prereg(study, capsys):
    repo, _ = study
    git(repo, "rm", "-q", "--cached", str(PREREG_PATH))
    git(repo, "commit", "-q", "--no-gpg-sign", "-m", "untrack")

    assert cli.main(["holdout"]) == 1
    assert "prereg.toml is not committed" in capsys.readouterr().err
    assert outputs(repo) == []


def test_holdout_refuses_an_edited_prereg(study, capsys):
    repo, _ = study
    path = repo / PREREG_PATH
    path.write_text(path.read_text().replace("cost_bps = 5", "cost_bps = 0"))

    assert cli.main(["holdout"]) == 1
    assert capsys.readouterr().err == ("uncommitted changes, refusing:\n M research/prereg.toml\n")
    assert outputs(repo) == []


def test_holdout_refuses_when_a_recorded_hash_differs(study, capsys):
    repo, data = study
    bars = pl.read_parquet(data / "market" / "XLK.parquet")
    bars.with_columns(pl.col("close") * 1.01).write_parquet(data / "market" / "XLK.parquet")

    assert cli.main(["holdout"]) == 1
    err = capsys.readouterr().err
    assert "does not match this code and data, refusing" in err
    assert [line[:5] for line in err.splitlines() if line.startswith(("-X", "+X"))] == [
        "-XLK ",
        "+XLK ",
    ], "the diff names the one file that changed"
    assert outputs(repo) == []


def test_holdout_refuses_when_the_code_drifts_from_the_prereg(study, capsys, monkeypatch):
    repo, _ = study
    monkeypatch.setattr(evaluate, "SHRINK_K", 40)

    assert cli.main(["holdout"]) == 1
    err = capsys.readouterr().err
    assert "-shrink_k = 50\n+shrink_k = 40" in err
    assert outputs(repo) == []


def test_holdout_runs_once_and_a_rerun_from_the_manifest_is_byte_identical(study, capsys):
    repo, _ = study
    assert cli.main(["holdout", "--verify"]) == 2, "nothing to verify before the run"

    assert cli.main(["holdout"]) == 0
    out = capsys.readouterr().out
    result = (repo / HOLDOUT_PATH).read_bytes()
    run = json.loads((repo / HOLDOUT_RUN_PATH).read_text())
    assert run == {
        "prereg_sha256": sha256((repo / PREREG_PATH).read_bytes()),
        "git_commit": git(repo, "rev-parse", "HEAD"),
        "result_sha256": sha256(result),
    }
    summary = json.loads(result)
    assert (summary["first"], summary["last"]) == ("2019-01-01", "2019-06-30")
    assert list(summary["arms"]) == list(ARMS)
    assert summary["arms"]["oracle"]["auc"] == {"point": 1.0, "lo": 1.0, "hi": 1.0}
    assert f"outcome {summary['outcome']}" in out

    assert cli.main(["holdout"]) == 1, "a second run refuses"
    assert "runs once, refusing" in capsys.readouterr().err
    assert (repo / HOLDOUT_PATH).read_bytes() == result

    assert cli.main(["holdout", "--verify"]) == 0
    assert "is byte-identical" in capsys.readouterr().out

    (repo / HOLDOUT_PATH).write_bytes(result.replace(b'"rows": ', b'"rows": 1'))
    assert cli.main(["holdout", "--verify"]) == 1, "verify compares the bytes"
    assert "differs" in capsys.readouterr().out


def test_holdout_reads_no_bar_after_the_end(inputs):
    data, _ = inputs
    market = {s: pl.read_parquet(data / "market" / f"{s}.parquet") for s in (*STUDY, CASH)}
    policy = pl.read_parquet(data / POLICY_PATH)
    cut = {s: bars.filter(pl.col("date") <= END) for s, bars in market.items()}
    after = pl.col("date") > END
    later = {
        s: bars.with_columns(
            pl.when(after).then(pl.col(c) * 3).otherwise(pl.col(c)).alias(c)
            for c in ("open", "high", "low", "close")
        )
        for s, bars in market.items()
    }

    assert holdout_result(later, policy, END) == holdout_result(cut, policy, END)


@pytest.mark.parametrize(
    ("lo", "hi", "expected"),
    [
        (0.01, 0.05, "jev_better"),
        (-0.05, -0.01, "jev_worse"),
        (-0.01, 0.05, "inconclusive"),
        (0.0, 0.05, "inconclusive"),
    ],
)
def test_outcome_follows_the_prereg_rule(lo, hi, expected):
    assert outcome(Interval(0.02, lo, hi)) == expected
