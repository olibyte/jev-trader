# Trade arena: build it, seal it, then see the test

Direction: users build their own strategies, a Python backend runs every backtest with the `research/` code, and a strategy sees the sealed test window only after its author commits to it. The user chose static now and a backend later. Phase 1 ships the rule format, the runner, the seal log, and the honesty rules as static files. Phase 2 puts the same code behind an API.

"Measured" means a read-only script on the local 2008-2018 bars. No holdout bar was read.

## 1. The first screen

It is for curious learners: one matchup, one verdict, one button.

- Two strategy pickers, A and B. They default to "Bollinger bounce" against "Always long".
- One chart with both equity curves over the sealed test window.
- One verdict on the excess Sharpe difference: "A ahead", "B ahead", or "Can't tell apart", with one plain sentence, the 95% CI, the block count, and the minimum detectable effect.
- Three fixed window tabs: Development, Sealed test, Live. There is no date input.
- One strip: "14 strategies sealed. The best of 14 random strategies would show +0.08 by luck." (+0.08 is measured on validate.)
- One button: "Build your own" (section 3).

The Jev tables, calibration bins, and arm grids move to `/studies/jev`.

## 2. How a strategy is defined

Every strategy is a user-built rule. The catalog is the rules already sealed.

**`arena-rule/v1`.** A rule is a set of "long when" conditions over the six `states/v1` levels (`State` and `DIMENSIONS` in `states.py`). Values within a dimension combine with OR, and dimensions combine with AND. A rule compiles to a 960-entry long or flat vector over `ALL_STATES`. That is the shape of a vote arm in `evaluate.ARMS`, so `decisions`, `backtest`, and `portfolio` run it unchanged. The sha256 of the vector is the rule's identity, so duplicate rules count once.

The rule fixes everything else: all 13 ETFs at equal weight, a decision at the close of t, a fill at the open of t+1, long or flat, and 5 bps per switch. There is no symbol field, because picking XLK in 2026 is hindsight. v1 has no memory, so it cannot express "MACD crossover, then hold 10 days". v2 adds entry and exit events, holding periods, and indicator parameters.

**The space is large.** There are 31 x 3 x 3 x 15 x 15 x 7 = 439,425 single-conjunction rules. At about 4 ms per development backtest (measured), all of them take 30 core-minutes. So a development figure proves nothing, and the seal has to exist.

**ML, in phase 2.** A user submits a recipe, not weights: a model family from a short list and features from the registry. The server trains it on `up_20`.

## 3. Where backtests run

**Compute does not force a server.** One full run takes about 0.25 s on one core (measured), including states for 13 symbols and a 2,000-rep Sharpe CI. The 14 Parquet files are 2.9 MB. A server is needed only as a trusted party for strangers: it puts the commit before the reveal, counts every seal, and refuses a sealed result to an uncommitted rule.

**Phase 1 is static.**

- Each strategy is an `arena-rule/v1` file in the repository. A git commit is the commit, and the merge is the reveal.
- `jt arena seal` runs sealed results only for rule files that are new in that commit. It appends one line per rule to `research/seals.jsonl`, append-only like `jev_calls.jsonl`. It refuses a rule whose identity is already in the log.
- `jt export` writes `export/v2/arena.json` with each strategy's curves, metrics, and CIs for each window, plus all K(K-1)/2 = 91 pair verdicts. For K = 14 at about 16 KB per curve, that is about 0.7 MB. The site stays plain S3 and CloudFront files, and zod still fails the build on a bad file.
- "Build your own" previews which states a rule covers and links to the rule format. It shows no development numbers, because a browser runner would bring back an uncounted search loop.

**Trigger for phase 2:** the first time a visitor who cannot open a pull request should get a sealed result for their own rule. Nothing is built before then.

**Phase 2 design, not built.**

- CloudFront routes `/api/*` to one Lambda container image with Python 3.14, polars, numpy, `jevtrader`, and the Parquet snapshot. A run costs a fraction of a cent. Cold start is not measured.
- The seal log moves to DynamoDB or to S3 with Object Lock.
- The browser parses responses with the zod schemas in `web/src/lib/export.ts`, and a CI contract test posts fixture rules to the handler. This is weaker than a build-time check: a failed parse shows an error, never a number.

## 4. How comparisons stay honest

**Three fixed windows replace the date picker.**

| Window | Dates |
|---|---|
| Development | 2008-01-02 to 2018-12-31, split into fit and validate as in `SPLIT_STARTS` |
| Sealed test | 2019-01-02 to 2026-10-09, the prereg holdout |
| Live | The first session after the seal commit to the latest bar |

The build and the tests enforce the windows:

1. The window field is a zod literal union of the three names.
2. The rule schema is strict. A file with `start`, `end`, or `symbols` fails the parse, and the phase 2 API returns 422 for it.
3. `check-honesty.mjs` bans `type="date"` under `web/src`.
4. In phase 2, every development figure carries `devRuns`, the draft's run count, which the schema requires.

