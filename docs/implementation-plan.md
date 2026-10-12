# Jev Trader implementation plan

> **This plan will change.** It records the design on 2026-10-12, before any code exists. Treat each milestone as the current best guess. When an experiment or a review changes a decision, edit the plan and add a dated line to the [decision log](#decision-log). The product goals live in [product-spec.md](product-spec.md).

## Architecture

The Python research package computes everything and writes versioned files. The Next.js site reads those files and renders them statically. Nothing runs on a server.

```text
Twelve Data ──▶ research/ (uv package `jevtrader`)
                  data.py      fetch, validate, Parquet snapshots + manifest
                  states.py    indicators, versioned state classifier, vote tables
                  jev.py       prompt versions, OpenRouter call, append-only JSONL log, policy table
                  evaluate.py  policy join, arms, metrics, block bootstrap, holdout lock
                  export.py    web export contract
                  cli.py       jt fetch | states | ceiling | jev-table | evaluate | holdout | export
                      │
                      ▼ export/v1/*.json
                web/ (Next.js static export, zod-validated at build time)
```

Each module owns one area of the domain. The web app never recomputes an indicator or a metric.

| Need | Choice now | Change when |
|---|---|---|
| Storage | Local files under `data/` (gitignored), `pathlib` | The site deploys and needs shared files. Then swap the read and write functions for S3. |
| Jev call log | `jev_calls.jsonl`, append-only, committed to git | The log grows past what git handles well. |
| Backend | None | Users need parameters that cannot be precomputed. |
| Hosting | Static export | Same as backend. |

## Core data shapes

```python
Split = Literal["warmup", "fit", "validate", "holdout"]  # fit 2008-2014, validate 2015-2018, holdout 2019-

@dataclass(frozen=True)
class State:  # "states/v1". No ticker, date, or price level, so Jev cannot recall history.
	rsi14: Literal["OVERSOLD", "WEAK", "NEUTRAL", "STRONG", "OVERBOUGHT"]
	vs_sma200: Literal["ABOVE", "BELOW"]
	sma50_vs_sma200: Literal["ABOVE", "BELOW"]
	macd_hist: Literal["POS_RISING", "POS_FALLING", "NEG_RISING", "NEG_FALLING"]
	bollinger: Literal["BELOW_LOWER", "LOWER_HALF", "UPPER_HALF", "ABOVE_UPPER"]
	atr_regime: Literal["LOW", "NORMAL", "HIGH"]  # ATR as % of price, tercile over trailing 252 bars
	# 5 * 2 * 2 * 4 * 4 * 3 = 960 states

class StateRow(TypedDict):  # states/{symbol}.parquet
	symbol: str
	date: date
	split: Split
	state_key: str  # sha256 of canonical State JSON
	state_version: str
	fwd_ret_20: float | None  # open[t+21] / open[t+1] - 1 on adjust=all bars
	up_20: bool | None

class JevCall(TypedDict):  # jev_calls.jsonl
	call_key: str  # sha256(model_requested, prompt_version, state_key, sample)
	sample: int
	key_order_seed: int  # varies state key order across samples; measures noise, is not a debias
	model_requested: Literal["typesafe/jev-1.13"]
	model_served: str  # the response `model` field
	prompt_version: str
	state_key: str
	request: dict  # verbatim
	response: dict  # verbatim
	p_hi: float  # P(yes) for "higher in 20 trading days"
	p_lo: float  # P(yes) for "lower or equal in 20 trading days"
	cost_usd: float
	called_at: str

class PolicyRow(TypedDict):  # derived from the JSONL; building fails if model_served has more than one value
	state_key: str
	prompt_version: str
	p_up: float  # mean over samples of (p_hi + 1 - p_lo) / 2
	p_sd: float
	coherence: float  # |p_hi + p_lo - 1|
	empirical_p: float  # dev-period up frequency for the state, shrunk toward the base rate
	n_dev: int

class Decision(TypedDict):  # derived by joining PolicyRow onto StateRow. Never stored as truth.
	symbol: str
	date: date
	arm: str
	score: float | None
	position: Literal[0, 1]  # held from the open of the next session

RunManifest = DevRun | HoldoutRun  # HoldoutRun requires prereg_sha256
```

The web export lives in `export/v1/`. It holds `manifest.json`, `summary.json` (the primary result, the outcome, and the metrics for each arm), `policy.json` (Jev's rulebook with readable states), and `symbols/{SYMBOL}.json` (bars, decisions, equity curves, and an `inStudy` flag). The site validates every file with zod, and a schema mismatch fails the build.

## Research method

### Universe

The study uses SPY, QQQ, IWM, DIA, and the nine original sector SPDRs (XLB, XLE, XLF, XLI, XLK, XLP, XLU, XLV, XLY). BIL supplies the cash return. ETFs avoid the survivorship bias of hand-picked stocks such as AAPL and NVDA.

### Timing

States use bars up to the close of day t. Positions fill at the open of day t+1. Positions are long or flat only. Costs are 5 bps per side, with 0, 10, and 20 bps as sensitivity runs. Flat days earn the BIL return, and Sharpe uses returns in excess of BIL.

### Jev question

The question is a pair of yes/no (Noul) questions in one request: "higher in 20 trading days?" and "lower or equal in 20 trading days?". Jev answers questions in isolation, so the pair checks whether the answers agree. Jev's first-option bias is documented for Choice questions only, so option reordering does not apply here. The model is pinned to `typesafe/jev-1.13`. The code asks Jev about every one of the 960 states, 5 samples each, once. All later work reads the frozen table.

### Arms

| Arm | What it is |
|---|---|
| `jev` | Long when `p_up > 0.5`. This is the user-facing strategy. |
| `jev_matched` | Jev with its threshold set on dev to match the vote arms' exposure. |
| `empirical_table` | Per-state up frequency from dev, shrunk toward the base rate. This is the primary comparator. |
| `vote_trend`, `vote_revert` | Two vote tables, frozen before the first Jev call. They read the same states as trend-following and as mean-reversion. |
| `sma_filter` | Long when the 50-day average is above the 200-day average. |
| `buy_hold` | Always long, total return. |
| `random_matched` | Random positions with the same exposure as `jev`. |
| `jev_labels` | A second prompt version that shows Jev Buy and Sell labels instead of descriptions. |

### Results, pre-registered before the holdout

- **Primary.** Holdout AUC of `jev` minus holdout AUC of `empirical_table`. The 95% CI comes from a bootstrap that resamples 20-session date blocks jointly across all tickers. The minimum detectable effect is computed on dev and written into `prereg.toml`. The outcome is "jev_better", "jev_worse", or "inconclusive".
- **Secondary.** Brier skill against the base rate. A calibration curve. R² of `p_up` on each vote count, to test whether Jev behaves like a vote counter. Excess Sharpe, exposure, turnover, and drawdown for every arm.

### Rules that keep the result honest

- The code iterates on prompts during fit and validate only. The cap is three prompt versions, and the report lists every version tried.
- The code does not revise the state grammar to raise the validate AUC. "The states carry no signal" is a publishable answer.
- `jt holdout` refuses to run without a committed `prereg.toml` whose hash matches. It also refuses a second run.

## Data pipeline

1. Read `TWELVE_DATA_API_KEY` only. Build request URLs in code. The `.env` URL template puts the key in the URL, so never log a URL and strip the key from archived responses.
2. Fetch each symbol with `adjust=all` and `order=asc` in two date-range calls, 1990 to 2009 and 2010 to now. One call returns at most 5,000 bars, so a single call reaches back only to about December 2006. Each call costs one credit, and the plan allows 8 credits per minute.
3. Archive each raw response as gzipped JSON under `data/raw/{symbol}/`.
4. Parse the string fields to numbers. Sort ascending. Drop a bar for a session that has not closed.
5. Validate OHLC invariants, duplicate dates, session alignment against SPY, and overnight moves over 40%.
6. Write `data/market/{symbol}.parquet` through a temp file and rename. A failed refresh leaves the previous file in place.
7. Record a manifest per symbol with the parameters, the fetch time, the row count, the date range, and the sha256 hash.

## Milestones

Each milestone ends in a command that passes or fails.

1. **Data.** `jt fetch` writes the 14 Parquet files. A one-off SPY `adjust=none` fetch confirms that adjusted opens scale like adjusted closes. The fills depend on this check.
   - Check that pytest passes on a recorded SPY fixture with no network.
   - Check that a second `jt fetch` changes no files.
   - Check that `jt fetch` prints the row count, the date range, and the 20-session up base rate for each symbol.
2. **States and ceiling.** The truncation property test passes: the state at t is the same on `df[:t]` and on the full frame. `jt ceiling` prints the state census and the validate AUC of `empirical_table` with its CI. This step needs no Jev key.
3. **Jev policy table.** One smoke call runs first, then 960 states × 5 samples. `jt jev-table --offline` rebuilds a byte-identical policy table with zero network calls. The command prints the sample spread, coherence, vote R², validate AUC, and total cost.
4. **Dev evaluation and pre-registration.** Golden tests pass: always-long equals buy and hold, and an oracle arm beats every other arm. The dev report and the MDE exist, and `prereg.toml` is committed.
5. **Holdout.** `jt holdout` writes the result once. A second run exits non-zero. A rerun from the manifest is byte-identical.
6. **Web.** `next build` passes with zod validation. Drive the built site and confirm that every number matches `export/`.

## Jev access

Use OpenRouter `POST https://openrouter.ai/api/alpha/decisions` with model `typesafe/jev-1.13`, called through `httpx`. It needs only an OpenRouter API key and no TypeSafe account. The endpoint is labelled alpha. The risk stays small because the policy table is built once and frozen. The estimated total cost is under $1, computed as 960 states × 5 samples × 2 prompt versions × about 700 tokens at $0.042 per million input tokens. The key is needed at milestone 3, not before.

## Open questions

- Does OpenRouter require a minimum credit purchase? Unverified.
- Which disclaimers does a public site that shows trading signals need?

## Risks

These risks are ranked by impact on the answer.

1. **Low statistical power.** The holdout has about 98 independent 20-session windows, and the ETFs move together. The joint-date bootstrap and the published MDE make an "inconclusive" result readable.
2. **Look-ahead bias.** The main sources are partial bars, percentiles computed over the full sample, and fills at the close. The truncation test and open fills guard against these.
3. **Jev drift.** Probabilities vary between runs, and the alias can move. The pinned model, the recorded `model_served`, and the frozen table guard against this.
4. **Memorization.** TypeSafe publishes no training cutoff. Anonymized states carry no ticker, date, or price to recall.
5. **Misleading UI.** The honesty rules in the product spec guard against this.

## Decision log

- **2026-10-12.** Research engine in Python. Static Next.js site reading exported files. No server, database, or AWS yet.
- **2026-10-12.** Descriptive states are the primary arm. Buy and Sell labels are a secondary arm.
- **2026-10-12.** Position-free question with a 20-session horizon, asked as a pair of yes/no (Noul) questions.
- **2026-10-12.** The primary metric is AUC against a shrunk empirical table. Sharpe at the 0.5 threshold stays as the site headline.
- **2026-10-12.** ETF universe. Dev runs 2008-2018 because the data starts in December 2006. Holdout runs 2019 to now.
- **2026-10-12.** Jev access goes through OpenRouter. All 960 states are asked once, and the table is frozen.
- **2026-10-12.** The plan publishes null and inconclusive results.
- **2026-10-12.** Cut from v1: fsspec, SQLite, exchange_calendars, permanent unadjusted copies, stock split assertions, the memorization probe, the live-testing cron, and logistic regression.
- **2026-10-12.** Milestone 1 measured the data. Twelve Data has full history: SPY from 1993-01-29, DIA from 1998-01-20, the sector funds from 1998-12-22, QQQ from 1999-03-10, IWM from 2000-05-26, and BIL from 2007-05-30. "The data starts in December 2006" was wrong. It was the reach of one 5,000-bar call. Dev still starts in 2008, because BIL supplies the cash return and starts in May 2007.
- **2026-10-12.** Adjusted opens scale like adjusted closes. On SPY, the largest gap between the open and close adjustment ratios is 2.2e-7, so fills at the adjusted open are sound.
- **2026-10-12.** Twelve Data allows 8 credits per minute on the current plan, read from the `api-credits-left` header. A full `jt fetch` costs 28 credits and takes about 3 minutes. python-dotenv reads the indented `.env` lines.
