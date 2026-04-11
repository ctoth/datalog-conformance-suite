# Issue: harvested Souffle core cases drop required semantics

## Summary

Some harvested Souffle core YAML cases in `src/datalog_conformance/_tests/basic/`
cannot be satisfied from the protocol-visible `program` payload that the runner
passes to evaluators.

This is not a generic evaluator limitation. In at least some cases, required
facts/rules/builtins were dropped during harvesting, while the expected output
still reflects the upstream Souffle testcase.

The same breakage is propagated into the derived strict-only defeasible fixtures.

## Why this is a suite bug

`YamlTestRunner` evaluates core cases by calling:

```python
evaluate(case.program)
```

See:

- `src/datalog_conformance/runner.py`

That means an evaluator only receives:

- `program.facts`
- `program.rules`

It does not receive the `source` string as executable semantics, and it cannot
look up upstream Souffle files through the protocol.

So if the YAML omits facts/rules/builtin semantics that are necessary to produce
`expect`, the case is unsatisfiable by construction.

## Confirmed examples

### 1. `souffle_evaluation_plus.yaml`

File:

- `src/datalog_conformance/_tests/basic/souffle_evaluation_plus.yaml`

The YAML provides:

```yaml
facts:
  R:
    - [2, 3]
    - [3, 5]
rules:
  - A(a, b, a+b) :- R(a,b).
```

But it expects:

```yaml
A:
  - [1, 2, 3]
  - [2, 3, 5]
  - [3, 5, 8]
```

The row `A(1,2,3)` is impossible from the YAML because `R(1,2)` is missing.

Upstream Souffle source does include that fact:

- <https://raw.githubusercontent.com/souffle-lang/souffle/master/tests/evaluation/plus/plus.dl>

## 2. files with `rules: []` but derived expected predicates

Examples:

- `src/datalog_conformance/_tests/basic/souffle_evaluation_aliases.yaml`
- `src/datalog_conformance/_tests/basic/souffle_evaluation_contains.yaml`
- `src/datalog_conformance/_tests/basic/souffle_evaluation_aggregates2.yaml`

These files have `rules: []` yet expect derived predicates such as:

- `p`
- `r`
- `outputData`
- `C1`
- `C2`
- `C3`
- `C4`

Those predicates are not present in the input facts, so they are impossible to
derive from the protocol-visible program alone.

This strongly suggests the harvest step dropped:

- required rules
- required builtin operators/functions
- or both

## 3. `souffle_evaluation_count_sccs1.yaml`

File:

- `src/datalog_conformance/_tests/basic/souffle_evaluation_count_sccs1.yaml`

The YAML keeps only:

- one recursive `reaches` rule
- one `mutually_reaching(A,A) :- nodes(A).` rule

But the upstream Souffle testcase also contains:

- `nodes(A) :- links(A,_) ; links(_,A).`
- a base `reaches(A, B) :- links(A, B).`
- `mutually_reaching(A, B) :- reaches(A, B), reaches(B, A).`
- `chain`
- `leader`
- an aggregate rule for `count_scc`

Upstream source:

- <https://raw.githubusercontent.com/souffle-lang/souffle/master/tests/evaluation/count_sccs1/count_sccs1.dl>

Given the current YAML, `count_scc` is not derivable.

## Reproduction

Example command:

```powershell
uv run pytest tests/test_conformance.py --datalog-evaluator=gunray.adapter.GunrayEvaluator --datalog-tags=basic
```

A large number of basic failures appear, but the cases above are already enough
to show that at least some fixtures are invalid independent of evaluator
correctness.

## Likely cause

The Souffle harvester intentionally filters out many non-portable features:

- `contains(`
- `match(`
- `substr(`
- `cat(`
- `count`
- `sum`
- `min`
- `max`
- comparison/arithmetic operators

See:

- `scripts/harvest_souffle.py`

That filtering makes sense for portability, but some generated YAML files appear
to keep the upstream expected output even after the rules/facts/builtins needed
to produce that output were removed.

## Current safeguard

The harvester now refuses to emit a testcase when:

- an exported relation has no retained derivation after filtering
- a retained rule still references a dropped relation
- a rule contains arithmetic-style expressions such as `a+b` without spaces

That narrows the failure mode to skipping unsafe cases instead of emitting YAML
whose `expect` payload cannot be justified by the portable `program`.

## Suggested fix

For each affected harvested testcase:

1. Re-harvest it and compare the emitted YAML against the upstream `.dl` and
   input/output files.
2. If required semantics were dropped, do one of:
   - drop the testcase from the portable corpus
   - rewrite it into a genuinely portable reduced testcase
   - extend the protocol/schema so the missing semantics are explicit
3. Re-generate the corresponding derived strict-only defeasible fixture if it
   came from the broken core case.

## Minimum known affected files

- `src/datalog_conformance/_tests/basic/souffle_evaluation_plus.yaml`
- `src/datalog_conformance/_tests/basic/souffle_evaluation_aliases.yaml`
- `src/datalog_conformance/_tests/basic/souffle_evaluation_contains.yaml`
- `src/datalog_conformance/_tests/basic/souffle_evaluation_aggregates2.yaml`
- `src/datalog_conformance/_tests/basic/souffle_evaluation_count_sccs1.yaml`

And corresponding derived strict-only files under:

- `src/datalog_conformance/_tests/defeasible/strict_only/`
