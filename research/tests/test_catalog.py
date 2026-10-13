import hashlib
import json
import shutil
from datetime import date, timedelta

import numpy as np
import polars as pl
import pytest

from jevtrader import cli
from jevtrader.catalog import (
    CATALOG,
    SCOPES,
    Strategy,
    critical_value,
    decisions,
    entry,
    fingerprint,
    random_walk,
    reconcile,
    refusals,
    scope_records,
    trades,
    windows,
)
from jevtrader.evaluate import (
    ARMS,
    COSTS_BPS,
    HOLDOUT_PATH,
    backtest,
    holdout_result,
    render_json,
)
from jevtrader.export import ARENA_PATH
from jevtrader.states import ALL_STATES, CASH, STUDY, labels, state_key

END = date(2019, 6, 30)
DAYS = (date(2019, 7, 8) - date(2005, 1, 3)).days + 1
FILES = sorted(
    [
        "catalog.json",
        "comparisons.json",
        "manifest.json",
        "windows.json",
        *(f"curves/{s}.json" for s in SCOPES),
        *(f"funds/{s}.json" for s in STUDY),
    ]
)


def first_peek(strategy: Strategy, bars: pl.DataFrame) -> int | None:
    full = strategy.positions(bars).to_list()
    for t in range(bars.height):
        if strategy.positions(bars.head(t + 1))[-1] != full[t]:
            return t
    return None


def _oracle(bars: pl.DataFrame) -> pl.Series:
    long = (pl.col("fwd_ret_20") > ARMS["oracle"].threshold).fill_null(False)
    return labels(bars).select(long.cast(pl.Int8).alias("position")).to_series()


ORACLE = Strategy(
    "oracle", 1, "Oracle", "Knows the future.", "Reads fwd_ret_20.", "None.", "control", _oracle
)


@pytest.mark.parametrize("seed", [0, 1, 2])
@pytest.mark.parametrize("strategy", CATALOG.values(), ids=list(CATALOG))
def test_positions_at_t_match_on_bars_truncated_at_t(strategy, seed):
    assert first_peek(strategy, random_walk(seed)) is None


def test_the_oracle_fails_the_truncation_check():
    assert {seed: first_peek(ORACLE, random_walk(seed)) for seed in range(3)} == {0: 0, 1: 0, 2: 7}


def test_tripling_prices_after_a_cut_changes_no_position_before_it():
    bars = random_walk(0)
    cut = 400
    prices = ("open", "high", "low", "close")
    later = pl.col("date") > bars["date"][cut]
    tripled = bars.with_columns(
        pl.when(later).then(pl.col(c) * 3).otherwise(pl.col(c)).alias(c) for c in prices
    )

    changed = {}
    for strategy in CATALOG.values():
        before, after = strategy.positions(bars), strategy.positions(tripled)
        assert after[: cut + 1].to_list() == before[: cut + 1].to_list(), strategy.id
        changed[strategy.id] = int((after[cut + 1 :] != before[cut + 1 :]).sum())
    assert changed == {"buy_hold": 0, "golden_cross": 33, "macd_cross": 11, "bollinger_bounce": 0}


def test_bollinger_bounce_enters_below_the_lower_band_and_exits_at_the_middle():
    closes = [100.0] * 20 + [90.0, 95.0, 100.0, 99.0, 80.0, 99.0, 97.0]
    days = [date(2005, 1, 3) + timedelta(days=i) for i in range(len(closes))]
    bars = pl.DataFrame({"date": days, "close": closes})

    positions = CATALOG["bollinger_bounce"].positions(bars).to_list()

    assert positions[:20] == [0] * 20, "flat until the band exists, and 100 is not below it"
    assert positions[20:] == [1, 1, 0, 0, 1, 0, 0]


def test_fingerprints():
    assert {i: fingerprint(s) for i, s in CATALOG.items()} == {
        "buy_hold": "ef8e09363081b03701cb1c135944501402b3e3d7f70cc6a0d4e945b0b4ff215a",
        "golden_cross": "208804d03ec4ddba87a381f48b531fabb74857914ba5518cf74bd32ae88638e5",
        "macd_cross": "d9ce2e036327ac78f688a83d382c10720cfc0a644db15d916c288db90c634ed4",
        "bollinger_bounce": "9b9c73a801c944c36896505507ed677c95f3efd4d96eaed77f98fde0b1ab2a1e",
    }


