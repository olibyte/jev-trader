# Every saved rule: one family for all learner verdicts

Labels: **[m]** measured by a script in this directory, **[a]** arithmetic, **[g]** guess.

## 1. The rule

- **Family.** On each night, the learner family is every pair (saved learner rule, catalog entry) in every market the rule plays, for every rule with at least 60 live sessions. At M rules and 8 entries that is 8M pairs.
- **Rule-vs-rule pairs stay out.** The site shows no learner-vs-learner matchup, so those verdicts need no cover. If it ever shows one, those pairs join.
- **Catalog pairs keep their own family.** Saving a rule never changes a catalog verdict.
- **Rules never leave.** A deleted rule is hidden but keeps playing and counting.
- **Different start dates.** One live calendar of 20-session blocks starts at the catalog's live start. Each pair reads only its rule's sessions, with the catalog entry cut to the same sessions, as the plan does for shorter markets. Each rep draws one weight per block, shared by every pair. Use exponential(1) weights, not multinomial counts: with counts, a 3-block rule gets zero weight in about e^-3 = 5% of reps [a]. Staggered starts raise the critical value by about 0.08 (3.95 against 3.87 at M = 100) [m], and the bootstrap measures that directly.
- **Two corrections.** Without them the 5% claim is false (section 3).
  1. *Small-sample cutoff.* Convert the family critical value c to its tail probability, then to each pair's cutoff under t with (blocks - 1) degrees of freedom. At 10,000 rules, 4.76 becomes 880 at 3 blocks, 9.5 at 12, and 5.3 at 63 [a].
  2. *Look adjustment.* c covers every pair and every nightly look in each rule's first 5 live years, and the verdict is final after 5 years. A simulation on the actual save calendar sets c, 1.2 to 1.3 times the single-look value [m]. The 5-year freeze is a new product decision.
- **Next to the verdict:** "This verdict counts all 9,412 saved rules against all 8 catalog strategies: 75,296 comparisons, each checked every night for 5 years. If no rule truly did better or worse than any catalog strategy, there is a 1 in 20 chance that any of them would ever show a win. Rules saved later can turn a win back to Too close to call."

## 2. Measured results (synthetic, shared setup)

Critical values from the Gaussian max-|z| [m]:

| saved rules M | 10 | 100 | 1,000 | 10,000 |
|---|---|---|---|---|
| single look | 3.33 | 3.89 | 4.35 | 4.76 |
| looks to 5 years, cohort | 4.16 | 4.68 | 5.16 | 5.50 |

One rule's own 8 pairs give 2.66. Adding rule-vs-rule pairs gives 6.00 at 10,000 rules [m].

Spot check against the real `block_bootstrap` and `critical_value` (80 pairs, 5 data seeds) [m]: 3.36 against 3.34 at 63 blocks, 3.22 at 12 blocks, and 3.08 at 3 blocks.

Power: chance that a rule with true advantage d over buy and hold reads "A wins" against it at the horizon, at rho = 0.75 (100,000 rules each) [m]:

| d, rule | M = 10: 1y / 3y / 5y | 100 | 1,000 | 10,000 |
|---|---|---|---|---|
| 1.0, per look | 1.2 / 14.4 / 37.8% | 0.2 / 4.5 / 17.8% | 0.0 / 1.3 / 7.6% | 0.0 / 0.4 / 2.9% |
| 1.0, proposed (look + t) | 0.2 / 2.8 / 11.1% | 0.0 / 0.6 / 3.6% | 0.0 / 0.1 / 0.9% | 0.0 / 0.0 / 0.3% |
| 0.5, per look | 0.2 / 1.3 / 3.3% | 0.0 / 0.3 / 0.8% | 0.0 / 0.1 / 0.2% | 0.0% |

At rho = 0.25, d = 1.0 at 5 years gives 5.6, 1.4, 0.4, and 0.1% per look [m]. At d = 0.3, power never exceeds 0.7% [m]. With a known sd, d = 1.0, 5 years, M = 10 reaches 43% [m]. The t cutoff costs 5 points of that, and the look adjustment 27 more.

## 3. Honesty

Null rules, chance of at least one false win against any of the 8 entries over the first 5 years [m]:

