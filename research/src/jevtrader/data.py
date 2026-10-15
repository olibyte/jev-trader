"""Twelve Data bars: fetch, archive, validate, and snapshot to Parquet."""

from __future__ import annotations

import gzip
import hashlib
import io
import json
import os
import tempfile
import time
from collections.abc import Callable
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
OPEN, CLOSE = clock_time(9, 30), clock_time(16, 0)
# SPY's worst gap in its first hourly fetch was 1.05%, its 2025-04-09 close. Unadjusted prices
# or a session shifted by a day still miss by more than 2%.
GAP_TOLERANCE = 0.02
# The worst hourly close outside its own high and low was 0.014%, about half a cent.
WICK_TOLERANCE = 0.0005
MAX_FILLED = 7  # one session of hourly bars
RATE_LIMIT_WAIT = 60.0
MINUTE_MARGIN = 2.0

Adjust = Literal["all", "none"]
Window = tuple[date | None, date | None]


@dataclass(frozen=True)
class BarSize:
    interval: Literal["1day", "1h"]  # the Twelve Data interval and the `jt fetch --bars` value
    windows: tuple[Window, ...]
    # True: a window is the last OUTPUTSIZE bars. False: a full response may be cut off.
    capped: bool
    folder: str  # under data/market/ and data/raw/
    # Bars carry `time`, keep regular hours, and are checked against the daily snapshot.
    intraday: bool
    last: date | None = None  # the session the snapshot must end on

    @property
    def key(self) -> Literal["date", "time"]:
        return "time" if self.intraday else "date"


DAY = BarSize("1day", RANGES, capped=False, folder="", intraday=False)
# 2026-10-10 is a Saturday, so the window ends on Friday whether or not end_date includes its day.
HOUR = BarSize(
    "1h",
    ((None, date(2026, 10, 10)),),
    capped=True,
    folder="1h",
    intraday=True,
    last=date(2026, 10, 9),
)
BAR_SIZES = {b.interval: b for b in (DAY, HOUR)}

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
    ranges: list[tuple[str | None, str | None]]
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
    up_base_rate: float | None  # daily only: the horizon counts sessions
    changed: bool
    gap: float | None  # the largest session gap against the daily snapshot, intraday only
    widened: int = 0  # bars whose high or low moved to cover the open and close
    filled: int = 0  # flat bars added for SPY's times with no bar


# Pure core


