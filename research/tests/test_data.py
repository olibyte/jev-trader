import gzip
import hashlib
import json
from dataclasses import replace
from datetime import UTC, date, datetime
from pathlib import Path

import httpx
import polars as pl
import pytest

from jevtrader.data import (
    DAY,
    HOUR,
    DataError,
    closed_bars,
    fetch_symbol,
    parse_response,
    regular_hours,
    request,
    up_base_rate,
    validate,
)

FIXTURES = Path(__file__).parent / "fixtures"
KEY = "test-key-123"
NOW = datetime(2026, 10, 12, 10, 0, tzinfo=UTC)
FIXTURE_RANGES = ((date(2024, 1, 1), date(2024, 3, 31)), (date(2024, 4, 1), date(2024, 6, 30)))
FIXTURE_DAY = replace(DAY, windows=FIXTURE_RANGES)
HEADERS = json.loads((FIXTURES / "spy_headers.json").read_text())


def fixture_body(start: str) -> str:
    return (FIXTURES / f"spy_{start}.json").read_text()


def fixture_client(seen: list[dict] | None = None) -> httpx.Client:
    def handler(req: httpx.Request) -> httpx.Response:
        assert req.url.params["apikey"] == KEY, "key travels as a query param"
        if seen is not None:
            seen.append({k: v for k, v in req.url.params.items() if k != "apikey"})
        start = req.url.params["start_date"]
        return httpx.Response(200, text=fixture_body(start), headers=HEADERS[start])

    return httpx.Client(transport=httpx.MockTransport(handler))


def fixture_bars() -> pl.DataFrame:
    frames = [parse_response(json.loads(fixture_body(s.isoformat()))) for s, _ in FIXTURE_RANGES]
    return pl.concat(frames)


def no_sleep(seconds: float) -> None:
    raise AssertionError(f"unexpected sleep({seconds})")


def snapshot(root: Path) -> dict[str, tuple[bytes, int]]:
    return {
        str(p.relative_to(root)): (p.read_bytes(), p.stat().st_mtime_ns)
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }


def test_fetch_symbol_writes_parquet_manifest_and_archive(tmp_path):
    seen = []
    result = fetch_symbol(
        fixture_client(seen), KEY, "SPY", tmp_path, NOW, None, no_sleep, FIXTURE_DAY
    )

    daily = {"symbol": "SPY", "interval": "1day", "adjust": "all", "order": "asc"}
    assert seen == [
        {**daily, "outputsize": "5000", "start_date": "2024-01-01", "end_date": "2024-03-31"},
        {**daily, "outputsize": "5000", "start_date": "2024-04-01", "end_date": "2024-06-30"},
    ]

    assert (result.rows, result.first, result.last, result.changed) == (
        124,
        date(2024, 1, 2),
        date(2024, 6, 28),
        True,
    )

    parquet = tmp_path / "market" / "SPY.parquet"
    assert hashlib.sha256(parquet.read_bytes()).hexdigest() == (
        "e56807e767ade2f95e146483fd5a238496d0745d231b90cc0807867836a609b7"
    ), "daily Parquet bytes match the fetch before bar sizes existed"
    bars = pl.read_parquet(parquet)
    assert bars.row(0) == (date(2024, 1, 2), 457.24271, 458.70501, 455.62546, 457.71722, 123623700)
    assert bars.height == 124

    raw_names = [
        hashlib.sha256(fixture_body(s.isoformat()).encode()).hexdigest() + ".json.gz"
        for s, _ in FIXTURE_RANGES
    ]
    manifest = json.loads((tmp_path / "market" / "SPY.manifest.json").read_text())
    assert manifest == {
        "symbol": "SPY",
        "adjust": "all",
        "ranges": [["2024-01-01", "2024-03-31"], ["2024-04-01", "2024-06-30"]],
        "fetched_at": "2026-10-12T10:00:00+00:00",
        "rows": 124,
        "first": "2024-01-02",
        "last": "2024-06-28",
        "sha256": hashlib.sha256(parquet.read_bytes()).hexdigest(),
        "raw": raw_names,
    }

    assert sorted(snapshot(tmp_path)) == [
        "market/SPY.manifest.json",
        "market/SPY.parquet",
        *sorted(f"raw/SPY/{n}" for n in raw_names),
    ]
    for (start, _), name in zip(FIXTURE_RANGES, raw_names, strict=True):
        text = gzip.decompress((tmp_path / "raw" / "SPY" / name).read_bytes()).decode()
        assert text == fixture_body(start.isoformat())
        assert "apikey" not in text and KEY not in text


