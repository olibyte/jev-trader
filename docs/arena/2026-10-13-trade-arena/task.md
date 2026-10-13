# Arena task: a product concept for the "trade arena" pivot

You are one candidate in a design arena. Other candidates get the same task with a different direction anchor. Write a product concept. Write no production code.

## Grounding (read these first, read-only)

The repository is the `jev-trader` checkout on branch `docs/trade-arena`. Do not edit, commit, or create anything inside it. Read:

- `README.md`, `docs/product-spec.md`, `docs/implementation-plan.md` (the decision log records every measured result).
- `research/src/jevtrader/evaluate.py` (arm registry `ARMS`, long-or-flat backtest with costs, AUC, Brier skill, excess Sharpe, drawdown, turnover, joint-date 20-session block bootstrap, prereg lock).
- `research/src/jevtrader/states.py` (causal indicators, `State`, purged forward labels, splits) and `research/tests/test_states.py` (the truncation property test that catches look-ahead).
- `research/src/jevtrader/export.py` and `web/src/lib/export.ts` (the versioned `export/v1/` contract; the site never computes a metric).
- `web/src/app/page.tsx` and the other pages under `web/src/app/` (the current front page, which the user calls "a little overwhelming").

Facts you can rely on:

- Daily adjusted OHLC from Twelve Data for 13 ETFs (SPY, QQQ, IWM, DIA, 9 sector SPDRs) plus BIL as cash, 1993 onward. Splits: fit 2008-2014, validate 2015-2018, holdout 2019-01-01 to 2026-10-09.
- The Jev study is finished. Pre-registered outcome "inconclusive": AUC(jev) minus AUC(empirical_table) = -0.012, 95% CI [-0.045, 0.024], 97 blocks, MDE 0.032. Its frozen files (`research/prereg.toml`, `research/holdout.json`, `research/holdout.manifest.json`, `research/jev_calls.jsonl`) can never change.
- The site is a static Next.js export, to be hosted on S3 behind CloudFront with Terraform. Nothing is deployed. There is no backend, no accounts.
- The repository is public and `export/v1/` (6.5 MB) publishes Twelve Data prices in git.
- Honesty rule 5 bans a free date picker for performance figures, because a reader could hunt for a window where a strategy wins.

## The pivot (the user's words)

The front page is a little overwhelming. The long-term goal is a "trade arena" where users can visualise how trading strategies compare against each other. Examples: a Bollinger bounce strategy against a MACD crossover, or a candlestick-pattern strategy against a machine-learning strategy.

## Your direction anchor

{ANCHOR}

Push this direction honestly. Where it is weak, say so and say how you would contain the weakness. Do not drift into another candidate's direction to cover the weakness.

## What your concept must cover

1. What a user sees and does on the first screen, and how it stays simple.
2. How a strategy is defined: a fixed catalog, parameters, or user-built.
3. Where backtests run (precomputed, in the browser, or on a server), and what that means for the static S3 and CloudFront site. Give rough numbers (file sizes, compute time, grid sizes) where they decide the question.
4. How comparisons stay honest: CIs, period labels, multiple-comparison and data-snooping guards, and what replaces the "no free date picker" rule. The replacement must be a rule a test or the build could enforce, not a hope.
5. How ML and candlestick strategies avoid look-ahead. Name what in `states.py`, the truncation test, and the purged labels you reuse or extend.
6. What happens to Jev and the finished study.
7. The first milestone, small enough to ship and verify, ending in a command or check that passes or fails.
8. Open product decisions you would hand the user. Do not decide these: target users, whether accounts or a backend come back into scope, data sources and licensing, the fate of the Jev pages. State the options and what your concept needs from each.

Ground every claim in the code. When you say "reuse X", name the function or file.

## Deliverables

Write to `{OUT}`:

- `concept.md`: the concept, under about 1,500 words, with one section per point above, plus a short "Alternatives considered and rejected" section.
- `first-screen.html`: one self-contained, throwaway HTML file (inline CSS and JS, no network requests, no external scripts) that mocks the first screen at desktop width, and works at 390 px wide. Use invented numbers and show a visible "mock data" badge. It exists so the judge can compare first-screen layouts by eye.

Write plain, short sentences. No em dashes.
