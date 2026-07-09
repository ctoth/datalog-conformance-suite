from __future__ import annotations

from collections import Counter
from pathlib import Path

from datalog_conformance.plugin import discover_yaml_tests
from datalog_conformance.schema import VerificationKind

GENERATED_PATH = (
    Path(__file__).parents[1]
    / "src"
    / "datalog_conformance"
    / "_tests"
    / "generated"
    / "positive_nemo_1000.yaml"
)


def test_generated_positive_nemo_corpus_has_1000_direct_oracles() -> None:
    cases = [
        case
        for yaml_path, case in discover_yaml_tests(GENERATED_PATH.parent)
        if yaml_path == GENERATED_PATH
    ]

    assert len(cases) == 1000
    assert len({case.name for case in cases}) == 1000
    for case in cases:
        assert case.verification is not None
        assert case.verification.implementation == "nmo"
        assert case.verification.kind is VerificationKind.DIRECT
        assert case.program is not None
        assert case.expect is not None
        assert "oracle-tabular" in case.tags


def test_generated_positive_nemo_corpus_covers_multiple_oracle_shapes() -> None:
    cases = [
        case
        for yaml_path, case in discover_yaml_tests(GENERATED_PATH.parent)
        if yaml_path == GENERATED_PATH
    ]
    tag_counts: Counter[str] = Counter(
        tag for case in cases for tag in case.tags if tag.startswith("oracle-")
    )

    assert tag_counts["oracle-projection"] == 300
    assert tag_counts["oracle-join"] == 300
    assert tag_counts["oracle-recursion"] == 250
    assert tag_counts["oracle-self-join"] == 100
    assert tag_counts["oracle-union"] == 50