def test_second_fetch_changes_no_file(tmp_path):
    fetch_symbol(fixture_client(), KEY, "SPY", tmp_path, NOW, None, no_sleep, FIXTURE_DAY)
    before = snapshot(tmp_path)

    later = datetime(2026, 10, 13, 10, 0, tzinfo=UTC)
    result = fetch_symbol(
        fixture_client(), KEY, "SPY", tmp_path, later, None, no_sleep, FIXTURE_DAY
    )

    assert result.changed is False
    assert snapshot(tmp_path) == before, "bytes and mtimes of every file are unchanged"


def test_closed_bars_waits_for_20_00_new_york():
    bars = pl.DataFrame(
        {"date": [date(2026, 10, 8), date(2026, 10, 9), date(2026, 10, 12)], "open": [1.0] * 3}
    )

    before = closed_bars(bars, datetime(2026, 10, 12, 23, 59, tzinfo=UTC))
    after = closed_bars(bars, datetime(2026, 10, 13, 0, 0, tzinfo=UTC))

    assert before["date"].to_list() == [date(2026, 10, 8), date(2026, 10, 9)], "19:59 NY"
    assert after["date"].to_list() == [
        date(2026, 10, 8),
        date(2026, 10, 9),
        date(2026, 10, 12),
    ], "20:00 NY"


def gap_bars(next_open: float) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "date": [date(2024, 1, 2), date(2024, 1, 3)],
            "open": [100.0, next_open],
            "high": [101.0, next_open + 1],
            "low": [99.0, next_open - 1],
            "close": [100.0, next_open],
            "volume": [10, 10],
        }
    )


def test_validate_rejects_overnight_move_over_40_percent():
    validate("XLE", gap_bars(139.0), None)

    with pytest.raises(DataError) as err:
        validate("XLE", gap_bars(141.0), None)
    assert str(err.value) == "XLE 2024-01-03: overnight move over 40% (1 rows)"


def test_validate_rejects_session_missing_against_reference():
    bars = fixture_bars()
    validate("SPY", bars, None)
    validate("QQQ", bars, bars["date"])

    gappy = bars.filter(pl.col("date") != date(2024, 2, 15))
    with pytest.raises(DataError) as err:
        validate("QQQ", gappy, bars["date"])
    assert str(err.value) == (
        "QQQ 2024-02-15: sessions differ from SPY in 2024-01-02..2024-06-28 "
        "(1 missing, e.g. 2024-02-15; 0 extra, e.g. none)"
    )


def test_up_base_rate_counts_strict_rises_from_next_open():
    bars = pl.DataFrame({"open": [10.0, 11.0, 12.0, 11.0, 13.0, 9.0]})

    # t=0: 11 -> 11 flat, t=1: 12 -> 13 up, t=2: 11 -> 9 down, t>=3 undefined.
    assert up_base_rate(bars, horizon=2) == pytest.approx(1 / 3)


def credit_client(*responses: tuple[str, dict]) -> httpx.Client:
    queue = list(responses)

    def handler(req: httpx.Request) -> httpx.Response:
        body, headers = queue.pop(0)
        return httpx.Response(200, text=body, headers=headers)

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_request_sleeps_to_next_minute_when_credits_run_out():
    sleeps = []
    client = credit_client((fixture_body("2024-01-01"), {"api-credits-left": "0"}))

    payload, _ = request(
        client,
        KEY,
        "SPY",
        date(2024, 1, 1),
        None,
        "all",
        sleeps.append,
        clock=lambda: 1_800_000_030.5,
    )

    assert payload["values"][0]["datetime"] == "2024-01-02"
    assert sleeps == [31.5], "30.5s into the minute waits to the boundary plus 2s"


