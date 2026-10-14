# Candidate 4: false-discovery control across all learner rules

Labels: (m) measured by a script here, (a) arithmetic, (g) guess.

**Plain answer.** This is not compatible with "a simultaneous 95% interval decides". An interval still decides, and it is never narrower than the rule's own 95% simultaneous interval. But its level is 1 − R·q/M, not 95%, and other people's rules move it every night. The promise is an average over nights and rules, not a statement about this verdict. Adopting it reopens that settled point and puts two meanings of "wins" on one site.

## 1. The rule

- **Family.** Learner rule j has 8 pairs: rule minus each catalog entry, excess Sharpe, portfolio scope, live period. Learner rules are never compared with each other.
- **p-value.** Each night, each rule with 3 or more blocks gets a one-sided "rule ahead" p_j = 8·Φc(max_k z_jk), with z = point / bootstrap sd. The bootstrap percentile cannot reach BH's thresholds: its floor is 5e-4 at 2,000 reps, and BH needs 2.5e-6 at M = 10,000 (a). The 8·Φc bound is 1.01 to 1.28 times the exact tail (m).
- **BH.** Benjamini-Hochberg at q = 0.025 over all M_t saved rules with 3 or more blocks, deleted ones included, identical live positions counted once. α_t = max(R_t, 1)·q/M_t. A second BH on "catalog ahead" p-values gives α'_t.
- **Interval.** [point − c(α_t)·sd, point + c(α'_t)·sd], where c(α) is the one-sided simultaneous critical value over the rule's 8 pairs. "Wins" exactly when it excludes zero, so the build check holds. With R = 1, c = 3.39, 3.99, 4.51, 4.98 at M = 10 to 10,000 (m). Today's 95% value for 8 pairs is 2.65 (m).
- **Shown beside it:** "1,000 rules in play tonight, 4 show a win. The share of wins that are luck is held at 2.5% on average over nights, and can be much higher on one night. Tonight's level: 99.99%. This verdict can change when others save rules."

## 2. Measured win rates

`sim.py` uses the Gaussian model of the shared setup. The common factor cancels in every difference, so rho only scales the effect. Within a rule, pair correlations are 0.5 for any rho (a). All M rules form one cohort saved on one day, the worst case for dependence through shared catalog entries. Looks run nightly from session 60.

**Spot check** (`spotcheck.py`, repo `block_bootstrap` and `critical_value`, m): the bootstrap critical value averaged 2.635 at 3 years (2.55 to 2.71 over 20 datasets), 2.632 at 1 year, and 2.621 at 5 years, against Gaussian 2.652, within 1.2%. The bootstrap sd ran 11% narrow at 1 year (12 blocks) and within 1% at 3 and 5.

**Null site (m).** "Tonight" averages the 1, 3, and 5 year looks.

| M | own pairs: false wins tonight | BH: P(any false win tonight) | BH: false wins tonight | BH: rules ever falsely won by 5y | every-rule family: same |
|---|---|---|---|---|---|
| 10 | 0.25 | 0.022 | 0.035 | 0.55 | 0.38 |
| 100 | 2.4 | 0.022 | 0.10 | 1.9 | 0.54 |
| 1,000 | 22 | 0.010 | 0.73 | 14 | 0.64 |
| 10,000 | 266 | 0.017 | 10.5 | 153 | 0.73 |

**Power at the 5-year look, 2% of rules with edge d (m).** Own-pairs power does not depend on M.

| rho | d | own pairs | BH M=10 | 100 | 1,000 | 10,000 | every-rule M=10,000 |
|---|---|---|---|---|---|---|---|
| 0.75 | 0.3 | 0.20 | 0.050 | 0.009 | 0.003 | 0.000 | 0.000 |
| 0.75 | 0.5 | 0.47 | 0.18 | 0.062 | 0.027 | 0.020 | 0.003 |
| 0.75 | 1.0 | 0.96 | 0.83 | 0.66 | 0.57 | 0.50 | 0.12 |
| 0.25 | 0.5 | 0.20 | 0.042 | 0.014 | 0.002 | 0.012 | 0.000 |
| 0.25 | 1.0 | 0.55 | 0.25 | 0.11 | 0.049 | 0.010 | 0.002 |

At 1 year (rho 0.75, d 1.0), BH power is 0.12 at M = 10 and 0.006 at 10,000 (m). Other horizons and BY: `results-mix_*.md`.

## 3. Honesty

**Site-wide.** Nightly FDR ran 0.001 to 0.036 across cells against q = 0.025 (m). Cells above 0.025 had 60 reps and burst noise.

**Per verdict, the guarantee is weak.** False wins come in bursts. When one catalog entry runs unlucky, every rule's p-value falls together, R grows, and the threshold loosens. At M = 10,000 under the null, a burst night shows about 600 false wins (a, 10.5 / 0.017). At rho 0.75, M = 1,000, d = 0.5, 3 years (m, `bursts.py`):

| | own pairs | BH | BY |
|---|---|---|---|
| P(any win shown tonight) | 0.98 | 0.073 | 0.013 |
| FDR (average over nights) | 0.60 | 0.018 | 0.002 |
| Luck share, given wins shown | 0.62 | 0.25 | 0.13 |
| P(over half luck, given wins shown) | 0.70 | 0.23 | 0.13 |

At d = 1.0 the luck share given wins drops to 0.033 (m). Marginal wins are luckier: at d = 1.0, M = 1,000, 5 years, the weaker half of wins was 13% luck against 3.5% overall (m).

**Re-looks.** BH holds each night, not the history. At M = 10 a null rule ever shows a win by 5 years 16 times as often as at one look (5.5% against 0.34%, m). Of rules that ever showed a win, 7% to 26% were null (m).

**Gaming** (m; honest M = 1,000, 2% at d = 0.5, 3 years):

| Attack | Effect |
|---|---|
| 9,000 null rules, many accounts | Attacker gets 0.03 false wins a night under BH, 263 under own pairs. Honest power falls from 0.008 to 0.001. |
| 9,000 certain losers (d = −2) | Two-sided BH: honest null win rate rises from 6e-5 to 0.027, 81% of wins luck. One-sided BH: no effect. |
| 1,000 clones of one real edge, plus 1,000 nulls | Honest null win rate rises 67 times. Attacker gets 3.75 false wins a night while the luck share reads 1.3%. Exact dedupe stops exact clones only (g). |

## 4. Cost

- **Compute.** Today's loop bootstrap takes 0.15 to 0.18 s per rule per night (m), 30 min at 10,000 rules (a). A vectorized weight matrix takes 0.004 s (m), 40 s (a). BH is one sort.
- **Static site.** α_t moves nightly, so all M rule pages change nightly. `jt arena` stays deterministic for fixed inputs.
- **Storage.** Ledger: 33M position rows a year at 10,000 rules (a). Verdict history: 500 MB a year (a).
- **Build.** About 1 week on top of the learner backend (g).
- **Catalog verdicts.** Unchanged. Learner pairs never join the catalog's 28-pair family.

## 5. For a curious learner

Your rule plays the 8 catalog strategies from the session after you saved it. Every night luck puts some saved rules ahead, so one rule ahead means little when thousands play. We call a win only when your interval clears zero, and the interval widens as more rules play. Our rule keeps the share of wins that are luck at 2.5% on average over nights. On one night it can be much higher, because one unlucky strategy makes many rules look ahead at once. Your verdict can change when other people save rules, and a win can disappear.

## 6. Rejected alternatives

- **FCR intervals for selected rules only (BY 2005).** An unselected rule would show a 95% interval excluding zero beside "Too close to call". Every rule uses the night's level instead.
- **Two-sided BH at q = 0.05.** Certain losers inflate R.
- **BY.** Valid under any dependence, with half of BH's luck given wins. But q shrinks by 9.8 at M = 10,000 (a), and power at d = 1.0, 5 years falls from 0.50 to 0.21 (m). It is the fallback if bursts are unacceptable.
- **Own pairs at 95%.** FDR 16% to 60%, and many accounts mint wins (m).
- **Every saved rule.** Honest per verdict, but power is 0.12 at d = 1.0 (m). BH beats it only when strong edges exist. For d of 0.5 or less, both are near zero.
- **Storey BH or online FDR.** Flooding moves Storey's π0 estimate. Online FDR handles arrivals and re-looks but rewards early savers and is hard to explain (g).
