# Cross-judge verdict

A read-only judge scored the four candidates against [rubric.md](rubric.md). It checked numbers against `export/arena/v1/` (final equity in `curves/*.json`, strategy stats in `comparisons.json`, and returns over the crash windows) and read every screenshot at 390 px and 1280 px.

## Scores (1 to 5)

| | Obvious action | Repeatable takeaway | Plain words, depth on demand | Product | Small build | Phone |
|---|---|---|---|---|---|---|
| 1. Pick two | 4. One-tap chips, but a pair is preselected, so "Pick two" reads slightly odd. | 5. The "can't tell yet" box is tied to the real portfolio result. Dollars sit next to time in market and biggest fall. | 5. No banned words visible. Full statistics in a collapsed section. | 4. A clean, calm tool. | 5. Reads only `curves/portfolio.json`, `catalog.json`, and `comparisons.json`. | 5. Chips and both dollar figures in the first screenful, no overflow. |
| 2. Guess first | 5. "Who ended with more money?" and two big buttons, one tap. | 3. Single years that flip carry "could be luck" well, but the takeaway opens with "buy and hold ended with more almost everywhere". | 4. The matchup table and statistics are one tap away. "Made-up trades" may read as fake data. | 4. Game-like and shareable, maybe a gimmick on a second visit. | 3. Works out single-year results that the export does not publish, ships about 580 KB of curves, and needs a 3-round state machine. | 5. The guess buttons fill the first screen. |
| 3. One rule against doing nothing | 4. Pick-a-rule cards, preselected. | 4. The dodged and missed cards make it concrete, but "$2,292 less" leads. | 5. The in-market strip and the "staying in would have left you with" cards. A rich details section. | 5. Reads as a story, with a shareable link. | 2. Needs new export fields (`cashSpans`, `episodes`) and computed what-if values. | 4. The picker fits, but the page is about 2,600 px tall. |
| 4. Everything at a glance | 2. Nothing to do. Every tap is optional. | 3. The lede is good, but the headline is false (see below). | 3. No banned words, but a log-scale axis is a technical idea for a newcomer. | 4. Polished, but feels like a dashboard. | 4. Existing data, but all 14 curves (about 600 KB). | 3. Four lines and 14 small charts, with cramped stat cards. |

## Base and second screen

- **Base: candidate 1.** It has the highest total, and every number checked matches the data. It says "can't tell" only where `comparisons.json` has a "no difference" result, which exists only for the 6 portfolio pairs. It reads only existing files and has one client component.
- **Second screen: candidate 2.** It is the most different interaction and has the most obvious action. Before building it, fix the SPY math, drop the "12 of 13 funds" count from the takeaway, and lead the end card with the single-year flips.
- Candidate 3 is the runner-up second screen, but it is close to candidate 1 (a picker and a chart) and costs export work.

## Suggested grafts

- From candidate 2: an optional "guess first" tap before the dollar figures, the one-sentence takeaway box, and its every-matchup table in the technical section.
- From candidate 3: the in-market and in-cash strip under the chart, the line "In cash means US Treasury bills, which pay a little interest", sharing a pair through the URL, and "Not investment advice." in the header.
- From candidate 4: shaded crash bands with plain labels, and the grid of every fund one tap away. "Golden cross turned $1 into $12.39 on the Nasdaq 100 and $1.66 on small companies" teaches luck without statistics, and both numbers check out.

## Problems found

- **Candidate 4's headline is false on its default view.** "The trading rules dodged part of every crash." In its own 2020 band (2020-02-19 to 2020-03-23, all 13 funds), the golden cross fell 29.0% and buy and hold fell 28.3%. The golden cross's worst fall is that 2020 drop.
- **Candidate 4's lede stays fixed on single funds.** "None of the four clearly did better" has no per-fund result behind it.
- **Candidate 2's SPY figures do not match the export.** The screen says $75,700 against $51,900, a gap of $23,800. The export gives $74,840 against $51,920, a gap of $22,920. The mock divided each line by its own first-day value, which drops buy and hold's first-day loss.
- **Candidate 2 frames a winner.** The "More money" badge, "You called it", the "Buy and hold ahead" legend, and "12 of 13 funds" all read as a scoreboard. It also says "18 years" where the span is 18.8.
- **Candidate 3** says the golden cross and holding are "too close to tell apart" on SPY, but the export has no result for single funds. Its what-if dollar values are computed in the mock, as its concept says.
- **Candidate 3 read the rubric by mistake.** The judge found no sign that the work was shaped by it.
- **Candidate 1** has one wording issue. "Trades the same 13 US stock funds" also covers buy and hold, which never trades.
- No first screen shows a banned word. No candidate uses "beats" or "the best".
