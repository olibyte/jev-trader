"""Jev's policy table: the prompt, the OpenRouter Decisions call, the call log, and the table."""

from __future__ import annotations

import hashlib
import io
import json
import os
import random
from collections.abc import Callable
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Literal, TypedDict

import httpx
import numpy as np
import polars as pl

from jevtrader.data import REPO_ROOT, atomic_write, strip_key
from jevtrader.states import ALL_STATES, State, state_key

MODEL = "typesafe/jev-1.13"
ENDPOINT = "https://openrouter.ai/api/alpha/decisions"
PROMPT_VERSION = "descriptive/v1"
SAMPLES = 5
ATTEMPTS = 4
CALLS_PATH = REPO_ROOT / "research" / "jev_calls.jsonl"
POLICY_PATH = Path("policy") / "jev.parquet"

FIELDS = {
    "rsi14": "momentum",
    "vs_sma200": "trend_200d",
    "sma50_vs_sma200": "trend_50d_vs_200d",
    "macd_hist": "macd",
    "bollinger": "bollinger",
    "atr_regime": "volatility",
}

# Jev is weak with numbers, so each level is words with the states/v1 cut point in parentheses.
DESCRIPTIONS: dict[str, dict[str, str]] = {
    "rsi14": {
        "OVERSOLD": "The 14-day RSI is oversold (below 30).",
        "WEAK": "The 14-day RSI is weak (30 to 45).",
        "NEUTRAL": "The 14-day RSI is neutral (45 to 55).",
        "STRONG": "The 14-day RSI is strong (55 to 70).",
        "OVERBOUGHT": "The 14-day RSI is overbought (70 or above).",
    },
    "vs_sma200": {
        "ABOVE": "The price is above its 200-day moving average.",
        "BELOW": "The price is at or below its 200-day moving average.",
    },
    "sma50_vs_sma200": {
        "ABOVE": "The 50-day moving average is above the 200-day moving average.",
        "BELOW": "The 50-day moving average is at or below the 200-day moving average.",
    },
    "macd_hist": {
        "POS_RISING": "The MACD histogram is positive and rising.",
        "POS_FALLING": "The MACD histogram is positive and falling.",
        "NEG_RISING": "The MACD histogram is negative and rising.",
        "NEG_FALLING": "The MACD histogram is negative and falling.",
    },
    "bollinger": {
        "BELOW_LOWER": "The price is below the lower Bollinger band (20-day, 2 sd).",
        "LOWER_HALF": "The price is between the lower Bollinger band and the 20-day average.",
        "UPPER_HALF": "The price is between the 20-day average and the upper Bollinger band.",
        "ABOVE_UPPER": "The price is above the upper Bollinger band (20-day, 2 sd).",
    },
    "atr_regime": {
        "LOW": "Volatility is low (14-day ATR in the bottom third of the past year).",
        "NORMAL": "Volatility is normal (14-day ATR in the middle third of the past year).",
        "HIGH": "Volatility is high (14-day ATR in the top third of the past year).",
    },
}

CONTEXT = "The state describes a US equity ETF's daily technical indicators at today's close."
HIGHER = "The price 20 trading days from now is higher than the price now."
LOWER_OR_EQUAL = "The price 20 trading days from now is lower than or equal to the price now."
QUESTIONS = {
    "higher": {
        "type": "noul",
        "instructions": f"{CONTEXT} Will the price be higher 20 trading days from now than now?",
        "criteria": {"true": HIGHER, "false": LOWER_OR_EQUAL},
    },
    "lower_or_equal": {
        "type": "noul",
        "instructions": f"{CONTEXT} Will the price be lower than or equal to now 20 trading days "
        "from now?",
        "criteria": {"true": LOWER_OR_EQUAL, "false": HIGHER},
    },
}


class JevError(Exception):
    """A failed Decisions call or a call log that cannot build the policy table."""


class JevCall(TypedDict):
    call_key: str
    sample: int
    key_order_seed: int
    model_requested: Literal["typesafe/jev-1.13"]
    model_served: str
    prompt_version: str
    state_key: str
    request: dict
    response: dict
    p_hi: float
    p_lo: float
    cost_usd: float
    called_at: str


def call_key(state_key: str, sample: int) -> str:
    text = json.dumps([MODEL, PROMPT_VERSION, state_key, sample], separators=(",", ":"))
    return hashlib.sha256(text.encode()).hexdigest()


def key_order_seed(state_key: str, sample: int) -> int:
    return int(call_key(state_key, sample)[:16], 16)


def build_request(state: State, sample: int) -> dict:
    fields = list(asdict(state).items())
    random.Random(key_order_seed(state_key(state), sample)).shuffle(fields)
    return {
        "model": MODEL,
        "state": {FIELDS[name]: DESCRIPTIONS[name][level] for name, level in fields},
        "questions": QUESTIONS,
    }


def parse_response(payload: dict) -> tuple[float, float, float, str]:
    try:
        model = payload["model"]
        p_hi = payload["answers"]["higher"]["noul"]
        p_lo = payload["answers"]["lower_or_equal"]["noul"]
        cost = payload["usage"]["cost"]
    except KeyError, TypeError:
        raise JevError(f"response lacks a field: {json.dumps(payload)[:300]}") from None
    for name, p in (("higher", p_hi), ("lower_or_equal", p_lo)):
        if not _is_number(p) or not 0 <= p <= 1:
            raise JevError(f"{name} noul is {p!r}, not a probability")
    if not _is_number(cost) or not isinstance(model, str):
        raise JevError(f"usage.cost {cost!r} or model {model!r} has the wrong type")
    return float(p_hi), float(p_lo), float(cost), model


