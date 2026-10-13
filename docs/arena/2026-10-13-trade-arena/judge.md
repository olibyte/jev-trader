# Judge verdict: trade arena concepts

I read all five concepts and mock sources, rendered C1, C2 and C4 at 1280 px (C3 and C5 supplied screenshots), and checked claims against `jev-trader-arena` on `docs/trade-arena`. No mock makes a network request.

## Scores

| Criterion | C1 catalog | C2 grid | C3 browser | C4 sealed | C5 league |
|---|---|---|---|---|---|
| 1. First-screen simplicity | 5 | 3 | 3 | 4 | 3 |
| 2. Enforceable honesty | 5 | 5 | 2 | 4 | 5 |
| 3. Look-ahead safety | 5 | 5 | 4 | 4 | 4 |
| 4. Architecture fit and cost | 5 | 4 | 3 | 3 | 3 |
| 5. First milestone | 5 | 4 | 4 | 5 | 4 |
| 6. Path to long-term goal | 4 | 4 | 4 | 4 | 3 |
| **Total** | **29** | **25** | **20** | **24** | **22** |

### One-line justifications

**C1, fixed catalog**
1. One pair, a three-word verdict, one interval bar, one chart, one stat row. No knobs.
2. Period enum, record bounds equal manifest bounds, verdict matches interval sign, `family.size === n(n-1)/2`, null symbol verdicts, broken-copy builds.
3. Truncation test over `CATALOG` incl. stateful rules, `oracle` negative control, purge generalized to refit dates, golden position hashes.
4. New `catalog.py` and `export/arena/v1/` beside untouched `export/v1/`; `block_bootstrap` unchanged; about 40 s compute, about 1.5 MB gzipped; static S3.
5. Four entries; pytest, exact reconciliation to `holdout.json`, idempotent rerun.
6. `positions(bars)` holds any kind; user-built waits for the backend trigger.

**C2, parameter grid**
1. Six rows of knob chips and variant counters crowd the verdict.
2. Strongest multiplicity design: append-only ledger N across grid versions, max-deviation band, `check:grid` cross product, holdout gated on a prereg hash.
3. Parametrized truncation, `labels()` cutoff, walk-forward refits, tripled prices, `oracle` control.
4. Reuses `backtest`, `portfolio`, `matched_cut`; `block_weights()` refactors study code; ARMS claim overstated (below).
5. Bundles research, a page and `check:grid`. Larger than needed.
6. Grid grows by family; free builder is the backend trigger.

**C3, in-browser engine**
1. Hashes, session tries and neighbourhood rank add concepts.
2. Trial count is per browser and resets with storage; admits only `live` guarantees anything.
3. TS truncation port, no negative lags; two implementations to keep honest; ML limited to the history table.
4. A second engine breaks "the site never computes a metric". Parity work is impressive (0 of 553,170 cells, Sharpe within 1.5e-15).
5. `pnpm check:engine` is clear, but needs a full TS port first.
6. Composition reaches "any vs any" fastest; each primitive needs parity.

**C4, sealed user-built rules**
1. Clean matchup, plus MDE and an "ahead bar" row.
2. Strict schema rejects `start`/`symbols`; zod ties "ahead" to Bonferroni over seal-log N. Sealing public 2019-2026 prices cannot stop offline tuning (admitted).
3. `candles()` in a `FEATURES` truncation registry, purged labels, tripled prices. ML deferred.
4. Phase 1 static; v1 rules are state membership only (no crossover or exit); phase 2 adds Lambda.
5. Smallest milestone: `jt arena run` reproduces `sma_filter` on validate.
6. Seal log plus server reuse of `jevtrader`; needs rule format v2.

**C5, live league**
1. A six-row standings table; a two-strategy head-to-head is a second action.
2. Windows declared in pre-season commits, live-only standings, `level` checked against K, too-early bands, `jt league verify` replay.
3. Production replay is the strongest look-ahead check here; ML purge mutates `SPLIT_STARTS` (below).
4. Needs a scheduler, 28 credits a night, bot commits, an off-git export.
5. Synthetic ledger tests, but "done" needs a live `jt fetch` by the user.
6. Forward-only, underpowered for years (1-year half-width 0.60 to 1.06).

## Recommendation: base on candidate 1

C1 is the only concept that scores well on every criterion. Its main honesty claim holds. `block_bootstrap` builds `np.random.default_rng(seed)` inside each call, and `statistic` consumes no randomness, so the same seed and the same dates draw identical blocks. That gives a max-t simultaneous band over pairs with no new resampling code. Its quoted holdout intervals (`buy_hold` 0.80 [0.10, 1.52], `sma_filter` 0.53 [-0.19, 1.33]) match `research/holdout.json`. It is also right that `ARMS` (`score > threshold`, scored per row) cannot express "exit at the middle band", and it adds a path-dependent `positions()` form instead of forcing one in.

Its main weakness is that the 2008 to 2026 "backtest" period merges development years with years the catalog author has already seen. Grafts 1 and 2 below address this.

## Grafts

- **From C2:** (1) Split the period into Development 2008 to 2018 and Holdout 2019 to 2026 instead of one backtest span. Keep C2's rule that a holdout figure needs a committed prereg hash. (2) Replace "the family is the current catalog" with the append-only ledger N, which counts every entry ever committed. Add C2's build failure on a zero-exposure strategy.
- **From C3:** (1) The period label "holdout, not pre-registered" for every catalog strategy except Jev. (2) The measured finding that 4-decimal prices flip 34 level cells. Anything recomputed must read full-precision bars, not `export/v1/symbols/`.
- **From C4:** (1) The "luck line": what the best of N random strategies shows by chance, next to the verdict. (2) A strict schema that rejects `start`, `end` and `symbols` fields. The seal log is a ready design for the later user-built phase.
- **From C5:** (1) The `live` period should come from C5's append-only position ledger and its `jt league verify` replay, not from recomputing over new bars. (2) Show "Too early" under 3 blocks, and use bands rather than ranks wherever more than two strategies appear.

## Claims found false or overstated

- **C2:** "Each grid point follows the `ARMS` pattern: a score, a threshold, and a long rule." This fails for Bollinger exit-at-band and candlestick hold-N, which depend on the path. `scored()` joins per-state score columns, and `decisions()` iterates the module-level `ARMS`. These rules fit only if the "score" is already a precomputed stateful position.
- **C4:** "`decisions`, `backtest`, and `portfolio` run it unchanged." `backtest` and `portfolio` do. `decisions()` runs only the fixed `ARMS` dict, with columns hard-coded in `scored()`, so an arena rule needs a new entry point.
- **C5:** Season 2 Bollinger, MACD and candlestick kinds "extend the Arm registry". That has the same exit problem as C2. "Entry adds a boundary to `SPLIT_STARTS`" edits the study's split table and its `Split` literal, which `test_split_follows_the_split_table` pins. It leaves `holdout.json` intact only because `holdout_result` cuts bars at `END`. It should be a per-entry cutoff parameter, as C1 and C2 propose. Minor: Jev's "58 switches a year" is 57.15 in `holdout.json`.
- **C1, C3:** no false claims found. C1's `block_bootstrap`, reconciliation, `test_levels_at_t_match_on_bars_truncated_at_t`, `random_walk`, the tripled-price test and `jev.policy_table(read_calls(...))` all check out. C3's claim that `export.symbol` rounds to 4 decimals and C5's claims about `SETTLED` (20:00) and 28 credits per fetch also check out.

Not checked: the timing and size figures each candidate measured, which I took as reported. Mobile layout at 390 px, because headless Chrome would not narrow below its minimum window width.
