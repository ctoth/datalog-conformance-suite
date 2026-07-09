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
  conflict-free fragments, plus live DePYsible-backed generated tests for the supported
  defeasible fragment.
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

## External Oracles

The suite's verification claims rest on real, independent implementations, not on code in this
repo. Four engines are integrated as first-class evaluators under
`datalog_conformance.oracles`:

- `NemoOracle` — [Nemo](https://github.com/knowsys/nemo) via a local `nmo` build
- `SouffleOracle` — [Souffle](https://github.com/souffle-lang/souffle) natively or through WSL
- `ClingoOracle` — [clingo](https://github.com/potassco/clingo) via the `oracles` extra
  (`uv sync --extra oracles`)
- `SwiPrologOracle` — [SWI-Prolog](https://www.swi-prolog.org/) with tabling (SLG resolution, a
  top-down strategy independent of the three bottom-up engines), natively or through WSL

Each implements the evaluator protocol, so the entire bundled suite can run against a real
engine directly:

```powershell
uv run pytest tests --datalog-evaluator=datalog_conformance.oracles.nemo.NemoOracle
```

`scripts/verify_core_multi_oracle.py` runs every core case against every available engine and
writes a per-case agreement matrix. As of 2026-07-09 the full corpus shows zero cross-engine
mismatches: Nemo, clingo, and SWI-Prolog each confirm all 1108 cases, and Souffle confirms
1105 (the remaining 3 mix numbers and symbols in one column, which Souffle's typed dialect
cannot express; recorded as `unsupported`, never guessed). Every case is therefore agreed upon
by at least three, and 1105 of 1108 by all four, independent engines.

## Current Corpus

- Core Datalog YAML cases: 1108 (including 1000 generated oracle cases)
- Defeasible YAML cases: 180
- KLM property YAML cases: 1
- Generated property and meta-tests remain under `tests/`

Current notable sources:

- Souffle portable subset
- Nemo testcases
- Crepe UI rejection cases
- DePYsible examples
- spindle-racket test theories
- spindle-racket inline reasoning tests
- spindle-racket query theory tests
- spindle-racket query integration tests
- Derived strict-only defeasible lifts from the core corpus
- Maher 2021 Examples 2-3, authored from local page images
- Antoniou 2007 ambiguity-policy examples, authored from local page images and checked against a
  local paper-reference evaluator for the reduced propositional fragment
- Morris 2020 Example 6 closure cases, authored from local page images and checked against a local
  ranked-worlds closure reference for the reduced propositional fragment
- Morris 2020 Appendix C.2 Or property cases, authored from local page images and checked against
  a local reduced closure-plus-relevance reference
- Bozzato 2020 Example 1, Goldszmidt and Pearl 1992 Example 1, and Morris 2020 Example 5,
  adapted from local paper notes and checked against the supported DePYsible surface

See [docs/IMPLEMENTATIONS.md](docs/IMPLEMENTATIONS.md) for concrete runtimes to confirm against.

## Verification

Current repo verification commands:

```powershell
uv run scripts/audit_program_surface.py
uv run scripts/verify_core_with_nemo.py
uv run --extra oracles scripts/verify_core_multi_oracle.py
uv run pytest tests/
uv run --with arpeggio --with colorama pytest tests/test_depysible_generated.py
uv run --extra dev ruff check .
uv run --extra dev pyright
```

`uv run scripts/verify_core_with_nemo.py` writes each run to its own timestamped report
directory under `reports/verify_core_with_nemo/`, groups cases by shared visible program, and
prefers a release `nmo` binary when one is available.

`scripts/verify_core_multi_oracle.py` does the same across Nemo, Souffle, and clingo at once
and emits `matrix.json`/`summary.json` with per-oracle outcomes and `verified_by_N` agreement
buckets. Differential property tests (`tests/test_oracle_differential.py`) additionally require
all available engines to agree on Hypothesis-generated programs.

## Layout

- `src/datalog_conformance/schema.py`: YAML dataclasses and validation.
- `src/datalog_conformance/protocol.py`: evaluator protocols.
- `src/datalog_conformance/plugin.py`: pytest discovery and parametrization.
- `src/datalog_conformance/runner.py`: bridge from YAML cases to evaluator methods.
- `src/datalog_conformance/oracles/`: real-engine adapters (Nemo, Souffle, clingo) implementing
  the evaluator protocol.
- `src/datalog_conformance/references/core.py`: the shared rule parser the oracle adapters
  translate through, plus a test-support evaluator (not a verification oracle).
- `src/datalog_conformance/strategies.py`: Hypothesis generators for generated programs and
  conflict-free defeasible theories.
- `src/datalog_conformance/depysible_strategies.py`: Hypothesis generators for live
  DePYsible-backed defeasible testing.
- `src/datalog_conformance/_tests/`: bundled YAML suites.
- `src/datalog_conformance/examples/depysible_adapter.py`: live example adapter for DePYsible.
- `scripts/`: source harvesters and helper scripts.
- `tests/`: meta-tests, property tests, and actual-implementation generated checks.

## License

The framework code in this repo is MIT. Harvested or derived test data keeps source attribution and
 upstream license notes in [docs/HARVESTING.md](docs/HARVESTING.md).
