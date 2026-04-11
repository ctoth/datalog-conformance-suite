# Proposal: Force Real Policy and Closure Implementations

## Problem

The suite already has schema vocabulary for:

- `expect_per_policy`
- `blocking`
- `propagating`
- `rational_closure`
- `lexicographic_closure`
- `relevant_closure`

But the current corpus does not yet apply enough pressure on those surfaces to force actual
implementation boundaries in evaluators.

In practice, this means an evaluator can pass the current suite while still:

- ignoring ambiguity policy selection
- hard-coding one defeasible behavior path in a monolithic evaluator
- shipping placeholder `closure.py`, `ambiguity.py`, `compile.py`, or `tolerance.py` modules
- avoiding a real architectural split between shared theory semantics and policy-specific behavior

That is a suite gap. The suite should force real externally visible capabilities, not just reward
one implementation path that happens to match today’s examples.

## Goal

Add conformance cases that require evaluators to expose and honor the semantic policy surfaces that
the schema already advertises.

The target is not a specific implementation architecture. The target is an observable capability:

1. the same defeasible theory must produce different valid outputs under different ambiguity
   policies when the logic says it should
2. the same defeasible theory must produce different valid outputs under different closure
   operators when the logic says it should
3. KLM-property cases must become real, not placeholder schema support

## Proposed Additions

### 1. Ambiguity Corpus That Forces `blocking` vs `propagating`

Add a new defeasible corpus slice, for example:

- `src/datalog_conformance/_tests/defeasible/ambiguity/`

Use `expect_per_policy` and require different outputs for the same theory under:

- `blocking`
- `propagating`

The first cases should be small, hand-authored, and paper-backed. Good starting sources:

- Antoniou/Bikakis ambiguity examples from the DR-Prolog paper and related defeasible logic papers
- SPINdle-family theories where ambiguity policy is already explicit in the source corpus

Acceptance criterion:

- at least one case where `blocking` yields a downstream conclusion and `propagating` does not
- at least one case where `propagating` yields an explicit ambiguous/undecided style section that
  differs from `blocking`

This is the cleanest way to force evaluators to honor the policy parameter instead of ignoring it.

### 2. Closure Corpus That Forces `rational_closure` vs `lexicographic_closure`

Add:

- `src/datalog_conformance/_tests/defeasible/closure/`

and begin populating the currently empty KLM surface with:

- direct defeasible cases using `expect_per_policy`
- KLM property declarations under `klm_property`

Primary source:

- Morris 2020 examples and counterexamples, authored from local page-image readings and then
  verified against an actual implementation where available

Acceptance criterion:

- at least one case where `rational_closure` and `lexicographic_closure` differ observably
- at least one KLM case for each of the core properties the schema is already prepared to encode
- explicit counterexamples showing `relevant_closure` fails the properties Morris proves it fails

This forces real closure support instead of a placeholder module or a single built-in closure path.

### 3. Verification Rule For New Policy/Closure Cases

New policy-sensitive and closure-sensitive cases should not be accepted as mere handwritten intent.

They should be verified against at least one concrete implementation or source-backed derivation.

Preferred order:

1. actual implementation confirmation
2. source-paper derivation with exact citation when no runnable implementation exists
3. temporary suite inclusion only when marked clearly as awaiting implementation confirmation

The repo already moved in this direction for core Datalog. The same discipline should apply here.

## What Should Stay Local To Evaluators

Not every missing module belongs in the shared suite.

These should stay implementation-local unless the suite defines a public protocol for them:

- trace/debug APIs
- exact compiled-program shape for Maher translation
- tolerance prefilter internals
- caches, profiling hooks, and internal justification structures

These are valid local tests, but not conformance targets by default.

## Where `compilation` and `tolerance` Fit

### Compilation

Compilation belongs in the conformance suite only when tested through an engine-neutral observable
surface, for example:

- compiled-vs-direct semantic equivalence
- a public compile protocol defined in `protocol.py`

Without such a protocol, exact emitted rule shape should remain local to the evaluator repo.

### Tolerance

Tolerance belongs in the conformance suite only if it becomes externally observable behavior.

Examples:

- a theory class whose expected classification differs because intolerable defaults must be filtered
- an agreed public API for tolerance checking

If tolerance remains an internal optimization or pruning step, it should stay local.

## Suggested Initial Deliverables

1. Add one new ambiguity YAML file with 2-4 hand-authored `expect_per_policy` cases.
2. Add one new closure YAML file with 1-2 Morris-derived `expect_per_policy` cases.
3. Add the first KLM property YAML file and wire it into repo tests.
4. Update `README.md` current corpus counts after those files land.
5. Update `docs/IMPLEMENTATIONS.md` to name the best current confirmation targets for:
   - ambiguity policy behavior
   - closure behavior

## Why This Matters

Right now the schema promises more than the corpus forces.

That gap encourages evaluator repos to:

- pass the suite with monolithic special-casing
- defer real policy support indefinitely
- treat closure support as documentation-only

Adding these policy-distinguishing and closure-distinguishing cases would make the suite a better
specification of defeasible reasoning behavior rather than only a collection of defeasible examples.
