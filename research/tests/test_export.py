import hashlib
import json
import random
import shutil
from dataclasses import asdict
from datetime import date

import polars as pl
import pytest

from jevtrader import cli
from jevtrader.catalog import random_walk
from jevtrader.evaluate import (
    HOLDOUT_PATH,
    HOLDOUT_RUN_PATH,
    PREREG_PATH,
    HoldoutRun,
    Power,
    holdout_result,
    render_json,
    render_prereg,
)
from jevtrader.export import CALL_LOG_PATH, EXPORT_PATH
from jevtrader.jev import (
    MODEL,
    POLICY_PATH,
    PROMPT_VERSION,
    SAMPLES,
    build_request,
    call_key,
    key_order_seed,
    policy_table,
    write_policy,
)
from jevtrader.states import ALL_STATES, CASH, STUDY, state_key, state_rows

END = date(2019, 6, 30)
DAYS = 5300  # 2005-01-03 to 2019-07-07 in calendar days, so bars run past END
SERVED = "typesafe/jev-1.13-20260917"
FILES = sorted(
    ["manifest.json", "policy.json", "summary.json", *(f"symbols/{s}.json" for s in STUDY)]
)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def synthetic_calls() -> list[dict]:
    rng = random.Random(7)
    calls = []
    for state in ALL_STATES:
        key = state_key(state)
        for sample in range(SAMPLES):
            p_hi, p_lo = round(rng.random(), 2), round(rng.random(), 2)
            calls.append(
                {
                    "call_key": call_key(key, sample),
                    "sample": sample,
                    "key_order_seed": key_order_seed(key, sample),
                    "model_requested": MODEL,
                    "model_served": SERVED,
                    "prompt_version": PROMPT_VERSION,
                    "state_key": key,
                    "request": build_request(state, sample),
                    "response": {},
                    "p_hi": p_hi,
                    "p_lo": p_lo,
                    "cost_usd": 2.5e-05,
                    "called_at": "2026-10-12T00:00:00+00:00",
                }
            )
    return calls


def write_result(repo, result: bytes) -> None:
    """Write holdout.json and a run manifest that matches it and the prereg."""
    (repo / HOLDOUT_PATH).write_bytes(result)
    prereg = sha256((repo / PREREG_PATH).read_bytes())
    run = HoldoutRun(prereg, "856de5dd182fe1a87676f45ccbd1361ad0c58899", sha256(result))
    (repo / HOLDOUT_RUN_PATH).write_text(render_json(run))


@pytest.fixture(scope="module")
def template(tmp_path_factory):
    """A repo and data dir whose call log, policy, prereg, and holdout result all agree."""
    root = tmp_path_factory.mktemp("template")
    repo, data = root / "repo", root / "data"
    (repo / "research").mkdir(parents=True)
    (data / "market").mkdir(parents=True)
    market = {s: random_walk(seed, DAYS) for seed, s in enumerate((*STUDY, CASH))}
    for s, bars in market.items():
        bars.write_parquet(data / "market" / f"{s}.parquet")
        fetched = {"first": "2005-01-03", "last": "2019-07-07", "rows": DAYS}
        fetched["fetched_at"] = "2026-10-12T10:29:33+00:00"
        (data / "market" / f"{s}.manifest.json").write_text(json.dumps(fetched))
    calls = synthetic_calls()
    (repo / CALL_LOG_PATH).write_text("".join(json.dumps(c) + "\n" for c in calls))
    policy = policy_table(calls)
    write_policy(policy, data)
    prereg = render_prereg(
        model_served=SERVED,
        policy_sha256=sha256((data / POLICY_PATH).read_bytes()),
        market_sha256={s: sha256((data / "market" / f"{s}.parquet").read_bytes()) for s in market},
        holdout_end=END,
        power=Power(se=0.0116, mde=0.0324, eval_blocks=50, holdout_blocks=97),
    )
    (repo / PREREG_PATH).write_text(prereg)
    write_result(repo, render_json(holdout_result(market, policy, END)).encode())
    return root


@pytest.fixture
def study(tmp_path, template, monkeypatch):
    """A private copy of the template with `jt` pointed at it."""
    shutil.copytree(template, tmp_path, dirs_exist_ok=True)
    repo, data = tmp_path / "repo", tmp_path / "data"
    monkeypatch.setattr(cli, "REPO_ROOT", repo)
    monkeypatch.setattr(cli, "DATA_DIR", data)
    return repo, data


