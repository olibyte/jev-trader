# Trade arena product spec

> **This spec will change.** The trade arena is a proof of concept. This version records what the user approved on 2026-10-14. When a decision changes, update this file and add a line to the decision log in [implementation-plan.md](implementation-plan.md). The [first-screen synthesis](arena/2026-10-14-first-screen/synthesis.md) records how the first screen was chosen.

## What the trade arena is

Trade Arena shows what famous trading strategies would have done with your money, in plain words. You pick two strategies and see what $1,000 became in each. Both ran on the same 13 US stock funds, over the same years, with the same small fee each time they moved in or out of the market. Then the site explains why the one with more money is not automatically the better strategy.

Priority is a simple screen that a person who has never traded can use and share. Statistical rigor, new data sources, and live scoring wait until the screen works for people. [PR #13](https://github.com/olibyte/jev-trader/pull/13) holds the deferred plan for them.

## Who it is for

- **Curious people who have never traded.** They have heard of a golden cross or a Bollinger band and wonder whether it works. They need plain words, one comparison at a time, and no statistics on the first screen.
- **Technical visitors.** They want the exact rules and the setup. They find those one tap away, never on the first screen.

## The first screen is "Pick two"

A visitor picks two strategies and sees what $1,000 became in each. They come away able to say something like this: "Buy and hold turned $1,000 into about $8,200 and the golden cross into about $4,700. But the golden cross sat in cash a quarter of the time and fell less, and 19 years of prices can't tell you which one is better."

The screen shows these parts, top to bottom:

1. A header with the name "Trade Arena", a "Prototype" tag, and "Not investment advice."
2. The heading "Pick two strategies. See what $1,000 became." and one sentence on the setup: the 13 funds, the first and last month of prices, and the fee.
3. Two slots, "Strategy A" and "Strategy B". Each shows its strategy's title and its rule in one plain sentence. A slot opens a searchable list of every strategy, grouped by kind and in catalog order inside each group. On phones the list is a bottom sheet. A is always blue and B is always amber.
4. The two dollar amounts in large type for the chosen range, the day the $1,000 went in, and one sentence on the gap, such as "By Oct 7, 2026, Buy and hold had $3,500 more." Under it, the question "Does that make it the better strategy?" On every range shorter than all years, the answer is "One year is too short to tell skill from luck", with that range's length. On all years, the answer is "These years can't tell us."
5. A chart panel. Range buttons pick one week, one month, three months, one year (the default), five years, or all years. A Line or Candles toggle picks the view. The line view shows both amounts each day, from $1,000 at the start of the range, with a dashed line at $1,000. The candles view shows one fund's daily prices, S&P 500 by default, and "Show trades" marks each strategy's buys and sells on that fund. A visitor can move across either view to read any day.
6. A card titled "More money is not the whole story." It compares the share of days each strategy was invested and the biggest fall each one took from a high point, over the chosen range. On all years it ends with "So which one is better? We can't tell yet." and says that the gap could be luck.
7. A collapsed section, "The numbers behind this, for the technically minded", with the exact rules, moves per year, and the setup.

The prototype is at `/preview/` in `web/`. The [screenshots](assets/trade-arena/) show it at 1280 px and 390 px. The [first-screen screenshots](arena/2026-10-14-first-screen/shots/) show the light design that the arena picked.

The default pair is the first two strategies in catalog order, never a pair chosen by its result.

## Rules for plain, honest copy

1. **The first screen uses no statistics words.** These words appear only behind the technical section: Sharpe, interval, confidence, bootstrap, significance, p-value, drawdown, and blocks.
2. **No strategy is called a winner.** The site does not use the words "beats", "outperforms", "winner", or "best strategy". It says which one "had more money", which is a fact about the past.
3. **"Could be luck" needs a result behind it.** On all years, the site says that a gap could be luck only where `comparisons.json` reads `no_difference` for that pair. That result exists only for all 13 funds together, so every amount covers all 13. The candles view shows one fund's prices and trades, never an amount for one fund. A range shorter than all years is too short to judge any pair, and the site says so for every pair.
4. **The ranges are fixed.** Each range counts back from the last day of prices, and `windows.json` holds its figures. The site has no date input and no chart zoom.
5. **The site reads exported files and computes no figure.** The gap between two amounts is the difference of the two amounts on screen. The line chart restarts each exported curve at $1,000 on the first day of the range, so its last point matches the amount from `windows.json`. Everything else comes from `export/arena/v1/`.
6. **Strategies stay in catalog order.** The site never sorts or numbers strategies by a result.
7. **Mock numbers appear only behind a visible "Mock data" badge.** The prototype uses real numbers and has no badge.
8. **Every page shows the disclaimers.** "Not investment advice. Nothing here is a recommendation to buy or sell any security." and "Backtests are hypothetical, include modeled trading costs only, and do not predict future returns."

## What exists today

Milestone 7 built four strategies: buy and hold, the golden cross, the MACD crossover, and the Bollinger bounce. Each one is in the market or in cash on each fund. It decides after the close and trades at the next open. Cash earns the short-term US Treasury bill return (BIL), and each move in or out costs 0.05%. The funds are SPY, QQQ, IWM, DIA, and nine sector funds, held in equal parts and rebalanced each day. The years run from 2008-01-02 to 2026-10-07.

## Deferred

These items wait until the first screen works for people. [PR #13](https://github.com/olibyte/jev-trader/pull/13) holds the plan for most of them.

- More strategies: a candlestick pattern, a learned model, Jev from its frozen policy table, and a coin flip.
- Verdicts in words such as "A wins", and the statistics behind them.
- A live period scored after each close.
- Hourly bars, volatile individual stocks, and the cost models and data sources they need.
- Rules that visitors build, and the backend they need.

## The Jev study is finished

The Jev study asked whether Jev, TypeSafe AI's decision model, ranks 20-day outcomes better than a history table that sees the same indicator states. The pre-registered result is "inconclusive". Its pages stay at their current URLs until the home page becomes "Pick two", and then they move unchanged to `/studies/jev/`.

## Data and licensing

Twelve Data supplies the prices. We checked our display and redistribution rights, and they cover publishing these prices. The API key stays server-side in `TWELVE_DATA_API_KEY` and never reaches the browser or git. The website reads only exported files and never calls Twelve Data or Jev.
