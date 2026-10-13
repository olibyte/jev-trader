# Trade arena, candidate 3: a backtest engine that runs in the browser

The site ships the bars and a TypeScript backtest engine. Learners pick two strategies, change parameters, and see the comparison redraw on their device. A build check holds the engine to `research/`. Every number below comes from offline throwaway scripts in `measure/`.

## 1. First screen

The audience is curious learners first, so the first screen shows one match and one verdict.

- A matchup bar: "Bollinger bounce vs MACD crossover". Each side has a dropdown and "Adjust", which opens fixed-step sliders.
- A period switch: Development 2008 to 2018, Holdout 2019 to 2026, Live (greyed until there are bars). No date picker.
- A verdict: "A better", "B better", or "No clear winner", from the 95% CI of the Sharpe difference A minus B and its block count. Same rule as `evaluate.outcome`.
- An equity chart of both, with buy and hold in grey, and four numbers per side: excess Sharpe with CI, max drawdown, turnover, exposure.
- A provenance line: "Computed in your browser", engine commit, strategy hash, bars hash, trial count.

The default match is prerendered from numbers `jt export` computes in Python, so first paint follows today's rule. The engine and bars load on the first touch. "Build your own" stays behind a button.

## 2. How a strategy is defined

Three layers share one JSON spec format.

1. **Catalog.** Bollinger bounce, MACD crossover, SMA filter, RSI reversion, hammer and engulfing candlesticks, a history table, buy and hold, and Jev. Each has textbook defaults and a fixed grid per parameter.
2. **Parameters.** Learners move along the grid, for example Bollinger window {10, 15, 20, 25, 30, 40, 50, 60, 80} × k {1, 1.5, 1.75, 2, 2.25, 2.5, 3}: 63 settings.
3. **Composition.** A form builds `long when ... / flat when ...` from a closed vocabulary: SMA, EMA, Wilder RSI, MACD, Bollinger, ATR, the six `State` levels, candlestick predicates over lags 0 to 2, comparisons, AND, OR, NOT. No user code, no `eval`.

Every spec is long or flat with next-open fills, BIL on flat days, and `evaluate.COSTS_BPS`, which is `evaluate.backtest` as written. The spec hash is sha256 of canonical JSON, like `states.state_key`.

## 3. Where backtests run

Backtests run in a Web Worker. The S3 and CloudFront plan is unchanged: the engine and bars are content-hashed static files.

| Measured | Value |
|---|---|
| Bars for 14 symbols, first bar through 2026-10-09 | 97,067 |
| Full-precision JSON: raw, gzip, brotli | 5.25 MB, 1.71 MB, 1.05 MB |
| Float32 binary, brotli | 0.90 MB, but lossy, so rejected |
| A naive JS port of `states.levels`, 13 symbols | 83 ms |
| One strategy on the 13-ETF holdout portfolio | 16 ms |
| The same run plus a 2,000-rep block bootstrap | 26 ms |
| All 63 Bollinger settings, without the bootstrap | 1.1 s |

CloudFront compresses files under 10 MB, so a learner downloads about 1 MB once. Bars start at each symbol's first bar, not 2008 like `export/v1/symbols/`, because indicators need 265 bars of warmup.

### Keeping the engine and `research/` in agreement

This direction breaks "the site never computes a metric". Three rules replace it.

- **The site never recomputes a published metric.** Study numbers are still copied from `holdout.json`.
- **Python is the reference.** A new `research/src/jevtrader/arena.py` interprets specs with polars, reusing `states.levels`, `states.labels`, `evaluate.backtest`, `portfolio`, `sharpe`, `max_drawdown`, and `bootstrap_interval`. `jt export` writes golden vectors: positions and metrics for every catalog grid point and 200 seeded random specs.
- **The build fails on disagreement.** `pnpm check:engine` runs the TS engine in Node on the same bars and compares every position and metric. Like `check-schema.mjs`, it also runs broken engine copies (close fills, one-bar look-ahead) and fails unless each fails.

The prototype shows the agreement is reachable.

- The JS levels matched `states.levels` in all 553,170 cells, with 0 mismatches.
- The holdout excess Sharpe for `sma_filter` and `buy_hold` at 0, 5, and 20 bps matched `holdout.json` to within 1.5e-15.
- CIs matched to within 2e-15 when the engine read numpy's block draws shipped as data: 2,000 reps × 98 blocks, 196 KB as uint8.
- Rounding prices to 4 decimals, as `export.symbol` does, flipped 34 level cells and moved Sharpe by about 1e-6. So the engine reads the full-precision bars research reads. Redistribution is confirmed.

## 4. Honest comparisons

Free parameters invite snooping. In the prototype, Bollinger bounce at (20, 2) scores holdout excess Sharpe 0.50, CI −0.07 to 1.19. Across 63 settings the best is 0.57, the median 0.41, the worst −0.13. The best buys 0.07 over the default; one CI is 1.25 wide. I ran that grid on the holdout to size the problem, which shows how easy it is.

