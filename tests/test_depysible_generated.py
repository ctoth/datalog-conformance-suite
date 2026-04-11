from __future__ import annotations

import pytest

from hypothesis import given, settings

from tests.depysible_test_support import (
    depysible_runtime_available,
    depysible_source_available,
    evaluate_supported_theory_locally,
    run_depysible_adapter,
)

if not depysible_source_available():
    pytest.skip(
        "DePYsible checkout not found under the expected temp directory",
        allow_module_level=True,
    )

if not depysible_runtime_available():
    pytest.skip(
        "DePYsible dependencies are unavailable in the local checkout",
        allow_module_level=True,
    )

from datalog_conformance.depysible_strategies import (
    GeneratedDePYsibleTheory,
    depysible_theories,
)
from datalog_conformance.schema import DefeasibleTheory, Rule

_GEN_SETTINGS = settings(deadline=None, max_examples=80)


@given(depysible_theories())
@_GEN_SETTINGS
def test_depysible_supported_fragment_matches_local_reference(
    generated: GeneratedDePYsibleTheory,
) -> None:
    actual = run_depysible_adapter(generated.theory).sections
    reference = evaluate_supported_theory_locally(generated.theory).sections
    assert actual == reference


@given(depysible_theories())
@_GEN_SETTINGS
def test_depysible_is_invariant_under_rule_reordering(
    generated: GeneratedDePYsibleTheory,
) -> None:
    baseline = run_depysible_adapter(generated.theory).sections
    reordered = _with_reordered_rules(generated.theory)
    actual = run_depysible_adapter(reordered).sections
    assert actual == baseline


@given(depysible_theories())
@_GEN_SETTINGS
def test_depysible_is_invariant_under_fact_reordering(
    generated: GeneratedDePYsibleTheory,
) -> None:
    baseline = run_depysible_adapter(generated.theory).sections
    reordered = _with_reordered_facts(generated.theory)
    actual = run_depysible_adapter(reordered).sections
    assert actual == baseline


def _with_reordered_rules(theory: DefeasibleTheory) -> DefeasibleTheory:
    return DefeasibleTheory(
        facts={predicate: [tuple(row) for row in rows] for predicate, rows in theory.facts.items()},
        strict_rules=[_copy_rule(rule) for rule in reversed(theory.strict_rules)],
        defeasible_rules=[_copy_rule(rule) for rule in reversed(theory.defeasible_rules)],
        defeaters=[],
        superiority=[],
        conflicts=[],
    )


def _with_reordered_facts(theory: DefeasibleTheory) -> DefeasibleTheory:
    reordered_facts = {
        predicate: [tuple(row) for row in reversed(rows)]
        for predicate, rows in reversed(list(theory.facts.items()))
    }
    return DefeasibleTheory(
        facts=reordered_facts,
        strict_rules=[_copy_rule(rule) for rule in theory.strict_rules],
        defeasible_rules=[_copy_rule(rule) for rule in theory.defeasible_rules],
        defeaters=[],
        superiority=[],
        conflicts=[],
    )


def _copy_rule(rule: Rule) -> Rule:
    return Rule(id=rule.id, head=rule.head, body=list(rule.body))
