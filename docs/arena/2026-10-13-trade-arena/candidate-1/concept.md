# Trade arena: a fixed, precomputed catalog

Direction: a small catalog of named strategies with frozen rules and no user parameters. `research/` computes every backtest and pairwise comparison. The site renders exported files. The user picks two strategies and a scope (one ETF or the 13-ETF portfolio).

Numbers marked "scratch" come from `measure/measure.py` in this folder. It runs the local market data through `evaluate.open_returns`, `backtest`, `portfolio`, `sharpe` and `block_bootstrap`, and reproduces `holdout.json` exactly for `buy_hold` (excess Sharpe 0.80 [0.10, 1.52]) and `sma_filter` (0.53 [-0.19, 1.33]).

## 1. The first screen

The screen asks one question: "A vs B: can you tell them apart?" It shows four things.

1. **Two pickers and a scope.** Strategy A, strategy B, and "All 13 ETFs" or one symbol. Each entry shows a one-line rule for learners ("Long when MACD(12,26) is above its 9-day signal").
2. **The verdict.** One of three words: "A ahead", "B ahead", "No detectable difference". It comes from the export's `verdict` field. Under it is the excess Sharpe difference with its simultaneous 95% interval drawn as a bar, and the line "1 of 28 portfolio comparisons. The interval is widened for all 28."
3. **Two equity curves** on one chart, with no zoom or scroll.
4. **A small stat row** for each side: excess Sharpe with CI, max drawdown, switches per year, and time in market. The last three are labelled "point value, no CI", as on the current results page.

A fixed period switch ("Backtest 2008 to 2026" and "Live since freeze") sits above the chart. The disclaimers and a link to the archived Jev study at `/studies/jev/` sit at the bottom. A test pins the default pair to catalog order (`golden_cross` vs `buy_hold`), never to a result.

It stays simple because the catalog has no knobs. The current front page renders 9 arms in five tables. The arena shows one pair.

## 2. How a strategy is defined

A new registry, `CATALOG` in a new `research/src/jevtrader/catalog.py`, holds `Strategy(id, version, title, rule, citation, positions)`. `positions(bars) -> pl.Series[Int8]` is causal. `evaluate.ARMS` is `score > threshold`, so it cannot express "enter below the lower band, exit at the mid". The catalog wraps arms that fit and adds a path-dependent form for the rest.

The first catalog has 8 entries with cited textbook parameters and no tuning:

| id | Rule |
|---|---|
| `buy_hold` | Always long. The benchmark. |
| `golden_cross` | SMA50 > SMA200. The same rule as the study's `sma_filter`. |
| `macd_cross` | MACD(12,26) > signal(9). |
| `bollinger_bounce` | Enter when the close is below the lower band (20, 2σ). Exit when the close is at or above the middle band. |
| `engulfing` | Enter on a bullish engulfing candle. Hold 5 sessions. |
| `ml_states` | Logistic model on the six `State` levels, refit each January on purged labels. |
| `jev_frozen` | Long when Jev's frozen `p_up > 0.5`. |
| `coin_flip` | A seeded coin, re-flipped every 20 sessions. A control that shows what noise looks like. |

Rules are frozen by version. A golden test pins the sha256 of each position vector on `random_walk(0)` from `tests/test_states.py`, so a rule change fails unless the id gets a new version. The catalog is append-only: `jt arena` refuses to export when an id in the committed `export/arena/v1/catalog.json` is missing, so a losing strategy cannot disappear.

## 3. Where backtests run

`jt arena` precomputes everything on a laptop. The site stays plain files on S3 behind CloudFront.

- **Grid.** 8 strategies give 28 unordered pairs. With 14 scopes and 2 periods, that is 784 pair records.
- **Compute.** Scratch: one pair bootstrap (2,000 reps, 4,720 sessions, 236 blocks) takes about 0.05 s, so 784 pairs take about 40 s. Signals and backtests take under a second. 20 strategies (5,320 records) take about 5 minutes.
- **Files.** Scratch: one compact daily equity curve for 2008 to 2026 is 41.9 KB. 8 × 14 curves is about 4.7 MB raw, or about 1.5 MB gzipped by CloudFront. The pair records are about 250 B each, so about 200 KB in total.
- **Layout.** The new contract lives in `export/arena/v1/`: `manifest.json`, `catalog.json`, `comparisons.json`, and `curves/{scope}.json`. `export/v1/` stays untouched. The first screen inlines the portfolio scope (about 340 KB raw) and fetches symbol scopes from the same origin, so the e2e "nothing beyond the static host" check holds.
- **Reuse.** `export.write_export`, the manifest hashes, and the zod and cross-file checks in `web/src/lib/export.ts`.

## 4. How comparisons stay honest

- **One metric.** The difference in annualized excess Sharpe at 5 bps (`evaluate.sharpe`, `COST_BPS`), with 0/10/20 bps as point values.
- **Joint-date block CIs.** Reuse `evaluate.block_bootstrap` unchanged. With the same seed and dates, every call draws the same blocks, so per-pair draws line up rep for rep. That gives a max-t simultaneous band over the family with no new resampling code. Scratch: for 6 pairs the critical value is 2.53 instead of 1.96.
- **Verdicts only where the family is controlled.** Only the portfolio scope over the backtest period gets a verdict word, with a family of C(n,2) = 28. Symbol scopes show the interval with `verdict: null`, and the copy says "1 of 364 per-symbol comparisons. Expect about 18 to exclude zero by chance."
- **Data-snooping guards on the catalog itself.** Whoever picks the catalog has seen 2008 to 2026, so no backtest period is a holdout for it. Guards: cited textbook parameters, the append-only catalog, the `coin_flip` control, and a default pair set by catalog order. Only `live` is out of sample, and it is labelled so.