The replacement for "no free date picker": **periods are a closed enum in the export contract (`development`, `holdout`, `live`), and no engine function or component accepts a date.** A `@ts-expect-error` type test rejects `run(spec, "2020-01-01")`. A new `check-honesty.mjs` rule bans `type="date"` and date-range query parameters. Playwright asserts every result card shows a period badge, CI, block count, trial count, and neighbourhood rank.

- **Period labels.** Only Jev's study arms say "holdout, pre-registered". Catalog holdout rows say "holdout, not pre-registered": those prices were public and never locked. Only `live` is unseen; a catalog spec's live row counts bars after the commit that added it.
- **Trials.** The engine counts distinct spec hashes run per period this session. The verdict uses a Bonferroni level 1 − 0.05/N, enforced by a unit test on the verdict function. Reps grow to keep 50 draws per tail (N = 10 costs about 100 ms). Past N = 50 the verdict reads "Too many tries to call". This bootstrap uses a seeded RNG specified in both TS and Python; numpy's draws serve only the frozen-study check.
- **Neighbourhood rank.** Each result shows its rank among up to 25 grid neighbours, about 0.4 s.
- **Limits.** Clearing storage resets the count, and a shared URL arrives labelled "trial count unknown". In a static site these guards slow and label snooping. Only `live` guarantees anything.

## 5. Look-ahead for ML and candlesticks

- **Vocabulary.** Specs have no negative lag, so the parser rejects future reads. Candlesticks read OHLC at t, t−1, t−2. A decision at the close of t fills at the open of t+1, as in `evaluate.backtest`.
- **Truncation test.** Port `test_levels_at_t_match_on_bars_truncated_at_t` to TS and extend it to positions: for every catalog spec and the 200 random specs, the position at t on `bars[:t+1]` equals the full run's, on the `random_walk` fixture as JSON. `arena.py` gets the same test.
- **In-browser ML is the history table only:** `evaluate.empirical_table` over a learner-chosen subset of the six dimensions and `k`, fit on `fit` labels from `states.labels` with the split purge. It counts, so it matches Python exactly. A fitted spec refuses to score its training split, and a test enforces it.
- **Heavier models** train in `research/` on `fit` and ship as frozen coefficients. General in-browser training is this direction's weak spot (solver parity, label hygiene in a composer), so I keep it out.

## 6. Jev and the finished study

Jev is a contestant. The engine computes `State` levels (exact match) and looks up `p_up` in the frozen policy table, 960 values, about 8 KB, long when `p_up > 0.5`. Its card carries the study result: "Pre-registered holdout: inconclusive. AUC(jev) − AUC(empirical_table) = −0.012, 95% CI −0.045 to 0.024, 97 blocks." The study pages move unchanged to `/studies/jev/` and keep reading `export/v1/`. The frozen files stay untouched. The arena contract sits beside it as `export/arena/v1/`.

## 7. First milestone: the engine parity check

This milestone makes no UI change.

- `jt export` also writes `export/arena/v1/`: full-precision bars from the first bar, numpy's 98-block draws, and `golden.json` with level arrays and the holdout metrics of `buy_hold`, `sma_filter`, `vote_trend`, `vote_revert`, `jev`, and `empirical_table`, copied from `holdout.json`.
- `web/src/engine/` holds `levels`, `labels`, `empiricalTable`, `backtest`, `portfolio`, `sharpe`, the block bootstrap, and numpy's linear quantile.
- **The check.** `pnpm check:engine` exits 0 only when every level cell matches, each arm's excess Sharpe at 0, 5, 10, 20 bps and its 5 bps CI match within 1e-12, the TS truncation test passes, and two broken engine copies fail. A second `jt export` reports every file unchanged.

## 8. Product decisions

The user has decided four things.

- **Curious learners first.** One match, one plain verdict, fixed-step sliders; the composer sits behind "Build your own".
- **Static now.** The backend trigger: learners want to publish strategies to a shared board with a global trial count, or score their own specs on live bars. Per-browser counts cannot do either. Nothing is built for it.
- **Redistribution confirmed.** The site publishes full-precision bars from the first bar.
- **Jev is a contestant and an archived study** at `/studies/jev/`.

Still open for the user:

- **Do shared URLs carry a spec?** Yes eases sharing, labelled "trial count unknown". No keeps results in the session that ran them.
- **Which catalog strategies ship first?** Each needs only a spec and a grid.
- **When does live start, and how often?** A scheduled static rebuild with a data refresh suffices; no backend.

## Alternatives considered and rejected

- **Pyodide running `states.py`.** Parity for free is its best argument. But `states.py` needs polars, which has no Pyodide build I would rely on, and the runtime is several MB before numpy (not measured) with a multi-second start. Wrong cost for a learner's first click.
- **Float32 bars.** Saves 15% but is lossy.
- **Precomputing every grid point.** Covers the catalog, not composition, which is the point of this direction. The golden vectors precompute the grid anyway, as a check.
- **A free date picker with a warning.** No test can enforce a warning.
