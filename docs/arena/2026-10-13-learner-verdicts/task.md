# Arena task: who does a learner-built rule's verdict account for?

## Context (read these first, read-only)

- docs/product-spec.md: "The question we answer", "What makes a win possible", honesty rules 3 and 5, "Learners build strategies later, and theirs play forward", "What brings a backend back", "Tradeoffs behind this version".
- docs/implementation-plan.md: "Comparisons", "Markets and 'Which one wins?'", milestone 11 (live period), "Open questions", the 2026-10-13 decision-log entries.
- research/src/jevtrader/catalog.py `critical_value` and research/src/jevtrader/evaluate.py `block_bootstrap`, `sharpe`: how the simultaneous interval is computed today.

Settled and not up for debate: three answers ("A wins", "B wins", "Too close to call"); a simultaneous 95% interval decides; a learner-built rule gets a verdict only from its live period, which starts at the first session after it is saved; every rule is logged with its fingerprint and save time before any result shows; the live verdict is recomputed after every session (nightly job, milestone 11) and reads "Too early" below 3 blocks of 20 sessions.

## Your job

You are assigned ONE answer (below). Make the strongest honest case for it, and report its weaknesses plainly. Produce `proposal.md` in your output directory with:

1. The rule, stated precisely: which pairs the simultaneous interval covers for a learner rule's verdict, and what the site states next to it.
2. Measured win rates on synthetic data (see the shared setup). Tables, with the script that produced them in your directory.
3. Honesty: chance that a shown "win" is luck, per verdict and site-wide; what a learner (or one person with many accounts) can do to game it; effect of nightly re-looks.
4. Cost: compute per night as saved rules grow, storage, build effort against the current static `jt arena` architecture, and whether saving a learner rule changes any catalog-vs-catalog verdict.
5. One paragraph a curious learner would read on the site to understand the verdict.
6. Alternatives you considered and rejected, with reasons.

Keep proposal.md under about 1,200 words. Plain, short sentences. No long dashes.

## Shared synthetic setup (use it so candidates compare)

- 252 sessions a year, 20-session blocks. Annualised excess Sharpe as in `evaluate.sharpe`.
- Strategies are long or flat on the same market, so their returns are correlated. Model daily excess returns as r_i = mu_i + s * (sqrt(rho) * f + sqrt(1 - rho) * e_i), with common f and independent e_i, standard normal. Measured anchor from milestone 7: over 18.8 years the per-pair standard error of the excess Sharpe difference was 0.16 to 0.29 (simultaneous half-widths 0.40 to 0.72 at a critical value of 2.53). rho = 0.75 and rho = 0.25 bracket that. Report both.
- The catalog has 8 entries (catalog version 1, 28 pairs).
- Learner rules arrive over time. Report the site at M = 10, 100, 1,000, and 10,000 saved rules. Most are null (true excess Sharpe equal to buy and hold). Report power for a rule with a true advantage d = 0.3, 0.5, and 1.0 excess Sharpe over buy and hold.
- Live horizons of 1, 3, and 5 years after a rule is saved.
- Report both "win at the horizon (single look)" and "ever showed a win at any nightly look from 3 blocks to the horizon" for null rules, because the site re-looks every night.
- You may use the Gaussian max-|z| equivalent of `critical_value` for speed, but spot-check it against a block bootstrap on one small case and say how close it was.
- Python: uv run python (from research/) (numpy and polars installed; no scipy). Do not install packages, do not run `uv sync`, make no network calls, run no `jt` command.

## Rules

- Write only inside your output directory. Do not edit any file in the repository.
- Label every number measured (from your script), arithmetic, or guess.
