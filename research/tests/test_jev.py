import json
import statistics
from datetime import UTC, date, datetime, timedelta

import httpx
import polars as pl
import pytest

from jevtrader import cli
from jevtrader.jev import (
    DESCRIPTIONS,
    FIELDS,
    POLICY_PATH,
    PROMPT_VERSION,
    QUESTIONS,
    SAMPLES,
    JevCall,
    JevError,
    append_call,
    build_request,
    call_jev,
    call_key,
    key_order_seed,
    pending,
    policy_table,
    read_calls,
)
from jevtrader.states import ALL_STATES, DIMENSIONS, STATE_VERSION, STUDY, State, state_key

KEY = "or-test-key-123"
NOW = datetime(2026, 10, 12, 10, 0, tzinfo=UTC)
SERVED = "typesafe/jev-1.13-20260917"
HOT = State("OVERBOUGHT", "ABOVE", "ABOVE", "POS_RISING", "ABOVE_UPPER", "HIGH")


def decision(p_hi: float, p_lo: float, model: str = SERVED) -> dict:
    return {
        "id": "gen-dec-1",
        "model": model,
        "provider": "TypeSafe",
        "answers": {
            "higher": {"type": "noul", "noul": p_hi},
            "lower_or_equal": {"type": "noul", "noul": p_lo},
        },
        "usage": {"input_tokens": 492, "output_tokens": 38, "cost": 0.000020664},
    }


def fake_call(state: State, sample: int, p_hi: float, p_lo: float, model=SERVED) -> JevCall:
    key = state_key(state)
    return JevCall(
        call_key=call_key(key, sample),
        sample=sample,
        key_order_seed=key_order_seed(key, sample),
        model_requested="typesafe/jev-1.13",
        model_served=model,
        prompt_version=PROMPT_VERSION,
        state_key=key,
        request=build_request(state, sample),
        response=decision(p_hi, p_lo, model),
        p_hi=p_hi,
        p_lo=p_lo,
        cost_usd=0.000020664,
        called_at=NOW.isoformat(),
    )


def full_log() -> list[JevCall]:
    first = ([0.6, 0.7, 0.5, 0.6, 0.8], [0.4, 0.2, 0.5, 0.5, 0.3])
    calls = []
    for i, state in enumerate(ALL_STATES):
        for sample in range(SAMPLES):
            if i == 0:
                p_hi, p_lo = first[0][sample], first[1][sample]
            else:
                p_hi = 0.3 + 0.4 * (i % 7) / 6 + 0.01 * sample
                p_lo = 1 - p_hi + 0.02
            calls.append(fake_call(state, sample, p_hi, p_lo))
    return calls


def test_every_level_has_a_description():
    assert {name: tuple(levels) for name, levels in DESCRIPTIONS.items()} == DIMENSIONS
    assert list(FIELDS) == list(DIMENSIONS)


def test_build_request_describes_the_state_in_words():
    request = build_request(HOT, 0)

    assert request["model"] == "typesafe/jev-1.13"
    assert request["questions"] == QUESTIONS
    assert list(request["questions"]) == ["higher", "lower_or_equal"]
    assert sorted(request["state"].items()) == [
        ("bollinger", "The price is above the upper Bollinger band (20-day, 2 sd)."),
        ("macd", "The MACD histogram is positive and rising."),
        ("momentum", "The 14-day RSI is overbought (70 or above)."),
        ("trend_200d", "The price is above its 200-day moving average."),
        ("trend_50d_vs_200d", "The 50-day moving average is above the 200-day moving average."),
        ("volatility", "Volatility is high (14-day ATR in the top third of the past year)."),
    ]


def test_build_request_order_is_fixed_per_sample_and_varies_across_samples():
    orders = [list(build_request(HOT, sample)["state"]) for sample in range(SAMPLES)]

    assert [list(build_request(HOT, sample)["state"]) for sample in range(SAMPLES)] == orders
    assert len({tuple(order) for order in orders}) > 1