def test_decisions_run_from_start_through_end_for_every_strategy_and_symbol():
    market = {s: random_walk(seed) for seed, s in enumerate(STUDY)}

    made = decisions(market, start=date(2005, 3, 1), end=date(2005, 6, 1))

    spans = made.group_by("arm", "symbol").agg(
        pl.col("date").min().alias("first"), pl.col("date").max().alias("last"), pl.len()
    )
    assert spans.height == len(CATALOG) * len(STUDY)
    assert set(spans.select("first", "last", "len").iter_rows()) == {
        (date(2005, 3, 1), date(2005, 6, 1), 93)
    }


@pytest.fixture(scope="module")
def made():
    market = {s: random_walk(seed) for seed, s in enumerate(STUDY)}
    return decisions(market, start=date(2005, 1, 1))


def committed(**changes: dict) -> list:
    entries = [entry(s) for s in CATALOG.values()]
    return [{**e, **changes.get(e["id"], {})} for e in entries]


@pytest.mark.parametrize(
    ("catalog", "flat", "expected"),
    [
        (committed(), None, []),
        (None, None, []),
        (
            [*committed(), {**entry(CATALOG["buy_hold"]), "id": "old_rule"}],
            None,
            ["catalog.json has old_rule, which CATALOG drops"],
        ),
        (
            committed(macd_cross={"fingerprint": "0" * 64}),
            None,
            [
                "macd_cross version 1 has fingerprint"
                " d9ce2e036327ac78f688a83d382c10720cfc0a644db15d916c288db90c634ed4,"
                f" not {'0' * 64} as in catalog.json. A changed rule needs a new version"
            ],
        ),
        (committed(macd_cross={"version": 0, "fingerprint": "0" * 64}), None, []),
        (None, "bollinger_bounce", ["bollinger_bounce is never long in the backtest period"]),
    ],
    ids=["clean", "first run", "dropped id", "changed rule", "new version", "never long"],
)
def test_refusals(made, catalog, flat, expected):
    if flat is not None:
        made = made.with_columns(
            pl.when(pl.col("arm") == flat).then(0).otherwise("position").alias("position")
        )

    assert refusals(catalog, made) == expected


def test_critical_value_scales_each_pair_by_its_spread_around_its_point():
    draws = np.array([[0.0, 2.0, 4.0], [1.0, 1.0, 4.0]])
    points = np.array([2.0, 1.0])

    assert critical_value(draws, points) == pytest.approx(1 + 0.9 * (3**0.5 - 1))


def test_a_portfolio_verdict_names_the_side_its_simultaneous_interval_favours():
    rng = np.random.default_rng(0)
    days = [date(2008, 1, 1) + timedelta(days=i) for i in range(400)]
    edge = {"buy_hold": 0.004, "golden_cross": 0.0, "macd_cross": 0.0, "bollinger_bounce": 0.004}
    rows = pl.concat(
        pl.DataFrame(
            {
                "arm": arm,
                "symbol": "SPY",
                "date": days,
                "ret": 0.0001 + mean + rng.normal(0, 0.01, len(days)),
                "r_cash": 0.0001,
                "position": pl.Series([1] * len(days), dtype=pl.Int8),
                "switch": False,
            }
        )
        for arm, mean in edge.items()
    )

    pairs = scope_records({bps: rows for bps in COSTS_BPS}, "portfolio").pairs

    assert [(p["a"], p["b"], p["verdict"]) for p in pairs] == [
        ("buy_hold", "golden_cross", "a_ahead"),
        ("buy_hold", "macd_cross", "a_ahead"),
        ("buy_hold", "bollinger_bounce", "no_difference"),
        ("golden_cross", "macd_cross", "no_difference"),
        ("golden_cross", "bollinger_bounce", "b_ahead"),
        ("macd_cross", "bollinger_bounce", "b_ahead"),
    ]


