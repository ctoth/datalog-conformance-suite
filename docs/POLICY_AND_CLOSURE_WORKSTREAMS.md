# Policy And Closure Workstreams

This document turns
[PROPOSAL_force_policy_and_closure_surfaces.md](../PROPOSAL_force_policy_and_closure_surfaces.md)
into an executable plan.

The goal is to make the suite force real externally visible defeasible-reasoning capabilities:

- ambiguity policy selection
- closure operator selection
- executable KLM property coverage

This plan deliberately separates semantic-corpus work from implementation-confirmation work. The
suite should not accept large new semantic surfaces without a verification story.

## Workstream A: Ambiguity Policy Corpus

### Objective

Force evaluators to distinguish:

- `blocking`
- `propagating`

for the same theory.

### Deliverables

- new directory:
  `src/datalog_conformance/_tests/defeasible/ambiguity/`
- first file:
  `src/datalog_conformance/_tests/defeasible/ambiguity/antoniou_basic_ambiguity.yaml`
- 2-4 small `expect_per_policy` cases

### Required Case Shapes

1. A case where `blocking` derives a downstream conclusion and `propagating` does not.
2. A case where `propagating` yields an explicit ambiguity-bearing section that differs from
   `blocking`.
3. If available from the source corpus, one superiority-sensitive ambiguity case.

### Sources

- Antoniou/Bikakis DR-Prolog ambiguity examples
- SPINdle-family theories where ambiguity mode is explicit

### Acceptance Gate

- at least one evaluator that currently passes defeasible basics must now produce different outputs
  under `blocking` and `propagating`
- each added case has either:
  - actual implementation confirmation
  - or exact paper-backed derivation with precise provenance

### Suggested Execution Slices

1. author one two-policy hand-built case
2. verify it
3. land it
4. repeat for the next case

## Workstream B: Closure-Distinguishing Corpus

### Objective

Force evaluators to distinguish:

- `rational_closure`
- `lexicographic_closure`

for the same defeasible theory.

### Deliverables

- new directory:
  `src/datalog_conformance/_tests/defeasible/closure/`
- first file:
  `src/datalog_conformance/_tests/defeasible/closure/morris_core_examples.yaml`
- 1-2 Morris-derived `expect_per_policy` cases

### Required Case Shapes

1. A case where `rational_closure` and `lexicographic_closure` differ observably.
2. A case that is stable across both closures, to guard against overfitting to only
   counterexamples.

### Sources

- Morris 2020 examples and counterexamples

### Acceptance Gate

- the corpus contains at least one actual closure-distinguishing theory
- provenance and derivation are strong enough to audit later

### Dependencies

- none at the schema level
- but this workstream is easier after Workstream A because the suite will already be exercising
  `expect_per_policy` more heavily

## Workstream C: KLM Property Surface

### Objective

Turn the schema’s `klm_property` support into real executable corpus coverage.

### Deliverables

- new directory:
  `src/datalog_conformance/_tests/defeasible/klm/`
- first property file:
  `src/datalog_conformance/_tests/defeasible/klm/morris_relevant_counterexamples.yaml`
- repo test wiring that actually executes KLM files, not just schema-validates them

### Required Case Shapes

1. At least one property case where:
   - `rational_closure: true`
   - `lexicographic_closure: true`
   - `relevant_closure: false`
2. At least one positive property case that is satisfied by both supported closures.

### Sources

- Morris 2020 property proofs and relevant-closure counterexamples

### Acceptance Gate

- KLM files are counted in the corpus and executed by repo tests
- `relevant_closure` failure cases are source-backed, not invented

### Dependencies

- Workstream B should go first
- closure examples should exist before abstract property cases become the main surface

## Workstream D: Verification And Oracle Discipline

### Objective

Prevent policy and closure cases from entering the suite as unverified handwritten intent.

### Deliverables

- update `docs/IMPLEMENTATIONS.md` with the best available confirmation targets for:
  - ambiguity behavior
  - closure behavior
- optional helper scripts if a runnable oracle is adopted
- explicit repo rule for what counts as verified for these surfaces

### Acceptance Gate

- every new policy/closure YAML case has a recorded verification path
- the path is either:
  - runnable implementation confirmation
  - or exact paper-image-backed derivation with citations

### Notes

This workstream can proceed in parallel with A and B, but at least one confirmation path should be
settled before those streams add many files.

## Workstream E: Boundary Decision For Compilation And Tolerance

### Objective

Decide what belongs in the shared suite versus evaluator-local tests.

### Questions To Resolve

1. Should Maher compilation be exposed as a public suite protocol?
2. Should tolerance be exposed as a public suite protocol?
3. If not, what semantic equivalence should the suite test instead?

### Default Rule

- If the behavior is externally observable through the evaluator contract, it may belong in the
  suite.
- If the behavior is only an internal optimization or internal intermediate representation, it
  stays local.

### Likely Outcome

- exact compiled-program shape stays local unless the suite defines a compile protocol
- tolerance internals stay local unless the suite defines a tolerance protocol

### Acceptance Gate

- a written repo decision exists, either as docs or implemented protocol support

## Recommended Order

1. Workstream A
2. Workstream D in parallel with A
3. Workstream B
4. Workstream C
5. Workstream E

This order is intentional:

- ambiguity is the smallest forcing function
- verification discipline must harden early
- closure and KLM should not be built on soft provenance
- compilation/tolerance should not be upstreamed by accident

## First Three Concrete Commits

1. Add `defeasible/ambiguity/antoniou_basic_ambiguity.yaml` with one verified two-policy case.
2. Add one more ambiguity case or expand the first file to 2-3 cases after confirmation.
3. Add `defeasible/closure/morris_core_examples.yaml` with one closure-distinguishing case.

Each commit should change exactly one semantic surface and carry its verification notes in the YAML
metadata or accompanying docs.
