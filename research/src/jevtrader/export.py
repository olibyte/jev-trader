"""The export/v1 files the site reads, rendered from the inputs the holdout run hashed."""

from __future__ import annotations

import hashlib
import io
import json
import tomllib
from dataclasses import asdict
from datetime import date, timedelta
from pathlib import Path
from typing import Literal, NamedTuple

import polars as pl

from jevtrader.data import REPO_ROOT, atomic_write, forward_return
from jevtrader.evaluate import (
    ARMS,
    BASELINE,
    CANDIDATE,
    COST_BPS,
    HOLDOUT_PATH,
    HOLDOUT_RUN_PATH,
    PREREG_PATH,
    SHRINK_K,
    backtest,
    decisions,
    empirical_table,
    n_blocks,
    open_returns,
    prereg_diff,
)
from jevtrader.jev import (
    CALLS_PATH,
    DESCRIPTIONS,
    FIELDS,
    MODEL,
    POLICY_PATH,
    PROMPT_VERSION,
    QUESTIONS,
    SAMPLES,
    JevCall,
    JevError,
    policy_table,
    read_calls,
)
from jevtrader.states import (
    ALL_STATES,
    CASH,
    DIMENSIONS,
    HORIZON,
    SPLIT_STARTS,
    STUDY,
    state_key,
    state_rows,
)

# Relative to the repository root.
EXPORT_PATH = Path("export") / "v1"
CALL_LOG_PATH = CALLS_PATH.relative_to(REPO_ROOT)
EQUITY_ARMS = (CANDIDATE, BASELINE, "buy_hold")
DEVELOPMENT = ("fit", "validate")


class ExportError(Exception):
    """Inputs the export cannot render. Nothing is written."""


class Inputs(NamedTuple):
    prereg: str
    holdout: dict  # research/holdout.json
    run: dict  # research/holdout.manifest.json
    calls: list[JevCall]
    policy: pl.DataFrame
    market: dict[str, pl.DataFrame]  # STUDY then CASH, uncut
    fetched: dict[str, dict]  # each symbol's data/market/{symbol}.manifest.json
    sha256: dict[str, str]  # repo-relative path of each hashed input file -> sha256 of its bytes


Status = Literal["changed", "unchanged", "removed"]


class Written(NamedTuple):
    path: str  # relative to the export directory
    status: Status
    sha256: str


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _market_path(symbol: str) -> str:
    return f"data/market/{symbol}.parquet"


def read_inputs(repo: Path, data_dir: Path) -> Inputs:
    """Read every input file once. Raises FileNotFoundError for a missing one."""
    symbols = (*STUDY, CASH)
    paths = {
        str(PREREG_PATH): repo / PREREG_PATH,
        str(HOLDOUT_PATH): repo / HOLDOUT_PATH,
        str(HOLDOUT_RUN_PATH): repo / HOLDOUT_RUN_PATH,
        str(CALL_LOG_PATH): repo / CALL_LOG_PATH,
        f"data/{POLICY_PATH}": data_dir / POLICY_PATH,
        **{_market_path(s): data_dir / "market" / f"{s}.parquet" for s in symbols},
    }
    raw = {label: path.read_bytes() for label, path in paths.items()}
    return Inputs(
        prereg=raw[str(PREREG_PATH)].decode(),
        holdout=json.loads(raw[str(HOLDOUT_PATH)]),
        run=json.loads(raw[str(HOLDOUT_RUN_PATH)]),
        calls=read_calls(repo / CALL_LOG_PATH),
        policy=pl.read_parquet(io.BytesIO(raw[f"data/{POLICY_PATH}"])),
        market={s: pl.read_parquet(io.BytesIO(raw[_market_path(s)])) for s in symbols},
        fetched={
            s: json.loads((data_dir / "market" / f"{s}.manifest.json").read_text()) for s in symbols
        },
        sha256={label: sha256(data) for label, data in raw.items()},
    )


