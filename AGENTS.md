# Agent instructions

## Start with the project docs

Read [README.md](README.md) for the project overview.
Read [docs/product-spec.md](docs/product-spec.md) before changing product behavior or research reporting.
Read [docs/implementation-plan.md](docs/implementation-plan.md) before changing the architecture or research method.
When a design decision changes, update the relevant document and add a dated entry to the implementation plan's decision log.

## Work in the current package

The implemented code lives in `research/`, a Python 3.14 package managed with uv.
The static Next.js site lives in `web/`. The later research modules in the implementation plan are planned work.
Check the source before treating a planned command or module as available.

- `research/src/jevtrader/data.py` owns market-data requests, validation, raw archives, Parquet snapshots, and manifests.
- `research/src/jevtrader/states.py` owns the indicators, the versioned `State`, the vote tables, the splits, and the purged forward labels.
- `research/src/jevtrader/evaluate.py` owns the arm registry, the decisions, the backtest, the metrics, the joint-date block bootstrap, the MDE, the pre-registration text, the prereg lock check, and the holdout result.
- `research/prereg.toml` is the committed pre-registration. Never edit it by hand. `jt evaluate --prereg` writes it and refuses to replace a different file.
- `research/holdout.json` and `research/holdout.manifest.json` are the one-shot holdout result and its run manifest. Never edit, delete, or regenerate them. `jt holdout` writes them once and refuses a second run. `jt holdout --verify` reruns the holdout and compares the bytes. Never run `jt holdout` on the real data. The user runs it.
- `research/src/jevtrader/jev.py` owns the Jev prompt, the OpenRouter Decisions call, the append-only call log, and the policy table.
- `research/src/jevtrader/export.py` owns the `export/v1/` and `export/arena/v1/` contracts that the site reads. It checks that the `export/v1/` inputs are the files the holdout read, renders every file, and converges each directory.
- `export/v1/` is the committed site export. Never edit it by hand. Regenerate it with `jt export`, which changes no files when the inputs are unchanged.
- `research/src/jevtrader/catalog.py` owns the arena strategies in `CATALOG`, their fingerprints, their decisions, the reconciliation with `research/holdout.json`, the refusals, and the pair comparisons.
- `export/arena/v1/` is the committed arena export. Never edit it by hand. Regenerate it with `jt arena`, which changes no files when the inputs are unchanged.
- `research/src/jevtrader/cli.py` owns the `jt` command and reads the API keys, clock, and network at the CLI boundary. Only `jt fetch` and `jt adjust-check` read `TWELVE_DATA_API_KEY`. Only `jt jev-table` without `--offline` reads `OPENROUTER_API_KEY`.
- `research/jev_calls.jsonl` is the frozen Jev call log. Never edit or regenerate it. Build from it with `jt jev-table --offline`.
- `research/tests/test_data.py` checks the data pipeline with recorded fixtures and mocked HTTP responses.
- `research/tests/test_states.py` holds the truncation property test, which fails if an indicator reads a later bar.
- `research/tests/test_jev.py` checks the Jev call, the call log, and the policy table with mocked HTTP responses.
- `research/tests/test_export.py` checks the export preconditions, the copied holdout numbers, the rebuilt Jev requests, and the unchanged rerun on synthetic data.
- `research/tests/test_catalog.py` checks the truncation property over `CATALOG`, the `oracle` negative control, the fingerprints, the refusals, the reconciliation, and `jt arena` on synthetic data.
- `research/tests/test_holdout.py` checks the holdout lock, the single run, and the byte-identical rerun on synthetic data in a temporary git repository.
- `research/pyproject.toml` defines dependencies and Ruff rules. Keep `research/uv.lock` in sync with dependency changes.
- `web/src/lib/export.ts` owns the zod schemas and the cross-file checks for `export/v1/`. Every page reads the export through `loadExport()`, so a bad file fails `next build`.
- `web/src/lib/arena.ts` reads `export/arena/v1/` for the "Pick two" prototype at `/preview/`. The Jev study pages live in the `web/src/app/(study)/` route group, which owns their layout and `globals.css`.
- `web/src/lib/format.ts` owns every number format on the site. `web/e2e/expected.ts` keeps an independent copy for the end-to-end test.
- `web/scripts/check-schema.mjs` builds against broken copies of the export and fails unless each build fails. `web/scripts/check-honesty.mjs` fails on banned wording such as "confidence" or "Reasoning".
- `web/pnpm-workspace.yaml` refuses packages published in the last 14 days. Keep `web/pnpm-lock.yaml` in sync with dependency changes.

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

Run these commands from `web/`.
Install the dependencies with `pnpm install --frozen-lockfile`.

```sh
pnpm build
pnpm typecheck
pnpm check:honesty
pnpm check:schema
pnpm test:e2e
```

`pnpm test:e2e` serves `web/out/`, so run it after `pnpm build`.
After changing `web/` code or the export, run all five.

After changing Python code, run the tests and both Ruff checks.
After changing `export.py`, run `uv run jt export` twice and check that the second run reports every file unchanged. Then run the `web/` checks.
For documentation changes, check referenced paths and commands, and check the diff for whitespace errors.
Report what you checked and any check you could not run.

## Preserve reproducible research

Keep routine tests offline. Use recorded fixtures and mocked HTTP responses.
Treat `jt fetch` and `jt adjust-check` as live API operations that consume Twelve Data credits.
Treat `jt jev-table` without `--offline` as a paid OpenRouter operation.
Keep `.env`, API keys, and generated `data/` files out of git.
Never print API keys or request URLs that contain them.
Use [.env.example](.env.example) for the required variable name.

Preserve atomic snapshot writes and the guarantee that an unchanged refresh changes no files.
Validate market data before replacing a snapshot.
For future evaluation work, prevent look-ahead bias and follow the documented development and holdout rules.
Read frozen Jev results during evaluation instead of triggering paid API calls.
Publish null and inconclusive results as valid outcomes.
Follow the product spec's honesty rules in `web/`. The site reads `export/v1/` and never recomputes a metric or calls Twelve Data or Jev.
