# Trade Arena as a live league

Strategies enter a season. Each entry is frozen when it enters and is scored only on bars that did not exist then. A nightly job fetches bars, appends each entry's positions to a ledger, rebuilds the static export, and redeploys. Backtests survive as each entry's "pre-season" record, on its own tab.

The audience is curious learners. The league answers their question, "which strategy is winning?", with the answer the data supports: usually "too close to call so far". The site teaches why.

Numbers marked "measured" come from `work/season_power.py`, a read-only script that runs the existing `evaluate.py` functions on the local holdout data.

## 1. The first screen

One standings table for the current season. Nothing else competes with it.

- A season strip: "Season 1. Day 168 of 306. 8 of 16 blocks. Last bar 2027-06-10."
- One plain sentence: "Every strategy was locked before the season started. Scores use only days that came after."
- Rows sit in three bands against the benchmark, `buy_hold`: **Ahead**, **Too close to call**, **Behind**. An entry is Ahead or Behind only when the CI of its excess-Sharpe difference from buy and hold lies wholly on one side of zero. Rows within a band sort by point estimate and carry no position number.
- Each row shows name and kind tag, season return, excess Sharpe with a CI bar, the band, and a greyed "pre-season (backtest)" figure.
- A "How to read this" line explains a CI bar in one sentence. A row opens its head-to-head against buy and hold. A matchup picker opens any pair.

The current front page's arm table, calibration, MDE panel, and rulebook move to entry pages and to `/studies/jev`.

## 2. How a strategy is defined

A fixed catalog, chosen by maintainers. Learners do not tune or build strategies.

An entry is a committed file, `league/entries/{name}.toml`: a strategy kind, fixed parameters, the hash of any fitted artifact, and a **behaviour fingerprint**. The fingerprint is the sha256 of the entry's positions on `random_walk` bars from `research/tests/test_states.py`, seeds 0 to 2. A code change that alters behaviour changes the fingerprint and fails verification, so "frozen" is checkable without freezing the codebase.

Kinds extend the `Arm` registry in `evaluate.py`: a score, a threshold, and a long rule. Season 1 uses arms that already run: `buy_hold`, `sma_filter`, `vote_trend`, `vote_revert`, `jev`, and `empirical_table` refit through 2026-10-09. Bollinger bounce, MACD crossover, candlestick, and ML entries join in Season 2. Each parameter set is its own entry and counts toward K, the season's entry count.

## 3. Where backtests run

In Python, on a schedule. Never in the browser, never on request.

- **Nightly tick.** After `SETTLED` (20:00 New York, `data.py`), the job runs `jt fetch` (28 credits, about 3 minutes, per the decision log), `jt league tick`, `jt export`, and `next build`, then syncs `web/out/` to S3 and invalidates CloudFront. Measured: states for 13 symbols take 0.3 s, and decisions plus a backtest of 9 arms over 25,402 holdout rows take 0.1 s. Compute is not the constraint.
- **Ledger.** `league/ledger.jsonl` is append-only, like `jev_calls.jsonl`. Each row holds one entry's 13 positions decided at close t, written before bar t+1 exists. The git push time is the public proof. About 230 KB a year for 6 entries.
- **Export.** A new `export/league/v1/` holds standings, per-entry equity, all K(K-1)/2 head-to-head files, and OHLC for entry charts, since redistribution rights are confirmed. Estimate: about 6 MB, mostly prices. It goes to S3, not git, so the repository does not grow by megabytes each night.
- **Pre-season.** Each entry's backtest runs once at entry with `decisions()`, `backtest()`, and `arm_reports()` and is never refreshed.

This stays static. **Backend trigger:** a backend comes back only when learners must submit their own strategy or parameters, which a nightly catalog cannot precompute. Nothing is built for it now.

## 4. How comparisons stay honest

This direction's weakness is power. Measured on the holdout at 5 bps with the joint-date 20-session bootstrap:

| Window | 95% CI half-width, pairwise excess-Sharpe difference |
|---|---|
| 63 sessions (a quarter) | 0.86 to 2.03 |
| 252 sessions (a year) | 0.60 to 1.06 |
| 1,952 sessions (the holdout) | 0.36 to 0.44 |

`vote_revert` minus `vote_trend` took the opposite sign to its full-holdout value in 5 of 7 years and 17 of 30 quarters. One season will mostly read "Too close to call". Four guards contain this:

1. **Bands, not ranks.** No position numbers.
2. **Family-wise intervals.** Standings use level 1 - 0.05/(K-1). Head-to-head uses 1 - 0.05/(K(K-1)/2). K = 6 makes intervals 31% wider than plain 95%, and K = 12 makes them 45% wider. Each season caps K at 12.
3. **No verdict before 3 blocks.** Under 60 sessions every band reads "Too early".
4. **Career records.** An entry's record since entry spans seasons, so its CI narrows over years.

**The replacement for honesty rule 5: windows are declared, never chosen.** Every figure belongs to one window kind. A season is declared in `league/seasons.toml` in a commit dated before its first session. A career starts at an entry's first ledger row. The pre-season is the two fixed study windows, development (2008 to 2018) and the old holdout (2019-01-02 to 2026-10-09). Checks enforce it:

