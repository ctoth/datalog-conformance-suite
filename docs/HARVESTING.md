# Harvesting

This file records where the bundled YAML suites came from, what translation choices were made, and
 what is still blocked or intentionally deferred.

## Current Corpus Summary

- Core Datalog YAML cases currently in `basic/`, `recursion/`, `negation/`, and `errors/`: 111
- Defeasible YAML cases currently in `defeasible/`: 180
- KLM property YAML cases currently in the bundled corpus: 1
- Generated property tests and implementation checks remain under `tests/`

The current defeasible corpus is still dominated by strict-only derived lifts from the core corpus,
plus a smaller set of genuinely defeasible examples.

Some recent defeasible additions are note-adapted paper examples that were only kept when the
notes were concrete enough to encode a supported fragment and the resulting theories reproduced
against a live implementation.

## Runner-Surface Audit

- Command: `uv run scripts/audit_program_surface.py`
- Purpose: fail when a retained program case expects rows that are not justified by the
  runner-visible `program` surface.
- Current enforced classes:
  - non-empty expected predicates absent from both visible facts and visible rule heads
  - facts-only program cases whose expected rows are not already present in the input facts
- Current cleanup applied:
  - 73 invalid core program cases were removed from the bundled YAML corpus
  - 73 corresponding strict-only derived defeasible cases were removed in lockstep

## Actual Runtime Verification

- Command: `uv run scripts/verify_core_with_nemo.py`
- Runtime used for the retained core corpus: `nmo`
- Report layout: one timestamped directory per run under `reports/verify_core_with_nemo/`
- Execution mode: batch cases by shared visible program and prefer a release `nmo` binary when
  one is available locally
- Current cleanup applied from concrete `nmo` runs:
  - 98 additional core program cases remain removed after failing direct runtime verification
  - 98 corresponding strict-only derived defeasible cases remain removed in lockstep
  - retained core YAML files in `basic/`, `negation/`, and `recursion/` are stamped with
    `verification: {implementation: nmo, kind: direct}`

## Souffle

- Upstream: `https://github.com/souffle-lang/souffle`
- License note: UPL-1.0
- Local source path during harvesting: temporary clone under `%TEMP%\datalog-harvest`
- Harvester: `scripts/harvest_souffle.py`
- Upstream areas targeted:
  - `tests/evaluation/`
  - `tests/example/`
- Translation policy:
  - keep portable facts, recursion, joins, and negation slices
  - skip or avoid Souffle-specific extensions when they do not map cleanly into the suite schema
  - emit multi-case YAML when one upstream directory produces multiple output relations
- Output areas:
  - `src/datalog_conformance/_tests/basic/`
  - `src/datalog_conformance/_tests/recursion/`
  - `src/datalog_conformance/_tests/negation/`
- Notes:
  - the current harvest materially exceeds the Phase 2 gate
  - some harvested filenames still reflect their upstream directory names even when the underlying
    semantics are broader than the local folder label

## Nemo

- Upstream: `https://github.com/knowsys/nemo`
- License note: Apache-2.0
- Local source path during harvesting: temporary clone under `%TEMP%\datalog-harvest`
- Harvester: `scripts/harvest_nemo.py`
- Upstream area targeted:
  - `resources/testcases/`
- Translation policy:
  - prefer textbook-like joins, projection, union, and negation slices
  - emit multi-case YAML where one upstream testcase contains multiple asserted relations
- Output areas:
  - `src/datalog_conformance/_tests/basic/`
  - `src/datalog_conformance/_tests/negation/`

## Crepe

- Upstream: `https://github.com/ekzhang/crepe`
- License note: Apache-2.0
- Local source path during harvesting: temporary clone under `%TEMP%\datalog-harvest`
- Harvester: `scripts/harvest_crepe.py`
- Upstream area targeted:
  - `tests/ui/`
- Translation policy:
  - keep only obviously portable rejection cases
  - map Rust-macro UI failures into suite-level rejection categories where the semantic intent is
    still clear