def weekdays(first: date, last: date) -> list[date]:
    days = (first + timedelta(days=i) for i in range((last - first).days + 1))
    return [d for d in days if d.weekday() < 5]


def test_windows_grow_from_the_last_curve_date_on_or_before_each_cutoff():
    days = [d for d in weekdays(date(2018, 12, 31), date(2024, 1, 8)) if d != date(2024, 1, 1)]
    moves = {date(2023, 12, 4): 0.25, date(2023, 12, 11): -0.2, date(2024, 1, 8): -0.1}

    def row(arm: str, symbol: str, day: date) -> tuple[int, float]:
        match arm:
            case "buy_hold":
                return 1, 0.01 if day > date(2023, 12, 20) else 0.0
            case "golden_cross":
                return int(symbol == "SPY" or day >= date(2024, 1, 3)), 0.0
            case "macd_cross":
                return 1, moves.get(day, 0.0)
        return 0, 0.0

    rows = [
        (arm, symbol, day, *row(arm, symbol, day))
        for arm in CATALOG
        for symbol in ("SPY", "QQQ")
        for day in days
    ]
    sleeves = pl.DataFrame(
        rows, schema=["arm", "symbol", "date", "position", "ret"], orient="row"
    ).with_columns(pl.lit(0.0).alias("r_cash"))

    found = windows(sleeves)

    assert [(w["range"], w["base"]) for w in found] == [
        ("1W", "2023-12-29"),
        ("1M", "2023-12-08"),
        ("3M", "2023-10-06"),
        ("1Y", "2023-01-06"),
        ("5Y", "2019-01-08"),
        ("All", None),
    ]
    figures = {
        w["range"]: {i: tuple(s.values()) for i, s in w["strategies"].items()} for w in found
    }
    assert figures["1W"] == {
        "buy_hold": (1.05101, 1.0, 0.0),
        "golden_cross": (1.0, 0.9, 0.0),
        "macd_cross": (0.9, 1.0, pytest.approx(0.1)),
        "bollinger_bounce": (1.0, 0.0, 0.0),
    }
    assert figures["1M"] == {
        "buy_hold": (1.126825, 1.0, 0.0),
        "golden_cross": (1.0, 0.6, 0.0),
        "macd_cross": (0.72, 1.0, pytest.approx(0.28)),
        "bollinger_bounce": (1.0, 0.0, 0.0),
    }
    assert figures["All"]["macd_cross"] == (0.9, 1.0, pytest.approx(0.28))
    assert figures["All"]["buy_hold"] == figures["3M"]["buy_hold"] == (1.126825, 1.0, 0.0)


def test_a_trade_falls_on_the_bar_after_the_decision():
    days = weekdays(date(2024, 1, 2), date(2024, 1, 9))
    bars = pl.DataFrame({"date": days})
    positions = {"buy_hold": [1, 1, 1, 1], "golden_cross": [0, 1, 0, 1]}
    made = pl.DataFrame(
        [
            (i, "SPY", day, p)
            for i in CATALOG
            for day, p in zip(days[:4], positions.get(i, [0] * 4), strict=True)
        ],
        schema=["arm", "symbol", "date", "position"],
        orient="row",
    )
    returns = pl.DataFrame({"symbol": "SPY", "date": days[:4], "r": 0.0, "r_cash": 0.0})

    assert trades(backtest(made, returns, 5), bars) == {
        "buy_hold": {"buy": ["2024-01-03"], "sell": []},
        "golden_cross": {"buy": ["2024-01-04", "2024-01-08"], "sell": ["2024-01-05"]},
        "macd_cross": {"buy": [], "sell": []},
        "bollinger_bounce": {"buy": [], "sell": []},
    }


@pytest.fixture(scope="module")
def template(tmp_path_factory):
    root = tmp_path_factory.mktemp("template")
    repo, data = root / "repo", root / "data"
    (repo / "research").mkdir(parents=True)
    (data / "market").mkdir(parents=True)
    market = {s: random_walk(seed, DAYS) for seed, s in enumerate((*STUDY, CASH))}
    for s, bars in market.items():
        bars.write_parquet(data / "market" / f"{s}.parquet")
    policy = pl.DataFrame(
        {
            "state_key": [state_key(s) for s in ALL_STATES],
            "p_up": np.random.default_rng(1).random(len(ALL_STATES)),
        }
    )
    (repo / HOLDOUT_PATH).write_text(render_json(holdout_result(market, policy, END)))
    return root


