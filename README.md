# datalog-conformance

Portable conformance suite for Datalog and Defeasible Datalog evaluators.

The package ships YAML suites plus a pytest plugin. An evaluator under test is supplied at runtime
 with `--datalog-evaluator=package.Class`, and the plugin dispatches each YAML case through a small
 runner/protocol layer.

## What This Repo Contains

- Core Datalog suites for facts, joins, recursion, negation, and rejection/error cases.
- Defeasible suites for strict-only equivalence, mixed theories, superiority,
  DePYsible-derived cases, and a first SPINdle-family slice from `spindle-racket`.
- Hypothesis property tests backed by a small internal reference evaluator for the positive and
  conflict-free fragments.
- Harvest scripts for Souffle, Nemo, Crepe, and a starter SPINdle-family slice.
- Source and license notes in [docs/HARVESTING.md](docs/HARVESTING.md).

## Install

For working on this repo:

```powershell
uv sync
```

From another project:

```powershell
uv add datalog-conformance --dev
```

## Run

Against a packaged evaluator:

```powershell
uv run pytest --pyargs datalog_conformance --datalog-evaluator=mypackage.MyEvaluator
```

Against this repo's bundled tests:

```powershell
uv run pytest tests --datalog-evaluator=mypackage.MyEvaluator
```

Filter by tags:

```powershell
uv run pytest tests --datalog-evaluator=mypackage.MyEvaluator --datalog-tags=defeasible,basic
```

## Current Corpus

- Core Datalog cases: 282
- Defeasible cases: 318
- Property tests: 15

Current notable sources:

- Souffle portable subset
- Nemo testcases
- Crepe UI rejection cases
- DePYsible examples
- spindle-racket test theories
- spindle-racket inline reasoning tests
- Derived strict-only defeasible lifts from the core corpus
- Maher 2021 Examples 2-3, authored from local page images

See [docs/IMPLEMENTATIONS.md](docs/IMPLEMENTATIONS.md) for concrete runtimes to confirm against.

## Verification

Current repo verification commands:

```powershell
uv run pytest tests/
uv run --extra dev ruff check .
uv run --extra dev pyright
```

## Layout

- `src/datalog_conformance/schema.py`: YAML dataclasses and validation.
- `src/datalog_conformance/protocol.py`: evaluator protocols.
- `src/datalog_conformance/plugin.py`: pytest discovery and parametrization.
- `src/datalog_conformance/runner.py`: bridge from YAML cases to evaluator methods.
- `src/datalog_conformance/strategies.py`: Hypothesis generators for generated programs and
  conflict-free defeasible theories.
- `src/datalog_conformance/_tests/`: bundled YAML suites.
- `src/datalog_conformance/examples/depysible_adapter.py`: live example adapter for DePYsible.
- `scripts/`: source harvesters and helper scripts.
- `tests/`: meta-tests and property tests for the suite itself.

## License

The framework code in this repo is MIT. Harvested or derived test data keeps source attribution and
 upstream license notes in [docs/HARVESTING.md](docs/HARVESTING.md).
