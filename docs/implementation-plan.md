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
	coherence: float  # mean over samples of |p_hi + p_lo - 1|

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