def test_reconcile_reproduces_the_holdout_sharpe_intervals_exactly(template):
    holdout = json.loads((template / "repo" / HOLDOUT_PATH).read_text())
    market = {
        s: pl.read_parquet(template / "data" / "market" / f"{s}.parquet") for s in (*STUDY, CASH)
    }
    made = decisions(market)

    assert reconcile(made, market, holdout) == []

    holdout["arms"]["sma_filter"]["excess_sharpe"]["lo"] = -2.25
    assert reconcile(made, market, holdout) == [
        "golden_cross excess Sharpe"
        " {'point': 0.8061769532882747, 'lo': -2.2881494329069016, 'hi': 4.137028667561658}"
        " is not {'point': 0.8061769532882747, 'lo': -2.25, 'hi': 4.137028667561658},"
        " the sma_filter arm in holdout.json"
    ]


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@pytest.fixture
def arena(tmp_path, template, monkeypatch):
    shutil.copytree(template, tmp_path, dirs_exist_ok=True)
    monkeypatch.setattr(cli, "REPO_ROOT", tmp_path / "repo")
    monkeypatch.setattr(cli, "DATA_DIR", tmp_path / "data")
    return tmp_path


def snapshot(repo) -> dict[str, tuple[bytes, int]]:
    root = repo / ARENA_PATH
    return {
        p.relative_to(root).as_posix(): (p.read_bytes(), p.stat().st_mtime_ns)
        for p in root.rglob("*")
        if p.is_file()
    }


def test_a_second_arena_run_changes_no_files_and_records_cover_the_period(arena, capsys):
    repo, data = arena / "repo", arena / "data"
    assert cli.main(["arena"]) == 0
    first = capsys.readouterr().out.splitlines()
    assert [line.split()[:2] for line in first] == [
        [f"export/arena/v1/{f}", "changed"] for f in FILES
    ]
    before = snapshot(repo)

    assert cli.main(["arena"]) == 0
    second = capsys.readouterr().out.splitlines()
    assert [line.split()[:2] for line in second] == [
        [f"export/arena/v1/{f}", "unchanged"] for f in FILES
    ]
    assert snapshot(repo) == before

    manifest = json.loads(before["manifest.json"][0])
    assert manifest["files"] == {f: sha256(before[f][0]) for f in FILES if f != "manifest.json"}
    assert manifest["inputs"] == {
        "research/holdout.json": sha256((repo / HOLDOUT_PATH).read_bytes()),
        **{
            f"data/market/{s}.parquet": sha256((data / "market" / f"{s}.parquet").read_bytes())
            for s in (*STUDY, CASH)
        },
    }
    assert manifest["periods"] == {
        "backtest": {"first": "2008-01-01", "last": "2019-07-06", "barsEnd": "2026-10-09"}
    }

    comparisons = json.loads(before["comparisons.json"][0])
    pairs, strategies = comparisons["pairs"], comparisons["strategies"]

    assert [(p["scope"], p["a"], p["b"]) for p in pairs[:6]] == [
        ("portfolio", "buy_hold", "golden_cross"),
        ("portfolio", "buy_hold", "macd_cross"),
        ("portfolio", "buy_hold", "bollinger_bounce"),
        ("portfolio", "golden_cross", "macd_cross"),
        ("portfolio", "golden_cross", "bollinger_bounce"),
        ("portfolio", "macd_cross", "bollinger_bounce"),
    ]
    assert [p["scope"] for p in pairs[::6]] == list(SCOPES)
    assert [s["scope"] for s in strategies[::4]] == list(SCOPES)
    assert {p["verdict"] for p in pairs[6:]} == {None}
    assert {p["family"] for p in pairs} == {6}

    spy = json.loads(before["curves/SPY.json"][0])
    curve = spy["periods"]["backtest"]
    assert (curve["date"][0], curve["date"][-1]) == ("2008-01-01", "2019-07-06")
    bars = pl.read_parquet(data / "market" / "SPY.parquet")
    opens = dict(zip(bars["date"].cast(pl.String), bars["open"], strict=True))
    r = opens["2008-01-03"] / opens["2008-01-02"] - 1
    assert curve["equity"]["buy_hold"][0] == round((1 - 5 / 1e4) * (1 + r), 6)


