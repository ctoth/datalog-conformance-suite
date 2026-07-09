"""Tests for the shared rule parser and the internal test-support evaluator.

The parser in ``datalog_conformance.references.core`` is load-bearing: the
Souffle and clingo oracle adapters translate through its AST, so its
conventions (bare identifiers are variables, constants are quoted or
numeric, ``not`` negation, ``_`` wildcards, comparison guards, head
arithmetic) are contract-tested here.

The bundled evaluator is deliberately NOT used as a verification oracle —
external engines are (see ``scripts/verify_core_multi_oracle.py``). It backs
generation and quick sanity checks only, and the corpus ``errors/`` cases
double as its rejection-surface contract.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from datalog_conformance.plugin import discover_yaml_tests, get_tests_dir
from datalog_conformance.references import (
    CoreReferenceEvaluator,
    CyclicNegationError,
    SafetyViolationError,
    UnboundVariableError,
)
from datalog_conformance.references.core import (
    Arithmetic,
    Constant,
    Variable,
    Wildcard,
    parse_rules,
)
from datalog_conformance.runner import YamlTestRunner
from datalog_conformance.schema import Model, Program, TestCase


def _error_cases() -> list[tuple[str, Path, TestCase]]:
    cases: list[tuple[str, Path, TestCase]] = []
    for yaml_path, case in discover_yaml_tests(get_tests_dir() / "errors"):
        if case.program is None or case.expect_error is None:
            continue
        cases.append((f"{yaml_path.stem}::{case.name}", yaml_path, case))
    return cases


_ERROR_CASES = _error_cases()


@pytest.mark.parametrize(
    "case",
    [case for _, _, case in _ERROR_CASES],
    ids=[case_id for case_id, _, _ in _ERROR_CASES],
)
def test_evaluator_rejection_surface_matches_errors_corpus(case: TestCase) -> None:
    runner = YamlTestRunner(CoreReferenceEvaluator())
    runner.run_test_case(case)


def test_parser_reads_variables_constants_and_wildcards() -> None:
    (rule,) = parse_rules(['q(X, "lit", 3) :- p(X, _), r(X).'])
    assert rule.head.predicate == "q"
    assert rule.head.terms[0] == Variable(name="X")
    assert rule.head.terms[1] == Constant(value="lit")
    assert rule.head.terms[2] == Constant(value=3)
    first, second = rule.positive
    assert first.predicate == "p"
    assert isinstance(first.terms[1], Wildcard)
    assert second.predicate == "r"


def test_parser_treats_lowercase_identifiers_as_variables() -> None:
    (rule,) = parse_rules(["A(a, b, a+b) :- R(a,b)."])
    assert rule.head.terms[0] == Variable(name="a")
    arithmetic = rule.head.terms[2]
    assert isinstance(arithmetic, Arithmetic)
    assert arithmetic.op == "+"


def test_parser_splits_negation_and_comparison_guards() -> None:
    (rule,) = parse_rules(["ok(X) :- n(X), not banned(X), (X <= 3)."])
    assert [atom.predicate for atom in rule.positive] == ["n"]
    assert [atom.predicate for atom in rule.negative] == ["banned"]
    (guard,) = rule.comparisons
    assert guard.op == "<="


def test_parser_expands_disjunctive_bodies() -> None:
    rules = parse_rules(["q(X) :- a(X); b(X)."])
    assert len(rules) == 2
    assert {rule.positive[0].predicate for rule in rules} == {"a", "b"}


def test_parser_keeps_arithmetic_left_associative() -> None:
    (rule,) = parse_rules(["q(a - b - c) :- p(a, b, c)."])
    outer = rule.head.terms[0]
    assert isinstance(outer, Arithmetic)
    assert outer.op == "-"
    assert isinstance(outer.left, Arithmetic)
    assert outer.right == Variable(name="c")


def test_evaluator_rejects_unbound_head_variable() -> None:
    program = Program(facts={"q": [("a",)]}, rules=["p(X) :- q(Y)."])
    with pytest.raises(UnboundVariableError):
        CoreReferenceEvaluator().evaluate(program)


def test_evaluator_rejects_unsafe_negation() -> None:
    program = Program(
        facts={"person": [("alice",)]},
        rules=["ok(X) :- person(X), not banned(X, Y)."],
    )
    with pytest.raises(SafetyViolationError):
        CoreReferenceEvaluator().evaluate(program)


def test_evaluator_rejects_cyclic_negation() -> None:
    program = Program(
        facts={"move": [("a", "b")]},
        rules=["win(X) :- move(X, Y), not win(Y)."],
    )
    with pytest.raises(CyclicNegationError):
        CoreReferenceEvaluator().evaluate(program)


def test_evaluator_supports_stratified_negation() -> None:
    program = Program(
        facts={"node": [("a",), ("b",), ("c",)], "edge": [("a", "b")]},
        rules=[
            "isolated(X) :- node(X), not touched(X).",
            "touched(X) :- edge(X, _).",
            "touched(Y) :- edge(_, Y).",
        ],
    )
    model = CoreReferenceEvaluator().evaluate(program)
    assert model.facts["isolated"] == {("c",)}


def test_evaluator_supports_head_arithmetic() -> None:
    program = Program(
        facts={"R": [(1, 2), (3, 5)]},
        rules=["A(a, b, a+b) :- R(a,b)."],
    )
    model = CoreReferenceEvaluator().evaluate(program)
    assert model.facts["A"] == {(1, 2, 3), (3, 5, 8)}


def test_evaluator_distinguishes_scalar_types() -> None:
    # 1 == True in Python; conformance tuples must not conflate them.
    program = Program(
        facts={"flag": [(True,)], "num": [(1,)]},
        rules=["both(X) :- flag(X), num(X)."],
    )
    model = CoreReferenceEvaluator().evaluate(program)
    assert model.facts.get("both", set()) == set()


def test_evaluator_returns_model_instance() -> None:
    model = CoreReferenceEvaluator().evaluate(Program(facts={}, rules=[]))
    assert isinstance(model, Model)
    assert model.facts == {}
