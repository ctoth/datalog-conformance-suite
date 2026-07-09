from __future__ import annotations

from pathlib import Path

from datalog_conformance.corpus_audit import (
    audit_policy_closure_verification,
    audit_program_surface,
    format_findings,
)


def test_audit_program_surface_flags_invisible_expected_predicates(tmp_path: Path) -> None:
    yaml_path = tmp_path / "bad.yaml"
    yaml_path.write_text(
        "\n".join(
            [
                "name: invisible_expectation",
                "description: Expectation cannot be derived from visible YAML.",
                "source: manual/test",
                "tags: [basic]",
                "program:",
                "  facts:",
                "    edge: [[a, b]]",
                "  rules:",
                "    - \"path(X, Y) :- edge(X, Y).\"",
                "expect:",
                "  query: [[a, b]]",
            ]
        ),
        encoding="utf-8",
    )

    findings = audit_program_surface(tmp_path)

    assert len(findings) == 1
    assert findings[0].code == "missing_visible_derivation"


def test_audit_program_surface_flags_facts_only_surplus_rows(tmp_path: Path) -> None:
    yaml_path = tmp_path / "bad.yaml"
    yaml_path.write_text(
        "\n".join(
            [
                "name: facts_only_surplus",
                "description: Facts-only case expects rows that are not input facts.",
                "source: manual/test",
                "tags: [basic]",
                "program:",
                "  facts:",
                "    edge: [[a, b]]",
                "  rules: []",
                "expect:",
                "  edge: [[a, b], [b, c]]",
            ]
        ),
        encoding="utf-8",
    )

    findings = audit_program_surface(tmp_path)

    assert len(findings) == 1
    assert findings[0].code == "facts_only_mismatch"


def test_bundled_program_cases_have_visible_derivations() -> None:
    findings = audit_program_surface()
    assert not findings, format_findings(findings, root=Path.cwd())


def test_policy_closure_audit_flags_missing_verification_path(tmp_path: Path) -> None:
    yaml_path = tmp_path / "unverified_closure.yaml"
    yaml_path.write_text(
        "\n".join(
            [
                "name: unverified_closure",
                "description: Closure case without an oracle path.",
                "source: manual/test",
                "tags: [defeasible, closure]",
                "theory:",
                "  facts: {s: [[]]}",
                "  strict_rules: []",
                "  defeasible_rules:",
                "    - {id: d1, head: m, body: [s]}",
                "  defeaters: []",
                "  superiority: []",
                "expect_per_policy:",
                "  rational_closure:",
                "    defeasibly: {m: [[]]}",
            ]
        ),
        encoding="utf-8",
    )

    findings = audit_policy_closure_verification(tmp_path)

    assert len(findings) == 1
    assert findings[0].path == yaml_path
    assert findings[0].code == "missing_verification_path"


def test_policy_closure_audit_flags_reduced_without_paper_image_citation(
    tmp_path: Path,
) -> None:
    yaml_path = tmp_path / "uncited_reduced_closure.yaml"
    yaml_path.write_text(
        "\n".join(
            [
                "name: uncited_reduced_closure",
                "description: Reduced closure case without page-image citation.",
                "source: manual/test",
                "tags: [defeasible, closure]",
                "verification:",
                "  implementation: local_reference",
                "  kind: reduced",
                "theory:",
                "  facts: {s: [[]]}",
                "  strict_rules: []",
                "  defeasible_rules:",
                "    - {id: d1, head: m, body: [s]}",
                "  defeaters: []",
                "  superiority: []",
                "expect_per_policy:",
                "  rational_closure:",
                "    defeasibly: {m: [[]]}",
            ]
        ),
        encoding="utf-8",
    )

    findings = audit_policy_closure_verification(tmp_path)

    assert len(findings) == 1
    assert findings[0].path == yaml_path
    assert findings[0].code == "missing_paper_image_citation"


def test_policy_closure_audit_accepts_direct_verification_path(tmp_path: Path) -> None:
    yaml_path = tmp_path / "direct_closure.yaml"
    yaml_path.write_text(
        "\n".join(
            [
                "name: direct_closure",
                "description: Closure case confirmed by a runnable implementation.",
                "source: implementation/local",
                "tags: [defeasible, closure]",
                "verification:",
                "  implementation: local_runnable_closure",
                "  kind: direct",
                "theory:",
                "  facts: {s: [[]]}",
                "  strict_rules: []",
                "  defeasible_rules:",
                "    - {id: d1, head: m, body: [s]}",
                "  defeaters: []",
                "  superiority: []",
                "expect_per_policy:",
                "  rational_closure:",
                "    defeasibly: {m: [[]]}",
            ]
        ),
        encoding="utf-8",
    )

    findings = audit_policy_closure_verification(tmp_path)

    assert not findings, format_findings(findings, root=tmp_path)


def test_bundled_policy_closure_and_klm_cases_have_verification_paths() -> None:
    findings = audit_policy_closure_verification()
    assert not findings, format_findings(findings, root=Path.cwd())
