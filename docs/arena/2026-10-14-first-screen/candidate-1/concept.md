# $1,000, two strategies, one chart

**What the visitor does.** They tap two strategies and watch what $1,000 became in each over the same 19 years.

**What they come away knowing.** "Buy and hold turned $1,000 into about $8,000 and the golden cross into about $4,700, but the golden cross sat in cash a quarter of the time and fell less, and the site says 19 years isn't enough to tell which is actually better."

## First screen, word for word (default pair, catalog order)

> **Trade arena** · How we got these numbers
> # Pick two strategies. See what $1,000 became.
> Each one starts with $1,000 in January 2008 and trades the same 13 US stock funds until October 2026. Each pays the same small fee every time it buys or sells.
> PICK TWO · [Buy and hold] [Golden cross] [MACD crossover] [Bollinger bounce]
> ● **Buy and hold.** Buy once and never sell.
> ● **Golden cross.** Stay in while the average price of the last 50 days is above the average of the last 200 days. Otherwise sit in cash.
> Tap another strategy to swap it in.
> ● Buy and hold **$8,248** · ● Golden cross **$4,748**
> After 19 years, **Buy and hold** ended with $3,500 more.
> Does that make it the better strategy? From 19 years of prices, nobody can tell. Here is why.
> Drag across the chart to see any month. The dotted line is the $1,000 you started with.
> [one chart, two lines, dollars from 2008 to 2026, no legend box: the tiles above are the key]
> ## More money is not the whole story.
> A strategy can end with more simply because it took more risk. Here is how differently these two got there.
> **Share of days invested.** Buy and hold 100%. Golden cross 76%. Golden cross sat in cash on 24% of days. Cash earns a little interest. It can't grow with the market, and it can't fall with it either.
> **Biggest fall from a high point.** Buy and hold 50%. Golden cross 32%. Buy and hold lost 50% of its value from May 2008 to Mar 2009. Golden cross's worst fall was 32%, in 2020.
> **So which one is better? We can't tell yet.** If both had taken the same amount of risk, the difference between them could be luck. 19 years of prices is not enough to tell these two apart.
> ▸ The numbers behind this, for the technically minded
> **Not investment advice.** Nothing here is a recommendation to buy or sell anything. These results replay past prices with a modeled fee on each trade. They do not predict future returns.

Every sentence below the pickers is generated from the pair's data. A near tie reads "they ended within $49 of each other" and "Is either one the better strategy?". Similar falls read "both lost about the same share". The luck box keys off the pair's verdict in `comparisons.json`, so it cannot say "can't tell" about a pair the statistics separate.

## One tap away

The disclosure holds the setup (the 13 tickers, BIL as cash, 5 bps per switch, the backtest years are not a holdout), this pair's excess Sharpe difference with its simultaneous 95% interval over 6 pairs and 236 blocks, the verdict, the smallest detectable difference, the exact catalog rules with citations, and a per-strategy table of excess Sharpe with interval, max drawdown, switches per year, and time in market.

## Rationale

I stripped the earlier matchup (two pickers, market picker, period switch, verdict, interval bar, chart, figure table) to chips, two dollar figures, one chart, and one "why" card. Rejected along the way:
- **Two dropdowns.** Each change costs two taps. Chips cost one, and "Pick two" is the whole instruction.
- **A fund picker.** Single funds have no verdict in `comparisons.json`, so the luck sentence would be unbacked there. It also invites shopping for the fund where your favourite ends ahead.
- **A year-by-year scoreboard as the luck signal.** I measured it. Buy and hold had the better year in 12 of 19 against golden cross and 15 of 19 against MACD. It reads as a win count, not as luck.
- **Dropping the risk card to stay "radical".** Without it the screen is dishonest. See the risk below.

**Biggest risk, and where this direction is wrong.** Ending dollars reward time in the market. In this data the strategy that was invested more ended with more in 5 of 6 pairs, and buy and hold ends highest in all three of its pairs. The largest number on screen will read as the answer, even though every pair is "no difference" once risk is counted. The "why" card carries that whole correction, and the visitor must take "could be luck" on trust because the evidence sits one tap away. A dollar race is the right hook for a non-technical visitor, but it cannot stand alone. If the owner wants the race without the card, I would not ship it.

## Building it in `web/`

- `app/page.tsx` stays a server component. It reads `export/arena/v1/` through a new `loadArena()` beside `loadExport()`, with zod schemas in `web/src/lib/arena.ts`, so a bad file fails `next build`.
- One client component, `Matchup`, holds `picks: [id | null, id | null]` and renders chips, tiles, an inline SVG chart, and the "why" card. No chart library. Number formats go in `web/src/lib/format.ts`.
- Data read: `catalog.json` (titles, rules, citations), `curves/portfolio.json` (equity × 1000), `comparisons.json` portfolio rows (`exposure`, `maxDrawdown`, `excessSharpe`, `switchesPerYear`, and the pair `verdict`, `simultaneous`, `blocks`, `family`, `mde`).
- Three additions belong in `jt arena` (`catalog.py`), not in the browser, because the site never computes a metric. A `plain` sentence per `CATALOG` entry, the worst fall's start and end dates, and a monthly curve. The daily curve is 4,720 points per strategy, and the mock's monthly trim is 227.
- Spec conflicts the owner must decide. The proposed spec requires an interval beside every metric, a verdict in large type, a period switch, and its own two disclaimers on the first screen. This concept moves the first three one tap away. Those are decision-log entries, not silent changes.
- `pnpm check:honesty` needs no new banned words. The mock passes the task's list on the first screen.

The mock is `first-screen.html`, built by `build.py` from `template.html`. `check.mjs` drives the picker, the scrub, and the disclosure at 390 px. It asserts no banned word outside the disclosure, the disclaimer, and zero network requests.
