"""`jt` command line: the boundary that reads the key, the clock, and the network."""

from __future__ import annotations

import argparse
import sys
import time
from datetime import UTC, datetime

import httpx
import polars as pl
from dotenv import dotenv_values

from jevtrader.data import DATA_DIR, REPO_ROOT, UNIVERSE, DataError, adjust_check, fetch_symbol

ROW = "{:<6}{:>7}  {:<12}{:<12}{:>8}  {}"


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(line_buffering=True)
    parser = argparse.ArgumentParser(prog="jt")
    commands = parser.add_subparsers(dest="command", required=True)
    fetch = commands.add_parser("fetch", help="fetch daily bars into data/market/")
    fetch.add_argument("symbols", nargs="*", metavar="SYMBOL", help="default: the full universe")
    commands.add_parser("adjust-check", help="compare SPY adjusted and raw open/close ratios")
    args = parser.parse_args(argv)

    key = dotenv_values(REPO_ROOT / ".env").get("TWELVE_DATA_API_KEY")
    if not key:
        print(f"TWELVE_DATA_API_KEY is not set in {REPO_ROOT / '.env'}", file=sys.stderr)
        return 2

    with httpx.Client(timeout=60) as client:
        if args.command == "adjust-check":
            gap = adjust_check(client, key, time.sleep)
            print(f"max |open_all/open_none - close_all/close_none|: {gap:.3e}")
            return 0
        return fetch_all(client, key, [s.upper() for s in args.symbols] or list(UNIVERSE))


def fetch_all(client: httpx.Client, key: str, symbols: list[str]) -> int:
    symbols = list(dict.fromkeys(symbols))
    spy_path = DATA_DIR / "market" / "SPY.parquet"
    if "SPY" in symbols or not spy_path.exists():
        symbols = ["SPY", *(s for s in symbols if s != "SPY")]

    print(ROW.format("symbol", "rows", "first", "last", "up_rate", "status"))
    failed = False
    for symbol in symbols:
        reference = None
        if symbol != "SPY":
            if not spy_path.exists():
                print(f"{symbol:<6}error: no SPY snapshot to check sessions against")
                failed = True
                continue
            reference = pl.read_parquet(spy_path, columns=["date"])["date"]
        try:
            r = fetch_symbol(
                client, key, symbol, DATA_DIR, datetime.now(UTC), reference, time.sleep
            )
        except DataError as e:
            print(f"{symbol:<6}error: {e}")
            failed = True
            continue
        status = "changed" if r.changed else "unchanged"
        print(
            ROW.format(symbol, r.rows, str(r.first), str(r.last), f"{r.up_base_rate:.3f}", status)
        )
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
