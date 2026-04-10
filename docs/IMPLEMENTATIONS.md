# Implementations To Confirm Against

This file names concrete existing evaluators and corpus sources that the conformance suite can
target with adapters or cross-checks.

## Core Datalog Runtimes

### Nemo

- Repo: `https://github.com/knowsys/nemo`
- Verified locally: cloned into temporary workspace from that exact Git URL.
- Stack: Rust workspace with `nemo-cli` and `nemo-python`.
- Fit: strongest immediate core-Datalog candidate because the source tree includes both a CLI and a
  Python package surface.
- Local environment: `cargo` is available on this machine.

### Souffle

- Repo: `https://github.com/souffle-lang/souffle`
- Verified locally: cloned into temporary workspace from that exact Git URL.
- Stack: C++ project with CMake build and CLI/runtime tooling.
- Fit: strong oracle for positive Datalog, recursion, and some negation slices. Also the largest
  immediate source of harvested core tests.
- Local environment: source is present, but the `souffle` binary is not currently installed.

## Error-Oriented Core Surface

### Crepe

- Repo: `https://github.com/ekzhang/crepe`
- Verified locally: cloned into temporary workspace from that exact Git URL.
- Stack: Rust crate.
- Fit: useful for rejection and safety cases. Less useful as a full runtime oracle because many of
  its UI failures are Rust-macro-specific rather than pure Datalog semantics.
- Local environment: `cargo` is available on this machine.

## Defeasible Reasoning Candidates

### DePYsible

- Repo: `https://github.com/stefano-bragaglia/DePYsible`
- Verified locally: cloned into temporary workspace and its own 47-unit-test suite passed here under
  `uv` when `PYTHONPATH=src/main/python` and the parser dependencies were supplied.
- Stack: Python.
- Fit: best first defeasible target because it is small, Python-native, and close to the evaluator
  protocol we want to test against.
- Repo state in this project: a thin example adapter now exists at
  `datalog_conformance.examples.depysible_adapter`, and fourteen DePYsible-derived defeasible cases
  were confirmed against it.

### SPINdle Family

- Original Java SPINdle: referenced by the spindle-rust docs as the original implementation.
- spindle-racket: `https://codeberg.org/anuna/spindle-racket`
- Verified locally: cloned from that exact Codeberg URL. The repo contains `.dfl` test theories,
  Racket reasoning tests, and docs.
- spindle-rust: `https://github.com/anuna-research/spindle-rust`
- Fit: strong longer-term defeasible confirmation targets, especially for ambiguity blocking vs
  propagating semantics and superiority handling.
- Repo state in this project: a first forty-two-case translated slice now exists from
  `spindle-racket/src/test-theories`, `tests/spindle-tests.rkt`,
  `tests/query/query-test.rkt`, and `tests/query/integration-test.rkt`. The
  `scripts/harvest_spindle.py` script currently regenerates the `src/test-theories` portion.
- Local environment: Java is installed, Rust is installed, Racket is not installed.

## Priority Order

1. Nemo adapter for core Datalog confirmation.
2. Souffle adapter or CLI bridge for broader core confirmation.
3. Crepe integration for rejection/error slices only.
4. DePYsible adapter for first defeasible runtime confirmation.
5. SPINdle-family adapters for stronger defeasible cross-checking.

## Local Runtime Snapshot

- `java --version`: available.
- `cargo --version`: available.
- `racket --version`: not available.
- `souffle --version`: not available.
