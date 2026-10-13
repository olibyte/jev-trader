# Rubric (picker's tool, not shown to candidates)

Score each criterion 1-5.

1. **First-screen simplicity.** A newcomer gets one honest head-to-head in one or two actions. The first screen carries fewer concepts than today's front page (outcome rule, MDE, AUC, Brier, calibration, arm table) without hiding the uncertainty.
2. **Enforceable honesty.** The replacement for "no free date picker" is a rule the build or a test can check. CIs, period labels, and a multiple-comparison or snooping guard survive the extra freedom.
3. **Look-ahead safety for new strategy kinds.** Candlestick and ML strategies reuse or extend the truncation test, the purged labels, and the split discipline, with a concrete mechanism.
4. **Architecture fit and cost.** Reuses `evaluate.py`, `states.py`, `export.py`, and the static S3 and CloudFront site. Numbers (bytes, compute, grid size) back the placement of compute. No new runtime without a reason.
5. **First milestone.** Small, ships alone, and ends in a pass/fail command.
6. **Path to the long-term goal.** Extends toward "any strategy against any strategy", including ML, without a rewrite.
