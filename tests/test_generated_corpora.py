"""Meta-tests for the generated family and feature-matrix corpora.

These pin the corpus composition so regressions in the generators (or an
accidental partial regeneration) show up as count mismatches, and enforce
the external-verification stamp on every generated case.
"""

from __future__ import annotations

import json
from collections import Counter

from datalog_conformance.plugin import discover_yaml_tests, get_tests_dir
from datalog_conformance.schema import VerificationKind

_GENERATED_DIR = get_tests_dir() / "generated"


def _generated_cases(prefix: str):
    return [
        case
        for yaml_path, case in discover_yaml_tests(_GENERATED_DIR)
        if yaml_path.name.startswith(prefix)
    ]


def test_family_corpus_composition() -> None:
    cases = _generated_cases("family_")
    assert len(cases) == 549
    assert len({case.name for case in cases}) == 549
    families = Counter(
        tag for case in cases for tag in case.tags if tag.startswith("family-")
    )
    assert set(families) == {
        "family-altpath",
        "family-chain",
        "family-complete",
        "family-cutchain",
        "family-cycle",
        "family-diff",
        "family-grid",
        "family-parity",
        "family-plus",
        "family-star",
        "family-tree",
    }
    for case in cases:
        assert case.verification is not None
        assert case.verification.kind is VerificationKind.DIRECT
        assert case.verification.implementation == "nmo+souffle+clingo+swipl"
        assert case.program is not None
        assert case.expect is not None


def test_feature_corpus_composition() -> None:
    cases = _generated_cases("feature_")
    assert len(cases) == 10944
    assert len({case.name for case in cases}) == 10944

    unique_programs = {
        json.dumps(
            {"facts": case.program.facts, "rules": case.program.rules},
            sort_keys=True,
        )
        for case in cases
        if case.program is not None
    }
    assert len(unique_programs) == 1152

    recursion_tags = Counter(
        tag for case in cases for tag in case.tags if tag.startswith("rec-")
    )
    assert set(recursion_tags) == {"rec-none", "rec-linear", "rec-nonlinear", "rec-mutual"}
    negation_tags = {
        tag for case in cases for tag in case.tags if tag.startswith("neg-")
    }
    assert negation_tags == {"neg-0", "neg-1", "neg-2"}

    for case in cases:
        assert case.verification is not None
        assert case.verification.kind is VerificationKind.DIRECT
        assert case.verification.implementation == "nmo+souffle+clingo+swipl"


def test_defeasible_generated_corpus_composition() -> None:
    cases = _generated_cases("defeasible_gen_")
    assert len(cases) == 701
    assert len({case.name for case in cases}) == 701

    shapes = Counter(
        tag for case in cases for tag in case.tags if tag.startswith("shape-")
    )
    assert set(shapes) == {
        "shape-ambiguity",
        "shape-chain",
        "shape-mixed",
        "shape-strict_override",
        "shape-team",
    }
    assert shapes["shape-ambiguity"] == 27
    assert shapes["shape-chain"] == 60
    assert shapes["shape-mixed"] == 558
    assert shapes["shape-strict_override"] == 9
    assert shapes["shape-team"] == 47

    for case in cases:
        assert case.verification is not None
        assert case.verification.kind is VerificationKind.DIRECT
        assert case.verification.implementation == "depysible"
        assert case.theory is not None
        assert case.expect is not None
        assert "defeasible" in case.tags
        assert "generated" in case.tags
        # The generator only emits the fragment the DePYsible adapter accepts.
        assert not case.theory.defeaters
        assert not case.theory.superiority
        assert not case.theory.conflicts


def test_total_corpus_crosses_ten_thousand() -> None:
    total = len(discover_yaml_tests())
    assert total >= 10000, f"corpus has shrunk to {total} cases"
