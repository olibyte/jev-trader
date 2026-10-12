# Jev Trader product spec

> **This spec will change.** Jev Trader is an evolving research app. The requirements below record what we believe on 2026-10-12. Expect them to move as experiments return results. When a decision changes, update this file and add a line to the decision log in [implementation-plan.md](implementation-plan.md).

## The question we answer

How good is Jev at making stock-trading decisions, compared with traditional technical-analysis rules given the same information?

Jev is TypeSafe AI's decision model (`jev-1.13`). It answers typed questions about a block of state and returns probabilities, not text. Whether those probabilities have trading value is an empirical question. We do not assume Jev wins. A result that says "Jev does no better than a simple rule" is a valid result, and we publish it.

## Why the question is narrower than "can Jev trade"

Jev's own documentation says it is weak with numbers ("Jev is not a calculator") and stronger with descriptive text. It is trained to judge things whose answer is in the state it receives. A future price move is not in a technical-analysis snapshot. So when Jev sees "RSI overbought, price above the 200-day average", it can only apply its built-in sense of what those signals mean.

That makes the testable question this one. Does Jev's mapping from a described market situation to "will it be higher in 20 trading days?" rank good days above bad days better than rules and history-based tables that see exactly the same situation?

We expect Jev to be most useful later on unstructured inputs such as news text. The technical-analysis study comes first because it is cheap, and because it builds the data, evaluation, and publishing pipeline that the news study needs.

## Who it is for

- **Readers of the public site.** These are people curious whether AI decision models add anything to trading. They need honest numbers with error bars, and a way to see exactly what Jev was shown.
- **The researcher (us).** We need reproducible experiments. Rerunning a notebook must never change a result or trigger a paid API call.

## What the public site shows

The [dashboard mockup](assets/dashboard-mockup.png) sets the visual direction: a dark dashboard with a symbol selector, a candlestick chart with Jev markers, an indicator snapshot, a Jev decision panel, backtest curves, a metrics table, and a decision history. The numbers in the mockup are invented and are not results.

The core interaction is "time travel". You select any day on the chart and see what Jev was shown, what it answered, and what the price did over the next 20 trading days.

The site lands on the pre-registered study result: the main comparison, its 95% confidence interval, and one of three pre-declared outcomes. The outcomes are "Jev better", "Jev worse", and "inconclusive". Per-symbol pages come after that result and are labelled descriptive.

The site also shows Jev's rulebook. Jev's inputs come from a small fixed set of described situations (960 in the first study), so we can publish Jev's answer for every one of them.

## Honesty rules for the UI

These rules change the mockup in specific places.

1. Jev returns no reasoning or free text. The site never shows a "Reasoning" panel. In its place, a "What Jev saw" panel shows the exact state sent to Jev.
2. Jev's yes/no answers carry no confidence value. The site shows Jev's probability as "P(higher in 20 trading days)". It never labels that number as confidence or as a chance of profit. Next to it, the site shows how often that situation actually rose during the development period.
3. Every number links to the run manifest that produced it: dataset hashes, state version, prompt version, the model snapshot that served the calls, and the git commit.
4. Every metric shows its confidence interval and the number of independent observations behind it.
5. Every period carries its label: development, holdout, or live. The site has no free date picker for performance figures, because a free picker lets a reader search for a window where Jev wins.
6. Mock data appears only in prototypes, and only behind a visible "mock data" badge.
7. The site shows the model version that actually served the calls (`jev-1.13`). The mockup's "jev-1.3.0" is wrong.
8. The site states that it is research and not investment advice. Check whether publishing trading signals needs any further disclaimers before launch.

## Scope

### In scope now

- Daily OHLC data from Twelve Data for 13 US equity ETFs, plus BIL as the cash return.
- Six technical indicators, described as categorical states.
- One Jev question, asked once per state and frozen.
- Deterministic baselines, evaluation, and a static public site.

### Out of scope for now

These items may return later.

- News and sentiment inputs (Alpha Vantage, Marketaux, EODHD).
- Individual stocks inside the study. Stock pages may appear as out-of-study demos.
- Intraday data, short selling, and portfolio allocation across assets.
- User accounts, watchlists, and settings.
- FastAPI, a database, AWS, and Terraform.
- Live forward testing. With a frozen rulebook, live testing later is a scheduled job that fetches bars and looks up answers.

## Data and licensing

Twelve Data supplies the OHLC data. We assume we have display and redistribution rights. The API key stays server-side in `TWELVE_DATA_API_KEY` and never reaches the browser or git. The website reads only exported files and never calls Twelve Data or Jev.
