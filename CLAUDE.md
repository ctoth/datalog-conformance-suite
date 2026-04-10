# CLAUDE.md

Repo-specific instructions for AI assistants working in `datalog-conformance`.

## Working Style

- Work directly against the current repository state.
- Use `uv run ...` for Python entrypoints and tests.
- Use `uv` rather than `pip` for dependency changes.
- Keep YAML suites implementation-agnostic.
- Preserve provenance in every test case `source`.

## Conformance Semantics

- Do not fail a test because an evaluator returned extra predicates or extra sections that the YAML
  did not assert.
- Tuple ordering is irrelevant.
- Row ordering is irrelevant.
- Policy-specific expectations belong under `expect_per_policy`, not ad hoc test logic.

## Harvesting

- Record upstream source and license notes in `docs/HARVESTING.md` whenever adding a new harvested
  slice.
- Prefer multi-case YAML files when many upstream cases share one provenance block.
- For strict-only derived defeasible cases, keep the derivation path explicit in `source`.

## External Confirmation

- Prefer confirming new slices against real existing implementations where practical.
- Current concrete confirmation target in this repo: DePYsible via
  `datalog_conformance.examples.depysible_adapter`.
- See `docs/IMPLEMENTATIONS.md` for other candidate runtimes and current blockers.

## Paper-Derived Cases

- Do not use `pdftotext` as the basis for rereading scientific papers.
- If a paper-derived case claims to come from a paper page, derive it from local page images or a
  direct PDF read path that preserves formulas and symbols.
- If only notes were used, say so explicitly in provenance or documentation.

## Verification

Run these before claiming repo-wide success:

```powershell
uv run pytest tests/
uv run --extra dev ruff check .
uv run --extra dev pyright
```
