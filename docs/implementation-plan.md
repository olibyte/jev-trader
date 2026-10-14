# Trade arena implementation plan

> **This plan will change.** It recorded the Jev study design on 2026-10-12 and adds the trade arena on 2026-10-13. Treat each milestone as the current best guess. When an experiment or a review changes a decision, edit the plan and add a dated line to the [decision log](#decision-log). The product goals live in [product-spec.md](product-spec.md). The [arena synthesis](arena/2026-10-13-trade-arena/synthesis.md) records the candidate concepts, the judging, and the grafts behind milestones 7 to 11.

## Architecture

The Python research package computes everything and writes versioned files. The Next.js site reads those files and renders them statically. Nothing runs on a server. Planned modules and commands are marked "planned".

```text
Twelve Data ──▶ research/ (uv package `jevtrader`)
                  data.py      fetch, validate, Parquet snapshots + manifest
                  states.py    indicators, candle flags (planned), versioned state classifier, vote tables, purged labels
                  jev.py       prompt versions, OpenRouter call, append-only JSONL log, policy table
                  evaluate.py  policy join, arms, backtest, metrics, block bootstrap, holdout lock
                  catalog.py   arena strategies: CATALOG, positions, fingerprints, comparisons
                  export.py    web export contracts: export/v1 (Jev study), export/arena/v1 (arena)
                  cli.py       jt fetch | states | ceiling | jev-table | evaluate | holdout | export | arena
                      │
                      ▼ export/v1/*.json, export/arena/v1/*.json
                web/ (Next.js static export, zod-validated at build time)
```

Each module owns one area of the domain. The web app never recomputes an indicator or a metric.

| Need | Choice now | Change when |
|---|---|---|
| Storage | Local files under `data/` (gitignored), `pathlib` | The site deploys and needs shared files. Then swap the read and write functions for S3. |
| Jev call log | `jev_calls.jsonl`, append-only, committed to git | The log grows past what git handles well. |
| Backend | None | A learner needs a result that `jt arena` cannot compute in advance, such as a parameter they set or a rule they build. The product spec names the prerequisites. |
| Hosting | Static export in `web/out/`, to be served from S3 behind CloudFront and managed with Terraform. Not deployed yet. | The same trigger as the backend. |
| Live scoring | None yet | Milestone 11 adds a nightly GitHub Actions job that fetches bars, appends positions to a ledger on the `ledger` branch, and rebuilds the static files. |

## Core data shapes

### Arena

```python
Period = Literal["backtest", "live"]
Kind = Literal["benchmark", "indicator", "candlestick", "ml", "jev", "control"]

@dataclass(frozen=True)
class Strategy:  # catalog.py. CATALOG: dict[str, Strategy] is append-only.
	id: str  # "macd_cross"
	version: int  # a changed rule is a new version, never an edit
	title: str
	plain: str  # one sentence for a visitor who has never traded, shown under the strategy slot
	rule: str  # the exact rule, shown in the technical section
	citation: str  # where the textbook parameters come from
	kind: Kind
	positions: Callable[[pl.DataFrame], pl.Series]  # adjusted bars -> 0 or 1 per session, decided at the close of t

class CatalogEntry(TypedDict):  # export/arena/v1/catalog.json
	id: str
	version: int
	title: str
	plain: str
	rule: str
	citation: str
	kind: Kind
	fingerprint: str  # sha256 of positions on random_walk(0..2) bars from catalog.py

class PairRecord(TypedDict):  # export/arena/v1/comparisons.json, one per pair, scope, and period
	a: str
	b: str  # a precedes b in catalog order
	scope: str  # "portfolio" or a symbol
	period: Period
	blocks: int  # 20-session blocks the bootstrap resamples
	diff: Interval  # excess Sharpe of a minus b at 5 bps, plain 95% interval
	simultaneous: Interval  # 95% interval that covers the whole family at once
	family: int  # pairs in the catalog version, n * (n - 1) / 2
	mde: float  # smallest difference this period can detect at 80% power, with the simultaneous critical value
	verdict: Literal["a_ahead", "b_ahead", "no_difference", "too_early"] | None  # None off the portfolio scope

class StrategyRecord(TypedDict):  # export/arena/v1/comparisons.json, one per strategy, scope, and period
	id: str
	scope: str
	period: Period
	blocks: int
	excessSharpe: Interval  # at 5 bps, plain 95% interval
	excessSharpeByCost: list[dict]  # {"costBps", "value"} at 0, 5, 10, and 20 bps, point values
	maxDrawdown: float  # point values from here on, at 5 bps
	switchesPerYear: float
	exposure: float

class WindowRecord(TypedDict):  # export/arena/v1/windows.json, one per range button, portfolio scope
	range: Literal["1W", "1M", "3M", "1Y", "5Y", "All"]
	base: str | None  # last curve date on or before `last` minus the range, None for All
	strategies: dict[str, WindowStats]  # growth (equity at last / equity at base), exposure, maxDrawdown over the dates after base

class Trades(TypedDict):  # export/arena/v1/funds/{symbol}.json, one per strategy
	buy: list[str]  # the bar after each decision that moved the strategy into the market
	sell: list[str]  # the bar after each decision that moved it to cash

class LedgerRow(TypedDict):  # arena/ledger.jsonl on the `ledger` branch (planned, milestone 11), append-only
	date: date  # the session whose close made the decisions
	catalog_version: int
	positions: dict[str, dict[str, Literal[0, 1]]]  # strategy id -> symbol -> position
	bars_sha256: str  # hash of the bars the decisions read
```

The arena export lives in `export/arena/v1/` beside `export/v1/`, which does not change. It holds `manifest.json` (period bounds, the catalog version, input and output hashes), `catalog.json`, `comparisons.json`, `curves/{scope}.json` (growth of $1 for each strategy in each period), `windows.json` (each range button's figures on the portfolio), and `funds/{symbol}.json` (the daily bars from 2008-01-02 through `barsEnd` and each strategy's trades). A file has no `start`, `end`, or `symbols` field that could carry a chosen window. The only windows are the fixed ranges in `windows.json`, each counted back from `last`. The period bounds live only in the manifest. For each period, `first` and `last` are the first and last decision dates that earn a return, and every record and curve covers exactly those dates. `barsEnd` is the last bar the decisions read. For the backtest period of catalog version 1, `first` is 2008-01-02, `last` is 2026-10-07, and `barsEnd` is 2026-10-09, because a decision at the close of t earns the open of t+1 to the open of t+2.

### Jev study (finished)

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
	coherence: float  # mean over samples of |p_hi + p_lo - 1|

class Decision(TypedDict):  # derived by joining PolicyRow onto StateRow. Never stored as truth.
	symbol: str
	date: date
	arm: str
	score: float | None
	position: Literal[0, 1]  # held from the open of the next session

class HoldoutRun(TypedDict):  # research/holdout.manifest.json
	prereg_sha256: str
	git_commit: str
	result_sha256: str  # of research/holdout.json

RunManifest = DevRun | HoldoutRun
```

The web export lives in `export/v1/` and is committed to git. It holds `manifest.json` (the study versions, the dataset hashes, the two runs, and the hash of every other file), `summary.json` (the primary result, the outcome, and the metrics for each arm, copied from `research/holdout.json`), `policy.json` (Jev's rulebook with readable states, the five logged samples, and each state's development frequency), and `symbols/{SYMBOL}.json` (columnar sessions with bars, states, Jev positions, and forward returns, the holdout equity curves, and an `inStudy` flag). `jt export` writes it. The site validates every file with zod at build time, and a schema mismatch or a file hash that differs from `manifest.json` fails the build.

## Arena method (planned)

### Strategies

`CATALOG` in `catalog.py` holds the strategies. The study's `ARMS` registry stays as it is. An arm is `score > threshold` on one session, so it cannot express an exit or a hold of N sessions, and `evaluate.decisions` reads only the fixed `ARMS` dict. A strategy is a causal function `positions(bars)` instead. Its output becomes the `position` column that `evaluate.backtest` already reads, so the arena reuses the study's fills, costs, cash return, and portfolio unchanged.

Catalog version 1 has the 8 entries in the product spec. Their parameters come from the textbook sources that each entry cites, and no entry is tuned on these bars.

- Buy and hold and the golden cross reproduce the study's `buy_hold` and `sma_filter` arms exactly.
- The MACD crossover and the Bollinger bounce reuse the indicator expressions in `states.levels`, at full precision rather than as levels.
- The bullish engulfing pattern reads `candles(bars)`, a new function beside `levels()` in `states.py`. Row t reads bars up to t only, and the pattern reads t-1 and t.
- The learned model is an L2 logistic regression from scikit-learn on one-hot `State` levels and candle flags. It refits each January on rows whose label exit open falls before the refit date. This generalises the split purge in `states.labels` to every refit date, in new code. `SPLIT_STARTS` does not change.
- Jev (frozen rulebook) reads `data/policy/jev.parquet`, rebuilt by `jt jev-table --offline`. It is long when `p_up > 0.5`, as the `jev` arm is.
- The coin flip draws one seeded coin for each symbol and each 20-session block.

### Periods

The backtest period runs from 2008-01-02, the start of fit, to the last bar before the catalog version froze. For catalog version 1, the end is 2026-10-09, the last bar on hand and the prereg end. The live period starts at the first session after the freeze. Warmup bars from before 2008 feed the indicators and the first refit of the learned model.

The arena has no development and holdout split. Whoever built the catalog had seen 2019 to 2026, so those years are not a holdout for any entry. Two backtest windows would also double the family and offer a window to choose.

### Comparisons

- **Metric.** The difference in annualised excess Sharpe (`evaluate.sharpe`) at 5 bps (`COST_BPS`), on the equal-weight portfolio of the 13 sleeves (`evaluate.portfolio`) or on one sleeve. Costs of 0, 10, and 20 bps are point values.
- **Intervals.** `evaluate.block_bootstrap` with seed 0, 2,000 reps, and 20-session blocks, unchanged. It creates its generator inside each call, so the same dates and seed draw the same blocks for every pair. Each rep therefore gives one draw for every pair in the family.
- **Simultaneous interval.** For each pair and rep, divide the draw's deviation from the pair's point value by the standard deviation of the pair's draws. Take the 95th percentile, across reps, of the largest absolute value of that ratio over the family. The simultaneous interval is the point plus or minus that critical value times the pair's standard deviation. For 6 pairs, a scratch run gave 2.53 instead of 1.96.
- **Verdict.** On the portfolio scope, "a_ahead" or "b_ahead" when the simultaneous interval excludes zero, and "no_difference" otherwise. In the live period, "too_early" below 3 blocks. Single-symbol scopes get no verdict.
- **MDE.** (critical value + z(0.8)) times the pair's bootstrap standard deviation, the study's MDE formula with the simultaneous critical value.

### Rules that keep the arena honest

- `jt arena` reads the full-precision Parquet bars, never the 4-decimal prices in `export/v1/`. Rounding to 4 decimals flipped 34 indicator cells in a scratch run.
- `jt arena` refuses to run unless `buy_hold` and the golden cross, cut to 2019-01-02 through 2026-10-09, reproduce the `buy_hold` and `sma_filter` excess Sharpe intervals in `research/holdout.json` exactly.
- `jt arena` refuses a strategy whose fingerprint differs from `catalog.json` for the same id and version, a strategy that is never long in the backtest period, and a catalog that drops an id from the committed `catalog.json`.
- The truncation property test runs over every catalog entry: the position at t on `bars.head(t + 1)` equals the position at t on the full frame, on `random_walk` bars. The `oracle` arm, which reads `fwd_ret_20`, must fail the same test, as a negative control.
- Tripling every price after a cut date changes no position before it.

## Markets and "Which one wins?" (deferred)

The [deferred "Which one wins?" spec](which-wins-spec.md) reframes the arena question and adds markets, each a universe on one bar size. Statistics are deferred, so the verdict parts wait. Milestone 12 builds the hourly market's data, backtest, and screen. The verdict rule does not change. This section lists what the change touches and what stays.

### What stays

- `evaluate.py` does not change. `open_returns`, `backtest`, and `portfolio` run on any bar key, so an intraday portfolio returns to equal parts at every bar. Every market compounds the portfolio's bar returns into one return per session, so `sharpe` (with `YEAR` = 252), `block_bootstrap` (20-session blocks), and `portfolio` serve every market. A simulation of 2,000 runs of 5 years gave the same spread of annualised Sharpe on daily, hourly, and 5-minute bars (0.45, 0.46, and 0.46), so per-bar Sharpe would gain no precision.
- The `PairRecord` verdict enum (`a_ahead`, `b_ahead`, `no_difference`, `too_early`) does not change. Only the labels that the site shows change.
- `positions(bars)` and the fingerprints do not change. A rule reads bars, whatever their size.
- The Jev study and its frozen files do not change.

### What changes

- **The arena contract.** `export/arena/v1/` has no market field, and the Trade Arena prototype already reads it. Milestone 12 moves the export to `export/arena/v2/`, with one folder for each market, and deletes v1.
- **The family.** `catalog.scope_records` computes a critical value for one market's pairs. The simultaneous interval over all markets needs one draw of blocks on a calendar that every market shares. `block_bootstrap` can serve this unchanged if each pair's statistic receives weights on the union of the markets' dates and reads only its own. Markets with shorter histories add no weight before their first date.
- **The catalog.** Jev (frozen rulebook) and the learned model read the daily `State` and a 20-session horizon. `Strategy` gains the markets an entry plays in, and the family counts pairs per market.
- **The data pipeline.** `data.py` is daily only. Bars are keyed by a `date` column, `closed_bars` settles a bar at 20:00 New York time, `validate` compares sessions with SPY and flags open-to-previous-close moves over 40%, and `RANGES` and `OUTPUTSIZE` are sized for daily history. Intraday bars need a timestamp key, a regular-hours filter, and a session check for each bar. Hourly bars need no paged backfill, because the user chose one 5,000-bar call for each symbol.
- **Backfill.** One call costs 1 credit for each symbol and returns up to 5,000 bars. Twenty years of hourly bars for 13 ETFs takes about 104 calls. Twenty years of 1-minute bars takes about 5,100, which is about 11 hours at 8 credits a minute, or 7 days at 800 credits a day. These counts are arithmetic from the published limits, not a measured run.
- **Storage.** Twenty years of 1-minute bars is about 2 million rows for each symbol. That fits in `data/`, which is not committed. The committed hourly curve keeps one point per bar, about 5,000, so the 1D and 1W ranges draw a line.
- **The volatile-stock universe.** `STUDY` is a fixed tuple, and `catalog.decisions` loops over it. A universe that changes each January needs a table of symbols by year, and `open_returns` needs a cash return for a stock after its last bar.
- **The live period.** The nightly job of milestone 11 records intraday positions after the close, so the ledger proves the order of each day's decisions, not each bar's. The replay still fails a rule that reads a later bar.
- **The site and the docs.** If verdicts return, the first screen, `web/src/lib/format.ts`, `web/e2e/expected.ts`, `check:honesty`, and the README tagline change wording.

### Learner verdicts (planned, no milestone)

The [learner-verdict arena](arena/2026-10-13-learner-verdicts/synthesis.md) settled which pairs a learner rule's verdict covers. The backend that scores learner rules inherits these requirements:

- **The family.** One rule's pairs with every catalog entry in every market where its inputs exist: 8 pairs on daily ETFs, with a critical value of 2.65 on synthetic data. Learner pairs never join the catalog family, so a save changes no other verdict.
- **The luck line.** The expected count of luck wins and its 95th percentile come from a null simulation on the real save dates. False wins arrive in bursts when one catalog entry has a bad stretch, so the 95th percentile ran about 3 times the mean.
- **Short windows.** Rules start on different dates. Each save cohort gets its own bootstrap draw, or exponential block weights, because a shared multinomial draw gives a 3-block window zero weight in about 5% of reps.
- **Compute.** The per-pair `block_bootstrap` loop took about 20 ms a pair, or about 25 minutes a night at 10,000 rules. Vectorized draws, one of which reproduces `block_bootstrap` to 5e-15, took 1.6 to 40 s across the four candidates.
- **Storage.** At 10,000 rules, the ledger holds about 33 million positions a year. It outgrows the git `ledger` branch, so learner results live in the backend store, not in a committed export.
- **Attack checks.** Candidate 4's clone and loser-flood attacks become tests of the luck line.

### Data source for volatile stocks (proposed)

Milestone 13 needs listings for each past date that include delisted stocks, daily bars for every US common stock, and terms that allow publishing figures derived from those bars. "Checked" means read on the provider's own page on 2026-10-13. "Unchecked" means read on a third-party page or not found.

| Source | What it offers | Checked | Unchecked |
|---|---|---|---|
| Massive, formerly Polygon.io (proposed) | A ticker list as of any date, daily bars for all US stocks in one file per day, and FIGI and CIK identifiers | The All Tickers `date` parameter returns "tickers available on that date". `active=false` returns delisted tickers, with `delisted_utc`. Daily files and the daily market summary cover all US stocks from 2003-09-10, with full history on the Advanced and Business plans. Bars are split-adjusted by default, and a dividends endpoint exists. | Whether a past daily file holds stocks delisted since. Dividend adjustment of the bars. Display and redistribution terms. Delisting reasons. Historical quotes for measuring spreads. Price. |
| Twelve Data (current provider) | `/stocks?include_delisted=true` | The flag exists on `/stocks` and `/etfs`. The response has no listing or delisting date. `/time_series` accepts a FIGI on the Ultra and Enterprise plans. | Whether `/time_series` returns bars for a delisted symbol, and how far back. The count of delisted US symbols. One call per symbol would take tens of thousands of calls. |
| CRSP, through WRDS | The research standard, including delisting returns | None | Delisting returns, coverage, license terms, and price. Shumway (1997) found delisting returns missing for most stocks delisted for poor performance. |
| Norgate Data | Listed and delisted US stocks | Its FAQ calls US listed and delisted coverage "essentially complete back to late 1992". | Delisted stocks only in the Platinum and Diamond plans. License terms, price, and the delivery software. |
| Sharadar, through Nasdaq Data Link | US prices with a tickers table | QuantRocket's documentation lists Sharadar end-of-day prices from 1998. | Delisted coverage. Table fields. License terms. |
| EODHD | A delisted-symbol list | `exchange-symbol-list/US?delisted=1` lists inactive symbols with no delisting date, and delisted tickers keep their end-of-day history. | Handling of reused tickers. Plan and terms. |

Massive is the proposal because it is the only source checked to answer "which stocks were listed on this date" directly, and its daily files hold the whole market for a date, which is the input the universe rule needs. CRSP is the fallback if the terms or the delisted coverage fail, and it is the only source that records delisting returns. Three probes settle the unchecked facts before any purchase, and the user runs them, because they call a paid API:

1. A daily file from 2008 holds a stock that was delisted in 2008.
2. All Tickers with `date=2008-06-02` and `active=true` lists that stock.
3. The license allows publishing strategy curves and figures derived from the bars.

## Jev study method (finished)

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
- `jt holdout` refuses to run without a committed `prereg.toml` that matches the code and the hash of every input file. It also refuses a second run.

## Data pipeline

1. Read `TWELVE_DATA_API_KEY` only. Build request URLs in code. The `.env` URL template puts the key in the URL, so never log a URL and strip the key from archived responses.
2. Fetch each symbol with `adjust=all` and `order=asc` in two date-range calls, 1990 to 2009 and 2010 to now. One call returns at most 5,000 bars, so a single call reaches back only to about December 2006. Each call costs one credit, and the plan allows 8 credits per minute.
3. Archive each raw response as gzipped JSON under `data/raw/{symbol}/`.
4. Parse the string fields to numbers. Sort ascending. Drop a bar for a session that has not closed.
5. Validate OHLC invariants, duplicate dates, session alignment against SPY, and overnight moves over 40%.
6. Write `data/market/{symbol}.parquet` through a temp file and rename. A failed refresh leaves the previous file in place.
7. Record a manifest per symbol with the parameters, the fetch time, the row count, the date range, and the sha256 hash.
8. `jt fetch --bars 1h` fetches hourly bars in one call per symbol. It keeps regular hours from the first full session, checks each session against the daily snapshot, and writes under `data/market/1h/` and `data/raw/1h/`.

## Milestones

Each milestone ends in a command that passes or fails.

1. **Data.** `jt fetch` writes the 14 Parquet files. A one-off SPY `adjust=none` fetch confirms that adjusted opens scale like adjusted closes. The fills depend on this check.
   - Check that pytest passes on a recorded SPY fixture with no network.
   - Check that a second `jt fetch` changes no files.
   - Check that `jt fetch` prints the row count, the date range, and the 20-session up base rate for each symbol.
2. **States and ceiling.** The truncation property test passes: the state at t is the same on `df[:t]` and on the full frame. `jt ceiling` prints the state census and the validate AUC of `empirical_table` with its CI. This step needs no Jev key.
3. **Jev policy table.** One smoke call runs first, then 960 states × 5 samples. `jt jev-table --offline` rebuilds a byte-identical policy table with zero network calls. The command prints the sample spread, coherence, vote R², validate AUC, and total cost.
4. **Dev evaluation and pre-registration.** Golden tests pass: always-long equals buy and hold, and an oracle arm beats every other arm. The dev report and the MDE exist, and `prereg.toml` is committed.
5. **Holdout.** `jt holdout` writes the result once. A second run exits non-zero. `jt holdout --verify` reruns from the manifest and confirms that the result is byte-identical.
6. **Web.** `jt export` writes `export/v1/`, and a second run changes no files. `next build` passes with zod validation, and a schema mismatch fails the build. Drive the built site and confirm that every number matches `export/`.

Milestones 1 to 6 are merged. The arena milestones follow. Each one ships alone.

7. **Arena research.** Add `catalog.py` with buy and hold, the golden cross, the MACD crossover, and the Bollinger bounce. Add `jt arena`, which writes `export/arena/v1/` for the portfolio and the 13 symbols over the backtest period. The site does not change.
   - Check that `uv run python -m pytest tests/test_catalog.py` passes. It holds the truncation test over `CATALOG`, the `oracle` negative control, the fingerprints, the refusal of a never-long strategy, and the refusal of a dropped id.
   - Check that `jt arena` passes its reconciliation with `research/holdout.json` on the real data.
   - Check that a second `uv run jt arena` reports every file unchanged.
8. **Arena first screen.** The home page becomes the "Pick two" screen in the product spec, built from the prototype at `/preview/`. The study pages move unchanged to `/studies/jev/`. `web/src/lib/arena.ts` reads `export/arena/v1/` with zod schemas, so a bad file fails `next build`. `check:honesty` bans the first-screen words in the product spec's copy rules 1 and 2.
   - Check that all five `web/` checks pass.
   - Check with Playwright that every dollar amount, share, and gap on the home page matches `export/arena/v1/` for every pair, and that the `/studies/jev/` pages still match `export/v1/`.
9. **Candlestick, machine-learning, Jev, and control entries.** Deferred on 2026-10-14. Add `candles()` to `states.py` and a feature registry that the truncation test runs over. Add the bullish engulfing pattern, the learned model, Jev (frozen rulebook), and the coin flip. Catalog version 1 then has 8 entries and 28 pairs, and it freezes.
   - Check that the truncation test passes for every entry, including the learned model at 20 seeded dates.
   - Check that the purge test passes: no training row for a refit at date R has an exit open on or after R.
   - Check that tripling every price after a cut date changes no position before it.
   - Check that a second `jt arena` reports every file unchanged, and rerun the five `web/` checks.
10. **Deploy.** Terraform creates the S3 bucket, the CloudFront distribution, and the CloudFront function that appends `index.html` to paths that end in `/`. The user runs `terraform apply`.
    - Check that a script requests every file in `web/out/` from the CloudFront URL, gets status 200, and gets the same bytes.
11. **Live period.** Deferred on 2026-10-14. `jt arena tick` reads the latest bars, decides each strategy's positions at the last close, and appends one `LedgerRow` before the next bar exists. `jt arena verify` replays every strategy over the current bars and fails unless each past position equals its ledger row. A nightly GitHub Actions job runs `jt fetch`, `jt arena tick`, `jt arena`, and the deploy after each close. It commits the ledger to the `ledger` branch, reads `TWELVE_DATA_API_KEY` from a repository secret, and deploys to AWS through a GitHub OIDC role, so no AWS key is stored. `jt fetch` spends Twelve Data credits, so the user starts the first run.
    - Check that `tests/test_arena_live.py` passes on synthetic bars in a temporary git repository: 30 simulated sessions append 30 rows, the replay equals the ledger, an edited row fails `verify`, a strategy that reads the next bar fails `verify`, and a second tick on the same bars changes no file.
    - Check that `jt arena verify` exits 0 after the user runs one `jt fetch` and one `jt arena tick`.
12. **Hourly ETF market, without statistics.** Planned on 2026-10-14, by the user's decision. The product spec's "Hourly bars come next" section describes the screen. Three PRs, in order. Each ends in its checks. Statistics, the family over both markets, and verdicts stay deferred.
    1. **Fetch hourly bars (PR 12a, `research/` only).** A `BarSize` table in `data.py` holds what differs between bar sizes: the Twelve Data interval, the request windows, whether a full 5,000-bar response is expected or an error, and the snapshot folder. The `1day` entry reproduces today's fetch exactly. The `1h` entry makes one call for each of the 14 symbols, BIL included, with `interval=1h`, `adjust=all`, `outputsize=5000`, and `end_date=2026-10-10`. That day is a Saturday, so the bars end on Friday 2026-10-09, the daily `barsEnd`, whether or not `end_date` includes its own day. The fetch fails unless the last session is 2026-10-09. `parse_response` keeps `time` (New York clock time) and `date` (the session). The fetch drops bars outside 09:30 to 16:00 and drops the bars before the first 09:30 bar, because the 5,000-bar window starts mid-session. `validate` checks duplicate times and each symbol's timestamps against SPY's. A new check compares each session's first hourly open and last hourly close with the daily snapshot's open and close for that session. Its tolerance starts at a provisional 1%, and the first fetch's measured gaps set it. Snapshots go to `data/market/1h/{symbol}.parquet` and raw responses to `data/raw/1h/{symbol}/`. The daily paths do not move, because `research/holdout.manifest.json` hashes them. `jt fetch --bars 1h` runs it, and `jt fetch` stays daily.
       - Check that pytest passes offline on a hand-built hourly fixture, then on a trimmed copy of the real SPY response after the user's fetch.
       - Check that tests cover a window that starts mid-session, a bar outside regular hours, a timestamp missing against SPY, and a daily fetch that is unchanged.
       - The user runs `uv run jt fetch --bars 1h` twice, about 14 credits each. Check that the second run changes no files. Record in the decision log what the run measured: the bar times, the bars per session, the session gaps, whether `adjust=all` applies, and the first session.
    2. **Run the arena on hourly bars (PR 12b, `research/`, plus the web path move).** A `MARKETS` table in `catalog.py` holds each market's bar size, range buttons, and whether it has statistics. Hourly decisions run every `CATALOG` entry on the hourly bars, unchanged, and score from the first session after the first 200 bars, the golden cross's longest average. The returns, fills, switch costs, cash, and portfolio go through `evaluate.open_returns`, `evaluate.backtest`, and `evaluate.portfolio` on the bar key, and `evaluate.py` does not change. The hourly market writes no `comparisons.json`. `jt arena` writes `export/arena/v2/`. It holds `manifest.json` (each market's period bounds, the settings, and the hashes) and `catalog.json` at the top, then `daily/` with `comparisons.json`, `curves/{scope}.json`, `windows.json`, and `funds/{symbol}.json`, and `hourly/` with `curves/portfolio.json`, `windows.json`, and `funds/{symbol}.json`. Hourly files carry a `time` array of New York clock times such as `2026-10-09T13:30` in place of `date`, and a window's `base` is a time. The same PR deletes `export/arena/v1/` and points `web/src/lib/arena.ts`, the route handlers, `check-schema.mjs`, AGENTS.md, and the README at `v2/daily/`, so the site does not change.
       - Before deleting v1, check with `diff -r` that every v1 file except `manifest.json` is byte-identical to its counterpart under `v2/daily/` or `v2/`.
       - Check that the truncation test passes for every entry on hourly random-walk bars.
       - Check that a hand-built pair of hourly sessions compounds to the expected session returns, with a switch cost and an overnight hold.
       - Check that the reconciliation with `research/holdout.json` still passes, that a second `jt arena` reports every file unchanged, and that the five `web/` checks pass.
    3. **Add the Daily or Hourly switch (PR 12c, `web/` only, reviewed by the user before merge).** The screen gains the switch, the hourly ranges, the 250-bar candles view, New York times on hourly bars, and the hourly copy in the product spec. The route handlers serve each market's curve and funds under `/preview/data/{market}/`. The page fetches a market's files only when a visitor first picks it. `format.ts` gains the hourly time format, and `e2e/expected.ts` keeps its own copy.
       - Check that `check-schema.mjs` fails the build on a broken copy of each market's files.
       - Check with Playwright that every amount and share matches `windows.json` on both markets, that the candles view shows the last 250 bars of a long range and every bar of a short one, that the switch keeps or resets the range as the spec says, and that hourly All shows no "could be luck" text.
       - Check that the five `web/` checks pass, and post screenshots of both bar sizes in both views at 1280 px and 390 px for the user's review.
13. **Volatile-stock market.** Deferred on 2026-10-14. A data source with point-in-time listings, delisted stocks included, supplies the universe. Massive is the proposed source, as [Data source for volatile stocks](#data-source-for-volatile-stocks-proposed) explains. Each January, the universe rule in the product spec picks 20 stocks from data dated before that January. A stock delisted during the year moves to cash.
    - Check that tripling every price after a January changes no stock picked for that January.
    - Check that a synthetic stock delisted mid-year earns the cash return from its last bar on.
    - Check that a second `jt arena` reports every file unchanged.

Learner-built rules get no milestone. They wait for the backend trigger in the product spec.

## Jev access

Use OpenRouter `POST https://openrouter.ai/api/alpha/decisions` with model `typesafe/jev-1.13`, called through `httpx`. It needs only an OpenRouter API key and no TypeSafe account. The endpoint is labelled alpha. The risk stays small because the policy table is built once and frozen. The estimated total cost is under $1, computed as 960 states × 5 samples × 2 prompt versions × about 700 tokens at $0.042 per million input tokens. The key is needed at milestone 3, not before.

## Open questions

- Does OpenRouter require a minimum credit purchase? Unverified.
- **Should every live verdict use a critical value calibrated by block count?** We recommend it for the catalog's live period and for learner rules. Today's `block_bootstrap` with `critical_value` gave a null rule a verdict in 64.5% of synthetic datasets at 3 blocks, 15.7% at 13 blocks, 7.3% at 63 blocks, and 6.2% at 236 blocks, against a 5% target. The bootstrap's spread is right on average, but with few blocks it varies too much from one dataset to the next. A t cutoff with blocks minus 1 degrees of freedom or a simulated table by block count would fix it. Either one makes a verdict before about 1 year unlikely, so honesty rule 5's 3-block minimum would rarely bind. The milestone 7 backtest, at 236 blocks, would barely move.
- **When does a live verdict get decided?** We recommend a verdict on each anniversary of the save, or of the catalog freeze, for 5 years, at a critical value that holds 5% over those 5 looks. With one rule's 8 pairs and a known spread, that value is 3.07, against 2.67 for one look. Recomputed every night at 2.67, a null rule showed a verdict on some night within 5 years in 41.8% of runs. A value held at 5% over every night is 3.54, and it gave a rule with a true edge of 1.0 a win by 5 years in 48% of runs, against 58% for the yearly verdict. A night count beside a nightly verdict discloses the leak but does not close it. This changes honesty rule 5 and milestone 11.
- **What are the volatile-stock floor and cost?** We recommend a closing price of at least $5 and a median daily dollar volume of at least $20 million over the previous 63 sessions. The cost is 25 basis points per switch, or the measured median quoted spread of the picked stocks if that is higher. The floor values and the 25 are guesses until the data source's quotes measure the spread.
- **Which source supplies point-in-time listings with delisted stocks?** We recommend Massive, after the three probes in [Data source for volatile stocks](#data-source-for-volatile-stocks-proposed). CRSP is the fallback.

## Risks

### Arena

1. **Low power.** Most pairs will read "Too close to call". Milestone 7 measured six of six. The first screen says so, shows the smallest difference the period can detect, and keeps the coin flip in the catalog as a picture of luck.
2. **Catalog snooping.** Whoever adds an entry has seen the backtest years. Cited textbook parameters, the append-only catalog, the family-wide interval, and the "not a holdout" label limit this. Only the live period removes it.
3. **Look-ahead in stateful rules and refits.** The truncation test over `CATALOG`, the `oracle` negative control, the refit purge test, and the live replay guard against this.
4. **Pressure to add knobs.** Each parameter value is a new catalog entry and widens every interval. A request for free parameters is the backend trigger, not a catalog change.
5. **Pressure to call wins.** "Which one wins?" invites a winner on every screen. The verdict comes only from the simultaneous interval, the family covers every market, `check:honesty` limits where "wins" appears, and the site never counts a strategy's wins.
6. **A cost model that decides intraday results.** A strategy that switches many times a day can win or lose on the cost per switch alone. Each market fixes its cost before its first run, and every market shows its figures at 2 and 4 times that cost.
7. **Luck wins in the live period.** Short windows and nightly looks each let a null pair show a verdict far more often than 5% of the time. The open questions on calibration by block count and on yearly verdicts address both. Milestone 11 should settle both before it shows a live verdict.
8. **Luck wins from many learner rules.** A learner verdict covers only its own rule's pairs, so a person who saves many rules, from many accounts, will see some wins by luck. The luck line, the public rule log, and the list of a learner's other rules disclose this. Nothing prevents it.
9. **Delisting prices.** A delisted stock exits at its last close. A source without delisting returns can flatter a stock that collapsed after its last trade. The volatile-stock market states how many of its stocks were delisted.

### Jev study

These risks are ranked by impact on the answer.

1. **Low statistical power.** The holdout has 97 labelled 20-session blocks, and the ETFs move together. Milestone 4 puts the minimum detectable effect at 0.032 AUC. The joint-date bootstrap and the published MDE make an "inconclusive" result readable.
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
- **2026-10-12.** States/v1 cut points, all on adjust=all bars. Wilder RSI14 reads OVERSOLD below 30, WEAK below 45, NEUTRAL up to 55, STRONG below 70, and OVERBOUGHT from 70. Both average comparisons are strict, so a tie reads BELOW. The MACD histogram is EMA12 minus EMA26 minus its EMA9 signal. It is POS above 0 and RISING above the prior session's value. The Bollinger bands sit 2 population standard deviations from the 20-day mean. The ATR regime counts how many of the trailing 252 values of Wilder ATR14 over close, today included, are at or below today's. A count in the bottom third reads LOW and one in the top third reads HIGH. A session gets a state only when every indicator has its history, which takes 265 bars.
- **2026-10-12.** A label is null when its exit open falls in a later split than its date. No fit label reads validate prices, and no validate label reads holdout prices. This costs the last 21 sessions of each split for each symbol.
- **2026-10-12.** The empirical table adds 50 pseudo-observations at the fit base rate to each state (SHRINK_K = 50). A state with no labelled fit rows scores the base rate.
- **2026-10-12.** The bootstrap splits the sorted distinct dates into non-overlapping 20-session blocks and draws as many blocks as there are, with replacement. All tickers on a date share its block. It runs 2000 reps with seed 0 and reports the 2.5th and 97.5th percentiles. The last block can be shorter than 20 sessions.
- **2026-10-12.** BIL gets no states. It supplies the cash return and is never traded, so states cover the other 13 symbols.
- **2026-10-12.** The vote tables are frozen as `states.py` defines them. `vote_trend` reads RSI, both averages, the MACD histogram, and band breakouts as momentum. `vote_revert` fades RSI and band extremes and MACD turns, and gives the averages no vote. Neither votes on the ATR regime.
- **2026-10-12.** Milestone 2 measured the ceiling. The `empirical_table` validate AUC is 0.489, with a 95% CI of 0.451 to 0.526. The same table scores 0.619 in sample on fit, so the states sort fit outcomes but the sort does not carry to validate. Fit sessions occupy 243 of the 960 states. Validate sessions in a state with at least 30 fit rows make up 90.9% of validate.
- **2026-10-12.** Prompt version `descriptive/v1` sends the six levels as plain sentences under readable field names (`momentum`, `trend_200d`, `trend_50d_vs_200d`, `macd`, `bollinger`, `volatility`), with each cut point in parentheses. A seed taken from the call key shuffles the field order for each state and sample. The log keeps each request in the order Jev saw it. Building the table fails when a logged request differs from the request the code builds now, so any prompt change needs a new prompt version.
- **2026-10-12.** The call log is `research/jev_calls.jsonl`, and the policy table is `data/policy/jev.parquet`. `p_sd` is the sample standard deviation (ddof 1) of the per-sample `p_up`. `coherence` is the mean over samples of `|p_hi + p_lo - 1|`. The policy table holds only Jev's answers and reads only the call log. It drops the planned `empirical_p` and `n_dev` columns, because dev-period frequencies read validate labels and could leak into a validate arm. The site export joins `empirical_table` when it needs them.
- **2026-10-12.** Milestone 3 ran 4,800 calls with no failures. Every call was served by `typesafe/jev-1.13-20260917`, and the total cost was $0.1202, about 594 input tokens and $0.000025 for each call. Jev returns noul probabilities rounded to 2 decimals.
- **2026-10-12.** Milestone 3 measured Jev on validate. The `jev` validate AUC is 0.490, with a 95% CI of 0.445 to 0.533. That matches the `empirical_table` ceiling of 0.489. Across states, `p_up` runs from 0.257 to 0.683 with a median of 0.478. At the 0.5 threshold, `jev` is long on 56.2% of validate sessions, while 62.0% of validate sessions rose. The R² of `p_up` on the vote count is 0.384 for `vote_revert` and 0.062 for `vote_trend`, so Jev reads the states more like a mean-reversion counter than a trend counter. The median sample spread `p_sd` is 0.019, and the median coherence is 0.030.
- **2026-10-13.** Milestone 4 leaves out the `jev_labels` arm and makes no Jev calls. Every Jev arm reads the frozen `descriptive/v1` policy table. `jev_labels` stays open work, and it needs its label mapping before any paid call.
- **2026-10-13.** The dev report fits on fit and scores on validate. `empirical_table` and the matched thresholds read fit labels only. The milestone 5 holdout refits them on fit and validate together. The code reads no holdout labels, and the dev backtest truncates bars at 2019-01-01, so it reads no holdout prices either.
- **2026-10-13.** Every arm is a score, a threshold, and a long rule `score > threshold` in one registry. A null score is flat. The vote arms are long unless the vote is net bearish (`vote >= 0`). On fit, that rule puts `vote_trend` long on 73.5% of sessions and `vote_revert` on 68.1%. The rule `vote > 0` gives 66.7% and 27.2%, which leaves the two vote arms too far apart to match one exposure to.
- **2026-10-13.** `jev_matched` takes the `p_up` cut whose fit exposure is closest to the mean fit exposure of the two vote arms, 70.8%. The candidate cuts are the distinct fit scores and one cut below the minimum, and a tie goes to the lower cut. Jev's coarse `p_up` values put `jev_matched` at 71.5% on fit. `random_matched` gives each state one seeded uniform score (seed 0) and takes the cut whose fit exposure is closest to the fit exposure of `jev`. A per-state draw keeps the turnover of a state policy. A per-session draw at 55% exposure would change position on about half of all sessions.
- **2026-10-13.** An `oracle` arm reads `fwd_ret_20` and is long when it is positive. It is a look-ahead check for the evaluation code, not a strategy. The dev report prints it, labelled as a check.
- **2026-10-13.** The backtest treats each symbol as one sleeve that starts flat. A decision at the close of t earns `open[t+2] / open[t+1] - 1` when long and the same BIL return when flat. A position change costs the cost rate as a multiplier at the fill, so always-long equity is exactly `(1 - c) * open[last+2] / open[first+1]`. The portfolio is the equal-weight mean of the 13 sleeves, rebalanced daily, with no cost for that rebalance.
- **2026-10-13.** Brier skill compares an arm with the fit base rate, and only probability arms get it (`jev`, `jev_matched`, `empirical_table`). The calibration curve uses 10 fixed-width bins on [0, 1]. Excess Sharpe is the annualized mean over the standard deviation (ddof 1) of the daily portfolio return minus the BIL return, times the square root of 252. Turnover counts position changes per sleeve per year, and the first entry counts as one change.
- **2026-10-13.** One block bootstrap now serves every metric. It draws block weights and passes them to a weighted statistic, so AUC, Brier skill, Sharpe, and the AUC difference share one resampler. The milestone 2 and 3 results are unchanged.
- **2026-10-13.** The minimum detectable effect uses validate only, because fit is in sample for `empirical_table`. The bootstrap draws as many blocks as the holdout will have, so the spread of AUC(`jev`) minus AUC(`empirical_table`) estimates the holdout standard error. MDE = (z(0.975) + z(0.8)) × SE, for a two-sided test at alpha 0.05 with 80% power. The holdout has 1,954 dates. The last 21 have no exit open, so 1,933 labelled dates make 97 blocks.
- **2026-10-13.** `research/prereg.toml` pins the holdout to 2019-01-01 through 2026-10-09, the last bar on hand, so nobody can choose when the holdout stops. It also records the policy table hash, the market snapshot hashes, the model that served the calls, every arm rule, the costs, the bootstrap settings, and the outcome rule. `jt evaluate --prereg` writes it and refuses to replace a different file.
- **2026-10-13.** Milestone 4 measured every arm on validate at 5 bps, with 95% CIs from 50 labelled blocks for AUC and 51 traded blocks for Sharpe. No arm's AUC CI excludes 0.5 except the oracle's. `jev` scores 0.490 [0.445, 0.533], `empirical_table` 0.489 [0.451, 0.526], `vote_revert` 0.503, `vote_trend` 0.483, `sma_filter` 0.483, and `random_matched` 0.509. Excess Sharpe is 0.60 for `buy_hold`, 0.58 for `empirical_table`, 0.50 for `sma_filter`, 0.21 for `jev`, and 0.02 for `random_matched`, and every Sharpe CI except the oracle's spans 0. The oracle scores AUC 1.000 and excess Sharpe 2.97 [2.36, 3.65].
- **2026-10-13.** Costs decide the `jev` backtest. `jev` changes position 58 times per sleeve per year, because states change from day to day. Its excess Sharpe falls from 0.61 at 0 bps to 0.21 at 5 bps and -1.00 at 20 bps, while `buy_hold` stays at 0.60.
- **2026-10-13.** Jev's `p_up` does not track the validate outcomes. The observed up rate is 0.636, 0.625, 0.626, and 0.590 in the `p_up` bins from 0.3 to 0.7. Brier skill against the fit base rate of 0.641 is -0.073 [-0.166, 0.005] for `jev` and -0.025 [-0.045, -0.007] for `empirical_table`.
- **2026-10-13.** The dev SE of AUC(`jev`) minus AUC(`empirical_table`) at 97 blocks is 0.0116, so the MDE is 0.032. The holdout detects a true difference of 0.032 in 80% of runs. A smaller true difference is more likely to read "inconclusive".
- **2026-10-13.** `jt holdout` checks the lock before it reads any holdout label. It refuses unless `research/prereg.toml` is tracked by git and no tracked file has uncommitted changes, so the recorded commit describes the code that ran. It then renders the prereg again from the code and the sha256 of each market Parquet file and the policy table, and refuses unless the text is byte-identical to the committed file. It prints the diff, so a changed file, arm rule, or setting is named. The model, the holdout end, and the power figures come from the file, because the holdout cannot recompute them. The policy hash already pins Jev's answers, so the holdout does not read the call log to check `model_served`.
- **2026-10-13.** The lock hashes the Parquet bytes, not the hash that each market manifest records, so a file replaced without its manifest still fails.
- **2026-10-13.** The holdout builds states in memory from the hashed market bars, cut at the prereg end, instead of reading `data/states/`. Every input is then a hashed file. Bars after the end are dropped before the indicators, the labels, and the returns, and a test checks that tripling every later price changes nothing.
- **2026-10-13.** The holdout refit on fit and validate keeps the labels of the dev splits. A label whose exit open falls in a later split stays null, so the last 21 sessions of fit stay out of the refit, as they did in milestone 4. The last 21 holdout sessions have no exit open by the prereg end and stay unlabelled.
- **2026-10-13.** The primary CI and every arm's CIs use the code's bootstrap constants. The lock proves that they equal the prereg values, so the holdout follows the prereg without a second copy of each setting.
- **2026-10-13.** `jt holdout` writes `research/holdout.json` and then `research/holdout.manifest.json` (`HoldoutRun`), and refuses to run when either file exists. The result holds the window, the row and block counts, the primary CI, the outcome, and every arm's report. It holds no time and no commit, so a rerun at a later commit can match it byte for byte. `jt holdout --verify` requires the prereg hash that the manifest records, reruns the holdout, and exits 0 only when the new bytes match the file and the manifest's `result_sha256`. Both files are meant to be committed after the run.
- **2026-10-13.** Milestone 5 tests `jt holdout` on synthetic bars and a synthetic policy in a temporary git repository. Nobody runs it on the real data until the user reviews the code. On the real files, `prereg_diff` returns no diff, so the lock passes. That check reads no holdout label.
- **2026-10-13.** Milestone 5 ran the holdout once, at commit `856de5d`, from 2019-01-02 through 2026-10-09. It used 25,129 labelled rows in 97 blocks. AUC(`jev`) minus AUC(`empirical_table`) is -0.012, with a 95% CI of -0.045 to 0.024, so the pre-registered outcome is "inconclusive". The MDE was 0.032, so the holdout cannot rule out a true difference smaller than that. `jt holdout --verify` reproduced `research/holdout.json` byte for byte.
- **2026-10-13.** `export/v1/` is committed to git, by the user's decision. Any machine can build the site without `data/` or an API key, and the PR diff shows every published number. The repository is public, so the per-symbol files publish Twelve Data adjusted prices in git history. The spec assumes display and redistribution rights.
- **2026-10-13.** The host is not chosen. The user asked whether Vercel now makes a later move to Terraform-managed AWS hard. It does not while the site stays a plain static export with no functions, ISR, middleware, or image optimizer. `next.config` sets `output: "export"` and `trailingSlash: true`, so `web/out/` is plain files that S3 can serve.
- **2026-10-13.** The site shows two disclaimers, chosen by the user. "Research, not investment advice. Nothing here is a recommendation to buy or sell any security." and "Backtests are hypothetical, include modeled trading costs only, and do not predict future returns." It shows no data attribution and no statement of independence from TypeSafe or OpenRouter.
- **2026-10-13.** `jt export` refuses unless its inputs are the files the holdout read. The sha256 of `research/holdout.json` and of `research/prereg.toml` must match the run manifest, `prereg_diff` must be empty for the market and policy hashes, and the policy table built from `research/jev_calls.jsonl` must equal `data/policy/jev.parquet` byte for byte. Bars are cut at the prereg end, and states are built in memory, as in the holdout.
- **2026-10-13.** Two runs produce the site's numbers. The holdout run (`856de5d`) produced every metric in `summary.json`, and the export copies them unchanged. The export run derives the development frequencies, the per-symbol sessions, the equity curves, and the Sharpe block count from the same hashed inputs. The export holds no commit and no time, so a rerun at a later commit, or after a squash merge, writes the same bytes. `manifest.json` records the sha256 of every input and every output file instead. The site shows the commit it was built from, which contains those files.
- **2026-10-13.** `holdout.json` gives no CI for exposure, turnover, max drawdown, or the excess Sharpe at each cost. The site shows them in a separate table labelled as point values with no confidence interval, and does not compute new intervals after the holdout. AUC and Brier skill show the 97 labelled blocks. Excess Sharpe shows the 98 traded blocks that its CI resamples, which the export counts from the same inputs.
- **2026-10-13.** The development frequency next to Jev's `p_up` counts the labelled fit and validate rows, the set the holdout refit `empirical_table` on: 35,438 rows from 2008-01-02 through 2018-12-31. `policy.json` also carries `empirical_p` on those rows, which is the comparator's score in the holdout.
- **2026-10-13.** Symbol pages are descriptive. Jev's position is shown for every session from 2008 through the holdout end, because its 0.5 threshold needs no fit. Equity curves cover the holdout only, for `jev`, `empirical_table`, and `buy_hold` at 5 bps, fitted on fit and validate as in the holdout. The shown forward return is `open[t+21] / open[t+1] - 1` without the split purge, and it is null only for the last 21 sessions. The export rounds prices to 4 decimals and forward returns and equity to 6. Metrics stay unrounded.
- **2026-10-13.** "What Jev saw" shows the six lines of one logged request in the order Jev saw them. `policy.json` stores each sample's field order and answers, and the export fails unless the dimension texts in that order rebuild each logged `request.state`, key order included.
- **2026-10-13.** The site's only data boundary is `web/src/lib/export.ts`. It checks each file's sha256 against `manifest.json` and parses every file with strict zod objects, so an unknown, renamed, or missing field fails the build. It then checks the cross-file invariants: the symbol files match the study symbols, every state index exists, the columnar arrays have equal lengths, and the candidate and baseline arms exist. Brier skill and calibration are present exactly when an arm's score is a probability. `pnpm check:schema` proves the gate on seven broken copies of the export.
- **2026-10-13.** Each table and panel carries one "Source" link to its run on the manifest page, instead of one link per cell. The Sharpe block count links to the export run on its own. The symbol panel shows each sample's raw P(higher) and P(lower or equal), not a per-sample `p_up`, so the site computes nothing. It calls the development `n` "labelled symbol-days", because it pools the 13 ETFs.
- **2026-10-13.** Milestone 6 checks the built site with Playwright. The test reads `export/v1/` itself and formats numbers with its own copy of the rules. It checks every number on the result page, all 960 rulebook rows in the static HTML, the time-travel panel of each symbol on its default day and on 5 seeded days, every hash on the manifest page, both disclaimers, and that pages request nothing beyond the static host. A separate check of the result page against `research/holdout.json` found 0 mismatches in 111 values.
- **2026-10-13.** `web/` pins next 16.3.6, react 19.3.0, zod 4.6.5, lightweight-charts 5.2.1, and TypeScript 6.0.3. pnpm refuses any package published in the last 14 days. TypeScript 7 needs an opt-in from Next, so the site stays on 6. lightweight-charts shows the TradingView attribution that its license asks for.
- **2026-10-13.** The site will be hosted on AWS, by the user's decision: S3 behind CloudFront, managed with Terraform. The deploy pipeline is later work. With `trailingSlash: true`, every page is a directory `index.html`, so a private S3 origin needs a CloudFront function that appends `index.html` to paths ending in `/`.
- **2026-10-13.** The product pivots from the Jev study to a trade arena, where learners compare two trading strategies on the same ETFs with the same costs. The user found the study's front page overwhelming. An arena of five candidate concepts chose the design: a fixed catalog, a precomputed parameter grid, a browser engine, user-built rules with a sealed window, and a live league. The fixed, precomputed catalog is the base, and the judge chose it separately. The [synthesis](arena/2026-10-13-trade-arena/synthesis.md) lists each graft and each rejection.
- **2026-10-13.** The arena is for curious learners first, by the user's decision. Learners pick catalog entries and do not set parameters or build rules.
- **2026-10-13.** The site stays static, by the user's decision. A backend returns only when a learner needs a result that `jt arena` cannot compute in advance. Nothing is built for it before then.
- **2026-10-13.** Twelve Data's display and redistribution rights cover publishing these prices. The user checked them. The product spec no longer calls them an assumption.
- **2026-10-13.** Jev is an arena contestant, "Jev (frozen rulebook)", from the frozen policy table, and its card states the study result. The study pages move unchanged to `/studies/jev/`. This is the user's decision. `research/prereg.toml`, `research/holdout.json`, `research/holdout.manifest.json`, `research/jev_calls.jsonl`, and `export/v1/` do not change.
- **2026-10-13.** Honesty rule 5 ("no free date picker") becomes "periods are fixed and named, never chosen". Every figure belongs to `backtest` or `live`, the period bounds live only in the arena manifest, and the build fails on a date input, a chart zoom, or a record whose dates differ from its period. The arena has no development and holdout split, because the catalog's authors had seen 2019 to 2026.
- **2026-10-13.** An arena verdict uses a simultaneous 95% interval over every pair in the catalog version, and only the portfolio scope gets a verdict. `evaluate.block_bootstrap` draws the same blocks for every pair with the same dates and seed, so the interval reuses it unchanged.
- **2026-10-13.** Arena strategies live in a new `CATALOG` of causal `positions(bars)` functions, not in `ARMS`, because `score > threshold` cannot express an exit or a hold. The backtest, portfolio, Sharpe, and bootstrap code in `evaluate.py` serve both.
- **2026-10-13.** The learned model is an L2 logistic regression from scikit-learn, refit each January on purged labels. The 2026-10-12 cut of logistic regression applied to the Jev study, and the arena needs a machine-learning entry that learners recognise.
- **2026-10-13.** The live period records positions in an append-only ledger before the next bar exists, and `jt arena verify` replays it. This turns the spec's planned "live forward testing" into milestone 11.
- **2026-10-13.** GitHub Actions runs the live period, by the user's decision. The code is on GitHub, scheduled runs are free for a public repository, and the job only has to finish between the close and the next open, so a late start does not matter. The job reads the Twelve Data key from a repository secret and deploys through a GitHub OIDC role. EventBridge with CodeBuild would need more Terraform for the same job.
- **2026-10-13.** A bot commits the live ledger every night to a separate `ledger` branch, by the user's decision. GitHub's record of each push is the public proof that a position came before the next bar. A commit's own date is set by its author and proves nothing alone. The separate branch keeps about 250 bot commits a year out of `main`.
- **2026-10-13.** The learned model reads only the `State` levels and the candle flags, by the user's decision. It sees the same information as the other entries and as Jev. Adding inputs after a weak result would be the tuning the arena warns against. A richer model enters as a new catalog entry with its inputs fixed before any run.
- **2026-10-13.** `comparisons.json` holds a `StrategyRecord` for each strategy, scope, and period beside the pair records. The first screen shows one row of figures for each side, and the plan's shapes had no record for it. A record carries the excess Sharpe interval at 5 bps, the point values at each cost, the max drawdown, the switches per year, and the exposure, as the study's arm report does.
- **2026-10-13.** `random_walk` moves from `tests/test_states.py` to `catalog.py`. The fingerprint reads it, and package code cannot import a test module. The tests import it from `jevtrader.catalog`.
- **2026-10-13.** The arena manifest records no git commit. `export/arena/v1/` is committed, so a commit in the manifest would change with every commit of the export, and a rerun would never report every file unchanged. The input hashes, the catalog version, and each strategy's version and fingerprint identify the run instead.
- **2026-10-13.** A period's `first` and `last` in the arena manifest are the scored decision dates, and `barsEnd` is the last bar. The last two bars before `barsEnd` decide nothing that earns a return, so `last` falls two sessions before `barsEnd`.
- **2026-10-13.** `reconcile` takes the market bars and cuts the returns at the last date of `research/holdout.json`, as `evaluate.holdout_result` does. Returns cut at the end of the backtest period would give the last two holdout sessions returns that the holdout never saw. On synthetic bars that run past the holdout end, that cut moved the golden cross excess Sharpe from 0.806 to 0.652, and the reconciliation failed. On the real data the two cuts are the same date.
- **2026-10-13.** Milestone 7 measured the four-strategy backtest from 2008-01-02 through 2026-10-07 on the portfolio of 13 ETFs, in 236 blocks. The reconciliation reproduced the `buy_hold` and `sma_filter` intervals in `research/holdout.json` exactly. The simultaneous critical value for the 6 pairs is 2.53. No portfolio pair's simultaneous interval excludes zero, so every verdict is "no_difference". The MDE runs from 0.52 to 0.96 excess Sharpe across the pairs. Excess Sharpe at 5 bps is 0.61 for buy and hold, 0.64 for the golden cross, 0.45 for the MACD crossover, and 0.41 for the Bollinger bounce.
- **2026-10-13.** The arena question becomes "Which one wins?", by the user's decision, because it is the question learners bring. The three answers are "A wins", "B wins", and "Too close to call". The simultaneous interval still decides, and the `PairRecord` verdict enum does not change. "Wins" appears only in the question and in a verdict that its interval supports, and the site never counts a strategy's wins.
- **2026-10-13.** The arena gains markets, each a universe on one bar size, by the user's decision. An hourly ETF market comes first, then a volatile-stock market, and 1-minute bars later. A simulation of 2,000 runs of 5 years showed that bar size and volatility do not narrow a Sharpe interval. The spread of annualised Sharpe was 0.45 on daily bars, 0.46 on hourly and on 5-minute bars, and 0.46 and 0.47 at 16% and 60% volatility. More markets can raise the real differences between strategies, not the precision. Each market compounds its bar returns into session returns, so `evaluate.py` serves every market unchanged.
- **2026-10-13.** A verdict's simultaneous interval covers every pair in every market, so a learner cannot find a win by trying markets. Each market added widens every interval.
- **2026-10-13.** The volatile-stock universe is chosen each January by a fixed rule from listings that include delisted stocks. Today's list of volatile stocks would hide every stock that collapsed.
- **2026-10-13.** Learner-built rules are the long-term goal, by the user's decision, and they wait for the backend trigger. A learner's rule gets a verdict only from its live period, because nobody can count the tries made on the backtest years before a rule is saved.
- **2026-10-13.** Twelve Data's redistribution rights cover intraday bars, by the user's check. The data source is replaceable, and history depth or plan tier does not constrain the design.
- **2026-10-13.** Jev (frozen rulebook) and the learned model play only in daily markets, by the user's decision. Both read the daily `State` and a 20-session horizon. Jev can be asked again later for another bar size, as a new catalog entry with a new call log. The frozen `research/jev_calls.jsonl` does not change.
- **2026-10-13.** A learner rule's verdict covers that rule's pairs with every catalog entry, in every market where its inputs exist. It does not cover other saved rules. The [learner-verdict arena](arena/2026-10-13-learner-verdicts/synthesis.md) compared four answers on synthetic data. With every saved rule in one family, a rule with a true edge of 1.0 excess Sharpe over buy and hold showed a win within 5 years in 0.3% of runs at 10,000 rules. With its own pairs, it did in 64% to 69% of runs at any site size. A family of one account's rules failed to a second account, and a false-discovery rate made each verdict's level move with strangers' rules. The site states the luck that this answer allows: rules played, expected luck wins, a 1-night-in-20 high, and wins shown. Deleted rules keep counting, and every saved rule appears in a public log with no verdicts.
- **2026-10-13.** The learner-verdict arena measured today's `block_bootstrap` with `critical_value` on one null rule's 8 pairs, over 1,500 synthetic datasets. A null rule got a verdict in 64.5% of datasets at 3 blocks, 15.7% at 13, 7.3% at 63, and 6.2% at 236. The spread of the bootstrap is right on average and noisy with few blocks. The milestone 7 backtest, at 236 blocks, is close to the 5% target. The live period is not. The fix is an open question.
- **2026-10-13.** The same arena measured nightly looks with a known spread. At today's single-look critical value of 2.67 for 8 pairs, a null rule showed a verdict on some night within 5 years in 41.8% of runs. The schedule is an open question.
- **2026-10-14.** The product is a proof of concept with a simple first screen for people who have never traded. It is no longer a Jev product. Statistical rigor, new data sources, and live scoring are deferred, and PR #13 holds their plan. An arena of four first-screen concepts picked "Pick two": a visitor taps two strategies and sees what $1,000 became in each, then reads why more money is not the whole story. The user approved it over a guess-first game, a single-strategy story, and an all-strategies view. The first screen shows no statistics words, and it says a gap "could be luck" only where `comparisons.json` reads `no_difference`. Milestone 8 now builds this screen. Milestones 9 and 11 are deferred. The record is in `docs/arena/2026-10-14-first-screen/`.
- **2026-10-14.** The "Pick two" prototype becomes Trade Arena, by the user's decision. Two slots, "Strategy A" and "Strategy B", each open a searchable list grouped by kind, so the screen holds 50 or more strategies. The screen opens on one year, with range buttons for one week, one month, three months, one year, five years, and all years. A Line or Candles toggle shows either both strategies on all 13 funds or one fund's candles with each strategy's buys and sells. The export gains `windows.json`, which holds each range's growth, exposure, and biggest fall on the portfolio, and `funds/{symbol}.json`, which holds the bars and the trades. Each strategy's plain sentence moves from the site into `catalog.py` as `Strategy.plain`. The fingerprint still reads only the positions, so no version changes. A range other than all years is too short to tell skill from luck, and the screen says so for every pair.
- **2026-10-14.** PR #13 merges as the deferred plan, by the user's decision. The current product spec stays the Trade Arena spec. The "Which one wins?" spec moves to [which-wins-spec.md](which-wins-spec.md), and its sections on markets, learner verdicts, and the volatile-stock data source stay in this plan. Its verdicts, honesty rules, and first screen do not apply until statistics return. Milestones 12 and 13 are deferred like 9 and 11. The next work plans the hourly market's data, backtest, and bar counts on screen, without verdicts.
- **2026-10-14.** The hourly market is planned as milestone 12, by the user's decisions, without statistics. Each fund gets one 5,000-bar hourly call, about 2.8 years at 7 bars a session by arithmetic, and daily history still starts in 2008. Hourly bars end on 2026-10-09 like the daily backtest, so a second fetch returns the same bars. The hourly cost per switch is 5 basis points. A Daily or Hourly switch sits on the same screen, not a separate page. The candles view shows at most 250 bars and the page loads every bar, so a later step back in time needs no new download.
- **2026-10-14.** Four calls settle the hourly plan, by the user's decisions. The candles view shows the last 250 bars of a longer range, because a range of more than 1,000 candles is too thin to read. On hourly All, the screen says "We haven't tested hourly results for luck yet." and never "could be luck", because no hourly result backs either claim. The intraday portfolio returns to equal parts at every bar, so its curve has a point for each hour and `evaluate.portfolio` serves it unchanged. This replaces the deferred sketch's portfolio of daily returns. The arena export moves to `export/arena/v2/` with one folder per market, and v1 is deleted in the same PR, because a market folder beside an unlabelled daily root would leave daily as a special case.
- **2026-10-14.** The hourly backtest scores from the first session after 200 bars. Before that, the golden cross's 200-hour average has no value, so the rule would sit in cash while buy and hold is invested.
- **2026-10-14.** The hourly fetch asks for bars through Saturday 2026-10-10. A Saturday holds no bars, so the window ends on Friday 2026-10-09 whether or not Twelve Data's `end_date` includes its own day. The fetch fails unless the last session is 2026-10-09. Each session's first hourly open and last hourly close must sit within 1% of the daily bar. The 1% is provisional until the first fetch measures the gaps. It still catches prices that `adjust=all` did not adjust, because BIL's dividends alone add up to more than 1% within a year. A full 5,000-bar hourly response is expected, because the window is the last 5,000 bars. A full daily response is still an error, because it may be cut off.