| | M = 10 | 100 | 1,000 | 10,000 |
|---|---|---|---|---|
| per rule, bootstrap sd, plain c | 73.5% | 60.8% | 52.3% | 45.9% |
| per rule, t cutoff, per look | 9.4% | 1.5% | 0.27% | 0.05% |
| per rule, proposed | 0.55% | 0.07% | 0.005% | 0.000% |
| site-wide, known sd, one look at 5y | 4.7% | 5.4% | 5.0% | 5.3% |
| site-wide, known sd, every night to 5y | 51% | 55% | 59% | 60% |

- **Short windows break any large family.** With the real bootstrap, 5.3% of null pairs at 3 blocks pass 4.76, where the normal gives 0.0002% [m]. A 3-block sd has 2 degrees of freedom. The t cutoff fixes this, and first-year wins become rare (1.2% power at d = 1.0, M = 10) [m]. This hits every candidate answer.
- **Nightly looks.** With saves spread over 5 years and nightly looks for 10, at least one false win shows at some night in 91% of runs at M = 100 and 96% at M = 1,000 [m]. The cohort look value with a 5-year freeze gives 12 to 13%, and scaling it by 1.04 to 1.07 gives 5% [m].
- **Gaming.** Many rules or accounts buy no false win, because the family is site-wide, and deleting losers does not shrink it. The attack is griefing: thousands of saved rules widen every interval. A d = 1.0 rule falls from 11.1% to 0.3% power [m]. Near-copies barely move the max, so a griefer needs different rules. Per-account rate limits do not stop many accounts.
- **Wins can revert.** The family grows every night, so a shown win can return to "Too close to call". The site says so.

## 4. Cost

- **Compute per night:** one critical value over 80,000 pairs, 2,000 reps, 10 years: 1.6 s vectorized [m]. The per-pair `block_bootstrap` loop averaged 17 ms a pair in the spot check, so at least 23 minutes [a]. The look simulation takes minutes and can run weekly [g]. Rule positions depend on the rule language [g].
- **Storage:** 10,000 rules x 13 symbols x 252 sessions = 33 million ledger positions a year [a], about 33 MB at a byte each [a], plus 20 MB of daily rule returns [a].
- **Static architecture:** any new rule moves every learner interval, so every rule page republishes nightly. That cannot be committed like `export/arena/v1/`, so learner results live in the backend store and S3. One failed rule tick holds back every learner verdict that night.
- **Build effort [g]:** 1 to 2 weeks beyond the backend any answer needs: per-pair windows, exponential weights, the t cutoff, the look simulation, vectorized family code, and a check that the family size equals 8 x eligible rules x markets.
- **Catalog verdicts:** unchanged by any save.

## 5. For a curious learner

"Your rule's verdict counts every rule anyone has saved, not just yours. Thousands of rules played forward will throw up some lucky streaks. So a win here has to be big enough that, among all of them, luck alone would show one only 1 time in 20, even though we check every night. That bar is high. Most rules, good ones included, will read Too close to call for years. When a win does show, it is very unlikely to be luck. As more rules are saved, the bar rises, and a win can go back to Too close to call."

## 6. Alternatives rejected

- **One rule's pairs only.** About 5% of null rules per look show a luck win [a], so luck wins grow with M and with accounts. At c = 3.33 it is already 9.4% per rule over 5 years [m].
- **Rule-vs-rule pairs.** They cover unseen verdicts and raise c to 6.00 [m].
- **One family with the catalog.** Saves would move catalog verdicts, and griefers could suppress them. Separate families bound site-wide luck at 10% [a].
- **No look adjustment.** 51 to 96% site-wide [m].
- **Alpha by arrival order** (rule j gets 0.05 x 6 / (pi^2 j^2)). Verdicts never shift, but late rules have almost no chance and early slots get grabbed.
- **False discovery rate.** It changes a verdict's meaning from an interval to a share of wins, which breaks the settled rule.

Scripts: `crit.py`, `spotcheck.py`, `tails.py`, `sitewide.py`, `sitewide_look.py`, `perrule.py`, `timing.py`, `common.py`. Outputs are in `results/`.