def preconditions(inputs: Inputs) -> list[str]:
    """The failed checks that the inputs are the ones the holdout read. Empty means all pass."""
    failures = []
    for label, field in ((HOLDOUT_PATH, "result_sha256"), (PREREG_PATH, "prereg_sha256")):
        if inputs.sha256[str(label)] != inputs.run.get(field):
            failures.append(f"sha256 of {label} is not {field} in {HOLDOUT_RUN_PATH}")
    policy_sha = inputs.sha256[f"data/{POLICY_PATH}"]
    market_sha = {s: inputs.sha256[_market_path(s)] for s in inputs.market}
    diff = prereg_diff(inputs.prereg, policy_sha, market_sha)
    if diff:
        failures.append("\n".join([f"{PREREG_PATH} does not match this code and data", *diff]))
    try:
        buffer = io.BytesIO()
        policy_table(inputs.calls).write_parquet(buffer)
        if sha256(buffer.getvalue()) != policy_sha:
            failures.append(
                f"the policy table built from {CALL_LOG_PATH} is not data/{POLICY_PATH}"
            )
    except JevError as e:
        failures.append(f"{CALL_LOG_PATH} cannot build the policy table: {e}")
    return failures


def render(inputs: Inputs) -> dict[str, bytes]:
    """Every export/v1 file's bytes, keyed by its path in the export directory.

    Bars after the prereg holdout end are dropped first, as in evaluate.holdout_result.
    """
    prereg = tomllib.loads(inputs.prereg)
    end: date = prereg["holdout"]["end"]
    bars = {s: b.filter(pl.col("date") <= end) for s, b in inputs.market.items()}
    rows = pl.concat(state_rows(s, b) for s, b in bars.items() if s != CASH).filter(
        pl.col("split") != "warmup"
    )
    dev = rows.filter(pl.col("split").is_in(DEVELOPMENT))
    test = rows.filter(pl.col("split") == "holdout")
    made = decisions(rows, dev, inputs.policy)
    returns = open_returns(bars, end + timedelta(days=1))
    holdout_start = dict(SPLIT_STARTS)["holdout"]
    sleeves = backtest(
        made.filter(pl.col("arm").is_in(EQUITY_ARMS), pl.col("date") >= holdout_start),
        returns,
        COST_BPS,
    )
    traded = test.join(returns, on=["symbol", "date"])["date"].to_numpy()

    files = {
        "summary.json": _indented(summary(prereg, inputs.holdout, n_blocks(traded))),
        "policy.json": _indented(policy(prereg, inputs.calls, inputs.policy, dev)),
        **{f"symbols/{s}.json": _compact(symbol(s, bars[s], rows, made, sleeves)) for s in STUDY},
    }
    files["manifest.json"] = _indented(manifest(prereg, inputs, rows, files))
    return files


def manifest(prereg: dict, inputs: Inputs, rows: pl.DataFrame, files: dict[str, bytes]) -> dict:
    """manifest.json: the study, the input datasets, the two runs, and every other file's hash."""
    study = prereg["study"]
    spans = rows.group_by("split").agg(pl.col("date").min().alias("first"), pl.col("date").max())
    span = {split: (first, last) for split, first, last in spans.iter_rows()}
    calls = inputs.calls
    return {
        "version": EXPORT_PATH.name,
        "study": {
            "stateVersion": study["state_version"],
            "promptVersion": study["prompt_version"],
            "modelRequested": MODEL,
            "modelServed": study["model_served"],
            "horizon": HORIZON,
            "symbols": list(STUDY),
            "cash": CASH,
            "periods": [
                {
                    "split": split,
                    "label": "development" if split in DEVELOPMENT else "holdout",
                    "first": span[split][0].isoformat(),
                    "last": span[split][1].isoformat(),
                }
                for split, _ in SPLIT_STARTS
            ],
        },
        "datasets": {
            "market": {
                s: {
                    "sha256": inputs.sha256[_market_path(s)],
                    "first": inputs.fetched[s]["first"],
                    "last": inputs.fetched[s]["last"],
                    "rows": inputs.fetched[s]["rows"],
                    "fetchedAt": inputs.fetched[s]["fetched_at"],
                }
                for s in inputs.market
            },
            "policy": {
                "path": f"data/{POLICY_PATH}",
                "sha256": inputs.sha256[f"data/{POLICY_PATH}"],
            },
            "callLog": {
                "path": str(CALL_LOG_PATH),
                "sha256": inputs.sha256[str(CALL_LOG_PATH)],
                "calls": len(calls),
                "costUsd": sum(c["cost_usd"] for c in calls),
            },
        },
        "runs": {
            "holdout": {
                "command": "jt holdout",
                "gitCommit": inputs.run["git_commit"],
                "preregSha256": inputs.run["prereg_sha256"],
                "resultSha256": inputs.run["result_sha256"],
                "files": [str(p) for p in (PREREG_PATH, HOLDOUT_PATH, HOLDOUT_RUN_PATH)],
            },
            "export": {"command": "jt export", "inputs": inputs.sha256},
        },
        "files": {path: sha256(files[path]) for path in sorted(files)},
    }


