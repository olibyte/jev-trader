# Learner verdicts: synthesis

This note records how the arena of 2026-10-13 answered the first open question on the "Which one wins?" draft. Does a learner-built rule's verdict account for every saved rule, or only for that rule's pairs with the catalog? The answer is in the [product spec](../../product-spec.md) and the [implementation plan](../../implementation-plan.md).

Labels: **[m]** measured by a script in this directory, **[a]** arithmetic, **[g]** guess. Every measurement is on synthetic data. Run a script from `research/` with `uv run python ../docs/arena/2026-10-13-learner-verdicts/<path>`.

## The arena

Four candidates got the same [task](task.md) and the same synthetic setup, each with a different answer. A separate judge scored them against the [rubric](rubric.md). Its report is in [judge.md](judge.md).

| Candidate | Answer | Power, d = 1.0 over buy and hold, 5 years, rho 0.75 | Judge's pick |
|---|---|---|---|
| [1](candidate-1/proposal.md) | Every saved rule in one family | 11.1% at 10 rules, 0.3% at 10,000 [m] | |
| [2](candidate-2/proposal.md) | One rule's pairs with the catalog, and a luck line | 64% to 69% at any site size [m] | Base |
| [3](candidate-3/proposal.md) | Every rule one account has saved | 70% at 1 rule, 28% at 50 [m] | |
| [4](candidate-4/proposal.md) | A false-discovery rate across all rules | 50% at 10,000 rules [m] | |

The two power figures in candidate 1 include its look adjustment and small-sample cutoff. The others are one look at 5 years.

## The base: candidate 2

The judge and I picked the same base on separate readings. Only one rule's own pairs keep a verdict reachable, stable, and independent of strangers:

- Candidate 1 is the most honest answer, but a rule with a full point of excess Sharpe over buy and hold shows a win in 5 years 0.3% of the time once 10,000 rules exist [m]. A stranger who saves thousands of rules lowers everyone's chance. Every save also moves every learner verdict, so every rule page changes every night.
- Candidate 3 needs accounts. One person with 50 accounts and one null rule in each shows a win with certainty [m], so the per-verdict claim fails exactly where it is needed.
- Candidate 4 breaks a settled decision. Its interval's level is 1 - R·q/M, which moves with other people's rules every night, and its guarantee is an average share of wins rather than a statement about one verdict. Its own author says so.

Candidate 2's weakness is that luck wins grow with the number of rules. It answers that by stating them, with numbers, next to every learner verdict. One save changes no catalog verdict and no other learner's verdict.

## Grafts

| From | Graft | Why |
|---|---|---|
| 1 | Deleted rules keep counting in the luck line | Deleting losers would otherwise shrink the count of tries. |
| 1 | Each save cohort gets its own bootstrap draw, or exponential block weights | A shared multinomial draw gives a 3-block window zero weight in about 5% of reps [a]. |
| 3 | The rule page lists the learner's other saved rules in save order, with no verdicts | It exposes variant mining without an account-wide family. |
| 3 | A public log of every saved rule, its fingerprint, and its save time, with no verdicts | Nobody can scan the log for wins, and anyone can count the tries. |
| 4 | The luck line states a 1-night-in-20 high, not only the mean | False wins arrive in bursts when one catalog entry has a bad stretch. The 95th percentile is about 3 times the mean [m]. |

## Rejected

- **C4's "BH would keep R of W wins" line as disclosure.** It puts a second meaning of a number beside every verdict, and the judge rated it hard to explain.
- **C3's account-wide family.** Its listing of a learner's rules survives as disclosure. The wider interval does not, because a second account escapes it.
- **C1's look-adjusted value with a 5-year freeze.** It holds a null rule to 5% over every night, but it costs more power than a yearly verdict. See the second finding.
- **C2's "shown a win on k of n nights" count as the only answer to re-looks.** A night count discloses the leak but does not close it. It also needs an exception to honesty rule 5.

## Two findings that apply to every answer, and to the catalog's live period

Both are new open questions in the plan, because they change honesty rule 5 and milestone 11. They are not settled here.

### Today's interval is too narrow on short windows

`evaluate.block_bootstrap` with `catalog.critical_value` estimates each pair's spread from the blocks it has. With few blocks, that estimate is noisy, and a fixed critical value then calls too many verdicts. [verify/smallblocks.py](verify/smallblocks.py) reproduces `block_bootstrap`'s draws exactly and applies `critical_value` to one null rule's 8 pairs, over 1,500 synthetic datasets [m]:

| Blocks | Null rule gets a verdict | Window |
|---|---|---|
| 3 | 64.5% | The first night a verdict can show today |
| 6 | 32.2% | |
| 13 | 15.7% | About 1 year |
| 26 | 8.7% | |
| 63 | 7.3% | About 5 years |
| 236 | 6.2% | The milestone 7 backtest |

The target is 5%. At 63 blocks the bootstrap's spread is right on average (0.314 against 0.316) but varies by 9% from one dataset to the next [m]. At 13 blocks it varies by 20% [m]. Candidates 1 and 2 found the same effect separately. The milestone 7 backtest, at 6.2%, is close. The live period, which shows a verdict from 3 blocks, is not.

### Nightly verdicts let luck show a win on some night

A verdict recomputed every night is a new look every night. [verify/looks.py](verify/looks.py) measures one rule's 8 pairs under three schedules, with the spread known, so these figures are a best case [m]:

| Schedule | Critical value | Null rule shows a verdict on some night by 5 years | Win, d = 1.0, rho 0.75, by 3 / 5 years | Win, d = 0.5, rho 0.75, by 3 / 5 years |
|---|---|---|---|---|
| Nightly, today's single-look value | 2.67 | 41.8% | 58% / 81%, much of it luck | 20% / 31% |
| Nightly, value held at 5% over every night | 3.54 | 5% | 23% / 48% | 4% / 7% |
| One verdict on each anniversary of the save | 3.07 | 5% | 30% / 58% | 5% / 9% |

The yearly verdict keeps the most power of the honest schedules. It is also the easiest to explain: "Your rule gets a verdict on each anniversary of the day you saved it". Between anniversaries, the page can show the running interval with no verdict.

## Verification

- My own nightly check ([verify/nightly.py](verify/nightly.py), [output](verify/nightly.txt)) gives the 8-pair critical value as 2.66, against 2.65 in candidates 2 and 3. A null rule shows "rule wins" at one look in 2.1% to 3.2% of runs, and on some night within 3 years in 22% to 23% [m]. Candidate 3 measured 20% and candidate 2 measured 22.9% with the same model.
- The judge flagged a conflict at 63 blocks. Candidate 2 measured 7.8% and candidate 4's spot check implied about 5%. My run of the real code gives 7.3% on 1,500 datasets [m], which sides with candidate 2.
- Candidate 4's power of 0.96 counts a win over any of the 8 entries. My check gives 0.97 under the same definition [m]. Against buy and hold alone, candidate 4's own result files give 0.70, which agrees with candidates 2 and 3.

## Power is low under any answer

Even the base answer gives a rule with a real edge of 0.5 excess Sharpe a 9% chance of a win within 5 years under the yearly schedule at rho 0.75 [m], and 3% at rho 0.25 [m]. For comparison, milestone 7 measured excess Sharpe of 0.41 to 0.64 for the four catalog strategies. An edge of 0.3 is out of reach. If few saved rules have a real edge, most learner wins that show will be luck [a]. The luck line exists so the site can say so on the same screen.
