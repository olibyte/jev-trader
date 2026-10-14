## 1. Critical values (Gaussian max-|z|, 400,000 draws)
- One learner rule, 8 pairs, one market: 2.654
- One learner rule, 14 pairs, two independent markets (8 + 6): 2.853
- Catalog only, 28 pairs: 3.030
- Every saved rule in one family (28 + 8M pairs), the rejected alternative:
  - M = 10: 3.412
  - M = 100: 3.900
  - M = 1000: 4.356
  - M = 10000: 4.755

## 2. Per-rule rates (20,000 synthetic runs per rho)

### rho = 0.75

Null rule (true excess Sharpe equal to buy and hold). Percent of rules.

| Horizon | Any win, single look | Rule wins, single look | Any win, ever (nightly) | Rule wins, ever (nightly) |
|---|---|---|---|---|
| 1y | 5.2 | 2.5 | 28.0 | 14.2 |
| 3y | 5.0 | 2.5 | 39.7 | 20.4 |
| 5y | 5.1 | 2.5 | 44.4 | 22.9 |

Power: percent of rules with a true advantage d that read 'A wins' over buy and hold. Single look at the horizon (ever, at any nightly look).

| d | 1y | 3y | 5y |
|---|---|---|---|
| 0.3 | 1.3 (5.5) | 2.7 (11.0) | 4.3 (15.4) |
| 0.5 | 2.5 (8.7) | 7.4 (20.0) | 14.2 (30.4) |
| 1.0 | 10.6 (22.0) | 41.3 (58.3) | 69.0 (81.2) |

Rule wins over at least one catalog entry, single look:

| d | 1y | 3y | 5y |
|---|---|---|---|
| 0.0 | 2.5 | 2.5 | 2.5 |
| 0.3 | 7.1 | 13.5 | 19.8 |
| 0.5 | 13.0 | 30.1 | 46.1 |
| 1.0 | 37.7 | 83.1 | 96.6 |

Null snapshot rate 'any win' across nights 60..1260: min 4.8%, max 5.8%, at night 60 5.8%, at 1260 5.1%.

### rho = 0.25

Null rule (true excess Sharpe equal to buy and hold). Percent of rules.

| Horizon | Any win, single look | Rule wins, single look | Any win, ever (nightly) | Rule wins, ever (nightly) |
|---|---|---|---|---|
| 1y | 5.3 | 2.7 | 29.3 | 14.8 |
| 3y | 5.3 | 2.6 | 40.9 | 21.0 |
| 5y | 5.2 | 2.6 | 45.7 | 23.7 |

Power: percent of rules with a true advantage d that read 'A wins' over buy and hold. Single look at the horizon (ever, at any nightly look).

| d | 1y | 3y | 5y |
|---|---|---|---|
| 0.3 | 0.8 (4.5) | 1.3 (7.9) | 1.9 (10.0) |
| 0.5 | 1.3 (5.7) | 2.7 (11.0) | 4.1 (15.3) |
| 1.0 | 3.4 (10.4) | 10.2 (24.8) | 20.4 (38.5) |

Rule wins over at least one catalog entry, single look:

| d | 1y | 3y | 5y |
|---|---|---|---|
| 0.0 | 2.7 | 2.6 | 2.6 |
| 0.3 | 4.8 | 7.1 | 9.6 |
| 0.5 | 7.1 | 13.0 | 19.0 |
| 1.0 | 16.0 | 38.3 | 58.4 |

Null snapshot rate 'any win' across nights 60..1260: min 4.9%, max 6.2%, at night 60 6.2%, at 1260 5.2%.

## 3. Chance that a shown 'rule wins' verdict is luck, at a 3-year single look
Arithmetic: pi0*a / (pi0*a + pi1*power). a and power are measured above. pi1, the share of rules with a real edge, is a guess.

| rho | pi1 | d = 0.5 | d = 1.0 |
|---|---|---|---|
| 0.75 | 1% | 89% | 75% |
| 0.75 | 5% | 61% | 36% |
| 0.75 | 20% | 25% | 11% |
| 0.25 | 1% | 95% | 87% |
| 0.25 | 5% | 79% | 56% |
| 0.25 | 20% | 45% | 21% |

## 4. Site-wide counts on one night, every learner rule null
Rules saved on uniform days over 5 years, read at the end of year 5 (staggered), or all saved on one day and read 1 year later (cohort). 'Played' = rules with at least 3 blocks. Counts are of rules that show 'rule wins' over at least one catalog entry.