- `web/src/lib/export.ts` rejects a metric whose `window` is not a declared season, career, or pre-season window. Standings rows are `period: z.literal("live")`, so no backtest enters that table.
- zod checks that each band agrees with its CI sign, each `level` equals the family-wise level for K, and bands read `too_early` when `blocks < 3`.
- `check-honesty.mjs` bans `type="date"` and range inputs under `web/src/`.
- `jt league verify` fails if a season file was committed on or after its start, an entry disappears, or a ledger row changes.

Entries close at season start, so K is fixed. A retired entry stays listed. Rows backfilled after a missed night carry `late: true`, and the site counts them.

## 5. Look-ahead for ML and candlestick entries

Checked twice.

- **In tests.** Generalise `test_levels_at_t_match_on_bars_truncated_at_t` in `test_states.py` from `levels()` to every catalog entry: the position at t on `bars.head(t + 1)` equals the position at t on the full frame. A new `candles(bars)` beside `levels()` in `states.py` returns pattern columns (engulfing, hammer, doji) from rows up to t and joins the same test.
- **In production.** `jt league verify` replays every entry over today's bars and requires each past position to equal its ledger row. A peeking strategy writes flat at tick time, because the future bar is missing, and something else on replay. The `oracle` arm (`lookahead=True`) is the test case: `league open` refuses it, and a copy with the flag removed fails `verify` on its first long day.
- **ML.** An ML entry fits once, at entry, on `labels()`. Entry adds a boundary to `SPLIT_STARTS`, so the existing purge (`_split(exit_day) == _split(day)`) nulls each label whose exit open falls after entry. Scalers and weights go in the hashed artifact. A refit is a new entry next season.

`adjust=all` rescales history after each dividend. Every states/v1 input is scale-invariant, so states should survive. A float tie at a threshold could still flip. The ledger stays the record, and a mismatch is investigated, never overwritten.

## 6. Jev and the finished study

The spec already planned this: "live testing later is a scheduled job that fetches bars and looks up answers." `jev` enters Season 1 from the frozen `data/policy/jev.parquet`, rebuilt by `jt jev-table --offline`, with its hash pinned in the entry file. It makes no API calls. Its row carries the label "Study result: inconclusive (AUC difference -0.012, 95% CI -0.045 to 0.024)" linking to `/studies/jev`. Its pre-season record is that pre-registered holdout. At 58 switches a year and 5 bps, it will likely land in "Behind", and the site says so.

The study pages move to `/studies/jev`, still built from `export/v1/`. `prereg.toml`, `holdout.json`, `holdout.manifest.json`, `jev_calls.jsonl`, and `export/v1/` never change.

## 7. First milestone: the ledger

Research only. No site, scheduler, or new strategy.

- `research/src/jevtrader/league.py` with `open_season`, `tick`, `replay`, and `verify`, and CLI commands `jt league tick` and `jt league verify` that read local files only.
- `league/seasons.toml` declares Season 1. Six entry files carry fingerprints.
- `research/tests/test_league.py` reuses the temporary git repository and synthetic bars from `test_holdout.py`. It checks that 30 simulated nights append 30 rows and the replay equals the ledger, an edited past row fails `verify`, `oracle` is refused, a de-flagged oracle fails `verify`, and a second tick on the same bars changes no file.

Done when `uv run python -m pytest tests/test_league.py` passes and `jt league verify` exits 0 on real data after the user runs one `jt fetch` and one `jt league tick`.

Milestone 8 adds the league export, the standings page, and `/studies/jev`. Milestone 9 adds the scheduler and deploy.

## 8. Product decisions

Decided by the user:

- **Target users: curious learners first.** Plain-language bands and a one-line CI explainer. Maintainers pick entries.
- **Static now.** The nightly rebuild counts as static. Backend trigger: learner-submitted strategies. Nothing built for it.
- **Prices may be published.** Twelve Data rights are confirmed, so the export carries OHLC for entry charts.
- **Jev is a contestant and an archive.** It plays from its frozen table with the study label, and the study lives at `/studies/jev`.

Still open:

- **Scheduler.** GitHub Actions cron on the public repository, or EventBridge with CodeBuild beside the Terraform-managed S3 and CloudFront. Either needs the Twelve Data key as a secret, and 28 credits a night.
- **Nightly commits.** The ledger needs a public timestamp. A bot commit to the public repository is simplest.
- **Season calendar and K cap.** Proposed: Season 1 runs from the first session after the entry commit through 2027-12-31, then calendar years, with K at most 12.

## Alternatives considered and rejected

- **Quarterly seasons.** Half-widths of 0.86 to 2.03 Sharpe, and the leader's sign flipped in over half the quarters measured. A table of coin flips.
- **Recomputing live records from bars.** Nothing would prove a position existed before its bar. Replay is the check. The ledger is the record.
- **Merging pre-season into live.** It mixes in-sample tuning into forward scores.
- **Numbered ranks.** They read noise as order.
- **Nightly ML refits.** Each refit is an unfrozen model. A refit waits for the next season.
