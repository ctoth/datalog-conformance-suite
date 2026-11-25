"""Verify the complete generated DeLP corpus against its paper reference."""

from __future__ import annotations

from typing import cast

import pytest

from datalog_conformance.plugin import discover_yaml_tests, get_tests_dir
from datalog_conformance.references.garcia import evaluate_corpus_theory
from datalog_conformance.schema import DefeasibleSections, DefeasibleTheory, Rule
from datalog_conformance.schema import TestCase as SuiteCase

_GENERATED_DIR = get_tests_dir() / "generated"


def _generated_defeasible_cases() -> list[SuiteCase]:
    cases = [
        case
        for yaml_path, case in discover_yaml_tests(_GENERATED_DIR)
        if yaml_path.name.startswith("defeasible_gen_")
    ]
    assert cases
    return cases


@pytest.mark.parametrize("case", _generated_defeasible_cases(), ids=lambda case: case.name)
def test_generated_defeasible_case_replays_on_garcia_reference(case: SuiteCase) -> None:
    assert case.theory is not None and case.expect is not None
    expected = {
        section: {predicate: set(rows) for predicate, rows in predicates.items()}
        for section, predicates in cast(DefeasibleSections, case.expect).items()
    }
    assert evaluate_corpus_theory(case.theory).sections == expected


def test_strict_conclusion_rules_out_contradictory_defeasible_support() -> None:
    """García & Simari (2004), Def. 3.1 and Observation 3.1, pp. 103–104."""
    theory = DefeasibleTheory(
        facts={"seed": [()]},
        strict_rules=[Rule("s", "~goal", ["seed"])],
        defeasible_rules=[Rule("d", "goal", ["seed"])],
    )
    assert evaluate_corpus_theory(theory).sections == {
        "definitely": {"seed": {()}, "~goal": {()}},
        "defeasibly": {"seed": {()}, "~goal": {()}},
        "not_defeasibly": {"goal": {()}},
    }


def test_garcia_example_35_respects_strict_activation_paths() -> None:
    """García & Simari (2004), Example 3.5, p. 108."""
    theory = DefeasibleTheory(
        facts={"chicken": [("tina",)], "scared": [("tina",)]},
        strict_rules=[Rule("s", "bird(X)", ["chicken(X)"])],
        defeasible_rules=[
            Rule("r1", "flies(X)", ["bird(X)"]),
            Rule("r2", "~flies(X)", ["chicken(X)"]),
            Rule("r3", "flies(X)", ["chicken(X)", "scared(X)"]),
        ],
    )

    model = evaluate_corpus_theory(theory)
    assert model.sections["defeasibly"]["flies"] == {("tina",)}
    assert model.sections["not_defeasibly"]["~flies"] == {("tina",)}
