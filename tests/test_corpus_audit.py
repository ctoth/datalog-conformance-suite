from __future__ import annotations

from pathlib import Path

from datalog_conformance.corpus_audit import audit_program_surface, format_findings


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
