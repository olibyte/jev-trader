# Task: the first screen of the trade arena

## Context

jev-trader is a proof-of-concept web app at `/Users/oliverbennett/jev-trader`. The owner is refining the product spec. The priority changed on 2026-10-13:

- The priority is a simple UI that the owner can review and that non-technical people can use. It should read as a product, not a research experiment.
- The product is no longer about Jev (an AI model from an earlier, finished study). Do not feature Jev.
- We are not backtesting competing strategies with statistical rigor yet. Data cleansing, backtesting rigor, and statistics are deferred.
- The screen must be free of statistical jargon. Banned on the first screen: Sharpe, interval, confidence, CI, bootstrap, significance, p-value, MDE, drawdown, excess return, verdict families, blocks. Plain words only. A technical visitor may find details one tap away, but nothing on the first screen needs them.

The current product idea (PR #13, `/Users/oliverbennett/jev-trader-spec/docs/product-spec.md`) is a "trade arena": well-known trading strategies, run on the same US ETFs with the same costs, so a visitor can compare them. Read it for the strategy catalog and the honesty rules, but treat its statistics as deferred. Earlier first-screen concepts and screenshots are in `/Users/oliverbennett/jev-trader/docs/arena/2026-10-13-trade-arena/` (see `synthesis.md` and `shots/`). They are research-heavy. Treat them as input, not as decisions.

## Real data you may use

`/Users/oliverbennett/jev-trader/export/arena/v1/` holds real milestone 7 results. Read only. Never edit it.

- `catalog.json`: 4 strategies (Buy and hold, Golden cross, MACD crossover, Bollinger bounce), each with a one-sentence rule.
- `curves/portfolio.json` and `curves/<SYMBOL>.json` (SPY, QQQ, IWM, DIA, XLB, XLE, XLF, XLI, XLK, XLP, XLU, XLV, XLY): `{scope, costBps, periods: {backtest: {date: [...], equity: {<strategy id>: [...]}}}}`. Equity is the growth of $1 from 2008-01-02 to 2026-10-07 after a 5 basis-point cost per switch. "portfolio" is all 13 ETFs, equal weight.
- `comparisons.json`: statistical pair results. Every pair reads "no difference". You may use the plain fact that the differences are small and could be luck, but do not show its statistics.

You may also invent extra strategies or data, but any invented number must sit behind a visible "Mock data" badge.

## The question to answer

What does a visitor do on the first screen, and what do they come away knowing? It must work for a non-technical person (never traded, never heard of a moving average) and still feel worth it to a technical person.

## Your direction anchor

DIRECTION

Push this direction as far as it honestly goes. If you conclude it is wrong, say so in the rationale and still deliver the best version of it.

## Deliverables, all in OUTPUT_DIR

1. `concept.md`, at most 60 lines:
   - One sentence: what the visitor does.
   - One sentence: what they come away knowing, written the way a visitor would repeat it to a friend.
   - The full first-screen copy, word for word.
   - What sits one tap away for a technical visitor.
   - Rationale: alternatives you considered and rejected, and the biggest risk of this concept.
   - How it would be built in `web/` (a Next.js 16 static site, React 19, no backend) and which data it reads.
2. `first-screen.html`: one self-contained throwaway mock. Inline any data you need (write a small script that reads the export and emits a trimmed JSON, for example weekly or monthly points). No external network requests. It must be interactive where your concept is interactive.
3. Screenshots: run `node /private/tmp/claude-501/-Users-oliverbennett-jev-trader/3b5bc8ea-b099-4b91-bc60-edfdc5e57b9d/scratchpad/arena/shot.mjs file://OUTPUT_DIR/first-screen.html OUTPUT_DIR/shot`. It writes `shot-1280.png` and `shot-390.png` and prints horizontal overflow, which must be 0 at 390 px. Look at both screenshots and fix what reads badly.

## Rules

- Write only inside OUTPUT_DIR. Do not edit any file in the repository.
- Make no network calls. Never run `jt` commands, never call Twelve Data, OpenRouter, or Jev.
- Plain language. Short sentences. No jargon from the banned list on the first screen.
- Do not say a strategy "beats", "outperforms", or is "the best". Results over one period can be luck, and the screen should leave the visitor knowing that without statistics words.
- Include the disclaimer "Not investment advice." somewhere on the screen.