def parse_response(payload: dict, size: BarSize = DAY) -> pl.DataFrame:
    """Raw Twelve Data JSON to Bars. Raises DataError on status != "ok".

    Intraday bars carry `time`, the New York clock time, and `date`, its session.
    """
    if payload.get("status") != "ok":
        raise DataError(f"Twelve Data error {payload.get('code')}: {payload.get('message')}")
    schema = {"time": pl.Datetime("us"), **BARS_SCHEMA} if size.intraday else BARS_SCHEMA
    values = payload.get("values") or []
    if not values:
        return pl.DataFrame(schema=schema)
    raw = pl.DataFrame(values, schema={k: pl.String for k in values[0]})
    if size.intraday:
        when = pl.col("datetime").str.to_datetime("%Y-%m-%d %H:%M:%S", time_unit="us")
        keys = (when.alias("time"), when.dt.date().alias("date"))
    else:
        keys = (pl.col("datetime").str.to_date("%Y-%m-%d").alias("date"),)
    return raw.select(
        *keys,
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


def regular_hours(bars: pl.DataFrame) -> pl.DataFrame:
    """Keep each session's unbroken run of hourly bars from 09:30 to 16:00.

    That drops the partial first session of a capped window and the flat 15:30 bar that some
    half days carry after their 13:00 close.
    """
    clock = pl.col("time").dt.time()
    minutes = pl.col("time").dt.hour().cast(pl.Int32) * 60 + pl.col("time").dt.minute()
    slot = OPEN.hour * 60 + OPEN.minute + 60 * pl.int_range(pl.len()).over("date")
    inside = bars.filter((clock >= OPEN) & (clock < CLOSE))
    return inside.filter(minutes == slot)


def widen_wicks(bars: pl.DataFrame) -> tuple[pl.DataFrame, int]:
    """Move a high up or a low down to the open or close when it misses by WICK_TOLERANCE or less.

    A few hourly bars close a fraction of a cent outside their own range. A larger miss stays for
    `validate` to reject.
    """
    o, h, lo, c = (pl.col(x) for x in ("open", "high", "low", "close"))
    top, bottom = pl.max_horizontal(o, c), pl.min_horizontal(o, c)
    up = (top > h) & (top <= h * (1 + WICK_TOLERANCE))
    down = (bottom < lo) & (bottom >= lo * (1 - WICK_TOLERANCE))
    widened = bars.select((up | down).sum()).item()
    fixed = bars.with_columns(
        pl.when(up).then(top).otherwise(h).alias("high"),
        pl.when(down).then(bottom).otherwise(lo).alias("low"),
    )
    return fixed, widened


def fill_quiet_hours(bars: pl.DataFrame, reference: pl.Series) -> tuple[pl.DataFrame, int]:
    """Add a flat bar at the last close for each reference time inside the bars that has none.

    BIL printed no hourly bar after 09:30 on 2024-10-02. More than MAX_FILLED missing times stay
    for `validate` to report.
    """
    grid = pl.DataFrame({"time": reference}).filter(
        pl.col("time").is_between(bars["time"].min(), bars["time"].max())
    )
    missing = grid.join(bars.select("time"), on="time", how="anti")
    if missing.height == 0 or missing.height > MAX_FILLED:
        return bars, 0
    added = missing.with_columns(pl.col("time").dt.date().alias("date"))
    close = pl.col("close").forward_fill()
    filled = (
        pl.concat([bars, added], how="diagonal")
        .sort("time")
        .with_columns(close)
        .with_columns(
            *(pl.col(x).fill_null(pl.col("close")) for x in ("open", "high", "low")),
            pl.col("volume").fill_null(0),
        )
        .select(bars.columns)
    )
    return filled, missing.height


def validate(
    symbol: str,
    bars: pl.DataFrame,
    reference: pl.Series | None,
    key: Literal["date", "time"] = "date",
) -> None:
    """OHLC invariants, duplicate keys, keys against SPY, overnight moves over 40%."""
    if bars.height == 0:
        raise DataError(f"{symbol}: no bars")
    o, h, lo, c = (pl.col(x) for x in ("open", "high", "low", "close"))
    rules = (
        (pl.min_horizontal(o, h, lo, c) <= 0, "price <= 0"),
        (lo > pl.min_horizontal(o, c), "low > min(open, close)"),
        (h < pl.max_horizontal(o, c), "high < max(open, close)"),
        (pl.col(key).is_duplicated(), f"duplicate {key}"),
        ((o / c.shift(1) - 1).abs() > MAX_OVERNIGHT_MOVE, "overnight move over 40%"),
    )
    problems = []
    for mask, rule in rules:
        bad = bars.filter(mask)[key]
        if bad.len():
            problems.append(f"{symbol} {bad[0]}: {rule} ({bad.len()} rows)")

    if reference is not None:
        first, last = bars[key].min(), bars[key].max()
        own = set(bars[key].to_list())
        ref = {d for d in reference.to_list() if first <= d <= last}
        missing, extra = sorted(ref - own), sorted(own - ref)
        if missing or extra:
            where = (missing or extra)[0]
            what = {"date": "sessions", "time": "times"}[key]
            problems.append(
                f"{symbol} {where}: {what} differ from SPY in {first}..{last} "
                f"({len(missing)} missing, e.g. {_examples(missing)}; "
                f"{len(extra)} extra, e.g. {_examples(extra)})"
            )
    if problems:
        raise DataError("\n".join(problems))


def _examples(keys: list) -> str:
    return ", ".join(str(k) for k in keys[:3]) or "none"


def session_gap(symbol: str, hourly: pl.DataFrame, daily: pl.DataFrame) -> float:
    """Largest relative gap of each session's first open and last close from its daily bar."""
    sessions = (
        hourly.sort("time")
        .group_by("date", maintain_order=True)
        .agg(pl.col("open").first(), pl.col("close").last())
    )
    joined = sessions.join(
        daily.select("date", "open", "close"), on="date", how="left", suffix="_day"
    )
    missing = joined.filter(pl.col("open_day").is_null())["date"]
    if missing.len():
        raise DataError(
            f"{symbol} {missing[0]}: session missing from the daily snapshot ({missing.len()} rows)"
        )
    gaps = joined.select(
        "date",
        pl.max_horizontal(
            (pl.col("open") / pl.col("open_day") - 1).abs(),
            (pl.col("close") / pl.col("close_day") - 1).abs(),
        ).alias("gap"),
    ).sort("gap", descending=True)
    worst, gap = gaps.row(0)
    if gap > GAP_TOLERANCE:
        raise DataError(
            f"{symbol} {worst}: hourly open or close is {gap:.2%} from the daily bar, "
            f"over {GAP_TOLERANCE:.0%}"
        )
    return gap


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
    start: date | None,
    end: date | None,
    adjust: Adjust,
    sleep: Callable[[float], None],
    clock: Callable[[], float] = time.time,
    interval: str = "1day",
) -> tuple[dict, str]:
    """One time_series call. Returns (payload, key-stripped body). Waits when credits run out."""
    params = {
        "symbol": symbol,
        "interval": interval,
        "adjust": adjust,
        "order": "asc",
        "outputsize": OUTPUTSIZE,
        "apikey": key,
    }
    if start is not None:
        params["start_date"] = start.isoformat()
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
    reference: pl.Series | None,
    sleep: Callable[[float], None],
    size: BarSize = DAY,
) -> FetchResult:
    """Fetch every window, archive raw, validate, write Parquet and manifest only on change.

    Each response is archived before parsing, so a failed check keeps what the credits bought.
    """
    raw_dir = data_dir / "raw" / size.folder / symbol
    frames, raw_names = [], []
    for start, end in size.windows:
        payload, body = request(
            client, key, symbol, start, end, "all", sleep, interval=size.interval
        )
        text = body.encode()
        name = f"{hashlib.sha256(text).hexdigest()}.json.gz"
        if not (raw_dir / name).exists():
            atomic_write(raw_dir / name, gzip.compress(text, mtime=0))
        raw_names.append(name)
        frame = parse_response(payload, size)
        if not size.capped and frame.height >= OUTPUTSIZE:
            raise DataError(
                f"{symbol}: {start}..{end} hit the {OUTPUTSIZE}-bar cap, may be cut off"
            )
        frames.append(frame)

    bars = closed_bars(pl.concat(frames).unique().sort(size.key), now)
    gap, widened, filled = None, 0, 0
    if size.intraday:
        bars, widened = widen_wicks(regular_hours(bars))
        if reference is not None:
            bars, filled = fill_quiet_hours(bars, reference)
        if size.last is not None and bars.height and bars["date"][-1] != size.last:
            raise DataError(f"{symbol}: last session {bars['date'][-1]}, expected {size.last}")
    validate(symbol, bars, reference, size.key)
    if size.intraday:
        daily_path = data_dir / "market" / f"{symbol}.parquet"
        if not daily_path.exists():
            raise DataError(f"{symbol}: no daily snapshot to check hourly sessions against")
        gap = session_gap(symbol, bars, pl.read_parquet(daily_path))
    bars = bars.rechunk()

    buffer = io.BytesIO()
    bars.write_parquet(buffer)
    parquet = buffer.getvalue()
    digest = hashlib.sha256(parquet).hexdigest()

    market = data_dir / "market" / size.folder
    parquet_path = market / f"{symbol}.parquet"
    manifest_path = market / f"{symbol}.manifest.json"
    changed = not (
        _manifest_sha(manifest_path) == digest
        and parquet_path.exists()
        and hashlib.sha256(parquet_path.read_bytes()).hexdigest() == digest
    )

    if changed:
        atomic_write(parquet_path, parquet)
        manifest = Manifest(
            symbol=symbol,
            adjust="all",
            ranges=[(_iso(s), _iso(e)) for s, e in size.windows],
            fetched_at=now.isoformat(),
            rows=bars.height,
            first=bars[size.key][0].isoformat(),
            last=bars[size.key][-1].isoformat(),
            sha256=digest,
            raw=raw_names,
        )
        text = json.dumps(asdict(manifest), sort_keys=True, indent=2) + "\n"
        atomic_write(manifest_path, text.encode())

    return FetchResult(
        symbol=symbol,
        rows=bars.height,
        first=bars["date"][0],
        last=bars["date"][-1],
        up_base_rate=None if size.intraday else up_base_rate(bars),
        changed=changed,
        gap=gap,
        widened=widened,
        filled=filled,
    )


def _iso(day: date | None) -> str | None:
    return day.isoformat() if day else None


def _manifest_sha(path: Path) -> str | None:
    try:
        return json.loads(path.read_text())["sha256"]
    except OSError, ValueError, KeyError:
        return None


def atomic_write(path: Path, data: bytes) -> None:
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