def summary(prereg: dict, holdout: dict, sharpe_blocks: int) -> dict:
    """summary.json: holdout.json's metrics, copied, with the prereg's rules and settings."""
    primary, power, settings = prereg["primary"], prereg["power"], prereg["settings"]
    return {
        "run": "holdout",
        "period": {"label": "holdout", "first": holdout["first"], "last": holdout["last"]},
        "rows": holdout["rows"],
        "labelled": holdout["labelled"],
        "blocks": holdout["blocks"],
        "sharpeBlocks": sharpe_blocks,
        "primary": {
            "metric": primary["metric"],
            "candidate": CANDIDATE,
            "baseline": BASELINE,
            **holdout["primary"],
        },
        "outcome": holdout["outcome"],
        "outcomeRule": primary["outcome"],
        "power": {
            "alpha": power["alpha"],
            "power": power["power"],
            "devSe": power["dev_se"],
            "mde": power["mde"],
            "validateBlocks": power["validate_blocks"],
            "holdoutBlocks": power["holdout_blocks"],
        },
        "bootstrap": {
            "level": primary["level"],
            "block": primary["block"],
            "reps": primary["reps"],
            "seed": primary["seed"],
        },
        "costBps": settings["cost_bps"],
        "costsBps": settings["costs_bps"],
        "fitOn": prereg["holdout"]["fit_on"],
        "arms": [_arm(name, prereg["arms"][name], holdout["arms"][name]) for name in ARMS],
    }


def _arm(name: str, rule: str, report: dict) -> dict:
    calibration = report["calibration"]
    return {
        "name": name,
        "rule": rule,
        "probability": ARMS[name].probability,
        "lookahead": ARMS[name].lookahead,
        "auc": report["auc"],
        "brierSkill": report["brier_skill"],
        "excessSharpe": report["excess_sharpe"],
        "excessSharpeByCost": [
            {"costBps": int(bps), "value": value}
            for bps, value in report["excess_sharpe_by_cost"].items()
        ],
        "exposure": report["exposure"],
        "switchesPerYear": report["switches_per_year"],
        "maxDrawdown": report["max_drawdown"],
        "calibration": None
        if calibration is None
        else [
            {"binLow": low, "binHigh": round(low + 0.1, 1), "rows": n, "meanScore": m, "upRate": u}
            for low, n, m, u in calibration
        ],
    }


def policy(prereg: dict, calls: list[JevCall], table: pl.DataFrame, dev: pl.DataFrame) -> dict:
    """policy.json: each state's levels, Jev's answers, and its development frequencies.

    Raises ExportError if a logged request.state is not the one rebuilt from the dimensions and
    the sample's order.
    """
    labelled = dev.filter(pl.col("up_20").is_not_null())
    counts = labelled.group_by("state_key").agg(
        pl.len().alias("n"), pl.col("up_20").sum().alias("ups")
    )
    per_state = table.join(empirical_table(dev), on="state_key", maintain_order="left").join(
        counts, on="state_key", how="left", maintain_order="left"
    )
    logged = {
        (c["state_key"], c["sample"]): c for c in calls if c["prompt_version"] == PROMPT_VERSION
    }
    return {
        "run": "export",
        "promptVersion": prereg["study"]["prompt_version"],
        "modelServed": prereg["study"]["model_served"],
        "samples": SAMPLES,
        "questions": QUESTIONS,
        "development": {
            "splits": list(DEVELOPMENT),
            "first": dev["date"].min().isoformat(),
            "last": dev["date"].max().isoformat(),
            "labelled": labelled.height,
            "baseRate": labelled["up_20"].mean(),
            "shrinkK": SHRINK_K,
        },
        "dimensions": [
            {
                "name": name,
                "field": FIELDS[name],
                "levels": [{"level": lv, "text": DESCRIPTIONS[name][lv]} for lv in levels],
            }
            for name, levels in DIMENSIONS.items()
        ],
        "states": [
            _state(levels, row, [logged[(row["state_key"], i)] for i in range(SAMPLES)])
            for levels, row in zip(
                (asdict(s) for s in ALL_STATES), per_state.iter_rows(named=True), strict=True
            )
        ],
    }