**One comparison per verdict.** The verdict is the paired difference in excess Sharpe on shared dates, computed with `bootstrap_interval` and the statistic `sharpe(a, w) - sharpe(b, w)`. This follows the pattern of `primary_statistic`. Every figure shows its CI, its block count, and its window label.

**The whole arena counts toward multiplicity.** N is the number of lines in the seal log. "Ahead" needs a 1 - 0.05/N interval, built as the point plus or minus z times the bootstrap SE, that excludes 0. A zod refinement rejects any "ahead" that fails this. The page also draws a luck line, the 95th percentile of the best of N random state strategies. On validate (measured), random 70%-exposure strategies trail always-long by 0.36 Sharpe on average, yet the best of 100 shows +0.21 by luck.

**The power is low.** The sealed window has 98 blocks. Scaled from validate (measured), it detects a Sharpe difference from always-long of 0.52 for a 200-day filter and 0.86 for a Bollinger rule. Most matchups will read "Can't tell apart", and the first screen says so.

**Weaknesses of this direction.**

- **Sealed does not mean unseen.** The 2019-2026 prices are public, and people remember 2020. The seal guarantees the order and the count, not ignorance, so someone can tune offline and seal only the winner. The fixed universe, the public log, and the luck line contain this. Live is the only clean test, and it stays weak for years: its MDE is 1.4 after 1 year and 0.7 after 4 (measured).
- **Every reveal leaks.** At a published cap N, sealed v1 is marked "spent", and the headline moves to Live.
- **Nobody can audit uploaded weights.** They get Live results only.

## 5. Look-ahead for candlestick and ML strategies

- **Candlestick features.** Add `candles(bars)` to `states.py`, with body-to-range, doji, hammer, and engulfing (which reads t-1). It keeps the `levels()` contract: row t reads `bars[: t + 1]` only. Extend `test_levels_at_t_match_on_bars_truncated_at_t` to run over a registry, `FEATURES = (levels, candles, ...)`, on the `random_walk` fixture. Adjusted candle shapes are sound, because the open and close adjustment ratios differ by at most 2.2e-7.
- **Labels.** Recipes train on `labels()`. It already purges at split boundaries, so no development label reads sealed prices.
- **Fitting.** A recipe fits on `fit`, sets its threshold on `validate` with `matched_cut`, and refits on both for the sealed result, as `holdout_result` does for `empirical_table`, which is already the first ML strategy. Features carry no ticker, date, or price level, as in `State`.
- **Check.** Reuse `test_holdout_reads_no_bar_after_the_end`. Triple every later price and require identical output.

## 6. Jev and the finished study

The frozen files never change. Jev is an arena contestant, "Jev (frozen rulebook)", with positions rebuilt offline from `data/policy/jev.parquet` through `evaluate.decisions`. Its card carries the study label: "Pre-registered study: inconclusive, AUC difference -0.012, 95% CI -0.045 to 0.024". The arena never calls OpenRouter.

The seal log starts with the 8 pre-registered arms (`oracle` excluded), committed under the sha256 of `research/prereg.toml`. The study pages move unchanged to `/studies/jev` and keep reading `export/v1/`.

## 7. First milestone

`jt arena run <rule.json>` runs one rule locally over the fit and validate parts of Development.

- Add `research/src/jevtrader/arena.py`. It holds the strict `arena-rule/v1` parser, the compiler to a 960-entry vector, and a runner built on `decisions`, `backtest`, `portfolio`, and `bootstrap_interval`.
- `tests/test_arena.py` checks four things:
  - `{"sma50_vs_sma200": ["ABOVE"]}` reproduces `arm_reports(...)["sma_filter"]` on validate exactly.
  - An empty rule equals `buy_hold`.
  - A file with `start` or `symbols` exits non-zero.
  - Tripling every bar from 2019-01-01 changes no output byte.
- It passes when `uv run python -m pytest tests/test_arena.py` and both Ruff checks pass, and `uv run jt arena run examples/sma_filter.json` prints a validate excess Sharpe of 0.50 (measured: 0.5003).

Then come `jt arena seal`, `export/v2/arena.json`, and the first screen.

## 8. Product decisions

**Decided by the user**

- **Curious learners first.** The first screen is one matchup in plain words. The builder and the seal log sit one level down.
- **Static now, backend later.** The trigger is the first sealed result for a visitor who cannot open a pull request.
- **Twelve Data rights are confirmed.** Curves and prices can be published. Live costs about 14 credits a day.
- **Jev is a contestant, and the study is archived at `/studies/jev`.**

**Still open**

- Phase 2 accounts. With them, users get "my strategies". Without them, a seal returns a capability link. The arena-wide N works either way.
- Who may seal in phase 1, and the spend cap N for sealed v1.

## Alternatives considered and rejected

- **A browser runner (Pyodide).** Fast enough, but it cannot order commit before reveal, and it brings back an uncounted search loop.
- **Withholding sealed prices.** They are public and already in git.
- **Live only.** Clean, but underpowered for years.
- **Per-user seal budgets.** Extra accounts get around them.
