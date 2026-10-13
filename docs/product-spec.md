# Trade arena product spec

> **This spec will change.** The trade arena is an evolving research app. The requirements below record what we believe on 2026-10-13. Expect them to move as experiments return results. When a decision changes, update this file and add a line to the decision log in [implementation-plan.md](implementation-plan.md). The [arena synthesis](arena/2026-10-13-trade-arena/synthesis.md) records how this version was chosen.

## The question we answer

Pick two well-known trading strategies, run them on the same ETFs with the same costs, and ask one question. Can you tell them apart?

Examples are a Bollinger bounce against a MACD crossover, or a candlestick pattern against a machine-learning model. The arena answers with a difference, an interval, and one of three verdicts: "A ahead", "B ahead", or "No detectable difference". We do not assume any strategy wins. Most pairs will read "No detectable difference", and we publish that as the answer, not as a failure.

## Why most answers will be "no detectable difference"

Twenty years of daily bars sounds like a lot of data. It is not. Thirteen ETFs that move together give about 236 independent 20-session blocks from 2008 onward. In the arena's scratch runs over 2019 to 2026, the 95% interval on the difference in excess Sharpe between two strategies was ±0.36 to ±0.44. An interval that covers many comparisons at once is wider. Over 2008 to 2018, ±0.42 for one comparison became ±0.78 for 55. The site explains this on the first screen instead of hiding it behind a ranking.

A window can also flatter a strategy. In a scratch run, a MACD crossover scored an excess Sharpe of 0.82 over 2019 to 2026 and 0.45 over 2008 to 2026. Readers cannot choose the window, for this reason.

## Who it is for

- **Curious learners.** People who have heard of Bollinger bands or a golden cross and want to know whether they work. They need plain words, one comparison at a time, and an honest picture of luck. They do not tune parameters or build rules in this version.
- **The researcher (us).** We need reproducible results. Rerunning `jt arena` must never change a published number or trigger a paid API call.

## What the site shows

### The first screen is one matchup

The home page asks "Pick two strategies. Can you tell them apart?" and shows five things:

1. Two strategy pickers, A and B, and a scope picker: "All 13 ETFs" or one ETF. Each strategy shows its rule in one plain sentence.
2. A period switch with two fixed periods: "Backtest" and "Live". There is no other way to choose dates.
3. The verdict, in large type. Below it are the difference A minus B, its interval drawn as a bar against zero, the number of independent blocks, and the smallest difference this period can detect.
4. One chart with the growth of $1 for A and B over the selected period. The chart has no zoom and no scroll.
5. One row of figures for each side: excess Sharpe with its interval, maximum drawdown, switches per year, and time in the market. The last three are labelled as point values with no interval.

The default pair follows catalog order, never a result. Everything else (strategy pages, the method, the run manifest, and the Jev study) sits one link away.

### The catalog is small and fixed

The arena compares strategies from one fixed catalog. Each entry has a name, a rule in one sentence, a short "how it works" note, a citation for its textbook parameters, and a kind. Learners choose entries. They do not change them.

The first catalog version has 8 entries:

| Strategy | Kind | Rule |
|---|---|---|
| Buy and hold | Benchmark | Always long. |
| Golden cross | Indicator | Long when the 50-day average is above the 200-day average. |
| MACD crossover | Indicator | Long when MACD(12, 26) is above its 9-day signal line. |
| Bollinger bounce | Indicator | Enter when the close falls below the lower band (20 days, 2 standard deviations). Exit when the close reaches the middle band. |
| Bullish engulfing | Candlestick | Enter after a bullish engulfing candle. Hold for 5 sessions. |
| Learned model | Machine learning | A logistic regression on the indicator states and candle flags, refit each January on past data only. Long when its probability of a rise over 20 sessions is above 0.5. |
| Jev (frozen rulebook) | AI model | Long when Jev's frozen P(higher in 20 trading days) is above 0.5. |
| Coin flip | Control | A seeded coin, flipped again every 20 sessions. It shows what luck looks like. |

Every strategy is long or flat on each ETF. It decides at the close and trades at the next open. Flat days earn the cash return (BIL), and each switch costs 5 basis points.

The catalog only grows. A changed rule is a new version of the entry, and an entry never disappears, so a losing strategy stays on the site. Each new entry widens every interval, so the catalog stays near 8 to 10 entries for learners.