- Output area:
  - `src/datalog_conformance/_tests/errors/`
- Current mapped error families:
  - `arity_mismatch`
  - `cyclic_negation`
  - `unbound_variable`
  - `safety_violations`

## Strict-Only Defeasible Lifts

- Source basis: existing core YAML corpus in
  - `src/datalog_conformance/_tests/basic/`
  - `src/datalog_conformance/_tests/recursion/`
  - `src/datalog_conformance/_tests/negation/`
- Generator: `scripts/promote_strict_only_defeasible.py`
- Output area:
  - `src/datalog_conformance/_tests/defeasible/strict_only/`
- Translation policy:
  - each core program is converted into a defeasible theory containing only `strict_rules`
  - the original `expect` mapping is copied into both `definitely` and `defeasibly`
  - this slice exists to exercise strict-only equivalence in the defeasible test surface
- Notes:
  - this is derived data, not an upstream external corpus
  - the generator uses rule-body splitting that respects commas inside argument lists

## DePYsible

- Upstream: `https://github.com/stefano-bragaglia/DePYsible`
- License note: BSD-2-Clause
- Local source path during verification: `%TEMP%\datalog-harvest\DePYsible`
- Verification status:
  - the upstream test suite passed locally with `PYTHONPATH=src/main/python`
  - a live adapter in `src/datalog_conformance/examples/depysible_adapter.py` confirmed the first
    converted cases against the real implementation
  - generated Hypothesis tests now exercise the supported fragment against the live implementation
    through `tests/test_depysible_generated.py`
  - note-adapted paper examples were checked against the same adapter before retention
- Current output area:
  - `src/datalog_conformance/_tests/defeasible/basic/depysible_birds.yaml`
  - `src/datalog_conformance/_tests/defeasible/basic/bozzato_example1_bob.yaml`
  - `src/datalog_conformance/_tests/defeasible/basic/goldszmidt_example1_nixon.yaml`
  - `src/datalog_conformance/_tests/defeasible/basic/morris_example5_birds.yaml`
- Current limitations of the example adapter:
  - no defeaters
  - no superiority
  - no explicit conflict sets
  - blocking-only policy
- Generated-testing support:
  - `src/datalog_conformance/depysible_strategies.py`
  - `tests/depysible_test_support.py`
  - `tests/test_depysible_generated.py`

## Paper-Derived Cases

- Local paper artifacts exist under `..\propstore\papers\...`
- Paper-reading rule followed here:
  - I did not use `pdftotext` as the basis for rereading any paper
  - the first retained paper-derived case was authored from local page images in `pngs/`
- Current retained paper-derived cases:
  - `src/datalog_conformance/_tests/defeasible/superiority/maher_example2_tweety.yaml`
  - source: Maher 2021 Example 2, from local page images corresponding to pp.7-8
  - `src/datalog_conformance/_tests/defeasible/superiority/maher_example3_freddie_nonflight.yaml`
  - source: Maher 2021 Example 3, from local page images corresponding to pp.8-9
  - `src/datalog_conformance/_tests/defeasible/basic/bozzato_example1_bob.yaml`
  - source: Bozzato 2020 Example 1, adapted from local `notes.md` and retained only after
    DePYsible-backed checking of the supported fragment
  - `src/datalog_conformance/_tests/defeasible/basic/goldszmidt_example1_nixon.yaml`
  - source: Goldszmidt and Pearl 1992 Example 1, adapted from local `notes.md` and retained only
    after DePYsible-backed checking of the supported fragment
  - `src/datalog_conformance/_tests/defeasible/basic/morris_example5_birds.yaml`
  - source: Morris 2020 Example 5, adapted from local `notes.md` and retained only after
    DePYsible-backed checking of the supported fragment
  - `src/datalog_conformance/_tests/defeasible/ambiguity/antoniou_basic_ambiguity.yaml`
  - source: Antoniou 2007 ambiguity-blocking and ambiguity-propagating clauses on pp.13-14, adapted
    from local `notes.md`
  - verification: reduced local paper-reference evaluator in `tests/test_ambiguity_corpus.py`
  - `src/datalog_conformance/_tests/defeasible/closure/morris_core_examples.yaml`
  - source: Morris 2020 Example 6 and Figures 3-5, from local page images corresponding to
    pp.152-157
  - verification: reduced local ranked-worlds closure evaluator in
    `tests/closure_test_support.py` and `tests/test_closure_corpus.py`
  - `src/datalog_conformance/_tests/defeasible/klm/morris_relevant_counterexamples.yaml`
  - source: Morris 2020 Appendix C.2 and Figures 6-7, from local page images corresponding to
    pp.167-168
  - verification: reduced local Or-property checker with rational, lexicographic, and minimal
    relevant closure support in `tests/closure_test_support.py` and `tests/test_klm_corpus.py`
