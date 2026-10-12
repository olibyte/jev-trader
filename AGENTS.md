# Agent instructions

## Start with the project docs

Read [README.md](README.md) for the project overview.
Read [docs/product-spec.md](docs/product-spec.md) before changing product behavior or research reporting.
Read [docs/implementation-plan.md](docs/implementation-plan.md) before changing the architecture or research method.
When a design decision changes, update the relevant document and add a dated entry to the implementation plan's decision log.

## Work in the current package

The implemented code lives in `research/`, a Python 3.14 package managed with uv.
The static Next.js site and the later research modules in the implementation plan are planned work.
Check the source before treating a planned command or module as available.

- `research/src/jevtrader/data.py` owns market-data requests, validation, raw archives, Parquet snapshots, and manifests.
- `research/src/jevtrader/states.py` owns the indicators, the versioned `State`, the vote tables, the splits, and the purged forward labels.
- `research/src/jevtrader/evaluate.py` owns the empirical table, AUC, and the joint-date block bootstrap.
- `research/src/jevtrader/cli.py` owns the `jt` command and reads the API key, clock, and network at the CLI boundary. Only `jt fetch` and `jt adjust-check` read the key.
- `research/tests/test_data.py` checks the data pipeline with recorded fixtures and mocked HTTP responses.
- `research/tests/test_states.py` holds the truncation property test, which fails if an indicator reads a later bar.
- `research/pyproject.toml` defines dependencies and Ruff rules. Keep `research/uv.lock` in sync with dependency changes.

Keep changes focused on the requested task.
Reuse the existing modules before adding layers or dependencies.
Preserve unrelated local changes.
Use relevant skills under `.agents/skills/` when requested or when their workflow fits the task.
Keep repository instructions in this file. Keep `CLAUDE.md` as a pointer to it.

## Run local checks

Run these commands from `research/`.
Install the package and development dependencies with `uv sync --locked`.

```sh
uv run python -m pytest
uv run ruff check .
uv run ruff format --check .
uv run jt --help
```

After changing Python code, run the tests and both Ruff checks.
For documentation changes, check referenced paths and commands, and check the diff for whitespace errors.
Report what you checked and any check you could not run.

## Preserve reproducible research

Keep routine tests offline. Use recorded fixtures and mocked HTTP responses.
Treat `jt fetch` and `jt adjust-check` as live API operations that consume Twelve Data credits.
Keep `.env`, API keys, and generated `data/` files out of git.
Never print API keys or request URLs that contain them.
Use [.env.example](.env.example) for the required variable name.

Preserve atomic snapshot writes and the guarantee that an unchanged refresh changes no files.
Validate market data before replacing a snapshot.
For future evaluation work, prevent look-ahead bias and follow the documented development and holdout rules.
Read frozen Jev results during evaluation instead of triggering paid API calls.
Publish null and inconclusive results as valid outcomes.
When building the site, follow the product spec's honesty rules and read exported results instead of recomputing metrics.
