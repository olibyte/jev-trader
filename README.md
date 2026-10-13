# jev-trader

A trade arena where you pick two well-known trading strategies, run them on the same market with the same costs, and ask which one wins. Most answers are "Too close to call", and the arena says so. It grew out of a finished study of Jev, TypeSafe AI's decision model, against technical-analysis rules.

- [Product spec](docs/product-spec.md) explains the question, the audience, and the honesty rules for the public site.
- [Implementation plan](docs/implementation-plan.md) lists the architecture, data shapes, methods, milestones, and decision log.
- [Arena synthesis](docs/arena/2026-10-13-trade-arena/synthesis.md) records the candidate concepts behind the arena design.

`research/` computes the study and `jt export` writes `export/v1/`. `web/` is a static Next.js site that reads only those files. Today it lands on the Jev study's pre-registered holdout result. The arena milestones in the plan move that result to `/studies/jev/` and make the matchup the home page.

Both documents change as the research progresses.
