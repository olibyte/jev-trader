# jev-trader

A research platform that tests how well Jev, TypeSafe AI's decision model, makes stock-trading decisions compared with technical-analysis rules.

- [Product spec](docs/product-spec.md) explains the question, the audience, and the honesty rules for the public site.
- [Implementation plan](docs/implementation-plan.md) lists the architecture, data shapes, research method, milestones, and decision log.

`research/` computes the study and `jt export` writes `export/v1/`. `web/` is a static Next.js site that reads only those files. It lands on the pre-registered holdout result.

Both documents change as the research progresses.