def snapshot(repo) -> dict[str, tuple[bytes, int]]:
    root = repo / EXPORT_PATH
    return {
        p.relative_to(root).as_posix(): (p.read_bytes(), p.stat().st_mtime_ns)
        for p in root.rglob("*")
        if p.is_file()
    }


def read(repo, path: str) -> dict:
    return json.loads((repo / EXPORT_PATH / path).read_text())


def test_a_second_export_changes_no_files(study, capsys):
    repo, _ = study
    assert cli.main(["export"]) == 0
    first = capsys.readouterr().out.splitlines()
    assert [line.split()[:2] for line in first] == [[f"export/v1/{f}", "changed"] for f in FILES]
    before = snapshot(repo)

    assert cli.main(["export"]) == 0
    second = capsys.readouterr().out.splitlines()
    assert [line.split()[:2] for line in second] == [[f"export/v1/{f}", "unchanged"] for f in FILES]
    assert snapshot(repo) == before
    assert read(repo, "manifest.json")["files"] == {
        f: sha256(before[f][0]) for f in FILES if f != "manifest.json"
    }


def test_summary_copies_the_holdout_numbers_verbatim(study):
    repo, _ = study
    result = json.loads((repo / HOLDOUT_PATH).read_text())
    result["primary"]["lo"] = -0.0123456789
    result["arms"]["jev"]["auc"]["point"] = 0.6180339887
    result["arms"]["oracle"]["excess_sharpe_by_cost"]["20"] = 1.25
    write_result(repo, (json.dumps(result, indent=2) + "\n").encode())

    assert cli.main(["export"]) == 0
    summary = read(repo, "summary.json")
    arms = {a["name"]: a for a in summary["arms"]}
    assert summary["primary"]["lo"] == -0.0123456789
    assert summary["primary"]["hi"] == result["primary"]["hi"]
    assert arms["jev"]["auc"]["point"] == 0.6180339887
    assert arms["oracle"]["excessSharpeByCost"][3] == {"costBps": 20, "value": 1.25}
    assert arms["oracle"]["lookahead"] is True
    assert arms["vote_trend"]["brierSkill"] is None
    assert arms["jev"]["rule"] == "p_up > 0.5"


def tamper_holdout(repo, data):
    path = repo / HOLDOUT_PATH
    path.write_text(path.read_text().replace('"rows": ', '"rows": 1', 1))


def tamper_market(repo, data):
    bars = pl.read_parquet(data / "market" / "XLK.parquet")
    bars.with_columns(pl.col("close") * 1.01).write_parquet(data / "market" / "XLK.parquet")


def tamper_calls(repo, data):
    path = repo / CALL_LOG_PATH
    path.write_text(path.read_text().replace('"p_hi": 0.', '"p_hi": 0.0', 1))


@pytest.mark.parametrize(
    ("tamper", "message"),
    [
        (tamper_holdout, "sha256 of research/holdout.json is not result_sha256"),
        (tamper_market, "research/prereg.toml does not match this code and data\n"),
        (
            tamper_calls,
            "the policy table built from research/jev_calls.jsonl is not data/policy/jev.parquet",
        ),
    ],
)
def test_export_refuses_inputs_the_holdout_did_not_read(study, capsys, tamper, message):
    repo, data = study
    assert cli.main(["export"]) == 0
    before = snapshot(repo)
    capsys.readouterr()

    tamper(repo, data)
    assert cli.main(["export"]) == 1
    captured = capsys.readouterr()
    assert message in captured.err
    assert captured.err.endswith(f"refusing, {repo / EXPORT_PATH} is unchanged\n")
    assert captured.out == ""
    assert snapshot(repo) == before


def test_export_removes_a_file_it_did_not_produce(study, capsys):
    repo, _ = study
    assert cli.main(["export"]) == 0
    (repo / EXPORT_PATH / "old.json").write_bytes(b"{}\n")
    (repo / EXPORT_PATH / "stale").mkdir()
    (repo / EXPORT_PATH / "stale" / "x.json").write_bytes(b"[]\n")
    capsys.readouterr()

    assert cli.main(["export"]) == 0
    out = capsys.readouterr().out
    assert f"export/v1/old.json removed {sha256(b'{}\n')}\n" in out
    assert f"export/v1/stale/x.json removed {sha256(b'[]\n')}\n" in out
    assert sorted(snapshot(repo)) == FILES
    assert not (repo / EXPORT_PATH / "stale").exists()


