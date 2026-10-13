"""`jt` command line: the boundary that reads the key, the clock, and the network."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
import tomllib
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path

import httpx
import numpy as np
import polars as pl
from dotenv import dotenv_values

from jevtrader.catalog import decisions as arena_decisions
from jevtrader.catalog import reconcile, refusals
from jevtrader.data import (
    DATA_DIR,
    REPO_ROOT,
    UNIVERSE,
    DataError,
    adjust_check,
    atomic_write,
    fetch_symbol,
)
from jevtrader.evaluate import (
    ARMS,
    BASELINE,
    BLOCK,
    CANDIDATE,
    COST_BPS,
    COSTS_BPS,
    HOLDOUT_PATH,
    HOLDOUT_RUN_PATH,
    LEVEL,
    PREREG_PATH,
    REPS,
    SHRINK_K,
    ArmReport,
    HoldoutRun,
    Interval,
    arm_reports,
    block_bootstrap_auc,
    empirical_table,
    holdout_blocks,
    holdout_result,
    n_blocks,
    open_returns,
    power,
    prereg_diff,
    prereg_status,
    render_json,
    render_prereg,
    write_prereg,
)
from jevtrader.export import (
    ARENA_PATH,
    EXPORT_PATH,
    ExportError,
    preconditions,
    read_arena_inputs,
    read_committed_catalog,
    read_inputs,
    render,
    render_arena,
    write_export,
)
from jevtrader.jev import (
    CALLS_PATH,
    POLICY_PATH,
    PROMPT_VERSION,
    SAMPLES,
    JevError,
    append_call,
    call_jev,
    pending,
    policy_table,
    read_calls,
    write_policy,
)
from jevtrader.states import (
    ALL_STATES,
    CASH,
    DIMENSIONS,
    SPLIT_STARTS,
    STATE_VERSION,
    STUDY,
    VOTE_REVERT,
    VOTE_TREND,
    State,
    state_key,
    state_table,
    vote,
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
    report = commands.add_parser("evaluate", help="fit on fit, report every arm on validate")
    report.add_argument("--prereg", action="store_true", help="write research/prereg.toml")
    once = commands.add_parser("holdout", help="run the pre-registered holdout once")
    once.add_argument("--verify", action="store_true", help="rerun from the manifest and compare")
    commands.add_parser("export", help="write export/v1/ for the site from the holdout inputs")
    commands.add_parser("arena", help="compare the catalog strategies, write export/arena/v1/")
    jev = commands.add_parser("jev-table", help="ask Jev about every state, write data/policy/")
    jev.add_argument("--offline", action="store_true", help="build from the call log only")
    jev.add_argument("--limit", type=int, help="ask at most N pending (state, sample) pairs")
    jev.add_argument("--workers", type=int, default=8, help="concurrent calls (default 8)")
    args = parser.parse_args(argv)
    if args.command == "states":
        return states()
    if args.command == "ceiling":
        return ceiling()
    if args.command == "jev-table":
        return jev_table(args.offline, args.limit, args.workers)
    if args.command == "evaluate":
        return evaluate(args.prereg)
    if args.command == "holdout":
        return holdout(REPO_ROOT, DATA_DIR, args.verify)
    if args.command == "export":
        return export(REPO_ROOT, DATA_DIR)
    if args.command == "arena":
        return arena(REPO_ROOT, DATA_DIR)
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


def state_paths() -> list[Path]:
    return [DATA_DIR / "states" / f"{s}.parquet" for s in STUDY]


def dev_rows() -> pl.DataFrame | None:
    paths = state_paths()
    if not all(p.exists() for p in paths):
        print("no state rows, run `jt states` first", file=sys.stderr)
        return None
    dev = pl.scan_parquet(paths).filter(pl.col("split") != "holdout").collect()
    if set(dev["state_version"]) != {STATE_VERSION}:
        print(f"state rows are not {STATE_VERSION}, run `jt states` first", file=sys.stderr)
        return None
    return dev


def ceiling() -> int:
    dev = dev_rows()
    if dev is None:
        return 2
    holdout = pl.scan_parquet(state_paths()).filter(pl.col("split") == "holdout")
    holdout = holdout.select(pl.len()).collect().item()

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


def jev_table(offline: bool, limit: int | None, workers: int) -> int:
    if not offline:
        key = dotenv_values(REPO_ROOT / ".env").get("OPENROUTER_API_KEY")
        if not key:
            print(f"OPENROUTER_API_KEY is not set in {REPO_ROOT / '.env'}", file=sys.stderr)
            return 2
        if ask_jev(key, pending(read_calls(CALLS_PATH))[:limit], workers):
            return 1

    calls = read_calls(CALLS_PATH)
    total = len(ALL_STATES) * SAMPLES
    gaps = len(pending(calls))
    if gaps:
        print(f"{total - gaps}/{total} calls logged")
        return 1
    dev = dev_rows()
    if dev is None:
        return 2
    try:
        table = policy_table(calls)
    except JevError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    changed, sha = write_policy(table, DATA_DIR)

    mine = [c for c in calls if c["prompt_version"] == PROMPT_VERSION]
    served = ", ".join(sorted({c["model_served"] for c in mine}))
    cost = sum(c["cost_usd"] for c in calls)
    print(f"calls {len(mine)} ({PROMPT_VERSION}); model_served {served}; log cost ${cost:.4f}")
    p_up, p_sd, coherence = (table[c].to_numpy() for c in ("p_up", "p_sd", "coherence"))
    print(
        f"sample spread: p_sd median {np.median(p_sd):.3f}, p90 {np.quantile(p_sd, 0.9):.3f}"
        f", max {p_sd.max():.3f}; p_up min {p_up.min():.3f}, median {np.median(p_up):.3f}"
        f", max {p_up.max():.3f}"
    )
    print(
        f"coherence |p_hi + p_lo - 1|: mean {coherence.mean():.3f}"
        f", median {np.median(coherence):.3f}, p90 {np.quantile(coherence, 0.9):.3f}"
    )
    r2 = {
        name: np.corrcoef(p_up, [vote(t, s) for s in ALL_STATES])[0, 1] ** 2
        for name, t in (("vote_trend", VOTE_TREND), ("vote_revert", VOTE_REVERT))
    }
    print(f"R² of p_up on vote_trend {r2['vote_trend']:.3f}, vote_revert {r2['vote_revert']:.3f}")

    validate = dev.filter(pl.col("split") == "validate", pl.col("up_20").is_not_null()).join(
        table.select("state_key", "p_up"), on="state_key", maintain_order="left"
    )
    point, lo, hi = block_bootstrap_auc(
        validate["date"].to_numpy(), validate["p_up"].to_numpy(), validate["up_20"].to_numpy()
    )
    print(
        f"jev ({PROMPT_VERSION}) validate AUC {point:.3f}  95% CI [{lo:.3f}, {hi:.3f}]"
        f"  ({REPS} reps, {BLOCK}-session blocks, seed 0)"
    )
    status = "changed" if changed else "unchanged"
    print(f"{DATA_DIR / POLICY_PATH} {status} sha256 {sha}")
    return 0


def evaluate(prereg: bool) -> int:
    dev = dev_rows()
    if dev is None:
        return 2
    if not (DATA_DIR / POLICY_PATH).exists():
        print("no policy table, run `jt jev-table --offline` first", file=sys.stderr)
        return 2
    policy = pl.read_parquet(DATA_DIR / POLICY_PATH)
    market = {
        s: pl.read_parquet(DATA_DIR / "market" / f"{s}.parquet", columns=["date", "open"])
        for s in (*STUDY, CASH)
    }
    returns = open_returns(market, dict(SPLIT_STARTS)["holdout"])
    fit, validate = (dev.filter(pl.col("split") == s) for s in ("fit", "validate"))
    reports = arm_reports(validate, fit, policy, returns)

    blocks = {}
    for name, part in (("fit", fit), ("validate", validate)):
        dates = part["date"]
        labelled = part.filter(pl.col("up_20").is_not_null())["date"]
        blocks[name] = n_blocks(labelled.to_numpy())
        print(
            f"{name:<9}{dates.min()}..{dates.max()}  {part.height} rows, {labelled.len()} labelled"
            f" on {labelled.n_unique()} dates = {blocks[name]} blocks"
        )
    traded = validate.join(returns, on=["symbol", "date"])["date"]
    print(f"traded validate dates {traded.n_unique()} = {n_blocks(traded.to_numpy())} blocks")
    print(f"symbols {' '.join(STUDY)}, cash {CASH}")
    print(
        f"{LEVEL:.0%} CIs from {REPS} reps of {BLOCK}-session joint-date blocks, seed 0: auc and"
        f" bss resample the {blocks['validate']} labelled validate blocks, sharpe_x the"
        f" {n_blocks(traded.to_numpy())} traded ones. sharpe_x is net of {COST_BPS} bps per switch"
    )
    print_reports(reports, "validate")

    holdout_dates = (
        pl.scan_parquet(state_paths())
        .filter(pl.col("split") == "holdout")
        .select("date")
        .collect()["date"]
    )
    dev_power = power(validate, fit, policy, holdout_blocks(holdout_dates))
    print()
    print(
        f"primary auc({CANDIDATE}) - auc({BASELINE}): dev SE {dev_power.se:.4f}"
        f" at {dev_power.holdout_blocks} blocks, MDE {dev_power.mde:.4f}"
        f"; validate {dev_power.eval_blocks} blocks, holdout {dev_power.holdout_blocks} blocks"
    )

    mine = [c for c in read_calls(CALLS_PATH) if c["prompt_version"] == PROMPT_VERSION]
    served = sorted({c["model_served"] for c in mine})
    if len(served) != 1:
        print(f"error: {PROMPT_VERSION} calls were served by {served}", file=sys.stderr)
        return 1
    text = render_prereg(
        model_served=served[0],
        policy_sha256=sha256(DATA_DIR / POLICY_PATH),
        market_sha256={
            s: json.loads((DATA_DIR / "market" / f"{s}.manifest.json").read_text())["sha256"]
            for s in market
        },
        holdout_end=holdout_dates.max(),
        power=dev_power,
    )
    path = REPO_ROOT / PREREG_PATH
    if not prereg:
        print(f"{path} {prereg_status(path, text)}")
        return 0
    status = write_prereg(path, text)
    if status == "differs":
        print(f"{path} differs from this run, refusing to overwrite it", file=sys.stderr)
        return 1
    print(f"{path} {'written' if status == 'missing' else 'unchanged'}")
    return 0


def print_reports(reports: dict[str, ArmReport], split: str) -> None:
    print()
    print(
        f"{'arm':<16}{'auc':<22}{'bss':<25}{'sharpe_x':<21}"
        f"{'exposure':>8}{'turnover/yr':>13}{'max_dd':>8}"
    )
    for name, r in reports.items():
        bss = "n/a" if r.brier_skill is None else interval(r.brier_skill, 3)
        note = "  look-ahead check, not a strategy" if ARMS[name].lookahead else ""
        print(
            f"{name:<16}{interval(r.auc, 3):<22}{bss:<25}{interval(r.excess_sharpe, 2):<21}"
            f"{r.exposure:>8.1%}{r.switches_per_year:>13.1f}{r.max_drawdown:>8.1%}{note}"
        )

    print()
    print(f"{'excess Sharpe':<16}" + "".join(f"{f'{c} bps':>8}" for c in COSTS_BPS))
    for name, r in reports.items():
        print(f"{name:<16}" + "".join(f"{r.excess_sharpe_by_cost[c]:>8.2f}" for c in COSTS_BPS))

    print()
    print(f"calibration on labelled {split} rows: bin, n, mean score, observed up rate")
    for name in ("jev", "empirical_table"):
        print(name)
        for lo, n, mean, up in reports[name].calibration or []:
            print(f"  [{lo:.1f}, {lo + 0.1:.1f}){n:>7}{mean:>7.3f}{up:>7.3f}")


def git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)


def holdout(repo: Path, data_dir: Path, verify: bool) -> int:
    """Run the holdout once, or with `verify` rerun it from the manifest and compare the bytes.

    Refuses unless the tracked files are committed and prereg.toml matches this code and the
    hashes of the input files. All of that is checked before any holdout label is read.
    """
    prereg, result_path, run_path = (
        repo / PREREG_PATH,
        repo / HOLDOUT_PATH,
        repo / HOLDOUT_RUN_PATH,
    )
    if not verify and (result_path.exists() or run_path.exists()):
        print(f"{result_path} exists and the holdout runs once, refusing", file=sys.stderr)
        print("`jt holdout --verify` reruns it from the manifest", file=sys.stderr)
        return 1
    if verify and not run_path.exists():
        print(f"no {run_path}, nothing to verify", file=sys.stderr)
        return 2
    recorded = HoldoutRun(**json.loads(run_path.read_text())) if verify else None

    if git(repo, "ls-files", "--error-unmatch", str(PREREG_PATH)).returncode != 0:
        print(f"{prereg} is not committed, refusing", file=sys.stderr)
        return 1
    dirty = git(repo, "status", "--porcelain", "--untracked-files=no").stdout
    if dirty:
        print(f"uncommitted changes, refusing:\n{dirty}", file=sys.stderr, end="")
        return 1
    head = git(repo, "rev-parse", "HEAD").stdout.strip()

    paths = {s: data_dir / "market" / f"{s}.parquet" for s in (*STUDY, CASH)}
    missing = [p for p in (*paths.values(), data_dir / POLICY_PATH) if not p.exists()]
    if missing:
        print(f"missing {', '.join(map(str, missing))}", file=sys.stderr)
        return 2

    text = prereg.read_text()
    diff = prereg_diff(
        text,
        sha256(data_dir / POLICY_PATH),
        {s: sha256(p) for s, p in paths.items()},
    )
    if diff:
        print(f"{prereg} does not match this code and data, refusing", file=sys.stderr)
        print("\n".join(diff), file=sys.stderr)
        return 1
    if recorded is not None and recorded.prereg_sha256 != sha256(prereg):
        print(f"{prereg} is not the prereg {run_path} ran on, refusing", file=sys.stderr)
        return 1

    end = tomllib.loads(text)["holdout"]["end"]
    market = {s: pl.read_parquet(p) for s, p in paths.items()}
    result = holdout_result(market, pl.read_parquet(data_dir / POLICY_PATH), end)
    body = render_json(result).encode()
    digest = hashlib.sha256(body).hexdigest()

    if recorded is not None:
        same = (
            digest == recorded.result_sha256
            and result_path.exists()
            and result_path.read_bytes() == body
        )
        print(
            f"rerun at {head} of the run at {recorded.git_commit}:"
            f" {result_path} {'is byte-identical' if same else 'differs'}"
        )
        return 0 if same else 1

    atomic_write(result_path, body)
    atomic_write(run_path, render_json(HoldoutRun(sha256(prereg), head, digest)).encode())
    print(
        f"holdout {result.first}..{result.last}  {result.rows} rows, {result.labelled} labelled"
        f" = {result.blocks} blocks, fitted on fit + validate"
    )
    print_reports(result.arms, "holdout")
    print()
    print(
        f"primary auc({CANDIDATE}) - auc({BASELINE}) {interval(result.primary, 4)}"
        f"  ({LEVEL:.0%} CI, {REPS} reps, {BLOCK}-session blocks, seed 0)"
    )
    print(f"outcome {result.outcome}")
    print(f"wrote {result_path} and {run_path}")
    return 0


def export(repo: Path, data_dir: Path) -> int:
    """Write export/v1 from the files the holdout read, after checking they are those files."""
    try:
        inputs = read_inputs(repo, data_dir)
    except FileNotFoundError as e:
        print(f"missing {e.filename}", file=sys.stderr)
        return 2
    try:
        failures = preconditions(inputs)
        if not failures:
            files = render(inputs)
    except ExportError as e:
        failures = [str(e)]
    if failures:
        print("\n".join(failures), file=sys.stderr)
        print(f"refusing, {repo / EXPORT_PATH} is unchanged", file=sys.stderr)
        return 1
    for path, status, digest in write_export(repo / EXPORT_PATH, files):
        print(f"{EXPORT_PATH / path} {status} {digest}")
    return 0


def arena(repo: Path, data_dir: Path) -> int:
    try:
        inputs = read_arena_inputs(repo, data_dir)
    except FileNotFoundError as e:
        print(f"missing {e.filename}", file=sys.stderr)
        return 2
    made = arena_decisions(inputs.market)
    failures = reconcile(made, inputs.market, inputs.holdout) + refusals(
        read_committed_catalog(repo), made
    )
    try:
        if not failures:
            files = render_arena(inputs)
    except ExportError as e:
        failures = [str(e)]
    if failures:
        print("\n".join(failures), file=sys.stderr)
        print(f"refusing, {repo / ARENA_PATH} is unchanged", file=sys.stderr)
        return 1
    for path, status, digest in write_export(repo / ARENA_PATH, files):
        print(f"{ARENA_PATH / path} {status} {digest}")
    return 0


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def interval(i: Interval, digits: int) -> str:
    return f"{i.point:.{digits}f} [{i.lo:.{digits}f}, {i.hi:.{digits}f}]"


def ask_jev(key: str, todo: list[tuple[State, int]], workers: int) -> int:
    """Ask Jev about each (state, sample), logging each answer as it lands. Returns failures."""
    print(f"asking Jev {len(todo)} pending calls with {workers} workers")
    failed = 0
    with httpx.Client(timeout=60) as client, ThreadPoolExecutor(workers) as pool:

        def ask(state: State, sample: int):
            return call_jev(client, key, state, sample, datetime.now(UTC), time.sleep)

        futures = {pool.submit(ask, s, i): (s, i) for s, i in todo}
        try:
            for done, future in enumerate(as_completed(futures), 1):
                state, sample = futures[future]
                try:
                    append_call(CALLS_PATH, future.result())
                except JevError as e:
                    print(f"{state_key(state)} sample {sample}: {e}")
                    failed += 1
                if done % 100 == 0:
                    print(f"{done}/{len(todo)} calls done, {failed} failed")
        finally:
            # On Ctrl-C, drop the queued calls instead of paying for answers nobody logs.
            pool.shutdown(cancel_futures=True)
    if failed:
        print(f"{failed}/{len(todo)} calls failed, rerun to retry them")
    return failed


if __name__ == "__main__":
    sys.exit(main())
