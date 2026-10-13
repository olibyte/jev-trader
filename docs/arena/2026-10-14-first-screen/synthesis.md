# First screen: synthesis

This note records how the arena of 2026-10-14 chose the first screen in the [product spec](../../product-spec.md).

## The question

On 2026-10-13 the user reset the priority. The project is a proof of concept, and the priority is a simple UI that non-technical people can use. It is no longer a Jev product, and statistics are deferred. The arena asked one question: what does a visitor do on the first screen, and what do they come away knowing?

## The arena

Four candidates got the same [task](task.md), each with one direction. Each wrote a concept and a throwaway mock on the real milestone 7 numbers. A separate judge scored them against the [rubric](rubric.md) and checked their numbers against `export/arena/v1/`. Its verdict is in [judge.md](judge.md).

| Candidate | Direction | Judge | Mine |
|---|---|---|---|
| [1](candidate-1/concept.md) | Pick two, see what $1,000 became | 28 | 29 |
| [2](candidate-2/concept.md) | Guess first, then reveal | 24 | 25 |
| [3](candidate-3/concept.md) | One rule against doing nothing | 24 | 22 |
| [4](candidate-4/concept.md) | Everything at a glance | 19 | 25 |

The [screenshots](shots/) show each mock at 1280 px and 390 px. The mocks themselves stayed in a scratch directory. Only the concepts and screenshots are kept here.

## The base: candidate 1

The judge and I picked the same base on separate scores. A visitor taps two strategies and sees two dollar amounts. Straight under them, the screen asks whether more money makes a strategy better, and answers that these years can't tell. Every number matched the export, and the page reads only files that `jt arena` already writes.

The judge's second screen was candidate 2, and I agreed after it showed candidate 4's headline was false for 2020. I built both as prototypes in `web/`. The user approved candidate 1 alone, and the game was removed. It is in commit `69ba6cb` on `feat/first-screen-prototype`.

## Grafts

| From | Graft | Why |
|---|---|---|
| Judge | "Invests in the same 13 US stock funds" instead of "trades" | Buy and hold never trades. |
| 3 | The footer says that "In cash" means short-term US Treasury bills | A visitor who reads "sat in cash" needs to know that cash earns a little. |
| 3 | The plain rule sentences, such as "Stay in while prices are on a long climb" | They are shorter than candidate 1's literal rules, which stay one tap away. |
| 3 | "Not investment advice." in the header | The disclaimer is visible before any number. |

## Rejected

- **Guess first as the home page** (candidate 2). Buy and hold ended with more money in 38 of 39 rule-and-fund matchups over the full period, so a visitor who always guesses buy and hold wins. The game also works out single-year results in the browser, which breaks the rule that the site never computes a figure.
- **Everything at a glance** (candidate 4). The visitor has nothing to do, and its headline was false for 2020. It also stops working past 4 strategies, because 10 lines on one chart cannot be read.
- **One rule against doing nothing** (candidate 3). It needs new export fields for the stretches in cash, and its "too close to tell apart" claim has no per-fund result behind it.
- **A fund picker on the first screen.** Only the all-funds view has a "no difference" result in `comparisons.json`, so "could be luck" would have nothing behind it on a single fund.
- **The in-market strip under the chart** (candidate 3). It needs positions that the export does not hold. It can return when `jt arena` exports them.

## Shared risk

Buy and hold ends with the most money in every pair it is in. The largest number on screen reads as the answer, although every portfolio pair reads "no difference" once falls are counted. The "More money is not the whole story" card carries that correction. A visitor who stops at the two amounts misses it.

## Verification

- I drove the built prototype in headless Chromium at 1280 px and 390 px. There was no horizontal overflow, no page error, no request beyond the static host, and none of the task's banned words in the visible text.
- `web/e2e/preview.spec.ts` checks the default pair ($8,248 and $4,748), the gap ($3,500), and a third tap that swaps in the MACD crossover ($2,779).
- All five `web/` checks pass.
- No candidate wrote to the repository, called Twelve Data or Jev, or touched a frozen file.