**The rule that replaces "no free date picker."** Every figure belongs to a period named in `PERIODS = ("backtest", "live")` in `catalog.py`. `backtest` runs from the `SPLIT_STARTS` fit start to the prereg end (2026-10-09). `live` runs from the catalog freeze date. The build enforces it:

1. zod types `period` as that enum.
2. `export.ts` fails unless each record's first and last dates equal its period's bounds in `manifest.json`.
3. `export.ts` fails unless a portfolio-scope `verdict` agrees with the sign of its simultaneous interval and `family.size === n*(n-1)/2`, and fails unless every symbol-scope `verdict` is null.
4. `check-honesty.mjs` fails on `type="date"`, on chart options that enable scale or scroll, and on literal "beats" or "outperforms" outside the verdict map.
5. `check-schema.mjs` gains broken copies for each of these, and each copy must fail the build.

Why fixed windows matter. Scratch: `macd_cross` scores 0.82 over 2019 to 2026, above `buy_hold` at 0.80. Over 2008 to 2026 it scores 0.45 against 0.61. A date picker would find the first window.

Weakness: none of the 6 scratch pairs excludes zero, even at the per-pair 95% level. Most verdicts will read "No detectable difference". I contain this by presenting it as the main finding, showing each interval's width, and letting the live period accumulate, not by adding windows or parameters.

## 5. ML and candlestick strategies without look-ahead

- **Candlesticks** are polars expressions over bars up to t, in the style of `states.levels`. Decisions at the close of t fill at the open of t+1, as in `evaluate.backtest`.
- **The truncation test extends to the catalog.** Parametrize `test_levels_at_t_match_on_bars_truncated_at_t` over `CATALOG`: `positions(bars.head(t+1))[-1] == positions(bars)[t]` on `random_walk(0..2)`. Stateful rules pass because their path depends only on the prefix. The `oracle` arm, which reads `fwd_ret_20`, is the negative control: the test must fail on it.
- **ML** reuses `states.labels` and generalizes its purge. Today a label is null when its exit open falls in a later split than its date. For a refit at date R, a training row is usable only if its exit open (t + `HORIZON` + 1) falls before R. This generalizes `_split` to refit boundaries. Features are the `State` levels from `state_rows`, the inputs Jev saw. A leaked label changes the refit on the truncated frame, so the truncation test catches it. ML fits are slow, so its test checks 20 seeded t values.
- **Price cut.** Reuse the holdout's check that tripling every later price changes nothing.

## 6. Jev and the finished study

The study is closed and its pages move unchanged to `/studies/jev/`. `prereg.toml`, `holdout.json`, `holdout.manifest.json`, `jev_calls.jsonl` and `export/v1/` never change. `jev_frozen` reads the policy table rebuilt offline through `jev.policy_table(read_calls(...))`, and makes no call. Its card says that 2019 to 2026 was a pre-registered holdout for Jev only, that the study measured AUC against `empirical_table`, and that it ended "inconclusive". The card links to `/studies/jev/`. An arena Sharpe verdict does not replace the study.

## 7. First milestone

Research only, with no site change:

- `catalog.py` with 4 entries: `buy_hold`, `golden_cross`, `macd_cross`, and `bollinger_bounce`.
- `jt arena` writes `export/arena/v1/` for the portfolio and 13 symbols over the backtest period.

It passes when:

1. `uv run python -m pytest tests/test_catalog.py` passes: the catalog truncation test, the oracle negative control, and the golden position hashes.
2. A reconciliation test passes. Run on 2019-01-02 to 2026-10-09, the arena's `buy_hold` and `golden_cross` portfolio Sharpe intervals equal `holdout.json`'s `buy_hold` and `sma_filter` intervals exactly. The scratch run already does.
3. A second `uv run jt arena` reports every file unchanged.

Milestone 2 adds the first screen, the zod schema, and the honesty checks above.

## 8. Product decisions

The user decided four of these on 2026-10-13.

- **Target users: curious learners first.** This sets the catalog cap at 8 to 10 entries and makes the verdict plain words. Each strategy card gets a two-sentence "how it works" line. More entries would widen every interval and crowd the pickers.
- **Static now, with a named trigger for a backend.** Nothing is built for a backend. The trigger is this: a catalog request that cannot be precomputed. Examples are user parameters, uploaded rules, or a catalog past 20 entries (5,320 records, about 5 minutes per `jt arena`). Until then, `jt arena` plus S3 and CloudFront covers every view.
- **Twelve Data redistribution rights are confirmed.** Publishing prices is fine. The arena still ships equity curves, because the site needs those and not OHLC. A candlestick card can show the triggering bars from the existing `export/v1/symbols/` files. `live` still needs a scheduled `jt fetch`, which spends credits, so its start date stays open.
- **Jev is both a contestant and an archived study.** `jev_frozen` enters the catalog from the frozen policy table, labelled with the study result (section 6). The current pages move to `/studies/jev/`, unchanged, and keep reading `export/v1/`.

Still open: who runs the scheduled fetch for `live`, and when the catalog freezes.

## Alternatives considered and rejected

- **User parameters over a precomputed grid.** A 3 × 3 × 3 grid per strategy multiplies the family by 27 and invites tuning to the window.
- **A leaderboard sorted by Sharpe.** It frames noise as rank and is the easiest snooping surface. The catalog lists in fixed order.
- **Reusing the study's `ARMS` as the catalog.** `score > threshold` cannot express exits, and the arms were built to test Jev.
