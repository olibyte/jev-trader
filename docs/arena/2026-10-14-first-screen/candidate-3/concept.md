# One rule against doing nothing

**What the visitor does.** They tap one of three famous trading rules and watch what it would have done with $1,000 in the S&P 500 since 2008, next to just holding.

**What they come away knowing.** "The golden cross dodged the 2008 crash but sat out big rebounds, so after 18 years it had $5,192 where just holding had $7,484, with smaller falls on the way, and a few lucky or unlucky switches decide most of that."

## First-screen copy (default state, word for word)

Trade Arena · Not investment advice.
**What would a trading rule have done with $1,000?**
Pick a well-known rule. See what it did with $1,000 since January 2008, next to simply buying once and holding.
PICK A RULE
- **Golden cross.** Stays in while prices are on a long climb. Moves to cash when the climb ends.
- **MACD crossover.** Stays in while prices are speeding up. Moves to cash when they slow down.
- **Bollinger bounce.** Buys after an unusually sharp drop. Sells once the price is back to normal.

Invested in [S&P 500 (SPY), 500 large US companies ▾]
Just holding **$7,484** Bought in Jan 2008. Never sold. | Golden cross **$5,192** In the market 77% of the time. 17 switches.
In the S&P 500 fund, Golden cross ended with **$2,292 less** than just holding. Its worst fall from a high was **32%**. Holding fell as much as **52%**.
Your $1,000, week by week. [Chart: two lines, a strip below marking "In the market" and "In cash". Touch or hover shows the month, both values, and in or out.] Legend: Just holding, Golden cross, In the market, In cash. ☐ Also draw the other two rules, faintly
WHAT IT DODGED
- **Jan 2008 to Jun 2009.** The fund fell 33% over 17 months while the rule sat in cash. Staying in would have left you with $3,421 today, not $5,192.
- **Mar 2022 to Jan 2023.** The fund fell 5% over 10 months while the rule sat in cash. Staying in would have left you with $4,833 today, not $5,192.

WHAT IT MISSED
- **Mar 2020 to Jul 2020.** The fund rose 28% over 3 months while the rule sat in cash. Staying in would have left you with $6,638 today, not $5,192.
- **Apr 2025 to Jun 2025.** The fund rose 17% over 2 months while the rule sat in cash. Staying in would have left you with $6,048 today, not $5,192.

WHAT SWITCHING COST
- **17 switches.** Each switch in or out costs a little. Without those costs it would have ended with about $5,236.

**So is the rule any good?** Sitting in cash 23% of the time cut both the falls and the gains. That is most of why it ended with less money and a smaller worst fall. / Measured against the size of the swings it put you through, Golden cross and holding come out too close to tell apart. Whatever gap is left could be luck. / One stretch of years shows what happened, not what will. A few calls like the ones above decide most of the gap, and different years bring different crashes and rebounds.
▸ Details for the technically minded
Footer: **Not investment advice.** Nothing here is a recommendation to buy or sell any security. Backtests are hypothetical, include modeled trading costs only, and do not predict future returns. / Real daily prices, Jan 2008 to Oct 2026. Every switch in or out costs 0.05%. "In cash" means short-term US Treasury bills, which pay a little interest.

Tapping a dodged or missed card shades that stretch on the chart. The URL keeps the choice (`#golden_cross/SPY`), so a visitor can share one story.

## One tap away

"Details for the technically minded" opens the catalog rule and citation, BIL as cash, 5 bps per switch, switches per year, time in the market, the largest peak-to-trough loss, excess Sharpe with its interval for the rule and for buy and hold, the difference with its 95% simultaneous interval over the 6 pairs on that fund (no verdict for a single fund), excess Sharpe at 0, 5, 10, and 20 bps, and the note that these years are not a holdout. The fund menu covers all 13 ETFs.

## Rationale

- The default rule is Golden cross because it comes first in catalog order. SPY is the default fund because most people know the S&P 500, not because of its result.
- The real data tells a consistent story. Every rule had a smaller worst fall than holding on all 13 funds, and 38 of the 39 rule and fund pairs ended with less money (measured from the export). Dollars plus worst fall make that trade visible without statistics. The second luck line maps the "no difference" result in `comparisons.json` to plain words.
- Rejected: the equal-weight portfolio as the default. "In the market 9 of 13 funds" breaks the in-or-out story, and nobody owns that portfolio. Ranking the three rules on one screen breaks honesty rule 5 and the direction. A "start in a different year" slider breaks honesty rule 1. "On 12 of 13 funds" was rejected because it counts wins.
- Biggest risk: the dollar view turns buy and hold into a visible winner, and a visitor may hear "trading rules lose money" as proven. Most of the dollar gap comes from time in cash during a rising market, not from bad timing. The luck box says so, but a visitor who stops at the two numbers misses it. A smaller risk is that the dodged and missed cards are picked as the biggest moves, so they show extremes by design. The card headings say what they are.
- Is the direction wrong? No. Buy and hold is already the catalog's benchmark, and "what if I'd just held" is the question a non-trader asks. Comparing two rules head to head stays secondary behind the faint-lines toggle.

## Build in `web/`

- Export first. `jt arena` adds, for each scope and strategy, `cashSpans` (first and last date of each stretch in cash) and `episodes` (fund change and "had it stayed in" value for each stretch) to `export/arena/v1/`. `catalog.py` already computes positions, so this adds fields and does no new research. The site keeps its rule that it never computes a metric. The mock infers spans from daily returns (`build_data.py`), and its golden cross switch counts match `comparisons.json` on SPY and QQQ. The real page must not infer them.
- `web/src/lib/arena.ts` holds zod schemas for `catalog.json`, `curves/<SYMBOL>.json`, `comparisons.json`, and the new fields, read at build through the existing `loadExport()` pattern.
- `app/page.tsx` is a server component that prerenders the default story. One client component, `RuleStory.tsx`, owns the picker, the fund menu, and the URL hash. A small SVG `StoryChart.tsx` draws the two lines and the in-or-out strip, which `lightweight-charts` cannot draw. Weekly points are downsampled at build.
- `format.ts` gets the dollar and month formats. `check:honesty` adds the banned first-screen words. The end-to-end test asserts the default copy above against `expected.ts`.

Files: `first-screen.html` (mock), `build_data.py` (export to inline JSON, writes the mock from `template.html`), `check.mjs` (drives the picker, a moment, the tooltip, and the details, and asserts no banned words and no network requests), `shot-1280.png`, `shot-390.png`, `check-390.png`.