def test_policy_states_rebuild_the_logged_requests(study):
    repo, data = study
    assert cli.main(["export"]) == 0
    policy = read(repo, "policy.json")
    calls = {
        (c["state_key"], c["sample"]): c
        for c in map(json.loads, (repo / CALL_LOG_PATH).read_text().splitlines())
    }
    dims = policy["dimensions"]
    texts = [{lv["level"]: lv["text"] for lv in d["levels"]} for d in dims]
    assert [s["key"] for s in policy["states"]] == [state_key(s) for s in ALL_STATES]
    for state in policy["states"]:
        assert len(state["samples"]) == SAMPLES
        for i, sample in enumerate(state["samples"]):
            rebuilt = {
                dims[d]["field"]: texts[d][state["levels"][dims[d]["name"]]]
                for d in sample["order"]
            }
            logged = calls[(state["key"], i)]
            assert json.dumps(rebuilt) == json.dumps(logged["request"]["state"])
            assert (sample["pHi"], sample["pLo"]) == (logged["p_hi"], logged["p_lo"])

    busiest = max(policy["states"], key=lambda s: s["development"]["n"])
    cut = {s: pl.read_parquet(data / "market" / f"{s}.parquet") for s in STUDY}
    labelled = pl.concat(state_rows(s, b.filter(pl.col("date") <= END)) for s, b in cut.items())
    labelled = labelled.filter(
        pl.col("split").is_in(["fit", "validate"]), pl.col("up_20").is_not_null()
    )
    base = labelled["up_20"].mean()
    mine = labelled.filter(pl.col("state_key") == busiest["key"])
    n, ups = mine.height, int(mine["up_20"].sum())
    assert n > 100
    assert busiest["development"] == {
        "n": n,
        "ups": ups,
        "upRate": ups / n,
        "empiricalP": pytest.approx((ups + 50 * base) / (n + 50)),
    }
    assert busiest["levels"] == asdict(ALL_STATES[policy["states"].index(busiest)])


def test_symbol_days_and_equity(study):
    repo, data = study
    assert cli.main(["export"]) == 0
    spy = read(repo, "symbols/SPY.json")
    states = read(repo, "policy.json")["states"]
    days, equity = spy["days"], spy["equity"]
    sessions = (END - date(2008, 1, 1)).days + 1
    assert {k: len(v) for k, v in days.items()} == dict.fromkeys(days, sessions)
    assert (days["date"][0], days["date"][-1]) == ("2008-01-01", "2019-06-30")
    assert days["split"][days["date"].index("2018-12-31")] == "validate"
    assert days["split"][days["date"].index("2019-01-01")] == "holdout"
    assert days["jev"] == [int(states[s]["pUp"] > 0.5) for s in days["state"]]
    assert 0 < sum(days["jev"]) < sessions

    bars = pl.read_parquet(data / "market" / "SPY.parquet")
    opens = dict(zip(bars["date"].cast(pl.String), bars["open"], strict=True))
    dates = bars["date"].cast(pl.String).to_list()
    t = dates.index("2008-01-01")
    assert days["open"][0] == round(opens["2008-01-01"], 4)
    assert days["fwdRet20"][0] == round(opens[dates[t + 21]] / opens[dates[t + 1]] - 1, 6)
    assert days["fwdRet20"][-22] is not None
    assert days["fwdRet20"][-21:] == [None] * 21

    assert (equity["date"][0], equity["date"][-1]) == ("2019-01-01", "2019-06-28")
    assert {k: len(v) for k, v in equity["arms"].items()} == dict.fromkeys(
        ["jev", "empirical_table", "buy_hold"], len(equity["date"])
    )
    h = dates.index("2019-01-01")
    r = opens[dates[h + 2]] / opens[dates[h + 1]] - 1
    assert equity["arms"]["buy_hold"][0] == round((1 - 5 / 1e4) * (1 + r), 6)