### The finished Jev study stays, and Jev competes

The Jev study is finished, and its pages move unchanged to `/studies/jev/`. Its question was whether Jev ranks 20-day outcomes better than a history table that sees the same indicator states. The pre-registered outcome is "inconclusive". AUC(`jev`) minus AUC(`empirical_table`) is -0.012, with a 95% CI of -0.045 to 0.024, over 97 blocks.

Jev also enters the arena as "Jev (frozen rulebook)". It plays from the frozen policy table and makes no API call. Its strategy card states the study result and links to `/studies/jev/`. An arena verdict on Sharpe never replaces the study's pre-registered result on AUC.

## Honesty rules for the UI

1. **Periods are fixed and named, never chosen.** Every figure belongs to the `backtest` period or the `live` period. The backtest period runs from 2008-01-02 to the last bar before the catalog version froze. The live period starts at the first session after the freeze. The site has no date input, no date range in a URL, and no chart zoom. The build fails if any of these appears, or if a figure's first and last dates differ from its period's bounds in the arena manifest.
2. **The backtest period is not a holdout.** The people who chose the catalog had seen these years. The site says so next to every backtest figure. Only the live period is out of sample.
3. **A verdict accounts for every pair.** The verdict uses a simultaneous 95% interval that covers all pairs in the catalog version at once, so 28 pairs for 8 entries. Only the "All 13 ETFs" scope gets a verdict. A single-ETF view shows its interval with no verdict and states how many single-ETF comparisons exist and how many would exclude zero by chance. The build fails if a verdict disagrees with its interval or if the family size differs from the catalog's pair count.
4. **Every metric shows its interval and the number of independent blocks behind it.** Figures without an interval say so.
5. **No ranks.** The site lists strategies in catalog order. It never sorts them by a result, numbers them by a result, or picks a default pair by a result. In the live period, a verdict reads "Too early" until the period has 3 blocks.
6. **Every number links to the run manifest that produced it:** dataset hashes, the catalog version, each strategy's version, and the git commit.
7. **The site does not use the words** "beats", "outperforms", "winner", "best strategy", "confidence", or "Reasoning". `pnpm check:honesty` enforces the list.
8. **Mock data appears only in prototypes, and only behind a visible "mock data" badge.**
9. **Every page shows two disclaimers.** "Research, not investment advice. Nothing here is a recommendation to buy or sell any security." and "Backtests are hypothetical, include modeled trading costs only, and do not predict future returns."

The Jev study pages and the Jev strategy card keep three more rules from the study:

10. Jev returns no reasoning or free text. The site never shows a "Reasoning" panel. A "What Jev saw" panel shows the exact state sent to Jev.
11. The site shows Jev's probability as "P(higher in 20 trading days)". It never labels that number as confidence or as a chance of profit.
12. The site shows the model version that served the calls, `jev-1.13`.

## Scope

### In scope now

- Daily OHLC data from Twelve Data for 13 US equity ETFs, plus BIL as the cash return.
- One fixed catalog of up to about 10 strategies, all long or flat.
- Backtests computed in `research/` and published as static files.
- A static site on S3 behind CloudFront, managed with Terraform.
- A live period, scored by a scheduled job that fetches bars, records each strategy's positions before the next bar exists, and rebuilds the static files.

### Out of scope for now

These items may return later.

- Parameters that learners set, and rules that learners build.
- User accounts, watchlists, and settings.
- A backend that computes on request.
- Individual stocks, intraday data, short selling, and allocation across assets.
- News and sentiment inputs.

### What brings a backend back

The site stays static until a learner needs a result that `jt arena` cannot compute in advance. Examples are parameters that learners set, rules that learners build, or a catalog too large to precompute. Nothing is built for a backend before that. When the trigger arrives, two prerequisites carry over from the arena candidates:

- A backtest engine that runs in the browser must first pass a parity check that compares every position and metric with `research/` on the same bars.
- A server that scores learner-built rules must log each rule before it shows any result, and must count every logged rule in the family that the verdict accounts for.

## Data and licensing

Twelve Data supplies the OHLC data. We checked our display and redistribution rights, and they cover publishing these prices. The API key stays server-side in `TWELVE_DATA_API_KEY` and never reaches the browser or git. The website reads only exported files and never calls Twelve Data or Jev.
