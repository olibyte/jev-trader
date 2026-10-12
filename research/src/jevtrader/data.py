"""Twelve Data daily bars: fetch, archive, validate, and snapshot to Parquet."""

from __future__ import annotations

import gzip
import hashlib
import io
import json
import os
import tempfile
import time
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass
from datetime import date, datetime
from datetime import time as clock_time
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo

import httpx
import polars as pl

REPO_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = REPO_ROOT / "data"
API_URL = "https://api.twelvedata.com/time_series"

# SPY first: every other symbol's sessions are checked against it.
UNIVERSE = (
    "SPY",
    "QQQ",
    "IWM",
    "DIA",
    "XLB",
    "XLE",
    "XLF",
    "XLI",
    "XLK",
    "XLP",
    "XLU",
    "XLV",
    "XLY",
    "BIL",
)

# Each call returns at most 5,000 bars, so two ranges cover the full history.
RANGES = ((date(1990, 1, 1), date(2009, 12, 31)), (date(2010, 1, 1), None))
OUTPUTSIZE = 5000

NEW_YORK = ZoneInfo("America/New_York")
# The regular session closes at 16:00. Wait until 20:00 so the provider has settled the bar.
SETTLED = clock_time(20, 0)
MAX_OVERNIGHT_MOVE = 0.40
RATE_LIMIT_WAIT = 60.0
MINUTE_MARGIN = 2.0

Adjust = Literal["all", "none"]
Range = tuple[date, date | None]

BARS_SCHEMA = {
    "date": pl.Date,
    "open": pl.Float64,
    "high": pl.Float64,
    "low": pl.Float64,
    "close": pl.Float64,
    "volume": pl.Int64,
}


class DataError(Exception):
    """A response or a bar series that fails validation. The previous snapshot stays."""


@dataclass(frozen=True)
class Manifest:  # data/market/{symbol}.manifest.json
    symbol: str
    adjust: Adjust
    ranges: list[tuple[str, str | None]]
    fetched_at: str
    rows: int
    first: str
    last: str
    sha256: str  # of the Parquet bytes
    raw: list[str]  # archive file names under data/raw/{symbol}/


@dataclass(frozen=True)
class FetchResult:
    symbol: str
    rows: int
    first: date
    last: date
    up_base_rate: float
    changed: bool


# Pure core


def parse_response(payload: dict) -> pl.DataFrame:
    """Raw Twelve Data JSON to Bars. Raises DataError on status != "ok"."""
    if payload.get("status") != "ok":
        raise DataError(f"Twelve Data error {payload.get('code')}: {payload.get('message')}")
    values = payload.get("values") or []
    if not values:
        return pl.DataFrame(schema=BARS_SCHEMA)
    raw = pl.DataFrame(values, schema={k: pl.String for k in values[0]})
    return raw.select(
        pl.col("datetime").str.to_date("%Y-%m-%d").alias("date"),
        *(pl.col(c).cast(pl.Float64) for c in ("open", "high", "low", "close")),
        pl.col("volume").cast(pl.Int64),
    )


def closed_bars(bars: pl.DataFrame, now: datetime) -> pl.DataFrame:
    """Drop a bar whose session has not closed in America/New_York at `now`."""
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    ny = now.astimezone(NEW_YORK)
    today = ny.date()
    if ny.time() >= SETTLED:
        return bars.filter(pl.col("date") <= today)
    return bars.filter(pl.col("date") < today)


def validate(symbol: str, bars: pl.DataFrame, reference_dates: pl.Series | None) -> None:
    """OHLC invariants, duplicate dates, sessions against SPY, overnight moves over 40%."""
    if bars.height == 0:
        raise DataError(f"{symbol}: no bars")
    o, h, lo, c = (pl.col(x) for x in ("open", "high", "low", "close"))
    rules = (
        (pl.min_horizontal(o, h, lo, c) <= 0, "price <= 0"),
        (lo > pl.min_horizontal(o, c), "low > min(open, close)"),
        (h < pl.max_horizontal(o, c), "high < max(open, close)"),
        (pl.col("date").is_duplicated(), "duplicate date"),
        ((o / c.shift(1) - 1).abs() > MAX_OVERNIGHT_MOVE, "overnight move over 40%"),
    )
    problems = []
    for mask, rule in rules:
        bad = bars.filter(mask)["date"]
        if bad.len():
            problems.append(f"{symbol} {bad[0]}: {rule} ({bad.len()} rows)")

    if reference_dates is not None:
        first, last = bars["date"].min(), bars["date"].max()
        own = set(bars["date"].to_list())
        ref = {d for d in reference_dates.to_list() if first <= d <= last}
        missing, extra = sorted(ref - own), sorted(own - ref)
        if missing or extra:
            where = (missing or extra)[0]
            problems.append(
                f"{symbol} {where}: sessions differ from SPY in {first}..{last} "
                f"({len(missing)} missing, e.g. {_examples(missing)}; "
                f"{len(extra)} extra, e.g. {_examples(extra)})"
            )
    if problems:
        raise DataError("\n".join(problems))


def _examples(dates: list[date]) -> str:
    return ", ".join(str(d) for d in dates[:3]) or "none"


def forward_return(horizon: int = 20) -> pl.Expr:
    """Enter at the next open, exit `horizon` sessions later: open[t+1+horizon] / open[t+1] - 1."""
    return pl.col("open").shift(-(horizon + 1)) / pl.col("open").shift(-1) - 1


