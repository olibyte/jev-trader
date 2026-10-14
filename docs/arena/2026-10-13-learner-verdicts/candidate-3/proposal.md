# Candidate 3: one learner's rules

Labels: **[m]** measured by `sim.py` (output in `results.txt`), **[a]** arithmetic, **[g]** guess.

## 1. The rule

A learner rule's verdict uses a simultaneous 95% interval over one family. The family holds every pair (rule i, catalog entry c), for every rule i that the same account has ever saved, every entry c in the current catalog version, and every market that rule i plays in. Each pair is scored on rule i's own live period.

- Rules never leave the family. Nobody can delete a saved rule, and a closed account's family stays frozen.
- A new save widens every interval in that account's family the next night. Rules still "Too early" count too.
- Verdicts are against catalog entries only, never against another rule.
- Catalog verdicts keep their own family (28 pairs in each market, all markets together). Learner pairs never enter it.

Next to the verdict, the site states (example figures from the grid below):

> This verdict accounts for the 5 rules this account has saved: 40 comparisons. Across the site, 1,408 accounts have saved 10,000 rules. If no rule had a real edge, about 35 accounts (1 in 40) would show "A wins" tonight by luck alone. 41 do.

The rule page lists the account's other rules in save order, all of them, with no verdicts. The public log lists every rule by save time with its fingerprint, account, and family size. It shows no verdicts, so nobody can scan it for wins.

## 2. Win rates on synthetic data

Shared setup. All 8 catalog entries have the true excess Sharpe of buy and hold. Pair correlations do not depend on rho in this model, so null rates are the same at both rho [a].

**Critical values** (Gaussian max-|z|) [m]:

| Family | Pairs | Critical value |
|---|---|---|
| Catalog, 4 entries | 6 | 2.57 (milestone 7 bootstrap: 2.53) |
| Catalog, 8 entries | 28 | 3.03 |
| Account with 1 / 5 / 50 rules | 8 / 40 / 400 | 2.65 / 3.15 / 3.74 |
| Site-wide, 10,000 rules (contrast) | 80,000 | 4.75 |

**Bootstrap spot check** [m]: `evaluate.block_bootstrap` and `catalog.critical_value` on 3 years of synthetic daily returns, rho 0.75, 5 datasets. For 1 rule the bootstrap gave 2.58 to 2.67 (mean 2.62) against 2.65 Gaussian. For 5 rules it gave 3.11 to 3.15 (mean 3.13) against 3.15. The Gaussian value is about 1% wider.

**Null account, rules saved on one day** [m], 6,000 runs:

| Rules | Horizon | Any verdict, single look | "A wins", single look | Per rule "A wins" | "A wins" ever, nightly |
|---|---|---|---|---|---|
| 1 | 1y / 3y / 5y | 0.05 / 0.05 / 0.06 | 0.02 / 0.03 / 0.03 | 0.024 / 0.027 / 0.028 | 0.13 / 0.20 / 0.22 |
| 5 | 1y / 3y / 5y | 0.05 / 0.05 / 0.06 | 0.03 / 0.03 / 0.03 | 0.006 / 0.007 / 0.006 | 0.16 / 0.24 / 0.27 |
| 50 | 1y / 3y / 5y | 0.05 / 0.05 / 0.05 | 0.03 / 0.03 / 0.03 | 0.0007 each | 0.18 / 0.28 / 0.32 |

**Power** [m]: chance that a rule with true edge d shows "A wins" against buy and hold, single look. Its account holds k - 1 other null rules.

| k | d | rho 0.75: 1y / 3y / 5y | rho 0.25: 1y / 3y / 5y |
|---|---|---|---|
| 1 | 0.3 | 0.01 / 0.03 / 0.04 | 0.01 / 0.01 / 0.02 |
| 1 | 0.5 | 0.03 / 0.08 / 0.14 | 0.01 / 0.03 / 0.04 |
| 1 | 1.0 | 0.11 / 0.42 / 0.70 | 0.03 / 0.11 / 0.20 |
| 5 | 1.0 | 0.04 / 0.24 / 0.51 | 0.01 / 0.04 / 0.09 |
| 50 | 1.0 | 0.01 / 0.10 / 0.28 | 0.00 / 0.01 / 0.03 |

At k = 5 and 50, d = 0.3 and 0.5 stay at or below 0.06 [m].

**Site grid** [m rates, a totals]. Account mix [g]: 60% save 1 rule, 30% save 5, 10% save 50 (7.1 rules per account).