def test_request_does_not_sleep_with_credits_left():
    sleeps = []
    client = credit_client((fixture_body("2024-01-01"), {"api-credits-left": "5"}))

    payload, _ = request(client, KEY, "SPY", date(2024, 1, 1), None, "all", sleeps.append)

    assert payload["status"] == "ok"
    assert sleeps == []


def test_request_retries_once_after_rate_limit():
    sleeps = []
    limited = json.dumps({"code": 429, "message": "out of credits", "status": "error"})
    client = credit_client((limited, {}), (fixture_body("2024-01-01"), {"api-credits-left": "3"}))

    payload, _ = request(client, KEY, "SPY", date(2024, 1, 1), None, "all", sleeps.append)

    assert payload["status"] == "ok"
    assert sleeps == [60.0]


FIXTURE_HOUR = replace(HOUR, last=date(2024, 1, 4))
HOURLY_BODY = (FIXTURES / "spy_1h.json").read_text()


def hourly_client(seen: list[dict] | None = None) -> httpx.Client:
    def handler(req: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append({k: v for k, v in req.url.params.items() if k != "apikey"})
        return httpx.Response(200, text=HOURLY_BODY, headers={"api-credits-left": "7"})

    return httpx.Client(transport=httpx.MockTransport(handler))


def write_daily(root: Path, opens: list[float], closes: list[float]) -> None:
    days = [date(2024, 1, 3), date(2024, 1, 4)][: len(opens)]
    market = root / "market"
    market.mkdir(parents=True, exist_ok=True)
    pl.DataFrame({"date": days, "open": opens, "close": closes}).write_parquet(
        market / "SPY.parquet"
    )


def hourly_bars() -> pl.DataFrame:
    return regular_hours(parse_response(json.loads(HOURLY_BODY), HOUR))


def test_hourly_fetch_keeps_regular_hours_from_the_first_full_session(tmp_path):
    write_daily(tmp_path, [100.0, 110.55], [107.0, 117.0])
    seen = []

    result = fetch_symbol(
        hourly_client(seen), KEY, "SPY", tmp_path, NOW, None, no_sleep, FIXTURE_HOUR
    )

    assert seen == [
        {
            "symbol": "SPY",
            "interval": "1h",
            "adjust": "all",
            "order": "asc",
            "outputsize": "5000",
            "end_date": "2026-10-10",
        }
    ]
    assert (result.rows, result.first, result.last, result.changed) == (
        14,
        date(2024, 1, 3),
        date(2024, 1, 4),
        True,
    )
    assert result.gap == pytest.approx(0.55 / 110.55)

    bars = pl.read_parquet(tmp_path / "market" / "1h" / "SPY.parquet")
    assert bars.columns == ["time", "date", "open", "high", "low", "close", "volume"]
    assert bars.row(0) == (
        datetime(2024, 1, 3, 9, 30),
        date(2024, 1, 3),
        100.0,
        101.5,
        99.5,
        101.0,
        1000,
    )
    assert bars["time"].dt.strftime("%H:%M").unique(maintain_order=True).to_list() == [
        "09:30",
        "10:30",
        "11:30",
        "12:30",
        "13:30",
        "14:30",
        "15:30",
    ]

    raw_name = hashlib.sha256(HOURLY_BODY.encode()).hexdigest() + ".json.gz"
    manifest = json.loads((tmp_path / "market" / "1h" / "SPY.manifest.json").read_text())
    assert manifest == {
        "symbol": "SPY",
        "adjust": "all",
        "ranges": [[None, "2026-10-10"]],
        "fetched_at": "2026-10-12T10:00:00+00:00",
        "rows": 14,
        "first": "2024-01-03T09:30:00",
        "last": "2024-01-04T15:30:00",
        "sha256": hashlib.sha256((tmp_path / "market/1h/SPY.parquet").read_bytes()).hexdigest(),
        "raw": [raw_name],
    }
    assert sorted(snapshot(tmp_path)) == [
        "market/1h/SPY.manifest.json",
        "market/1h/SPY.parquet",
        "market/SPY.parquet",
        f"raw/1h/SPY/{raw_name}",
    ]


def test_second_hourly_fetch_changes_no_file(tmp_path):
    write_daily(tmp_path, [100.0, 110.0], [107.0, 117.0])
    fetch_symbol(hourly_client(), KEY, "SPY", tmp_path, NOW, None, no_sleep, FIXTURE_HOUR)
    before = snapshot(tmp_path)

    later = datetime(2026, 10, 13, 10, 0, tzinfo=UTC)
    result = fetch_symbol(
        hourly_client(), KEY, "SPY", tmp_path, later, None, no_sleep, FIXTURE_HOUR
    )

    assert result.changed is False
    assert snapshot(tmp_path) == before, "bytes and mtimes of every file are unchanged"


def test_validate_rejects_hourly_time_missing_against_reference():
    bars = hourly_bars()
    validate("QQQ", bars, bars["time"], "time")

    gappy = bars.filter(pl.col("time") != datetime(2024, 1, 3, 12, 30))
    with pytest.raises(DataError) as err:
        validate("QQQ", gappy, bars["time"], "time")
    assert str(err.value) == (
        "QQQ 2024-01-03 12:30:00: times differ from SPY in "
        "2024-01-03 09:30:00..2024-01-04 15:30:00 "
        "(1 missing, e.g. 2024-01-03 12:30:00; 0 extra, e.g. none)"
    )


def test_hourly_fetch_rejects_a_session_far_from_the_daily_bar(tmp_path):
    write_daily(tmp_path, [100.0, 110.0], [107.0, 120.0])

    with pytest.raises(DataError) as err:
        fetch_symbol(hourly_client(), KEY, "SPY", tmp_path, NOW, None, no_sleep, FIXTURE_HOUR)
    assert str(err.value) == (
        "SPY 2024-01-04: hourly open or close is 2.50% from the daily bar, over 2%"
    )
    raw_name = hashlib.sha256(HOURLY_BODY.encode()).hexdigest() + ".json.gz"
    assert sorted(snapshot(tmp_path)) == [
        "market/SPY.parquet",
        f"raw/1h/SPY/{raw_name}",
    ], "the response is archived and no hourly snapshot is written"


def test_hourly_fetch_rejects_a_session_missing_from_the_daily_bars(tmp_path):
    write_daily(tmp_path, [100.0], [107.0])

    with pytest.raises(DataError) as err:
        fetch_symbol(hourly_client(), KEY, "SPY", tmp_path, NOW, None, no_sleep, FIXTURE_HOUR)
    assert str(err.value) == "SPY 2024-01-04: session missing from the daily snapshot (1 rows)"


def test_hourly_fetch_needs_a_daily_snapshot(tmp_path):
    with pytest.raises(DataError) as err:
        fetch_symbol(hourly_client(), KEY, "SPY", tmp_path, NOW, None, no_sleep, FIXTURE_HOUR)
    assert str(err.value) == "SPY: no daily snapshot to check hourly sessions against"


def test_hourly_fetch_rejects_an_unexpected_last_session(tmp_path):
    write_daily(tmp_path, [100.0, 110.0], [107.0, 117.0])
    size = replace(HOUR, last=date(2024, 1, 5))

    with pytest.raises(DataError) as err:
        fetch_symbol(hourly_client(), KEY, "SPY", tmp_path, NOW, None, no_sleep, size)
    assert str(err.value) == "SPY: last session 2024-01-04, expected 2024-01-05"


def test_regular_hours_stops_a_half_day_at_its_close():
    times = [datetime(2024, 11, 29, h, 30) for h in (9, 10, 11, 12, 15)]
    bars = pl.DataFrame({"time": times, "date": [date(2024, 11, 29)] * 5})

    kept = regular_hours(bars)

    assert kept["time"].dt.strftime("%H:%M").to_list() == ["09:30", "10:30", "11:30", "12:30"]
