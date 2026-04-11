# Compilation And Tolerance Boundary

This document resolves what belongs in the shared conformance suite versus evaluator-local tests.

## Decision

### Maher-Style Compilation

- No public suite compile protocol will be added at this stage.
- The suite will not assert exact compiled-program shape, intermediate predicates, or compiler
  staging artifacts.
- If an evaluator uses compilation internally, the shared suite should test only the externally
  visible semantic result through the existing evaluator contract.

### Tolerance

- No public suite tolerance protocol will be added at this stage.
- The suite will not expose internal tolerance checks, minimal exceptional subsets, caches, or
  intermediate rankings as first-class shared outputs.
- If an evaluator uses tolerance internally, the shared suite should test only the externally
  visible semantic consequences that depend on that tolerance step.

## What The Suite Should Test Instead

- direct defeasible outputs under the public evaluator contract
- policy-sensitive outputs for blocking, propagating, rational closure, lexicographic closure, and
  relevant closure where those are externally observable
- KLM property satisfaction through `satisfies_klm_property(...)`

## Rule For Future Expansion

- Add a new shared protocol only if there is an external consumer that needs the intermediate
  artifact itself rather than the final semantic result.
- Without that external requirement, update every evaluator against the semantic surface and keep
  compilation and tolerance internals local.