def _is_number(x: object) -> bool:
    return isinstance(x, int | float) and not isinstance(x, bool)


def pending(calls: list[JevCall]) -> list[tuple[State, int]]:
    done = {(c["state_key"], c["sample"]) for c in calls if c["prompt_version"] == PROMPT_VERSION}
    return [(s, i) for s in ALL_STATES for i in range(SAMPLES) if (state_key(s), i) not in done]


def policy_table(calls: list[JevCall]) -> pl.DataFrame:
    """PolicyRow frame, one row per State in ALL_STATES order, from PROMPT_VERSION's calls."""
    mine = [c for c in calls if c["prompt_version"] == PROMPT_VERSION]
    served = sorted({c["model_served"] for c in mine})
    if len(served) > 1:
        raise JevError(f"{PROMPT_VERSION} calls were served by {len(served)} models: {served}")

    by_pair: dict[tuple[str, int], JevCall] = {}
    for c in mine:
        pair = (c["state_key"], c["sample"])
        if pair in by_pair:
            raise JevError(f"two calls for state {pair[0]} sample {pair[1]}")
        by_pair[pair] = c

    p = np.empty((len(ALL_STATES), SAMPLES, 2))
    for i, state in enumerate(ALL_STATES):
        key = state_key(state)
        for sample in range(SAMPLES):
            c = by_pair.pop((key, sample), None)
            if c is None:
                raise JevError(f"no call for state {key} sample {sample}")
            # dict == ignores key order, and the field order is part of what Jev saw.
            if json.dumps(c["request"]) != json.dumps(build_request(state, sample)):
                raise JevError(
                    f"logged request for state {key} sample {sample} differs from "
                    f"build_request; a prompt change needs a new PROMPT_VERSION"
                )
            p[i, sample] = c["p_hi"], c["p_lo"]
    if by_pair:
        raise JevError(f"{len(by_pair)} calls are outside ALL_STATES x range({SAMPLES})")

    p_hi, p_lo = p[..., 0], p[..., 1]
    u = (p_hi + 1 - p_lo) / 2
    return pl.DataFrame(
        {
            "state_key": [state_key(s) for s in ALL_STATES],
            "prompt_version": [PROMPT_VERSION] * len(ALL_STATES),
            "p_up": u.mean(axis=1),
            "p_sd": u.std(axis=1, ddof=1),
            "coherence": np.abs(p_hi + p_lo - 1).mean(axis=1),
        }
    )


def call_jev(
    client: httpx.Client,
    key: str,
    state: State,
    sample: int,
    now: datetime,
    sleep: Callable[[float], None],
) -> JevCall:
    """One Decisions call. Retries 429 and 5xx with backoff, raises JevError on anything else."""
    body = build_request(state, sample)
    headers = {"Authorization": f"Bearer {key}"}
    for attempt in range(ATTEMPTS):
        try:
            response = client.post(ENDPOINT, json=body, headers=headers)
        except httpx.HTTPError as e:
            raise JevError(f"{type(e).__name__} calling OpenRouter") from None
        retry = response.status_code == 429 or response.status_code >= 500
        if retry and attempt < ATTEMPTS - 1:
            sleep(2.0**attempt)
            continue
        if not response.is_success:
            text = strip_key(response.text, key)[:300]
            raise JevError(f"HTTP {response.status_code} after {attempt + 1} attempts: {text}")
        break
    try:
        payload = response.json()
    except ValueError:
        raise JevError(f"HTTP {response.status_code} with a non-JSON body") from None
    p_hi, p_lo, cost, model_served = parse_response(payload)

    skey = state_key(state)
    return JevCall(
        call_key=call_key(skey, sample),
        sample=sample,
        key_order_seed=key_order_seed(skey, sample),
        model_requested=MODEL,
        model_served=model_served,
        prompt_version=PROMPT_VERSION,
        state_key=skey,
        request=body,
        response=payload,
        p_hi=p_hi,
        p_lo=p_lo,
        cost_usd=cost,
        called_at=now.isoformat(),
    )


def read_calls(path: Path) -> list[JevCall]:
    """Every complete line of the log. A missing file is empty; a torn last line is skipped."""
    try:
        lines = path.read_text().split("\n")
    except FileNotFoundError:
        return []
    return [json.loads(line) for line in lines[:-1]]


def append_call(path: Path, call: JevCall) -> None:
    """Append one JSON line and fsync, first cutting a torn last line a crash left behind.

    Keys keep insertion order rather than sort_keys, so the logged request keeps its field order.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as f:
        end = f.seek(0, os.SEEK_END)
        f.seek(max(end - 1, 0))
        if end and f.read(1) != b"\n":
            f.seek(0)
            f.truncate(f.read().rfind(b"\n") + 1)
        f.write((json.dumps(call) + "\n").encode())
        f.flush()
        os.fsync(f.fileno())


def write_policy(table: pl.DataFrame, data_dir: Path) -> tuple[bool, str]:
    buffer = io.BytesIO()
    table.write_parquet(buffer)
    parquet = buffer.getvalue()
    path = data_dir / POLICY_PATH
    changed = not (path.exists() and path.read_bytes() == parquet)
    if changed:
        atomic_write(path, parquet)
    return changed, hashlib.sha256(parquet).hexdigest()
