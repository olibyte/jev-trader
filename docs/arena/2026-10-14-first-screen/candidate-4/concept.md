# Candidate 4: everything at a glance

**What the visitor does.** They read one sentence and one chart that already shows all four strategies on all 13 funds, and they may tap a strategy to read its rule or a fund to see it large.

**What they repeat to a friend.** "Those famous trading rules dodged part of the crashes but grew less than just holding, and none of them clearly came out ahead, so a good result could just be luck."

## First-screen copy, word for word

Header. Trade Arena. Famous trading rules, tested side by side. Not investment advice.

Headline. The trading rules dodged part of every crash. They also missed part of every climb.

Lede. Here is what **$1** became with each of four strategies, on the same US funds with the same trading costs, from January 2008 to October 2026. Once you allow for the smaller falls, **none of the four clearly did better than another.** Gaps this size could be luck.

Chart card. What $1 became. Fund [All 13 funds ▾]. One chart with four lines, end labels ($8.25 Buy and hold, $4.75 Golden cross, $2.83 Bollinger bounce, $2.78 MACD crossover), shaded bands 2008, 2020, 2022. Note below it: Each grid line doubles the money. Shaded: the 2008 crash, the 2020 drop, and the 2022 slide. Tap a strategy to read its rule.

Four cards in catalog order. Each shows name, one plain line, "$1 became $X", "Worst fall", "In the market", "Trades".
- Buy and hold. Buy on day one. Never sell. $8.25. Worst fall −50%. In the market 100%. Trades: buys once.
- Golden cross. Own it while prices trend up. $4.75. −32%. 76%. 1 a year.
- MACD crossover. Own it while prices are speeding up. $2.78. −27%. 51%. 20 a year.
- Bollinger bounce. Buy after an unusually sharp drop. $2.83. −31%. 20%. 9 a year.

Below the fold. The same four strategies on every fund. Same four lines, in the same colors, on each fund. The three rules swap places from fund to fund. Golden cross turned $1 into $12.39 on the Nasdaq 100 and $1.66 on small companies. A result that looks strong on one fund can look weak on the next. Tap a fund to see it large. Then 14 small charts in fixed order, each with its four ending values.

Footer. These are past results over one stretch of history. Everyone who picked these rules had already lived through these years, so a good past result is no promise. Each buy or sell costs 0.05%. Money out of the market earns short-term US Treasury bill interest. Every rule decides after the close and trades at the next open. **Not investment advice. Backtests are hypothetical and do not predict future returns.** [How this was tested, for the technically curious]

## One tap away for a technical visitor

- Tapping a card expands the plain "how it works", the exact textbook rule, and the citation. It also dims the other three lines.
- Hover or touch the chart for a date and all four values.
- "How this was tested" opens, for the chosen fund, excess Sharpe with its 95% interval, max drawdown, exposure, switches per year, Sharpe at 0, 5, 10, and 20 bps (MACD falls from 0.55 to 0.16 on all funds), and the six pair differences with simultaneous intervals, MDE, and verdict. It also states the fill timing, the BIL cash leg, the block bootstrap settings, and that the window is not a holdout.

## Rationale

The lesson in this data is a pattern, and a pattern only shows when every line is on screen. On all 14 views, each rule's worst fall is smaller than holding's (measured from `comparisons.json`). Holding ends with the most money on 13 of 14 views. The site never states that count, because counting one strategy's wins is a ranking. Every pair is "no difference". A picker hides all three facts behind a choice the visitor cannot yet make.

Rejected:
- A two-strategy matchup (the 2026-10-13 base). It asks a newcomer to pick before they know the names, and its default pair carries an implied question about who wins.
- A table of ending values. It reads as a scoreboard and invites sorting.
- A headline that changes with the fund ("X grew the most here"). That names a winner per fund. The headline stays fixed and holds on every fund.
- Linear axis. The 2008 fall vanishes once the top reaches $8. The log axis is labelled in dollars and the note says each line doubles the money.

Biggest risk. "$8.25 against $2.78" looks like a clear winner, and the risk-adjusted "could be luck" line asks the visitor to trust a sentence over a picture. The worst-fall row and the crash bands carry that sentence, but a skimmer may still leave thinking "holding wins". A second risk is that the direction stops at 4 strategies. At the spec's 8 to 10, one chart with 10 lines is spaghetti. The fix then is a 2-column grid of small charts, one strategy each against a gray buy-and-hold line, which keeps "all at once, fixed order".

## How it would be built in `web/`

- One page, `web/src/app/page.tsx`, a server component that reads `export/arena/v1/catalog.json`, `manifest.json`, `comparisons.json`, and every `curves/<scope>.json` at build time. The build thins the curves to weekly points.
- Add zod schemas for `arena/v1` beside the `v1` ones in `web/src/lib/export.ts`, so a bad file fails `next build`. Number formats go in `web/src/lib/format.ts`.
- Client islands are three. The chart (SVG, log scale, crosshair), the strategy cards (expand and highlight), and the fund state shared by the select and the tiles. No chart library is needed.
- Plain one-liners and "how it works" text are new catalog fields, written in `research/` so the export stays the one source. Fund display names are a small map in `web/`.
- `check:honesty` gains the first-screen word list, and a test asserts the cards render in `catalog.json` order.

Files. `build.py` inlines a trimmed export into `template.html` and writes `first-screen.html`. `interact.mjs` drives the taps, checks for banned words, and checks overflow and errors.