def _state(levels: dict[str, str], row: dict, calls: list[JevCall]) -> dict:
    names = list(DIMENSIONS)
    index = {FIELDS[name]: i for i, name in enumerate(names)}
    samples = []
    for call in calls:
        order = [index[field] for field in call["request"]["state"]]
        rebuilt = {FIELDS[names[i]]: DESCRIPTIONS[names[i]][levels[names[i]]] for i in order}
        # dict == ignores key order, and the field order is part of what Jev saw.
        if json.dumps(rebuilt) != json.dumps(call["request"]["state"]):
            raise ExportError(f"state {row['state_key']} sample {call['sample']} does not rebuild")
        samples.append({"order": order, "pHi": call["p_hi"], "pLo": call["p_lo"]})
    n, ups = row["n"] or 0, row["ups"] or 0
    return {
        "key": row["state_key"],
        "levels": levels,
        "pUp": row["p_up"],
        "pSd": row["p_sd"],
        "coherence": row["coherence"],
        "samples": samples,
        "development": {
            "n": n,
            "ups": ups,
            "upRate": ups / n if n else None,
            "empiricalP": row["empirical_p"],
        },
    }


def symbol(
    name: str, bars: pl.DataFrame, rows: pl.DataFrame, made: pl.DataFrame, sleeves: pl.DataFrame
) -> dict:
    """symbols/{name}.json: the sessions from the fit start through the holdout end, and the
    holdout equity of each EQUITY_ARMS sleeve.

    bars are cut at the holdout end. Raises ExportError if a session in range has no state.
    """
    index = pl.DataFrame(
        {"state_key": [state_key(s) for s in ALL_STATES], "state": range(len(ALL_STATES))}
    )
    mine = pl.col("symbol") == name
    jev = made.filter(mine, pl.col("arm") == CANDIDATE).select("date", "position")
    days = (
        bars.with_columns(forward_return(HORIZON).alias("fwd_ret_20"))
        .filter(pl.col("date") >= dict(SPLIT_STARTS)["fit"])
        .join(rows.filter(mine).select("date", "split", "state_key"), on="date", how="left")
        .join(index, on="state_key", how="left")
        .join(jev, on="date", how="left")
    )
    if days["state"].null_count():
        missing = days.filter(pl.col("state").is_null())["date"]
        raise ExportError(f"{name} has {missing.len()} sessions with no state, first {missing[0]}")

    sleeves = sleeves.filter(mine).with_columns(
        (1 + pl.col("ret")).cum_prod().over("arm").alias("equity")
    )
    curves = {arm: sleeves.filter(pl.col("arm") == arm) for arm in EQUITY_ARMS}
    return {
        "run": "export",
        "symbol": name,
        "inStudy": True,
        "days": {
            "date": _dates(days["date"]),
            **{c: _rounded(days[c], 4) for c in ("open", "high", "low", "close")},
            "split": days["split"].to_list(),
            "state": days["state"].to_list(),
            "jev": days["position"].to_list(),
            "fwdRet20": _rounded(days["fwd_ret_20"], 6),
        },
        "equity": {
            "period": "holdout",
            "costBps": COST_BPS,
            "date": _dates(curves[CANDIDATE]["date"]),
            "arms": {arm: _rounded(curve["equity"], 6) for arm, curve in curves.items()},
        },
    }


def _dates(series: pl.Series) -> list[str]:
    return [d.isoformat() for d in series.to_list()]


def _rounded(series: pl.Series, digits: int) -> list[float | None]:
    return [None if v is None else round(v, digits) for v in series.to_list()]


def _indented(value: dict) -> bytes:
    return (json.dumps(value, indent=2, allow_nan=False) + "\n").encode()


def _compact(value: dict) -> bytes:
    return (json.dumps(value, separators=(",", ":"), allow_nan=False) + "\n").encode()


def write_export(directory: Path, files: dict[str, bytes]) -> list[Written]:
    """Converge `directory` to exactly `files`, sorted by path.

    A file is written only when its bytes differ, and any other file under `directory` is
    removed, so a rerun on the same inputs changes nothing.
    """
    existing = {p.relative_to(directory).as_posix(): p for p in directory.rglob("*") if p.is_file()}
    written = []
    for path in sorted(files.keys() | existing.keys()):
        target = directory / path
        if path not in files:
            written.append(Written(path, "removed", sha256(target.read_bytes())))
            target.unlink()
            continue
        same = path in existing and target.read_bytes() == files[path]
        if not same:
            atomic_write(target, files[path])
        written.append(Written(path, "unchanged" if same else "changed", sha256(files[path])))
    for folder in sorted((p for p in directory.rglob("*") if p.is_dir()), reverse=True):
        if not any(folder.iterdir()):
            folder.rmdir()
    return written
