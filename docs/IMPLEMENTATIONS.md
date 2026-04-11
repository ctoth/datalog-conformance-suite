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
  were confirmed against it. The repo also now includes generated Hypothesis checks against the
  live DePYsible implementation for its supported fragment.

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

## Policy And Closure Confirmation

### Ambiguity Behavior

- Best direct oracle target: SPINdle-family runtimes once one is runnable locally.
- Current retained reduced oracle:
  - `tests/test_ambiguity_corpus.py`
  - zero-arity local paper-reference evaluator for the Antoniou section 3.5 ambiguity example
- Current paper-backed source:
  - sibling local path `..\gunray\papers\Antoniou_2007_DefeasibleReasoningSemanticWeb\pngs\page-010.png`

### Closure Behavior

- No external closure runtime is currently integrated in this repo as a direct oracle.
- Current retained reduced oracle:
  - `tests/closure_test_support.py`
  - `tests/test_closure_corpus.py`
  - ranked-worlds rational and lexicographic closure for the zero-arity propositional fragment
- Current paper-backed source:
  - sibling local path `..\gunray\papers\Morris_2020_DefeasibleDisjunctiveDatalog\pngs\page-011.png`
  - sibling local path `..\gunray\papers\Morris_2020_DefeasibleDisjunctiveDatalog\pngs\page-012.png`
  - sibling local path `..\gunray\papers\Morris_2020_DefeasibleDisjunctiveDatalog\pngs\page-015.png`
  - sibling local path `..\gunray\papers\Morris_2020_DefeasibleDisjunctiveDatalog\pngs\page-016.png`

### KLM Property Behavior

- No external KLM-property oracle is currently integrated in this repo as a direct runtime check.
- Current retained reduced oracle:
  - `tests/closure_test_support.py`
  - `tests/test_klm_corpus.py`
  - reduced `Or` checker with rational, lexicographic, and minimal relevant closure support
- Current paper-backed source:
  - sibling local path `..\gunray\papers\Morris_2020_DefeasibleDisjunctiveDatalog\pngs\page-026.png`
  - sibling local path `..\gunray\papers\Morris_2020_DefeasibleDisjunctiveDatalog\pngs\page-027.png`

## Verification Rule For Policy And Closure Cases

- Every new ambiguity, closure, or KLM YAML case must include `verification` metadata naming the
  confirmation path.
- A new case counts as verified only if it is one of:
  - `kind: direct`: reproduced against a runnable implementation named in `verification.implementation`
  - `kind: reduced`: derived from exact local page images with precise page or figure provenance
    and reproduced against a reduced local reference evaluator whose supported fragment is named in
    the accompanying test or docs
- New notes-only policy, closure, or KLM cases are not acceptable. If the retained case did not
  come from a runnable implementation, the source must be page-image-backed.
- The retained YAML must preserve whether it is exact or reduced. If it is reduced, the description
  must say what was reduced.

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
