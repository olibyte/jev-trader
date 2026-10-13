# Trade arena: synthesis

This note records how the arena of 2026-10-13 became the proposed [product spec](../../product-spec.md) and the milestones in the [implementation plan](../../implementation-plan.md).

## The arena

Five candidates got the same [task](task.md), each with one direction anchor. Each wrote a concept and a throwaway first-screen mock. A separate judge scored them against the [rubric](rubric.md) and checked claims against the code. Its verdict is in [judge.md](judge.md).

| Candidate | Direction | Judge | Mine |
|---|---|---|---|
| [1](candidate-1/concept.md) | Fixed, precomputed catalog | 29 | 27 |
| [2](candidate-2/concept.md) | Precomputed parameter grid | 25 | 24 |
| [3](candidate-3/concept.md) | Backtests in the browser | 20 | 22 |
| [4](candidate-4/concept.md) | User-built rules with a sealed window, server later | 24 | 24 |
| [5](candidate-5/concept.md) | Live, forward-tested league | 22 | 23 |

All five candidates hit the usage limit partway through. Each one resumed from its own files. The user's four decisions reached them on resume: curious learners first, static now with a backend trigger later, Twelve Data rights confirmed, and Jev both a contestant and an archived study.

## The base: candidate 1

The judge and I picked the same base on separate scores. Candidate 1 has the simplest first screen, honesty rules that the build can check, and the smallest first milestone. That milestone ends in an exact match against `research/holdout.json`. Its scratch script reproduced `buy_hold` at 0.80 [0.10, 1.52] and `sma_filter` at 0.53 [-0.19, 1.33].

Its key claim holds. `evaluate.block_bootstrap` makes `default_rng(seed)` inside each call, so the same dates and seed draw the same blocks for every pair. A simultaneous interval over all pairs therefore needs only the per-pair draws, not a new resampler. The judge checked this separately.

## The first screen settled by observation

Candidates 1 to 4 drew the same layout without seeing each other's work: two strategy pickers, a three-way verdict above one interval bar, one equity chart, and a fixed period switch. Candidate 5 drew a standings table. That table carries a row per strategy, and with intervals this wide most rows read "too close to call". The [screenshots](shots/) show all five at 1280 px. Candidates 1 and 4 also render at 390 px with no horizontal scroll. The proposed spec keeps the shared matchup layout.

## Grafts

| From | Graft | Why |
|---|---|---|
| 2 | Build fails on a strategy that never trades in the backtest | Its probe found two RSI settings that never trade. A dead entry inflates the family for nothing. |
| 2 | The measured cost of a larger family | The adjusted half-width grows from 0.42 at 1 variant to 0.78 at 55. This sets the catalog cap. |
| 3 | `jt arena` reads full-precision bars, never the 4-decimal export | Rounding to 4 decimals flipped 34 indicator cells. |
| 3 | A parity gate (`check:engine`) is the precondition for any future browser engine | It showed parity is reachable (0 of 553,170 cells differ) and named its price. This goes in the backend trigger, not in the plan. |
| 4 | The verdict panel shows the smallest difference the period can detect | A learner who reads "no detectable difference" needs to know how big a difference could have been seen. |
| 4 | `candles()` beside `levels()` in `states.py`, and a feature registry that the truncation test runs over | It gives candlestick patterns the same look-ahead check that the indicators have. |
| 4 | The arena contract has no `start`, `end`, or `symbols` fields | A missing field cannot carry a chosen window. |
| 5 | The live period is an append-only position ledger that a replay verifies | Only a ledger written before the next bar proves a position came first. Replay catches a strategy that peeks. |
| 5 | Plain bands, never ranks, and "too early" below 3 blocks | Ranks read noise as order. |

## Rejected

- **Separate development and holdout periods** (judge's graft from candidate 2). Whoever builds the catalog has seen 2019 to 2026, and candidates 1, 3, and 5 computed results on it during this arena. The years are not a holdout for any catalog strategy, and a "holdout, not pre-registered" label asks a learner to hold a subtle idea. Two backtest windows would also double the family and offer a window to pick. Candidate 1's own scratch number shows the risk: `macd_cross` scores 0.82 over 2019 to 2026 and 0.45 over 2008 to 2026. The arena keeps one backtest period and one live period.
- **Candidate 4's luck line.** The simultaneous interval and the `coin_flip` control already show what chance looks like.
- **Knobs on the first screen** (candidate 2). They crowd the verdict for curious learners. Parameter variants can enter later as catalog entries that count toward the family.
- **A browser engine now** (candidate 3). It breaks "the site never computes a metric", and its trial count resets when the browser clears storage.
- **A sealed window for user rules** (candidate 4). The sealed prices are public, so the seal fixes the order and the count but not what the author has seen. It returns only with the backend trigger.
- **Seasons as the main view** (candidate 5). A one-year season gives a 95% half-width of 0.60 to 1.06 Sharpe, so standings would mostly read "too close to call" for years.

## Claims the judge found false

- Candidates 2, 4, and 5 each said their strategies fit `evaluate.ARMS` or run through `evaluate.decisions` unchanged. `ARMS` is `score > threshold`, which cannot express an exit or a hold of N sessions, and `decisions` iterates the fixed `ARMS` dict. This is why the plan adds a separate `CATALOG` with a `positions(bars)` function.
- Candidate 5 would add a boundary to `SPLIT_STARTS` for its ML purge. The plan instead generalises the purge to each refit date in new code and leaves the study's split code unchanged.

## Verification

- The judge and I agreed on the base before either saw the other's pick.
- The bootstrap claim that the base rests on was read in `research/src/jevtrader/evaluate.py` (`block_bootstrap`).
- Every first-screen mock was rendered with headless Chromium. Each shows a "mock data" badge and makes no network request.
- No candidate wrote to the repository, called Twelve Data or Jev, or touched a frozen file.
