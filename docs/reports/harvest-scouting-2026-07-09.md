# Harvest Scouting: clingo/Potassco and XSB Prolog (2026-07-09)

Scouting report for the next two candidate upstream sources of portable
stratified-Datalog test programs with stored expected outputs. Findings were
gathered by fetching the actual upstream files, and the XSB verdict was then
proven out by a real first-slice harvest (see the end of this report).

## Source (a): clingo / Potassco — NOT harvestable as-is

- Repo: `https://github.com/potassco/clingo` (license: MIT, `LICENSE.md` at
  the repo root, confirmed via the GitHub license API).
- Layout: there is no top-level `tests/` directory. Test assets live in
  `libgringo/tests/{ground,input,output}` and `libclingo/tests/`, which are
  C++ sources; expected results are embedded in `EXPECT_EQ` assertions as
  answer sets, not stored as machine-readable files next to the programs.
- `examples/clingo/*` and `examples/gringo/*` are ASP encodings. Files read
  verbatim during scouting:
  - `examples/gringo/sort/encoding.lp` — `@`-external functions
    (`gather(@gather(X)) :- p(X).`).
  - `examples/clingo/consequences/example.lp` — choice rule with cardinality
    (`{ holds(X) : atom(X) } 3.`).
  - `examples/clingo/well-founded/example.lp` — `#external`, non-stratified
    `x :- not x.`, no stored oracle.
  - `examples/gringo/toh/tohE.lp` — `#include <incmode>`, `#program step(t)`,
    choice rules, integrity constraints.
- Obstacles: pervasive ASP constructs (choice rules, aggregates,
  `#program`/`#external`/`#show`, `@`-functions, integrity constraints,
  non-stratified negation) and, decisively, no stored expected outputs for
  the examples. Harvesting would mean manufacturing oracles by running
  clingo, which this suite already does directly through its integrated
  `ClingoOracle` — there is nothing upstream to harvest.
- Estimated mechanically-translatable yield with stored oracle: ~0.
- Verdict: skip. clingo remains valuable as one of the four verification
  engines, not as a corpus source.

## Source (b): XSB Prolog tabling test suite — harvestable, first slice done

- Canonical source: SourceForge SVN repository `xsb/src`, directory
  `trunk/xsbtests/`. Raw files fetch cleanly via
  `https://sourceforge.net/p/xsb/src/HEAD/tree/trunk/xsbtests/<dir>/<file>?format=raw`.
  The GitHub mirror `flavioc/XSB` does not carry the main testsuite.
- License: LGPL v2 (GNU Library General Public License), `trunk/XSB/LICENSE`,
  Copyright The Research Foundation of SUNY / ECRC. No separate test-data
  license; provenance is recorded in `docs/HARVESTING.md`.
- Test mechanism: each test is a `<name>.P` program plus a `<name>_old`
  expected-stdout file diffed by `gentest.sh`.

### `wfs_tests/` (66 `pNN.P` programs) — the gold directory

Every program opens with a self-describing oracle fact:

```
query(Name, Query, AllAtoms, TrueAtoms, UndefinedAtoms).
```

for example `query(p06,p,[p,q,r],[p,q],[]).` over the program
`p :- q, tnot(r).  q.  r :- fail.` The fifth list splits the directory
mechanically: `UndefinedAtoms == []` means a two-valued well-founded model
(candidate for all four engines), anything else is a genuinely three-valued
WFS case (usable later via `expect_per_policy` for WFS-capable engines, but
not for a stratified-Datalog agreement slice).

Measured yield from the actual first-slice harvest (`scripts/harvest_xsb.py`
over all 66 programs):

- 12 kept: two-valued, statically stratified, plain surface, and the stored
  oracle reproduces exactly (p06, p07, p08, p18, p36, p60, p79, p80, p81,
  p82, p83, p85).
- ~26 skipped as three-valued (undefined atoms present).
- ~17 skipped as dynamically/modularly stratified (recursion through
  negation; XSB answers them via WFS, but Souffle-style stratified engines
  cannot).
- 2 skipped for floundering-style safety (variable only under negation).
- 1 skipped for nested-term arguments (`s(0)` inside an atom argument).
- 3 skipped because their `query/5` oracle lists only query-relevant atoms
  rather than full predicate extensions (p19, p37, p42) — the suite asserts
  exact extensions, so those oracles cannot be used mechanically. The local
  reference-evaluator cross-check caught these; without it they would have
  become wrong cases.

Translation obstacles and the policies adopted (all recorded in
`docs/HARVESTING.md` and in the harvester docstring): `tnot` -> `not`,
`:- table` dropped, `fail`-rules dropped, zero-arity atoms lifted to unary
over a marker constant (Souffle has no nullary relations), and an
always-true positive guard prepended to purely-negative rule bodies (Nemo
rejects rules without positive body literals).

### `neg_tests/` (~26 programs) — next candidate slice

Classic stratified-negation programs (`neg1.P`: `p :- tnot(q). q.`;
`ullman1.P`, `lmod*.P`, `ldynstrat*.P`). No `query/5` fact; the oracle is
the `_old` stdout transcript (`p is: true (OK)` lines), which needs its own
small parser. Upstream's own `test.sh` categorizes them: only the plainly
stratified ones (roughly `neg1-3`, `ullman1`, `mod1-2`) fit the four-engine
slice; the modularly/dynamically stratified rest belongs with the future WFS
slice. Estimated additional yield: ~6-10 four-engine cases, ~15 WFS cases.

### Other `xsbtests/` directories

`table_tests/` is mostly engine-internal (abolish/GC/trie) or full Prolog
(assert/retract, HiLog); low semantic yield. `basic_tests/`, `sem_tests/`,
`delay_tests/`, `sub_table_tests/` were not deep-dived and are not needed
for the first slices.

## First slice shipped with this report

`src/datalog_conformance/_tests/negation/xsb_wfs_two_valued.yaml` — 12 cases
harvested by `scripts/harvest_xsb.py`, every case verified by all four
engines (`verified_by_4: 12`, zero errors/mismatches) via:

```
uv run --extra oracles scripts/verify_core_multi_oracle.py --case-filter xsb_wfs
```

## Recommended next steps

1. Parse `neg_tests/` `_old` transcripts for the ~6-10 additional stratified
   cases.
2. Design the WFS/three-valued slice: the ~26 undefined-atom `wfs_tests`
   programs are a coherent future corpus for engines with well-founded
   semantics (SWI tabling, XSB itself), but they need a policy story
   (`expect_per_policy`) rather than the core `expect` shape.
3. Do not revisit clingo/Potassco for harvesting; use it only as an engine.
