# YAML Schema

This package supports three top-level YAML shapes:

- core Datalog test cases
- defeasible theory test cases
- KLM property declarations

The loader accepts either a single test case per file or a suite file with top-level `tests:`.

## Suite Wrapper

Multi-case files may define shared `source` and `tags` at the file level:

```yaml
source: souffle/example/tc
tags: [recursion, basic]
tests:
  - name: transitive_small
    description: Small closure example.
    program: ...
    expect: ...
```

File-level `source` and `tags` are inherited by each child case unless a child overrides `source`.

## Core Datalog Case

```yaml
name: transitive_closure
description: Two-rule transitive closure.
source: manual/scaffold
tags: [recursion, basic]
verification:
  implementation: nmo
  kind: direct
skip: null
program:
  facts:
    edge: [[a, b], [b, c]]
  rules:
    - "path(X, Y) :- edge(X, Y)."
    - "path(X, Y) :- edge(X, Z), path(Z, Y)."
expect:
  path: [[a, b], [a, c], [b, c]]
```

Required fields:

- `name`: string, unique within the file
- `description`: string
- `source`: string
- `tags`: list of strings
- exactly one of `expect` or `expect_error`
- `program`: mapping with `facts` and `rules`

Optional fields:

- `verification`: mapping describing one concrete implementation confirmation
- `skip`: string or null

`verification`:

- `implementation`: string naming the runtime used for confirmation
- `kind`: either `direct` or `reduced`
- suite-wrapper files may define `verification` once and let child tests inherit it

`program.facts`:

- mapping from predicate name to list of tuples
- each tuple is a YAML list of scalar values
- scalar values may be strings, integers, floats, or booleans

`program.rules`:

- list of rule strings
- the suite treats them as evaluator-owned syntax
- the bundled corpus uses a Datalog-like `head :- body.` convention

`expect`:

- mapping from predicate name to unordered tuple rows
- only predicates listed under `expect` are asserted
- extra predicates returned by an evaluator are ignored

`expect_error`:

- string code or class-name-style label
- the runner matches either the exception class name, the exact string form, or `exc.code`

## Defeasible Case

```yaml
name: penguin_priority
description: Penguin non-flight defeats generic bird flight.
source: paper/maher-2021-example-2-p7-p8
tags: [defeasible, superiority, paper]
theory:
  facts:
    penguin: [[tweety]]
  strict_rules:
    - id: r1
      head: "bird(X)"
      body: ["penguin(X)"]
  defeasible_rules:
    - id: r2
      head: "fly(X)"
      body: ["bird(X)"]
    - id: r3
      head: "~fly(X)"
      body: ["penguin(X)"]
  defeaters: []
  superiority:
    - [r3, r2]
  conflicts:
    - [fly, "~fly"]
expect:
  definitely:
    bird: [[tweety]]
  defeasibly:
    "~fly": [[tweety]]
  not_defeasibly:
    fly: [[tweety]]
```

Required fields:

- `name`
- `description`
- `source`
- `tags`
- `theory`
- at least one of `expect`, `expect_per_policy`, or `expect_error`

`theory` fields:

- `facts`: same tuple encoding as core programs
- `strict_rules`: list of rule objects
- `defeasible_rules`: list of rule objects
- `defeaters`: list of rule objects
- `superiority`: list of two-item string pairs `[stronger_rule_id, weaker_rule_id]`
- `conflicts`: optional list of two-item string predicate pairs

Rule object shape:

```yaml
- id: r1
  head: "bird(X)"
  body: ["penguin(X)"]
```

`expect` for defeasible cases:

- mapping from section name to predicate facts
- common sections include `definitely`, `defeasibly`, `not_defeasibly`, `ambiguous`, and
  `undecided`
- section names are not hard-coded by the schema; the evaluator and test case define them

`expect_per_policy`:

```yaml
expect_per_policy:
  blocking:
    defeasibly:
      q: [[a]]
  propagating:
    ambiguous:
      q: [[a]]
```

- keys must match `blocking`, `propagating`, `rational_closure`, `lexicographic_closure`, or
  `relevant_closure`
- each policy maps to the same section shape used by `expect`

## KLM Property Case

```yaml
name: relevant_closure_counterexample
description: A theory that fails a KLM property under relevant closure.
source: paper/morris-2020-example
tags: [klm, rm, paper]
klm_property: RM
theories:
  - theory:
      facts: {}
      strict_rules: []
      defeasible_rules: []
      defeaters: []
      superiority: []
      conflicts: []
    satisfies:
      rational_closure: true
      lexicographic_closure: true
      relevant_closure: false
```

Required fields:

- `name`
- `description`
- `source`
- `tags`
- `klm_property`
- `theories`

`klm_property`:

- free string at the schema layer
- the bundled conventions use `Reflexivity`, `LLE`, `RW`, `And`, `Or`, `CM`, and `RM`

`theories`:

- list of entries
- each entry contains a `theory` and a `satisfies` mapping
- `satisfies` maps policy names to booleans

## Validation Rules

- exactly one of `program`, `theory`, or `klm_property`/`theories` must be present
- program cases cannot use `expect_per_policy`
- theory cases must supply `expect`, `expect_per_policy`, or `expect_error`
- KLM cases cannot also define `program`, `theory`, `expect`, or `expect_error`

## Comparison Semantics

- tuple order is ignored
- row order is ignored
- model predicates not mentioned by the test are ignored
- missing expected sections or predicates fail the test

## Practical Notes

- Single-case files are useful for hand-authored tests.
- Multi-case files are better for harvested corpora with shared provenance.
- Use `source` strings that preserve the upstream location and enough detail to audit the
  translation later.