| rho | starts | M | played (mean) | expected luck wins, 2.5% x played | mean wins | 95th pct wins | P(>= 1 win) |
|---|---|---|---|---|---|---|---|
| 0.75 | staggered | 10 | 10 | 0.2 | 0.2 | 1 | 19% |
| 0.75 | staggered | 100 | 95 | 2.4 | 2.5 | 8 | 71% |
| 0.75 | staggered | 1000 | 953 | 23.8 | 26.2 | 82 | 98% |
| 0.75 | staggered | 10000 | 9531 | 238.3 | 253.9 | 764 | 100% |
| 0.75 | cohort | 10 | 10 | 0.2 | 0.3 | 2 | 18% |
| 0.75 | cohort | 100 | 100 | 2.5 | 2.6 | 12 | 59% |
| 0.75 | cohort | 1000 | 1000 | 25.0 | 24.5 | 106 | 92% |
| 0.75 | cohort | 10000 | 10000 | 250.0 | 239.6 | 1043 | 100% |
| 0.25 | staggered | 10 | 9 | 0.2 | 0.2 | 1 | 20% |
| 0.25 | staggered | 100 | 95 | 2.4 | 2.4 | 9 | 68% |
| 0.25 | staggered | 1000 | 954 | 23.9 | 22.8 | 71 | 99% |
| 0.25 | staggered | 10000 | 9527 | 238.2 | 221.8 | 856 | 100% |
| 0.25 | cohort | 10 | 10 | 0.2 | 0.3 | 2 | 19% |
| 0.25 | cohort | 100 | 100 | 2.5 | 2.9 | 12 | 61% |
| 0.25 | cohort | 1000 | 1000 | 25.0 | 23.0 | 114 | 95% |
| 0.25 | cohort | 10000 | 10000 | 250.0 | 250.8 | 1202 | 98% |

Expected 'ever showed a win' for staggered null rules (arithmetic: mean of the measured per-rule ever curve over uniform live lengths):
- rho 0.75: 17.5% of all saved rules (snapshot: 2.4%)
- rho 0.25: 18.1% of all saved rules (snapshot: 2.5%)

## 5. One person saves K null rules on one day (many accounts)
Percent of runs where at least one of the K rules shows 'rule wins'. 1,000 runs (400 for K = 100). Independent-rule arithmetic in brackets: 1 - (1 - a)^K.

| rho | K | 1y single look | 1y ever (nightly) | 5y ever (nightly) |
|---|---|---|---|---|
| 0.75 | 1 | 2% [2%] | 12% | 22% |
| 0.75 | 10 | 16% [20%] | 62% | 80% |
| 0.75 | 20 | 29% [42%] | 79% | 92% |
| 0.75 | 100 | 60% [94%] | 98% | 100% |
| 0.25 | 1 | 2% [2%] | 12% | 22% |
| 0.25 | 10 | 16% [21%] | 63% | 80% |
| 0.25 | 20 | 29% [41%] | 80% | 93% |
| 0.25 | 100 | 59% [94%] | 98% | 100% |

## 6. Spot check: real block_bootstrap + critical_value vs the Gaussian rule
rho 0.75, null rule, 8 pairs, 2,000 reps, seed 0, 200 datasets each. Same data for both rules.

| Sessions | Blocks | Bootstrap any-win rate | Gaussian any-win rate | Mean bootstrap critical value | Median bootstrap SD / delta SE |
|---|---|---|---|---|---|
| 60 | 3 | 57.5% | 7.5% | 2.57 | 0.72 |
| 252 | 13 | 13.5% | 5.0% | 2.61 | 0.94 |
| 1260 | 63 | 4.0% | 3.0% | 2.64 | 1.00 |
(Gaussian critical value 2.65.)

## 7. Nightly compute
- fast_draws equals block_bootstrap: max abs diff 5.3e-15
- Today's per-pair block_bootstrap, 630 sessions: 0.02 s per pair, so 0.1 s per rule (8 pairs)
- Shared-weights matmul, M = 10 rules: 0.0 s per night (per-pair loop would take about 0 min)
- Shared-weights matmul, M = 100 rules: 0.3 s per night (per-pair loop would take about 0 min)
- Shared-weights matmul, M = 1000 rules: 3.0 s per night (per-pair loop would take about 2 min)
- Shared-weights matmul, M = 10000 rules: 6.0 s per night (per-pair loop would take about 24 min)

Total run time 130 s.