def jev_client(*responses: httpx.Response, seen: list | None = None) -> httpx.Client:
    queue = list(responses)

    def handler(req: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(req)
        return queue.pop(0)

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_call_jev_posts_build_request_and_parses_the_answers():
    seen = []
    client = jev_client(httpx.Response(200, json=decision(0.61, 0.42)), seen=seen)

    call = call_jev(client, KEY, HOT, 2, NOW, lambda s: pytest.fail(f"slept {s}"))

    (req,) = seen
    assert str(req.url) == "https://openrouter.ai/api/alpha/decisions"
    assert req.headers["Authorization"] == "Bearer or-test-key-123"
    assert json.dumps(json.loads(req.content)) == json.dumps(build_request(HOT, 2))
    assert (call["p_hi"], call["p_lo"], call["cost_usd"]) == (0.61, 0.42, 0.000020664)
    assert call["model_served"] == "typesafe/jev-1.13-20260917"
    assert (call["state_key"], call["sample"]) == (state_key(HOT), 2)
    assert call["called_at"] == "2026-10-12T10:00:00+00:00"


def test_call_jev_retries_a_server_error():
    sleeps = []
    client = jev_client(httpx.Response(500, text="busy"), httpx.Response(200, json=decision(1, 0)))

    call = call_jev(client, KEY, HOT, 0, NOW, sleeps.append)

    assert (call["p_hi"], call["p_lo"]) == (1.0, 0.0)
    assert sleeps == [1.0]


def test_call_jev_gives_up_after_four_rate_limits():
    sleeps = []
    client = jev_client(*[httpx.Response(429, text="slow down")] * 4)

    with pytest.raises(JevError, match="HTTP 429 after 4 attempts"):
        call_jev(client, KEY, HOT, 0, NOW, sleeps.append)
    assert sleeps == [1.0, 2.0, 4.0]


def test_call_jev_raises_on_a_client_error_without_the_key():
    client = jev_client(httpx.Response(400, text=f"bad key {KEY}"))

    with pytest.raises(JevError, match="HTTP 400") as error:
        call_jev(client, KEY, HOT, 0, NOW, lambda s: pytest.fail(f"slept {s}"))
    assert KEY not in str(error.value)


def test_call_jev_raises_on_a_missing_noul():
    payload = decision(0.61, 0.42)
    del payload["answers"]["lower_or_equal"]["noul"]
    client = jev_client(httpx.Response(200, json=payload))

    with pytest.raises(JevError, match="lacks a field"):
        call_jev(client, KEY, HOT, 0, NOW, lambda s: pytest.fail(f"slept {s}"))


def test_call_jev_raises_on_a_probability_outside_0_1():
    client = jev_client(httpx.Response(200, json=decision(1.2, 0.42)))

    with pytest.raises(JevError, match="higher noul is 1.2"):
        call_jev(client, KEY, HOT, 0, NOW, lambda s: pytest.fail(f"slept {s}"))


def test_policy_table_averages_the_samples():
    table = policy_table(full_log())

    assert table.columns == [
        "state_key",
        "prompt_version",
        "p_up",
        "p_sd",
        "coherence",
    ]
    assert table.height == 960
    key, version, p_up, p_sd, coherence = table.row(0)
    assert (key, version) == (state_key(ALL_STATES[0]), "descriptive/v1")
    u = [0.6, 0.75, 0.5, 0.55, 0.75]
    assert p_up == pytest.approx(statistics.mean(u))
    assert p_sd == pytest.approx(statistics.stdev(u))
    assert coherence == pytest.approx(0.06), "|p_hi + p_lo - 1| = 0, .1, 0, .1, .1"


def test_policy_table_rejects_two_served_models():
    calls = full_log()
    calls[7] = fake_call(ALL_STATES[1], 2, 0.5, 0.5, model="typesafe/jev-1.13-20261001")

    with pytest.raises(JevError, match="served by 2 models"):
        policy_table(calls)


def test_policy_table_rejects_a_missing_call():
    calls = full_log()
    del calls[12]

    with pytest.raises(JevError, match=f"no call for state {state_key(ALL_STATES[2])} sample 2"):
        policy_table(calls)


def test_policy_table_rejects_a_duplicate_call():
    calls = full_log()
    calls.append(calls[3])

    with pytest.raises(JevError, match="two calls"):
        policy_table(calls)


def test_policy_table_rejects_a_request_edited_without_a_version_bump():
    calls = full_log()
    calls[5]["request"]["state"]["momentum"] = "The 14-day RSI is very oversold (below 20)."

    with pytest.raises(JevError, match="needs a new PROMPT_VERSION"):
        policy_table(calls)


def test_policy_table_rejects_a_request_in_another_field_order():
    calls = full_log()
    state = calls[5]["request"]["state"]
    calls[5]["request"]["state"] = dict(reversed(state.items()))

    with pytest.raises(JevError, match="needs a new PROMPT_VERSION"):
        policy_table(calls)


def test_pending_returns_exactly_the_gaps():
    log = [fake_call(ALL_STATES[0], sample, 0.5, 0.5) for sample in range(SAMPLES) if sample != 3]
    log += [fake_call(ALL_STATES[1], sample, 0.5, 0.5) for sample in range(SAMPLES)]
    old = fake_call(ALL_STATES[2], 0, 0.5, 0.5)
    old["prompt_version"] = "descriptive/v0"

    gaps = pending([*log, old])

    assert len(gaps) == 960 * 5 - 9
    assert gaps[:3] == [(ALL_STATES[0], 3), (ALL_STATES[2], 0), (ALL_STATES[2], 1)]


def test_append_call_survives_a_torn_last_line(tmp_path):
    path = tmp_path / "calls.jsonl"
    first, second = fake_call(HOT, 0, 0.6, 0.4), fake_call(HOT, 1, 0.7, 0.3)
    append_call(path, first)
    with path.open("ab") as f:
        f.write(b'{"call_key": "torn')

    assert read_calls(path) == [first], "the torn line is not a call yet"
    append_call(path, second)
    assert read_calls(path) == [first, second]
    assert read_calls(tmp_path / "missing.jsonl") == []


def write_state_rows(data_dir) -> None:
    keys = [state_key(s) for s in ALL_STATES[:4]]
    rows = []
    for d in range(60):
        rows.append((date(2010, 1, 4) + timedelta(days=d), "fit", keys[d % 4], d % 3 == 0))
        rows.append((date(2015, 1, 5) + timedelta(days=d), "validate", keys[d % 4], d % 2 == 0))
    rows.append((date(2019, 1, 2), "holdout", keys[0], True))
    frame = pl.DataFrame(rows, schema=["date", "split", "state_key", "up_20"], orient="row")
    for symbol in STUDY:
        path = data_dir / "states" / f"{symbol}.parquet"
        path.parent.mkdir(parents=True, exist_ok=True)
        frame.select(
            pl.lit(symbol).alias("symbol"),
            "date",
            "split",
            "state_key",
            pl.lit(STATE_VERSION).alias("state_version"),
            pl.lit(0.01).alias("fwd_ret_20"),
            "up_20",
        ).write_parquet(path)


def test_offline_jev_table_is_idempotent(tmp_path, monkeypatch, capsys):
    def no_network(*args, **kwargs):
        raise AssertionError("offline must not build an httpx client")

    monkeypatch.setattr(httpx, "Client", no_network)
    monkeypatch.setattr(cli, "dotenv_values", no_network)
    monkeypatch.setattr(cli, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(cli, "CALLS_PATH", tmp_path / "jev_calls.jsonl")
    write_state_rows(tmp_path / "data")
    log = full_log()
    (tmp_path / "jev_calls.jsonl").write_text("".join(json.dumps(c) + "\n" for c in log[:-1]))

    assert cli.main(["jev-table", "--offline"]) == 1
    assert capsys.readouterr().out == "4799/4800 calls logged\n"

    append_call(tmp_path / "jev_calls.jsonl", log[-1])
    policy = tmp_path / "data" / POLICY_PATH
    assert cli.main(["jev-table", "--offline"]) == 0
    first_out, first_bytes = capsys.readouterr().out, policy.read_bytes()
    assert cli.main(["jev-table", "--offline"]) == 0
    second_out = capsys.readouterr().out

    assert policy.read_bytes() == first_bytes
    assert "calls 4800 (descriptive/v1); model_served typesafe/jev-1.13-20260917" in first_out
    assert "log cost $0.0992" in first_out
    assert f"{policy} changed sha256" in first_out
    assert f"{policy} unchanged sha256" in second_out


def test_online_jev_table_logs_answers_and_skips_failures(tmp_path, monkeypatch, capsys):
    real_client = httpx.Client
    replies = [decision(0.7, 0.3), decision(0.6, 0.4)]

    def handler(req: httpx.Request) -> httpx.Response:
        try:
            return httpx.Response(200, json=replies.pop())
        except IndexError:
            return httpx.Response(400, text="no")

    monkeypatch.setattr(
        httpx, "Client", lambda **kw: real_client(transport=httpx.MockTransport(handler))
    )
    monkeypatch.setattr(cli, "dotenv_values", lambda path: {"OPENROUTER_API_KEY": KEY})
    monkeypatch.setattr(cli, "CALLS_PATH", tmp_path / "jev_calls.jsonl")
    monkeypatch.setattr(cli.time, "sleep", lambda s: pytest.fail(f"slept {s}"))

    assert cli.main(["jev-table", "--limit", "3", "--workers", "2"]) == 1

    calls = read_calls(tmp_path / "jev_calls.jsonl")
    assert sorted(c["p_hi"] for c in calls) == [0.6, 0.7]
    assert {c["state_key"] for c in calls} == {state_key(ALL_STATES[0])}
    out = capsys.readouterr().out
    assert "HTTP 400 after 1 attempts: no" in out
    assert out.endswith("1/3 calls failed, rerun to retry them\n")
    assert len(pending(calls)) == 4798
