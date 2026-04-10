from __future__ import annotations

from pathlib import Path

from datalog_conformance.plugin import discover_yaml_tests


def test_discover_yaml_tests_loads_valid_cases(tmp_path: Path) -> None:
    yaml_path = tmp_path / "joins.yaml"
    yaml_path.write_text(
        "\n".join(
            [
                "name: joins",
                "description: Join test",
                "source: manual/test",
                "tags: [basic, joins]",
                "program:",
                "  facts:",
                "    edge: [[a, b], [b, c]]",
                "  rules:",
                "    - \"path(X, Y) :- edge(X, Y).\"",
                "expect:",
                "  path: [[a, b], [b, c]]",
            ]
        ),
        encoding="utf-8",
    )

    discovered = discover_yaml_tests(tmp_path)

    assert len(discovered) == 1
    path, case = discovered[0]
    assert path == yaml_path
    assert case.name == "joins"
    assert case.tags == ["basic", "joins"]


def test_discover_yaml_tests_supports_multi_case_files(tmp_path: Path) -> None:
    yaml_path = tmp_path / "suite.yaml"
    yaml_path.write_text(
        "\n".join(
            [
                "source: manual/suite",
                "tags: [basic]",
                "tests:",
                "  - name: facts",
                "    description: Facts only",
                "    tags: [facts]",
                "    program:",
                "      facts:",
                "        edge: [[a, b]]",
                "      rules: []",
                "    expect:",
                "      edge: [[a, b]]",
                "  - name: bad_rule",
                "    description: Rejected rule",
                "    tags: [errors]",
                "    program:",
                "      facts: {}",
                "      rules:",
                "        - \"p(X) :- q(Y).\"",
                "    expect_error: unbound_variable",
            ]
        ),
        encoding="utf-8",
    )

    discovered = discover_yaml_tests(tmp_path)

    assert [case.name for _, case in discovered] == ["facts", "bad_rule"]
    assert all(case.source == "manual/suite" for _, case in discovered)