| Saved rules M | Accounts | Null rules showing "A wins" at one look (3y) | Accounts ever showing a null "A wins" by 3y |
|---|---|---|---|
| 10 | 1 | 0.0 | 0.3 |
| 100 | 14 | 0.4 | 3 |
| 1,000 | 141 | 4 | 31 |
| 10,000 | 1,408 | 42 | 306 |

For contrast, a site-wide family at d = 1.0, 3 years, rho 0.75, gives power 0.19 at M = 10 and 0.01 at M = 10,000 [m]. This rule keeps 0.42 at k = 1, whatever M is.

## 3. Honesty

**Per verdict.** For each account, the chance of any false verdict at one look stays at 5%, and of a false "A wins" at 2.6% [m]. That holds for 1 rule or 50.

**Shown win that is luck** [a from m, 3 years, single look]. If 1% of rules have a real edge [g], a shown win from a 1-rule account is luck 97% of the time at d = 0.5 and 86% at d = 1.0 (rho 0.75). If 10% have an edge [g], those figures are 76% and 36%. At rho 0.25 they run from 69% to 99%. Live power is low, so most shown wins will be luck under any family rule.

**Site-wide.** False wins grow with accounts, about 1 in 40 at any look [m]: about 42 null rules a night at 10,000 rules [a]. The luck line puts this next to tonight's real count.

**Nightly re-looks.** The largest leak. A null 1-rule account shows "A wins" on some night by 3 years in 20% of runs, against 2.7% at one look [m], and 28% with 50 rules [m]. Every family rule shares this leak. The rule page should show how many nights the verdict has read each answer.

**Gaming** [m]. A person who saves 50 null rules gets:

| Strategy | P(some "A wins" ever, 5 years) |
|---|---|
| One account, all 50 saved at once | 0.32 |
| One account, one new rule each block | 0.50 (overstated; equal-window critical value) |
| 50 accounts, one rule each | 1.00 |

At one look, 5 accounts give 0.13 and 50 give 0.74 [a]. Many accounts per person break the per-verdict claim. A verified sign-in (email plus one OAuth provider) raises the cost but does not stop a determined person [g]. Accounts found to be linked merge into one family, and their verdicts widen. The luck line is the backstop: it counts every rule on the site, whoever saved it.

## 4. Cost

- **Compute** [m]: a vectorised block bootstrap of 10,000 rules × 8 pairs, 2,000 reps, 5 years of staggered windows, took 1.8 s on this laptop. 1,000 rules took 0.1 s. The per-account critical value is a group-by on those draws. The current per-pair Python loop would take over an hour at that size [a: 80,000 pairs × 2,000 calls at about 30 µs each, g], so the batch needs this rewrite.
- **Windows.** A draw on the shared calendar misses all 3 blocks of a new rule's window in about 5% of reps [a: (60/63)^63]. Each save cohort needs its own block draw.
- **Storage** [a]: 10,000 rules × 13 symbols is 130,000 ledger rows a night, about 5 MB at 40 bytes a row [g], or 1.3 GB a year. That is too much for the nightly git ledger branch. The size is the same under any family rule.
- **Build effort** [g]: the rule needs accounts. Saving a rule needs a small backend (sign-in, save, log). Verdicts still come from the nightly batch as static files, so `jt arena` stays a static build with a learner section. The account family adds about 2 days beyond a site-wide rule: the group-by, the luck line, and the account merge.
- **Catalog verdicts**: no learner save changes any catalog-vs-catalog verdict, or any other account's verdict [a, by construction].

## 5. For a curious learner

Your rule's verdict accounts for every rule your account has saved. Each saved rule is another chance to get lucky, so every interval in your account widens a little with each save. One rule faces the lowest bar. With 50 rules, a real edge must be larger to show. Other people's rules do not move your bar. We still state how many accounts have saved rules and how many would show a win tonight by luck alone. If that number is close to the real count, most of tonight's wins are luck. The verdict is recomputed every night, so "A wins" one night may read "Too close to call" the next.

## 6. Alternatives rejected

- **One rule's own 8 pairs only.** Saving 50 variants would cost nothing. A null account with 50 rules would then show "A wins" on some night with probability near 1 [a: 1 - (1 - 0.22)^50, treating rules as independent].
- **Every saved rule site-wide.** Power at d = 1.0 falls from 0.19 to 0.01 as M grows from 10 to 10,000 [m]. A learner's chance would depend on strangers.
- **Adding the 28 catalog pairs to each family.** The learner did not choose them, so they widen the interval and protect nothing.
- **Save quotas.** More accounts dodge them, and any cutoff is arbitrary.
- **Document identity checks.** Too heavy and intrusive for a learning site.
