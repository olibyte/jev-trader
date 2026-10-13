# Trade arena: a precomputed parameter grid

Every strategy is a family from a fixed catalog. Each family has two or three knobs, and each knob takes a value from a small finite set. `research/` backtests every grid point once and exports it. The site lets a reader turn knobs, but only across files that already exist. Because the grid is finite and fixed, the site knows exactly how many variants were tried and widens every interval to match.

"Probe" numbers come from `work/grid_probe.py`, a read-only script on the local data cut before 2019-01-01. It read no holdout bar.

## 1. The first screen

The reader sees one question: "Pick two strategies. Is the gap bigger than luck?"

- Two strategy cards, A and B. Each has a family menu and two or three rows of knob chips. A card says "Variant 7 of 18 in this family" and tags the textbook default.
- One chart: the equal-weight portfolio of the 13 ETFs for A, B, and always long.
- One verdict in plain words: "A ahead", "B ahead", or "No detectable difference". Under it: the excess Sharpe gap and its 95% CI, labelled "adjusted for 96 variants".
- A period switch with two buttons: Development 2008 to 2018, and Holdout 2019 to 2026. There is no date field.
- A strip: "96 variants tried. Every one is on this site." A second strip links Jev's archived study.

Below the fold: drawdown, exposure, turnover, cost sensitivity, and a price chart with entry markers. Each knob has a one-line tooltip for learners, and the verdict stays the only big number.

## 2. How a strategy is defined

A fixed catalog of families. Knob values are fixed per grid version.

| Family | Knobs | Points |
|---|---|---|
| Bollinger bounce | window {10, 20, 50}, width {1.5, 2.0, 2.5} SD, exit {middle, upper band} | 18 |
| MACD crossover | fast/slow {8/17, 12/26, 19/39}, signal {5, 9, 12}, trend filter {off, above 200-day} | 18 |
| Moving-average cross | fast {10, 20, 50}, slow {100, 150, 200} | 9 |
| RSI reversion | window {2, 14}, entry {10, 20, 30}, exit {50, 70} | 12 |
| Candlestick | pattern {hammer, bullish engulfing, morning star, three white soldiers}, hold {5, 10, 20} sessions, trend filter {off, on} | 24 |
| Machine learning | model {shrunk state table, logistic regression on the states/v1 levels}, strength {3 values}, threshold {0.5, exposure-matched} | 12 |
| References, no knobs | always long, Jev (frozen), random exposure-matched | 3 |

That makes 96 entries. Each one is long or flat, filled at the next open, with 5 bps per side, through the existing `backtest()` and `portfolio()` in `evaluate.py`. Each grid point follows the `ARMS` pattern: a score, a threshold, and a long rule. Exposure-matched thresholds reuse `matched_cut()`. The state table at k = 50 with a 0.5 threshold is the study's `empirical_table`.

The probe found a flaw: RSI14 never fell below 10 on development, so two RSI points never trade. The build fails on any zero-exposure variant, so the grid gets fixed before pre-registration.

## 3. Where backtests run

Precomputed in `research/`. Nothing runs in the browser or on a server.

- **Compute.** The probe ran 57 grid points over 13 symbols (2.1 million decision rows). Signals took 0.1 s, the backtest 0.1 s, and a 2,000-rep block bootstrap over all 57 at once took 0.4 s. Compute does not limit the grid. Statistics and the reader's attention do.
- **Files.** One `export/arena/v1/variants/{id}.json` per variant holds metrics per period, portfolio equity, per-symbol switch dates (probe median 9 per sleeve per year, maximum 57), and its pair intervals against the other 95. That is 20 KB (weekly equity) to 60 KB (daily), or 2 to 6 MB in all, plus a 30 KB `grid.json`. The price chart reuses the bars in `export/v1/symbols/`.
- **Static hosting.** One page, `/arena/`, holds the state in the query string (`?a=…&b=…&period=holdout`), and it fetches two variant files from the same origin. Pair pages would need 96 × 95 = 9,120 HTML files. S3 and CloudFront serve about 100 JSON objects with no functions.
- **Build gate.** `loadArena()` in a new `web/src/lib/arena.ts` parses every variant file with strict zod at build time, as `loadExport()` does. The client parses each fetched file with the same schema and computes nothing.
- **Backend trigger.** The site stays static. Build a backend only when a requested strategy cannot be written as a finite grid within the variant budget, such as a user-built rule. Nothing is built for that now.

## 4. Honest comparisons

**Intervals.** Every interval comes from the joint-date 20-session block bootstrap. Each variant file says how many independent blocks are behind it: 139 on development and 98 traded blocks on the holdout.

**Multiplicity.** A new `block_weights()` generator in `evaluate.py` yields the per-row weights, and `block_bootstrap()` calls it, so the study's numbers stay byte-identical (`jt holdout --verify` proves this). Each rep applies one weight draw to every variant. The adjusted half-width is the 95th percentile, across reps, of the largest deviation over the whole ledger. The probe measured the Sharpe gap against always long:

| Variants searched | 1 | 5 | 20 | 55 |
|---|---|---|---|---|
| 95% half-width | 0.42 | 0.61 | 0.72 | 0.78 |

The width grows slowly because variants are correlated. On development, 5 of 55 unadjusted intervals exclude zero, all below always long. None survive adjustment. The best development point, a 20/200 average cross, leads always long by 0.26, inside the band. Across all 1,485 pairs, the adjusted half-width is 1.13.