- Additional paper sources present locally:
  - `Maher_2021_DefeasibleReasoningDatalog`
  - `Antoniou_2007_DefeasibleReasoningSemanticWeb`
  - `Morris_2020_DefeasibleDisjunctiveDatalog`
  - `Goldszmidt_1992_DefeasibleStrictConsistency`
- Current blocker on expanding this slice quickly:
  - the existing notes identify example names and page locations, but many do not preserve enough
    formal detail to author exact YAML expectations without another image-based reread

## SPINdle Family

- Family reference:
  - `https://spindle-rust.anuna.io/`
- Documentation page identifies:
  - original Java SPINdle
  - `spindle-racket` on Codeberg
  - `spindle-rust`
- Usable upstream in this environment:
  - `https://codeberg.org/anuna/spindle-racket`
- Verified locally:
  - the Codeberg `spindle-racket` repo cloned successfully and contains `.dfl` test theories,
    Racket tests, docs, and examples
- Current harvested slice:
  - `src/datalog_conformance/_tests/defeasible/basic/spindle_racket_test_theories.yaml`
  - `src/datalog_conformance/_tests/defeasible/basic/spindle_racket_inline_tests.yaml`
  - `src/datalog_conformance/_tests/defeasible/basic/spindle_racket_query_tests.yaml`
  - `src/datalog_conformance/_tests/defeasible/basic/spindle_racket_query_integration.yaml`
  - `scripts/harvest_spindle.py` currently regenerates the `src/test-theories` slice
  - the bundled SPINdle-family slice currently covers 42 cases total
- Translation policy for the current slice:
  - facts use zero-arity predicate rows such as `p: [[]]`
  - `->` maps to `strict_rules`
  - `=>` maps to `defeasible_rules`
  - `~>` maps to `defeaters`
  - `¬` is normalized to `~`
  - expectations are taken from the upstream `.dfl` comments and matching Racket assertions in
    `tests/spindle-tests.rkt`
- Remaining blocker:
  - the public `https://github.com/anuna-research/spindle-rust` repository still clones locally as
    an empty repository, so it is not currently a usable GitHub mirror from this environment
- Open expansion path:
  - extend the SPINdle harvester beyond the current simple `src/test-theories` files and into the
    broader Racket test corpus, especially ambiguity and richer superiority cases

## Manual and Scaffolded Cases

- Manual scaffold files remain in the corpus for baseline coverage and runner/plugin validation:
  - `basic/facts.yaml`
  - `basic/joins.yaml`
  - `recursion/transitive.yaml`
  - `errors/unbound_variable.yaml`
  - `defeasible/basic/mixed.yaml`

## Provenance Rules For Future Additions

- Preserve a meaningful `source` string on every case.
- Record the upstream repo or paper, plus the local translation policy.
- Note the upstream license here before adding a large harvested slice.
- If a paper-derived case is authored from notes rather than a direct image reread, say that
  explicitly instead of implying a direct reread.