def test_arena_refuses_a_changed_rule_and_a_dropped_strategy(arena, capsys):
    repo = arena / "repo"
    assert cli.main(["arena"]) == 0
    path = repo / ARENA_PATH / "catalog.json"
    catalog = json.loads(path.read_text())
    catalog["strategies"][2]["fingerprint"] = "0" * 64
    catalog["strategies"].append({**catalog["strategies"][0], "id": "old_rule"})
    path.write_text(json.dumps(catalog, indent=2) + "\n")
    before = snapshot(repo)
    capsys.readouterr()

    assert cli.main(["arena"]) == 1
    captured = capsys.readouterr()
    assert captured.err == (
        "macd_cross version 1 has fingerprint"
        " d9ce2e036327ac78f688a83d382c10720cfc0a644db15d916c288db90c634ed4,"
        f" not {'0' * 64} as in catalog.json. A changed rule needs a new version\n"
        "catalog.json has old_rule, which CATALOG drops\n"
        f"refusing, {repo / ARENA_PATH} is unchanged\n"
    )
    assert captured.out == ""
    assert snapshot(repo) == before


def test_the_arena_windows_and_funds_agree_with_the_curves_and_comparisons(arena):
    repo, data = arena / "repo", arena / "data"
    assert cli.main(["arena"]) == 0

    def read(path: str) -> dict:
        return json.loads((repo / ARENA_PATH / path).read_text())

    windows_file, portfolio = read("windows.json"), read("curves/portfolio.json")
    curve = portfolio["periods"]["backtest"]

    assert (windows_file["scope"], windows_file["last"]) == ("portfolio", "2019-07-06")
    assert [(w["range"], w["base"]) for w in windows_file["windows"]] == [
        ("1W", "2019-06-29"),
        ("1M", "2019-06-06"),
        ("3M", "2019-04-06"),
        ("1Y", "2018-07-06"),
        ("5Y", "2014-07-06"),
        ("All", None),
    ]
    whole = windows_file["windows"][-1]["strategies"]
    rows = read("comparisons.json")["strategies"]
    for i in CATALOG:
        (row,) = (r for r in rows if r["id"] == i and r["scope"] == "portfolio")
        assert whole[i] == {
            "growth": curve["equity"][i][-1],
            "exposure": row["exposure"],
            "maxDrawdown": row["maxDrawdown"],
        }
    year = windows_file["windows"][3]["strategies"]["buy_hold"]["growth"]
    at = curve["date"].index("2018-07-06")
    assert year == pytest.approx(curve["equity"]["buy_hold"][-1] / curve["equity"]["buy_hold"][at])

    spy = read("funds/SPY.json")
    bars = pl.read_parquet(data / "market" / "SPY.parquet").filter(
        pl.col("date") >= date(2008, 1, 1)
    )
    assert spy["symbol"] == "SPY"
    assert (spy["date"][0], spy["date"][-1], len(spy["date"])) == (
        "2008-01-01",
        "2019-07-08",
        bars.height,
    )
    assert spy["close"][0] == round(bars["close"][0], 4)
    assert spy["trades"]["buy_hold"] == {"buy": ["2008-01-02"], "sell": []}
    for symbol in STUDY:
        fund = read(f"funds/{symbol}.json")
        assert list(fund["trades"]) == list(CATALOG)
        for i, side in fund["trades"].items():
            assert set(side["buy"] + side["sell"]) <= set(fund["date"]), (symbol, i)
            marked = sorted([(d, "buy") for d in side["buy"]] + [(d, "sell") for d in side["sell"]])
            sides = [s for _, s in marked]
            assert sides == [("buy", "sell")[k % 2] for k in range(len(sides))], (symbol, i)
