# jev-trader

Trade Arena is a site where you pick two famous trading strategies and see, in plain words, what $1,000 became in each on the same 13 US stock funds. It is a proof of concept. It grew out of a finished study of Jev, TypeSafe AI's decision model, against technical-analysis rules.

- [Product spec](docs/product-spec.md) explains the first screen, the audience, and the rules for plain, honest copy.
- [Deferred "Which one wins?" spec](docs/which-wins-spec.md) keeps the plan for verdicts, markets such as hourly bars, and learner-built rules.
- [Implementation plan](docs/implementation-plan.md) lists the architecture, data shapes, methods, milestones, and decision log.
- [First-screen synthesis](docs/arena/2026-10-14-first-screen/synthesis.md) records how the "Pick two" screen was chosen.

`research/` computes the results. `jt export` writes `export/v1/` for the Jev study, and `jt arena` writes `export/arena/v1/` for the arena. `web/` is a static Next.js site that reads only those files. Today it lands on the Jev study's pre-registered holdout result, and the "Pick two" prototype is at `/preview/`. Milestone 8 in the plan makes "Pick two" the home page and moves the study to `/studies/jev/`.

Both documents change as the research progresses.
