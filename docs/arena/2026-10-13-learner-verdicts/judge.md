# Judge

A separate read-only judge scored the four proposals against the [rubric](rubric.md). It read each proposal and checked the scripts and logs where a number decided a score. This is its report.

## Scores (1 to 5)

| | Honesty | Reach | Cost | Fit | Explain | Evidence |
|---|---|---|---|---|---|---|
| C1 site-wide family | 5 | 1 | 2 | 3 | 3 | 4 |
| C2 own pairs + luck line | 2 | 5 | 5 | 4 | 4 | 4 |
| C3 per-account family | 3 | 4 | 3 | 4 | 4 | 3 |
| C4 BH / FDR | 3 | 2 | 3 | 1 | 2 | 2 |

**C1**

- Honesty 5. Across the site, the chance of any false win is held near 5% even with nightly looks. Saving many rules buys no false win. The open hole is griefing, which suppresses other people's wins.
- Reach 1. With the proposed cutoffs, a d = 1.0 rule has an 11.1% chance of a win at 5 years when M = 10, and 0.3% at M = 10,000. At d = 0.5 the chance is about 0. The result depends entirely on strangers' rules.
- Cost 2. Every save moves every learner verdict, so all rule pages republish each night. It also needs a nightly or weekly look simulation.
- Fit 3. It keeps the simultaneous 95% interval, but it adds a 5-year verdict freeze, which is a new product decision.
- Explain 3. The paragraph is honest, but it tells learners that most good rules will read "Too close to call" for years.
- Evidence 4. The bootstrap spot check holds at 3, 12, and 63 blocks. C1 alone tested the 3-block case directly. At 3 blocks, 5.3% of null pairs pass 4.76.

**C2**

- Honesty 2. A single look is honest (2.5 to 3% false wins). Nothing bounds false wins across the site, and the luck line only discloses them. A null rule shows a win on some night within 5 years 27 to 29% of the time. One person with K accounts reaches 80 to 100%.
- Reach 5. At d = 1.0 over 5 years, the chance of a win is 64 to 69% at rho 0.75 and 20 to 23% at rho 0.25. It does not depend on strangers' rules.
- Cost 5. A save changes no other verdict. A night takes 6 s at 10,000 rules.
- Fit 4. It keeps the three answers and the 95% interval, but it needs an explicit exception to honesty rule 5.
- Explain 4. The paragraph is clear and concrete.
- Evidence 4. It is the only candidate that ran the real procedure every night. One label slip. At 63 blocks it gives "4.0%" and "7.8%" as the same quantity, but `real75.log` shows 4.0% is "rule wins" and 7.8% is "any win".

**C3**

- Honesty 3. The 5% per-verdict claim holds for one honest account. 50 accounts with one rule each give 1.00 ever. It never models the few-block bootstrap problem.
- Reach 4. One rule matches C2 (0.70 at d = 1.0, 5 years). Power falls only with the learner's own saves, to 0.28 at 50 rules.
- Cost 3. It needs accounts and account linking.
- Fit 4. It fits the settled decisions.
- Explain 4. "Your saves raise your bar" is easy to follow.
- Evidence 3. It uses a known-sd Gaussian only. Its "over an hour" loop estimate contradicts the measured 23 to 30 minutes from C1, C2, and C4. Its 1.3 GB a year of storage is far above C1's 33 MB.

**C4**

- Honesty 3. Nightly FDR stays at or below about 2.5%. But false wins come in bursts (about 600 on a burst night at M = 10,000), and a clone attack raises the honest null win rate 67 times. Its p-values need tails near 2.5e-6, which a bootstrap sd from 3 blocks cannot give. The proposal does not address this.
- Reach 2. Against buy and hold, power at d = 1.0 is 0.18 to 0.42 at 5 years, and about 0 at d = 0.5 when M = 10,000. It depends on strangers.
- Cost 3. The interval level moves every night, so every page republishes nightly.
- Fit 1. The proposal itself says it breaks "a simultaneous 95% interval decides".
- Explain 2. "Luck share on average over nights" is hard for a learner to follow.
- Evidence 2. Its headline power counts a win against any of the 8 entries. Its "own pairs 0.96" contradicts C2 and C3 (0.69 to 0.70), and its "every-rule 0.12" contradicts C1 (2.9%). Its own `results-mix` files show 0.704 and 0.026 against buy and hold, which agree with the others.

**Numbers that agree across candidates:** the 8-pair critical value (2.65 to 2.66), the site-wide value at 10,000 rules (4.75 to 4.76), and the null rule's 5-year "ever" rate (22% in C3, 22.9% in C2's Gaussian).

**Unresolved conflict:** at 63 blocks, C2 measured 7.8% any-win with today's bootstrap. C4's spot check (c and sd within 1%) implies about 5%. Neither measured the other's quantity.

## Recommendation

**Base: C2.** It is the only answer that leaves verdicts reachable, stable, and independent of strangers. Its weakness is site-wide luck, and it answers that by disclosing it, with numbers.

- **From C1:** exponential(1) block weights, or one bootstrap draw per save cohort, so a short window never gets zero weight. Also keep counting deleted rules.
- **From C3:** the rule page lists the learner's other saved rules in save order, and the public log shows fingerprints with no verdicts.
- **From C4:** a site-wide line of the form "BH at q = 0.025 would keep R of tonight's W wins", shown as disclosure and never as the verdict. Also keep C4's clone and loser-flood attacks as checks.

## Findings that apply to every answer

1. Today's `block_bootstrap` with `critical_value` is badly anti-conservative at few blocks. Any answer needs a cutoff calibrated by block count.
2. Nightly re-looks are the largest leak. Each answer needs a night count or a look adjustment.
3. Shared catalog entries cause bursts of false wins, so the 95th percentile of luck wins is about 3 times the mean. Any luck disclosure must state a high percentile, not only the mean.
4. The per-pair loop takes about 25 minutes at 10,000 rules. A vectorized bootstrap takes 2 to 6 s and is needed under every answer.
5. Power is low under every answer. d = 0.3 is out of reach. With a low share of real edges, most shown wins will be luck, and the site should say so.
6. Exact-fingerprint dedupe catches only exact clones. The live ledger outgrows git, so every answer needs a backend.