This is the weak point. With 98 holdout blocks, expect a band near 0.9, so nearly every pair will read "No detectable difference". I contain this in the copy, not by narrowing the band. That verdict gets the same visual weight as a lead. Each family's textbook default is pre-registered, so its unadjusted interval is honest and labelled "pre-registered default".

**The rule that replaces "no free date picker".** A figure belongs to a cell from a closed list, (grid version, period), and every interval for a knob-chosen variant is adjusted for the ledger size N. The build enforces this:

1. zod: `period` is `z.enum(["development", "holdout", "live"])`. Variant files carry no dates. Dates come from `grid.json` for each grid version.
2. `research/arena/ledger.jsonl` is append-only, like `jev_calls.jsonl`. N counts every variant in every grid version ever committed.
3. `pnpm check:grid` fails unless the cross product of knob values equals the set of variant files, and every adjusted interval records the same N as the ledger. It also builds against broken copies, as `check:schema` does.
4. A variant may carry `holdout` only if its grid version's prereg hash appears in the arena holdout run manifest. A grid version committed after that run gets development and live only.
5. The e2e test checks that the page counter equals N. `check:honesty` adds "winner" and "best strategy" to its banned wording.

The verdict fixes cost at 5 bps, so nobody can pick 0 bps. Per-symbol views show no verdict, because a symbol choice multiplies N by 13.

## 5. Look-ahead in ML and candlestick strategies

- Every family is a polars expression over bars, written like `levels()` in `states.py` ("row t reads bars[: t + 1] only"). Stateful rules use only `forward_fill` and counters.
- `test_levels_at_t_match_on_bars_truncated_at_t` in `test_states.py` becomes a test parametrized over every grid point, using the same `random_walk()` fixture, at sampled t plus the last 30 bars.
- A candlestick pattern reads bars t-2 through t. When a pattern needs a confirmation bar, its signal date is the confirmation close. Fills stay at open t+1 through `open_returns()`.
- The ML features are the six levels from `levels()`, which the test already covers. Training labels come from `labels()`. I extend it with a `cutoff`: a label is null when its exit open falls on or after the refit date. Development uses walk-forward yearly refits, with 1994 to 2007 warmup rows feeding 2008. The holdout uses one fit on everything before 2019, as `holdout_result()` does.
- I reuse the idea of `test_holdout_reads_no_bar_after_the_end`: triple every price after a cutoff, and no model coefficient or exported byte may change.
- The `oracle` arm (`lookahead=True`) stays as a positive control. The golden tests need the oracle to top the grid and always long to equal `buy_hold` exactly.

## 6. Jev and the finished study

Per the user's decision, Jev joins the arena as a reference with no knobs. Its threshold is 0.5 and its scores come from the frozen `data/policy/jev.parquet`, built with `jt jev-table --offline`. No API calls. Its card carries the study label: "Pre-registered study: inconclusive, AUC gap -0.012, 95% CI -0.045 to 0.024". The arena export fails unless its recomputed holdout excess Sharpe for `jev` and `buy_hold` equals `research/holdout.json` exactly. The frozen files never change. The study pages move unchanged to `/studies/jev/` and still read `export/v1/` through `loadExport()`.

## 7. First milestone

Development only, two families: Bollinger bounce (18), MACD crossover (18), and always long.

- `research/src/jevtrader/arena.py` and `jt arena` write `export/arena/v1/`. The bars are cut before 2019-01-01, as the holdout cuts at its end.
- `tests/test_arena.py` holds the truncation test for all 37 variants, always long equal to `buy_hold`, a zero-exposure variant that fails, and the tripled-price test on bars after 2018.
- A second `uv run jt arena` reports every file unchanged.
- `/arena/` shows the development period. The holdout button is disabled, labelled "pre-registration pending".
- **Done when** `pnpm check:grid` exits 0 on the real files and exits 0 in broken-copy mode only when each of three broken builds fails: a missing file, an extra file, and an N mismatch.

## 8. Product decisions

Decided by the user:

- **Users: curious learners first.** Two or three knobs per family, tooltips, one verdict, and a budget of about 100 variants.
- **Static now.** The named backend trigger is in section 3. Nothing is built for it.
- **Twelve Data redistribution rights are confirmed.** The site may show price charts with entry markers.
- **Jev is a contestant and the study is archived** under `/studies/jev`, as section 6 describes.

Still open:

- **Variant budget.** The probe shows the cost: 0.42 at one variant and 0.78 at 55. The concept needs a cap before grid v1 is pre-registered.
- **Spend the 2019 to 2026 holdout on grid v1, or not.** Everyone has seen that market. It is untouched for these rules, but always long's holdout result is already public. The other option is development plus a live period only.
- **A live period.** It needs a scheduled `jt fetch` and a re-export. The concept needs to know if a scheduled job counts as "static".

## Alternatives considered and rejected

- **A free strategy builder.** It has an unbounded N, so no interval can be adjusted for it. This is the backend trigger, not v1.
- **Backtests in the browser.** The site would compute metrics, against the current rule, to save under a second of research compute.
- **Bonferroni or the deflated Sharpe ratio.** Bonferroni at 0.05/96 needs a 0.05% tail, which is 1 draw in 2,000 reps. The deflated Sharpe ratio assumes i.i.d. returns. The max-deviation bootstrap reuses the resampler the study already trusts.
