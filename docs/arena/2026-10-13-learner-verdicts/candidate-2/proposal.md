# Candidate 2: one rule's pairs, with a measured luck line

Labels: **[m]** measured by a script here, **[a]** arithmetic, **[g]** guess. `sim.py` writes `results.md` (Gaussian rule, site counts, spot check, compute). `real.py` writes `real75.log` and `real25.log` (today's bootstrap, every night). `tu.py` writes `tu.log` (time-uniform alternative).

## 1. The rule

**Family.** A learner rule's verdict uses one simultaneous 95% interval over the pairs (rule, c), for every catalog entry c in every market the rule plays in. The learner does not pick markets. A rule plays in every market where its inputs exist, so nobody finds a win by trying markets. Daily ETFs alone give 8 pairs (critical value 2.65 [m]). Daily plus hourly give 14 pairs (2.85 [m]).

The window is the rule's live period. Catalog entries use the same dates from the ledger. Only the whole-market scope gets a verdict. A pair of two learner rules shows its interval with no verdict. Catalog pairs keep their own 28-pair family.

**Prerequisite (affects every candidate).** Today's `block_bootstrap` plus `critical_value` is badly anti-conservative with few blocks. Learner verdicts need a critical value calibrated by block count (section 2).

**The luck line**, beside every learner verdict:

> {N} learner rules have played at least 3 blocks. If none had a real edge, about {E} would show a win tonight, and up to {U} on 1 night in 20. {W} show a win tonight. {X} have shown a win on at least one night. Luck alone would give about {Y}.

The rule page adds "This rule has shown a win on {k} of {n} nights." E and Y sum p_snap(blocks) and p_ever(blocks) over rules, from a committed luck table measured by simulating the exact nightly procedure. U comes from a null simulation on the real save dates, labelled as a model. Honesty rule 5 needs an explicit exception for W, X, and k.

## 2. Measured win rates

Null rule, percent showing "rule wins" over at least one catalog entry. "Ever" means any nightly look from 3 blocks on.

| Procedure | rho | 1y single | 1y ever | 5y single | 5y ever |
|---|---|---|---|---|---|
| Today's bootstrap [m] | 0.75 | 8.5 | 48.7 | 3.8 | 55.3 |
| Today's bootstrap [m] | 0.25 | 6.2 | 53.5 | 3.8 | 58.8 |
| Calibrated bootstrap [m] | 0.75 | 3.0 | 18.3 | 2.7 | 28.7 |
| Calibrated bootstrap [m] | 0.25 | 1.8 | 18.0 | 2.5 | 27.0 |
| Gaussian max-\|z\| [m] | 0.75 | 2.5 | 14.2 | 2.5 | 22.9 |
| Gaussian max-\|z\| [m] | 0.25 | 2.7 | 14.8 | 2.6 | 23.7 |

With today's bootstrap, a null rule gets a verdict other than "Too close to call" on its first night 62% of the time [m]. That falls to 15% at 13 blocks and 8% at 63 [m]. The critical value that holds 5% is 11.8 at 3 blocks, 5.2 at 5, 3.3 at 13, 2.9 at 26, and 2.8 at 63 [m].

**Spot check.** The Gaussian rule holds 5 to 6% from night 60 on [m]. At 13 blocks, on the same 200 datasets, the real bootstrap showed a null win in 13.5% and the Gaussian rule in 5.0% [m]. At 63 blocks the figures were 4.0% and 3.0% on 100 datasets [m], and 7.8% for the bootstrap on 600 datasets [m].

Power is the percent of rules with true advantage d that read "rule wins" over buy and hold, single look. Calibrated bootstrap [m], Gaussian [m] in brackets:

| rho | d | 1y | 3y | 5y |
|---|---|---|---|---|
| 0.75 | 0.3 | 1.0 [1.3] | 2.2 [2.7] | 3.5 [4.3] |
| 0.75 | 0.5 | 1.8 [2.5] | 5.0 [7.4] | 11.5 [14.2] |
| 0.75 | 1.0 | 6.5 [10.6] | 33.0 [41.3] | 63.8 [69.0] |
| 0.25 | 0.3 | 1.0 [0.8] | 1.5 [1.3] | 2.0 [1.9] |
| 0.25 | 0.5 | 1.5 [1.3] | 3.2 [2.7] | 4.0 [4.1] |
| 0.25 | 1.0 | 3.0 [3.4] | 10.5 [10.2] | 22.5 [20.4] |

Site-wide, every rule null, Gaussian rule, rho 0.75. Saves fall on uniform days over 5 years, and the site is read at year 5:

| M saved | played [m] | luck wins tonight, mean [m] | 95th pct [m] | P(at least 1) [m] | ever shown a win [a] |
|---|---|---|---|---|---|
| 10 | 10 | 0.2 | 1 | 19% | 1.7 |
| 100 | 95 | 2.5 | 8 | 71% | 17.5 |
| 1,000 | 953 | 26 | 82 | 98% | 175 |
| 10,000 | 9,531 | 254 | 764 | 100% | 1,750 |

At rho 0.25, the 95th percentiles are 1, 9, 71, and 856 [m]. If every rule is saved on one day and read a year later, they are 2, 12, 106, and 1,043 [m].

## 3. Honesty

**Per verdict.** One look is honest. A null rule shows a win 2.5 to 3% of the time [m]. Whether a shown win is real depends on how many rules have edges. Suppose 5% of rules had d = 1.0 [g]. Then at 3 years, 36% (rho 0.75) to 56% (rho 0.25) of shown wins would be luck [a]. At 1% [g], it would be 75 to 87% [a].

**Site-wide.** Luck wins come in waves. When a catalog entry has a bad stretch, many rules pull ahead of it at once, so the 95th percentile is about 3 times the mean [m]. The luck line therefore states U, not only E.

**Gaming.** One person saves K null rules from K accounts on one day [m]:

| K | 1y single | 1y ever | 5y ever |
|---|---|---|---|
| 10 | 16% | 62% | 80% |
| 20 | 29% | 79% | 92% |
| 100 | 60% | 98% | 100% |

Only disclosure defends against this. Every saved rule counts in N and E, whatever the account. The night count exposes a win that appeared once. Identical fingerprints count once.

**Nightly re-looks are the largest leak.** Even calibrated, 27 to 29% of null rules show a win on some night within 5 years [m]. With today's bootstrap, 55 to 59% do [m].

## 4. Cost

**Compute.** The bootstrap draws depend only on the block count and the seed. Rules saved on the same day can share one weight matrix and one matmul, which reproduces `block_bootstrap` to 5e-15 [m]. One night takes 3.0 s for 1,000 rules and 6.0 s for 10,000 [m], and time grows linearly. Today's per-pair loop takes 0.02 s per pair [m], or about 24 minutes at 10,000 rules [a].

**Storage.** Positions and returns take about 5 KB per rule-year [a], or 265 MB for 10,000 rules over 5 years [a]. A 50 KB curve file per rule [a] means 500 MB uploaded every night at 10,000 rules [a]. Split the curves by year so that only the current file changes.

**Build effort.** The backend, sandbox, and rule log are shared by all candidates. This candidate adds four things:

- `export/arena/learners/v1/` with one file per rule
- a calibrated critical-value table, which the live catalog verdicts need anyway
- the luck table and a few-second null simulation
- zod checks, including 8 pairs per daily market and 6 per intraday market, plus wording changes to rules 3 and 5 and `check:honesty`

**Catalog verdicts.** A new save changes no catalog verdict and no other learner's verdict. Only the luck line moves.

## 5. For a curious learner

Your rule's verdict compares it with each of the 8 catalog strategies in its market, over the sessions since you saved it. If your rule had no real edge, it would show a win on a given night about 1 time in 40. With 1,000 rules, luck alone puts about 25 in the win column on a normal night, and up to about 80 on a bad one. When one catalog strategy has a poor stretch, many rules pull ahead of it at once. Verdicts are recomputed every night, so a rule with no edge has about a 1 in 4 chance of showing a win on some night within 5 years. That is why we show how many nights each rule has shown a win. A win that holds night after night means more than one that appears once.

## 6. Alternatives rejected

- **Every saved rule in one family.** The critical value goes from 3.03 to 3.41 at 10 rules and to 4.76 at 10,000 [m]. A rule with d = 1.0 would show a win at 5 years about 5% of the time instead of 69% [a]. Every save would also move every published verdict.
- **A time-uniform interval over all nights.** The critical value is 3.58 [m]. Power at d = 1.0 over 5 years falls to 34% (rho 0.75) and 4% (rho 0.25) [m]. Disclosure keeps the power.
- **A first verdict at 25 blocks.** The 3-block rule is settled. Even at 25 blocks, today's bootstrap gives 14 to 17% ever [m].
- **A luck line of "5% of rules".** With today's bootstrap, the real rate is about 3 times that [m]. The line would also hide the waves and the re-looks.

**Model limits [g].** Every catalog entry shares one true Sharpe, and every pair shares one rho. Real long-or-flat rules correlate more with one another, which would make the waves larger.
