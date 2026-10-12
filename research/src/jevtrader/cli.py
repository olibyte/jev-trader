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
from jevtrader.evaluate import BLOCK, REPS, SHRINK_K, block_bootstrap_auc, empirical_table
from jevtrader.states import (
    ALL_STATES,
    DIMENSIONS,
    STATE_VERSION,
    STUDY,
    state_table,
    write_states,
)

ROW = "{:<6}{:>7}  {:<12}{:<12}{:>8}  {}"


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(line_buffering=True)
    parser = argparse.ArgumentParser(prog="jt")
    commands = parser.add_subparsers(dest="command", required=True)
    fetch = commands.add_parser("fetch", help="fetch daily bars into data/market/")
    fetch.add_argument("symbols", nargs="*", metavar="SYMBOL", help="default: the full universe")
    commands.add_parser("adjust-check", help="compare SPY adjusted and raw open/close ratios")
    commands.add_parser("states", help="classify each study session into data/states/")
    commands.add_parser("ceiling", help="state census and the validate AUC of empirical_table")
    args = parser.parse_args(argv)
    if args.command == "states":
        return states()
    if args.command == "ceiling":
        return ceiling()
    return online(args)


def online(args: argparse.Namespace) -> int:
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


def states() -> int:
    missing = [s for s in STUDY if not (DATA_DIR / "market" / f"{s}.parquet").exists()]
    if missing:
        print(f"no bars for {', '.join(missing)}, run `jt fetch` first", file=sys.stderr)
        return 2
    print(ROW.format("symbol", "rows", "first", "last", "defined", "states"))
    for symbol in STUDY:
        bars, rows = write_states(symbol, DATA_DIR)
        first, last = str(bars["date"][0]), str(bars["date"][-1])
        print(
            ROW.format(symbol, bars.height, first, last, rows.height, rows["state_key"].n_unique())
        )
    return 0


def ceiling() -> int:
    paths = [DATA_DIR / "states" / f"{s}.parquet" for s in STUDY]
    if not all(p.exists() for p in paths):
        print("no state rows, run `jt states` first", file=sys.stderr)
        return 2
    scan = pl.scan_parquet(paths)
    holdout = scan.filter(pl.col("split") == "holdout").select(pl.len()).collect().item()
    dev = scan.filter(pl.col("split") != "holdout").collect()
    if set(dev["state_version"]) != {STATE_VERSION}:
        print(f"state rows are not {STATE_VERSION}, run `jt states` first", file=sys.stderr)
        return 2

    print(f"{'split':<10}{'rows':>7}{'labelled':>10}{'base_up':>9}{'distinct_states':>17}")
    for split in ("warmup", "fit", "validate"):
        part = dev.filter(pl.col("split") == split)
        up = part["up_20"].drop_nulls()
        distinct = part["state_key"].n_unique()
        print(f"{split:<10}{part.height:>7}{up.len():>10}{up.mean():>9.3f}{distinct:>17}")
    print(f"{'holdout':<10}{holdout:>7}  row count only, holdout labels stay unread")

    fit = dev.filter(pl.col("split") == "fit")
    table = empirical_table(fit)
    validate = dev.filter(pl.col("split") == "validate", pl.col("up_20").is_not_null()).join(
        table, on="state_key", maintain_order="left"
    )
    seen = table.filter(pl.col("n_dev") > 0).height
    covered, unseen = (validate["n_dev"] >= 30).mean(), (validate["n_dev"] == 0).mean()
    print(
        f"coverage: validate rows whose state has n_fit >= 30: {covered:.1%}"
        f"; states with labelled fit rows: {seen}/{len(ALL_STATES)}"
        f"; validate rows in states unseen in fit: {unseen:.1%}"
    )

    print("fit level shares")
    named = fit.join(state_table(), on="state_key")
    for name, levels in DIMENSIONS.items():
        counts = dict(named[name].cast(pl.String).value_counts().iter_rows())
        shares = "  ".join(f"{level} {counts.get(level, 0) / named.height:.1%}" for level in levels)
        print(f"  {name:<16}{shares}")

    point, lo, hi = block_bootstrap_auc(
        validate["date"].to_numpy(),
        validate["empirical_p"].to_numpy(),
        validate["up_20"].to_numpy(),
    )
    print(
        f"empirical_table (k={SHRINK_K}) validate AUC {point:.3f}  95% CI [{lo:.3f}, {hi:.3f}]"
        f"  ({REPS} reps, {BLOCK}-session blocks, seed 0)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
