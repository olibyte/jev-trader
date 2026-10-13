# Guess the rule

**What the visitor does.** They play three quick rounds of "who ended with more money?", tapping a guess before each answer appears.

**What they repeat to a friend.** "Over 18 years, just buying and holding ended with more money almost everywhere, but in single years the answer flipped a lot, so one good year proves nothing."

## First screen, word for word (round 1, before the tap)

> **Trade Arena** · Guess the rule  Round 1 of 3
> S&P 500 fund (SPY) · Jan 2, 2008 to Oct 7, 2026
> **Who ended with more money?**
> Each rule started with $10,000 in the S&P 500 fund, the 500 largest US companies, and followed its rule for 18 years.
> [Buy and hold. Buy on day one. Never sell.]  [Golden cross. Stay in while prices trend up. Move to cash when the trend turns down.]
> Tap your guess. Real prices, made-up trades, trading costs included.
> How this works, for the curious
> Not investment advice. These are past prices with simulated trades. Nothing here predicts the future.

**After the tap (real numbers).** Both amounts appear ($75,700 and $51,900), a "More money" tag marks Buy and hold, and the two lines draw in. "You called it. Buy and hold ended $23,800 ahead." Then a strip of 13 fund tiles under "The same 18 years in all 13 funds" and "Buy and hold ended with more money in 12 of 13 funds. Golden cross did in 1. Over a long stretch, the fund rarely changed the answer." [Next round]

**Round 2.** "Same two rules, same fund. Just one year this time." The year is drawn at random. The reveal shows SPY one year at a time as 19 tiles: "Golden cross came out ahead in 3 of 19 years (2008, 2018, 2022). Buy and hold did in 10. 6 were ties. Most of Golden cross's years were years the fund fell. Pick a different year and the answer often flips."

**Round 3.** "New fund, one year. Who ended with more?" The fund and year are drawn at random, so the visitor tests what round 2 taught (crash years go to the rule that holds cash).

**End card.** "You called 2 of 3." Then three lines, counted over all 13 funds:
1. Over 18 years in which prices mostly rose, Buy and hold ended with more money in 12 of 13 funds.
2. One year at a time, the answer flipped. Golden cross came out ahead in 46 of 247 fund-years, about 1 year in 5. Buy and hold did in 129. 72 were ties.
3. Money at the end is not the whole story. Rules that sit in cash fall less in a crash and gain less in a rally. When our tests weighed the gains against the ups and downs, they could not tell these two rules apart. The gap could be luck.

Then the one-sentence takeaway and "Play again: Buy and hold vs MACD crossover". Each replay moves to the next of the 6 pairs in catalog order.

## One tap away

"How this works, for the curious" opens the exact rules with their citations, the simulation (13 ETFs, cash in BIL, 0.05% per switch, how a one-year round starts), a table of every matchup with its full-stretch and single-year counts, and the statistics: excess Sharpe, the simultaneous 95% interval, the block bootstrap, "no difference" on all six pairs, and the warning that these years are not out of sample.

## Rationale

- **Rejected. A quiz with hand-picked surprising rounds.** It would be more fun, but choosing rounds by their result is cherry-picking. Round 1 is fixed by familiarity (SPY, full period, catalog-order pair), and rounds 2 and 3 are random draws. The tiles always show every year or every fund, so no draw hides the rest.
- **Rejected. Letting the visitor choose the years.** It invites window shopping. The game varies the window, but the strips show all 19 years at once.
- **Rejected. Scoring against a "luck line".** "A coin would get 1.5 of 3" is true but teaches about the guesser, not the rules.
- **Where the direction is weaker than it looks.** On ending money, buy and hold is ahead in 38 of 39 full-period fund matchups against the three timing rules. After one round, a sharp visitor always guesses buy and hold, and over 18 years they are right. The game stays honest only because rounds 2 and 3 switch to single years, where the rules come out ahead about 1 year in 4 against buy and hold, mostly in falling years. Ending money also rewards time in a rising market. Line 3 of the end card carries the "could be luck" idea, and it is the line most likely to be skimmed.
- **Biggest risk.** The visitor leaves with "buy and hold wins" instead of "one stretch proves little". Single-year ties (Golden cross held the fund all year in 72 of 247 fund-years) also make some rounds anticlimactic. I kept them because a tie is a real outcome and removing them would be choosing rounds by result.

## How it would be built in `web/`

- One client component `GuessGame` on the home page, with a reducer over `{pair, rounds[3], index, guesses}`. The page stays static. The round draws run in the browser from `Math.random`.
- It reads `export/arena/v1/catalog.json` and `curves/<SYMBOL>.json` through a new `loadArena()` beside `loadExport()` in `web/src/lib/export.ts`, with zod schemas and a check that every curve spans the manifest period. Build time trims each curve to weekly points plus year-end anchors (about 580 KB for 13 funds, mostly dates, so it can split per fund).
- It picks a winner by comparing the ratio of two stored equity values. That is a comparison of published numbers, not a new metric, but it does derive single-year results the export does not publish. If the honesty rule needs every figure in the export, `jt arena` should emit a `years.json` with each pair's year-end values, and the site only reads it.
- Plain descriptions of each strategy and fund live in a typed table in `web/src/lib/`, keyed by catalog id and symbol. Money formats go in `format.ts`. `check:honesty` already covers the banned words.
- The prototype is `first-screen.html`. `build_data.py` is the trimming script that emits it from `template.html`. `states.mjs` captures the reveal and end states.
