# Trade arena product spec

> **This spec will change.** The trade arena is an evolving research app. The requirements below record what we believe on 2026-10-13. Expect them to move as experiments return results. When a decision changes, update this file and add a line to the decision log in [implementation-plan.md](implementation-plan.md). The [arena synthesis](arena/2026-10-13-trade-arena/synthesis.md) records how the first version was chosen. The section [Tradeoffs behind this version](#tradeoffs-behind-this-version) records why the question changed to "Which one wins?".

## The question we answer

Pick two trading strategies, run them on the same market with the same costs, and ask one question. Which one wins?

Examples are a Bollinger bounce against a MACD crossover, or a candlestick pattern against a machine-learning model. The arena answers with a difference, an interval, and one of three verdicts: "A wins", "B wins", or "Too close to call".

A win has one meaning. Over a named market and period, the simultaneous 95% interval for A minus B in excess Sharpe lies entirely above zero. "B wins" means the interval lies entirely below zero. Any other interval reads "Too close to call", and we publish that as an answer, not as a failure. Milestone 7 compared the first four strategies on 13 ETFs from 2008 to 2026, and all six pairs read "Too close to call".

## What makes a win possible

Three things set how wide an interval is:

- **The years in the period.** Milestone 7 had 18.8 years of daily bars in 236 independent 20-session blocks.
- **How differently the two strategies trade.** Two strategies that are long on mostly the same days have a narrow interval, because luck moves them together. In milestone 7, buy and hold against the golden cross had a simultaneous interval of ±0.40 excess Sharpe. The MACD crossover against the Bollinger bounce had ±0.72.
- **The number of pairs that the verdict covers.** Six pairs needed a critical value of 2.53 instead of 1.96. In a scratch run over 2008 to 2018, the half-width grew from 0.42 for one pair to 0.78 for 55.

Two things do not narrow an interval, and we checked both with a simulation of 2,000 runs of 5 years each. Shorter bars do not help. The spread of the annualised Sharpe estimate was 0.45 on daily bars, 0.46 on hourly bars, and 0.46 on 5-minute bars. Volatility does not change it either, at 0.46 for 16% annual volatility and 0.47 for 60%. Sharpe divides volatility out, and its precision depends on years, not on how many bars those years hold.

Faster bars and volatile stocks matter for a different reason. They change what a strategy can do. A rule that makes many independent decisions a day can have a much larger real difference from buy and hold than a rule that switches four times a year, and that difference is what a win needs. Trading costs grow with every switch, so the same markets also produce large real losses. Results will vary more, and most of that variety will still be luck. The verdict shows which part is not.

A window can also flatter a strategy. In a scratch run, a MACD crossover scored an excess Sharpe of 0.82 over 2019 to 2026 and 0.45 over 2008 to 2026. Readers cannot choose the window, for this reason.

## Who it is for

- **Curious learners.** People who have heard of Bollinger bands or a golden cross and want to know whether they work. They need plain words, one matchup at a time, and an honest picture of luck. They do not tune parameters or build rules in this version.
- **Strategy builders, later.** People who want their own rule to compete. They arrive with the backend, under the rules in [Learners build strategies later, and theirs play forward](#learners-build-strategies-later-and-theirs-play-forward).
- **The researcher (us).** We need reproducible results. Rerunning `jt arena` must never change a published number or trigger a paid API call.

## What the site shows

### The first screen is one matchup

The home page asks "Pick two strategies. Which one wins?" and shows five things:

1. Two strategy pickers, A and B, a market picker, and a scope picker. The scope is the whole market, such as "All 13 ETFs", or one symbol in it. Each strategy shows its rule in one plain sentence.
2. A period switch with two fixed periods: "Backtest" and "Live". There is no other way to choose dates.
3. The verdict, in large type, with the market and the period it applies to. Below it are the difference A minus B, its interval drawn as a bar against zero, the number of independent blocks, and the smallest difference this period can detect.
4. One chart with the growth of $1 for A and B over the selected period. The chart has no zoom and no scroll.
5. One row of figures for each side: excess Sharpe with its interval, maximum drawdown, switches per year, and time in the market. The last three are labelled as point values with no interval.

The default pair and market follow catalog order, never a result. Everything else (strategy pages, the method, the run manifest, and the Jev study) sits one link away.

### Markets are fixed pairs of a universe and a bar size

A market is a universe of symbols traded on one bar size, such as "13 ETFs, daily". We choose the list of markets. Learners pick from it and never define one. Each market has its own backtest period, because history differs by bar size and by symbol, and its own live period.

| Market | Status |
|---|---|
| 13 ETFs, daily | Built. Milestone 7. |
| 13 ETFs, hourly | Planned. The first intraday market. |
| Volatile stocks, daily | Planned. Needs the universe rule below. |
| 13 ETFs, 1-minute | Later. Waits for a cost model that has held up at hourly bars. |

A rule is written in bars. On daily bars a bar is a session, so "the 50-day average" is the 50-bar average. On hourly bars the same rule reads the 50-hour average, which is a different idea, and the strategy card says so. Parameters stay the cited textbook values. Jev (frozen rulebook) and the learned model are daily only. They read the daily `State` and a 20-session horizon, so they play only in daily markets.

In an intraday market, a strategy decides at the close of a bar and trades at the open of the next bar, inside regular session hours. A position can stay open overnight and earns the gap to the next open. Bar returns compound into one return per session, and the excess Sharpe, the bootstrap, and the portfolio read those daily returns. That keeps intervals comparable across markets.

Each market has a cost per switch, fixed before its first run. Daily ETFs keep 5 basis points. Every market also shows its figures at 2 and 4 times its cost as point values. The costs for the planned markets are proposals that wait for a decision:

- **13 ETFs, hourly: 5 basis points.** A switch pays the instrument's spread, and the bar size does not change the spread. On 2026-10-12, State Street listed a 30-day median quoted spread of 0.02% for XLB and 0.00% for SPY. Five basis points is at least 5 times the half-spread of either. Spreads are wider just after the open, and the figures at 2 and 4 times the cost cover that.
- **Volatile stocks, daily: 25 basis points, or the measured median spread if that is higher.** Before the first run, we measure the quoted spread of the stocks that the universe picks, from the data source's quotes. A full spread on each switch leaves room for price impact in thinner stocks. The 25 is a guess. We do not estimate spreads from daily highs and lows, because those estimates are biased for volatile stocks. The spread depends on the universe's floor, and the proposed floor is a closing price of at least $5 and a median daily dollar volume of at least $20 million over the previous 63 sessions.

### Volatile stocks need a universe chosen without hindsight

Today's list of volatile stocks leaves out the ones that collapsed or were delisted, and that flatters every long strategy. A fixed rule chooses the universe at each past date instead. Each January, it takes the 20 US common stocks with the highest volatility over the previous 252 sessions, among stocks above a price and volume floor, using only data from before that January. The universe holds for the year. A stock that is delisted during the year moves to cash.

The rule needs listings that include delisted stocks. The proposed source is Massive, formerly Polygon.io. Its ticker list answers which stocks were listed on a past date, and its daily files cover every US stock from 2003-09-10. The first January with a full prior year is then January 2005, which starts this market's backtest. Three facts about it are unchecked. Do its past daily files hold stocks that were delisted since? Do its terms let us publish figures derived from its prices? How does it adjust for dividends? The implementation plan compares the alternatives, and the choice waits for a decision.

A delisted stock exits at its last close. Only some sources record what holders got after the last trade, so that price can flatter a stock that collapsed after it. The market states how many of its stocks were delisted during a year.

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

Every strategy is long or flat on each symbol. Flat periods earn the cash return (BIL).

The catalog only grows. A changed rule is a new version of the entry, and an entry never disappears, so a losing strategy stays on the site. Each new entry widens every interval, so the catalog stays near 8 to 10 entries for learners.

### Learners build strategies later, and theirs play forward

Learners building and testing their own rules is the long-term goal. It needs a backend, and it waits for the trigger in [What brings a backend back](#what-brings-a-backend-back). Its cost and effort may change the plan.

A learner's rule gets a verdict only from its live period, which starts at the first session after the rule is saved. Its backtest is shown with no verdict. A learner can try hundreds of rules on the backtest years and keep the one that wins, and no interval can correct for tries that nobody logged. Forward play cannot be tuned that way.

The site logs each rule, with its fingerprint and the time it was saved, before it shows any result.

A learner rule's verdict accounts for that rule's pairs with every catalog entry, in every market where the rule's inputs exist. The learner does not choose the markets. The verdict does not account for other saved rules. One learner's save therefore changes no other verdict, and a rule with a real edge keeps the same chance of a win however large the site grows. A pair of two learner rules shows its interval with no verdict.

The cost is that luck wins grow with the number of rules, so the site states them on the same screen. Next to every learner verdict, it states four numbers:

- how many rules have played
- how many would show a win that night if none had a real edge
- the higher count that luck gives on 1 night in 20
- how many rules show a win that night

Deleted rules keep counting. The rule page lists the learner's other saved rules in save order, with no verdicts. A public log lists every saved rule with its fingerprint and save time, also with no verdicts.

Wins will be rare. In a simulation, a rule that beat buy and hold by a true 0.5 excess Sharpe showed a win at the 5-year mark in at most 15% of runs. The [learner-verdict arena](arena/2026-10-13-learner-verdicts/synthesis.md) measured this answer against counting every saved rule, every rule from one account, and a false-discovery rate. It also found two problems that wait for a decision, because they change every live verdict. Today's interval is too narrow on short windows, and a verdict recomputed every night lets luck show a win on some night. The implementation plan's open questions describe both.

### The finished Jev study stays, and Jev competes

The Jev study is finished, and its pages move unchanged to `/studies/jev/`. Its question was whether Jev ranks 20-day outcomes better than a history table that sees the same indicator states. The pre-registered outcome is "inconclusive". AUC(`jev`) minus AUC(`empirical_table`) is -0.012, with a 95% CI of -0.045 to 0.024, over 97 blocks.

Jev also enters the arena as "Jev (frozen rulebook)". It plays from the frozen policy table and makes no API call. Its strategy card states the study result and links to `/studies/jev/`. An arena verdict on Sharpe never replaces the study's pre-registered result on AUC.

## Honesty rules for the UI

1. **Periods are fixed and named, never chosen.** Every figure belongs to the `backtest` period or the `live` period of one market. The daily ETF backtest runs from 2008-01-02 to the last bar before the catalog version froze. Each other market's backtest runs from its first bar with enough history to the same freeze. The live period starts at the first session after the freeze. The site has no date input, no date range in a URL, and no chart zoom. The build fails if any of these appears, or if a figure's first and last dates differ from its period's bounds in the arena manifest.
2. **The backtest period is not a holdout.** The people who chose the catalog had seen these years. The site says so next to every backtest figure. Only the live period is out of sample.
3. **A verdict accounts for every pair in every market.** The verdict uses a simultaneous 95% interval that covers all pairs in all markets of the catalog version at once, so a learner cannot find a win by trying markets. Only the whole-market scope gets a verdict. A single-symbol view shows its interval with no verdict and states how many single-symbol comparisons exist and how many would exclude zero by chance. The build fails if a verdict disagrees with its interval or if the family size differs from the number of pairs in all markets.
4. **Every metric shows its interval and the number of independent blocks behind it.** Figures without an interval say so.
5. **One matchup, no ranks.** "Which one wins?" asks about one pair. The site lists strategies in catalog order. It never sorts them by a result, numbers them by a result, counts a strategy's wins, or picks a default pair by a result, because each extra comparison is another draw of luck. In the live period, a verdict reads "Too early" until the period has 3 blocks.
6. **Every number links to the run manifest that produced it.** An arena number links to the input file hashes, the catalog version, and each strategy's version and fingerprint. The arena manifest records no git commit, because the export is committed and a commit would change it on every run. A Jev study number links to the git commit of its holdout run.
7. **"Wins" appears only where an interval supports it.** The word appears in the question "Which one wins?" and in a verdict whose simultaneous interval excludes zero, next to its market and period. The site does not use the words "beats", "outperforms", "winner", "best strategy", "confidence", or "Reasoning". `pnpm check:honesty` enforces both rules.
8. **Mock data appears only in prototypes, and only behind a visible "mock data" badge.**
9. **Every page shows two disclaimers.** "Research, not investment advice. Nothing here is a recommendation to buy or sell any security." and "Backtests are hypothetical, include modeled trading costs only, and do not predict future returns."

The Jev study pages and the Jev strategy card keep three more rules from the study:

10. Jev returns no reasoning or free text. The site never shows a "Reasoning" panel. A "What Jev saw" panel shows the exact state sent to Jev.
11. The site shows Jev's probability as "P(higher in 20 trading days)". It never labels that number as confidence or as a chance of profit.
12. The site shows the model version that served the calls, `jev-1.13`.

## Scope

### In scope now

- The "13 ETFs, daily" market, with daily OHLC bars from Twelve Data for 13 US equity ETFs and BIL as the cash return.
- One fixed catalog of up to about 10 strategies, all long or flat.
- Backtests computed in `research/` and published as static files.
- A static site on S3 behind CloudFront, managed with Terraform.
- A live period, scored by a scheduled job that fetches bars, records each strategy's positions before the next bar exists, and rebuilds the static files.

### Planned next

- The "Which one wins?" question and its three verdicts on the first screen.
- An hourly ETF market, then a volatile-stock market. Each one widens every interval, so each one must earn its place.

### Out of scope for now

These items may return later.

- Parameters that learners set, and rules that learners build. They arrive together with the backend.
- User accounts, watchlists, and settings.
- A backend that computes on request.
- Short selling and allocation across assets.
- News and sentiment inputs.

### What brings a backend back

The site stays static until a learner needs a result that `jt arena` cannot compute in advance. Examples are parameters that learners set, rules that learners build, or a catalog too large to precompute. Nothing is built for a backend before that. When the trigger arrives, three prerequisites carry over:

- A backtest engine that runs in the browser must first pass a parity check that compares every position and metric with `research/` on the same bars.
- A server that scores learner-built rules must log each rule before it shows any result.
- A learner-built rule gets a verdict only from its live period, over its own pairs with the catalog, with the count of luck wins beside it.

The nightly job records intraday positions after the close, not before each bar. The replay still fails a rule that reads a later bar, but the ledger proves the order of each day's decisions only, not each bar's. A job that records each bar as it closes is a backend, and it waits for the same trigger.

## Tradeoffs behind this version

The first version asked "Can you tell them apart?". It was accurate, but it asked learners to care about a statistical idea before they cared about the matchup. "Which one wins?" is the question learners already have. The risk is that the new question promises winners that the data cannot deliver, so every choice below keeps the promise conditional on the interval.

| Choice | Picked | Rejected | Why |
|---|---|---|---|
| The question | "Which one wins?" with three answers | "Can you tell them apart?" | The new question is the one learners bring. Three answers keep "Too close to call" as a full answer. |
| The answer | The simultaneous interval decides | The larger point value wins | A point value names a winner every time, and most of those winners would be luck. |
| Pairs that a verdict covers | Every pair in every market | Each market on its own | Separate markets would let a learner try markets until one shows a win. Each market added widens every interval, so we add markets slowly. |
| First intraday bar size | Hourly | 1-minute | Shorter bars do not narrow intervals. Hourly bars have spreads we can model, and 1-minute strategies would be judged mostly on a cost model we cannot yet check. |
| Volatile-stock universe | Chosen each January by a fixed rule, delisted stocks included | Today's most volatile stocks | Today's list hides every stock that collapsed. That bias favours every long strategy. |
| Learner-built rules | Verdict from the live period only | Backtest verdicts with a wider interval | Nobody can count the tries a learner makes before saving a rule. Forward play needs no count. |
| Pairs that a learner rule's verdict covers | The rule's own pairs with the catalog, with the luck count beside the verdict | Every saved rule, every rule from one account, or a false-discovery rate | With every saved rule in one family, a rule that beat buy and hold by a true 1.0 excess Sharpe showed a win within 5 years in 0.3% of runs at 10,000 rules. A family of one account's rules fails as soon as a person opens a second account. A false-discovery rate makes each verdict's level move with strangers' rules. |
| Sharpe in intraday markets | Computed from daily returns | Computed per bar | Precision depends on years, not bars, so per-bar Sharpe gains nothing. Daily returns keep markets comparable and reuse the existing code. |

The cost of this direction is that "Too close to call" will stay the most common answer for a long time. We think that is the honest product, and the live period is where wins can come from. Each session adds evidence that nobody can tune.

## Data and licensing

Twelve Data supplies the OHLC data. We checked our display and redistribution rights, and they cover publishing daily and intraday prices. The data source is replaceable. How far back a provider's history goes and which plan tier we use do not constrain the design, because we can move to another API or a paid tier when a market needs it. The API key stays server-side in `TWELVE_DATA_API_KEY` and never reaches the browser or git. The website reads only exported files and never calls Twelve Data or Jev.