def up_base_rate(bars: pl.DataFrame, horizon: int = 20) -> float:
    """Share of days t where open[t+1+horizon] > open[t+1]."""
    up = bars.select((forward_return(horizon) > 0).alias("up"))["up"].drop_nulls()
    return float(up.mean())


def strip_key(text: str, key: str) -> str:
    return text.replace(key, "") if key else text


# I/O shell


def request(
    client: httpx.Client,
    key: str,
    symbol: str,
    start: date,
    end: date | None,
    adjust: Adjust,
    sleep: Callable[[float], None],
    clock: Callable[[], float] = time.time,
) -> tuple[dict, str]:
    """One time_series call. Returns (payload, key-stripped body). Waits when credits run out."""
    params = {
        "symbol": symbol,
        "interval": "1day",
        "adjust": adjust,
        "order": "asc",
        "start_date": start.isoformat(),
        "outputsize": OUTPUTSIZE,
        "apikey": key,
    }
    if end is not None:
        params["end_date"] = end.isoformat()

    for attempt in range(2):
        try:
            response = client.get(API_URL, params=params)
        except httpx.HTTPError as e:
            # `from None`: the chained httpx error carries the request URL, which holds the key.
            raise DataError(f"{symbol}: {type(e).__name__} calling Twelve Data") from None
        body = strip_key(response.text, key)
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            raise DataError(f"{symbol}: HTTP {response.status_code} with a non-JSON body") from None

        if payload.get("code") == 429 or response.status_code == 429:
            if attempt == 0:
                sleep(RATE_LIMIT_WAIT)
                continue
            raise DataError(f"{symbol}: rate limited twice: {payload.get('message')}")

        if response.headers.get("api-credits-left") == "0":
            now = clock()
            sleep(60 - now % 60 + MINUTE_MARGIN)
        return payload, body
    raise AssertionError("unreachable")


def fetch_symbol(
    client: httpx.Client,
    key: str,
    symbol: str,
    data_dir: Path,
    now: datetime,
    reference_dates: pl.Series | None,
    sleep: Callable[[float], None],
    ranges: Sequence[Range] = RANGES,
) -> FetchResult:
    """Fetch both ranges, archive raw, validate, write Parquet and manifest only on change."""
    frames, bodies = [], []
    for start, end in ranges:
        payload, body = request(client, key, symbol, start, end, "all", sleep)
        frame = parse_response(payload)
        if frame.height >= OUTPUTSIZE:
            raise DataError(
                f"{symbol}: {start}..{end} hit the {OUTPUTSIZE}-bar cap, may be cut off"
            )
        frames.append(frame)
        bodies.append(body)

    bars = closed_bars(pl.concat(frames).unique().sort("date"), now)
    validate(symbol, bars, reference_dates)
    bars = bars.rechunk()

    buffer = io.BytesIO()
    bars.write_parquet(buffer)
    parquet = buffer.getvalue()
    digest = hashlib.sha256(parquet).hexdigest()

    market = data_dir / "market"
    parquet_path = market / f"{symbol}.parquet"
    manifest_path = market / f"{symbol}.manifest.json"
    changed = not (
        _manifest_sha(manifest_path) == digest
        and parquet_path.exists()
        and hashlib.sha256(parquet_path.read_bytes()).hexdigest() == digest
    )

    if changed:
        raw_dir = data_dir / "raw" / symbol
        raw_names = []
        for body in bodies:
            text = body.encode()
            name = f"{hashlib.sha256(text).hexdigest()}.json.gz"
            if not (raw_dir / name).exists():
                _atomic_write(raw_dir / name, gzip.compress(text, mtime=0))
            raw_names.append(name)
        _atomic_write(parquet_path, parquet)
        manifest = Manifest(
            symbol=symbol,
            adjust="all",
            ranges=[(s.isoformat(), e.isoformat() if e else None) for s, e in ranges],
            fetched_at=now.isoformat(),
            rows=bars.height,
            first=bars["date"][0].isoformat(),
            last=bars["date"][-1].isoformat(),
            sha256=digest,
            raw=raw_names,
        )
        text = json.dumps(asdict(manifest), sort_keys=True, indent=2) + "\n"
        _atomic_write(manifest_path, text.encode())

    return FetchResult(
        symbol=symbol,
        rows=bars.height,
        first=bars["date"][0],
        last=bars["date"][-1],
        up_base_rate=up_base_rate(bars),
        changed=changed,
    )


def _manifest_sha(path: Path) -> str | None:
    try:
        return json.loads(path.read_text())["sha256"]
    except OSError, ValueError, KeyError:
        return None


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix=f".{path.name}.", delete=False) as f:
        f.write(data)
    os.replace(f.name, path)


def adjust_check(client: httpx.Client, key: str, sleep: Callable[[float], None]) -> float:
    """Max |open_adj/open_raw - close_adj/close_raw| over SPY's history."""
    series = {}
    for adjust in ("all", "none"):
        frames = [
            parse_response(request(client, key, "SPY", start, end, adjust, sleep)[0])
            for start, end in RANGES
        ]
        series[adjust] = pl.concat(frames).select("date", "open", "close")
    joined = series["all"].join(series["none"], on="date", suffix="_raw")
    gap = (pl.col("open") / pl.col("open_raw") - pl.col("close") / pl.col("close_raw")).abs()
    return float(joined.select(gap.max()).item())
