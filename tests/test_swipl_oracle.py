"""Tests for the SWI-Prolog oracle (tabled evaluation, native or WSL).

Skipped when no swipl invocation is available.
"""

from __future__ import annotations

import pytest

from datalog_conformance.oracles import SwiPrologOracle, find_swipl
from datalog_conformance.schema import Program

pytestmark = pytest.mark.skipif(
    find_swipl() is None,
    reason="no swipl invocation available (native or WSL)",
)


def test_swipl_oracle_computes_transitive_closure() -> None:
    oracle = SwiPrologOracle()
    model = oracle.evaluate(
        Program(
            facts={"edge": [("a", "b"), ("b", "c")]},
            rules=[
                "path(X,Y) :- edge(X,Y).",
                "path(X,Z) :- path(X,Y), edge(Y,Z).",
            ],
        )
    )
    assert model.facts["path"] == {("a", "b"), ("b", "c"), ("a", "c")}


def test_swipl_oracle_handles_left_recursion_via_tabling() -> None:
    # Left-recursive rules loop forever without tabling; this is the point
    # of using SLG resolution as the fourth lineage.
    oracle = SwiPrologOracle()
    model = oracle.evaluate(
        Program(
            facts={"edge": [("a", "b"), ("b", "c"), ("c", "a")]},
            rules=[
                "path(X,Z) :- path(X,Y), edge(Y,Z).",
                "path(X,Y) :- edge(X,Y).",
            ],
        )
    )
    nodes = ("a", "b", "c")
    assert model.facts["path"] == {(x, y) for x in nodes for y in nodes}


def test_swipl_oracle_handles_stratified_negation_with_tnot() -> None:
    oracle = SwiPrologOracle()
    model = oracle.evaluate(
        Program(
            facts={
                "node": [("a",), ("b",), ("c",)],
                "edge": [("a", "b")],
            },
            rules=[
                "touched(X) :- edge(X, _).",
                "touched(Y) :- edge(_, Y).",
                "isolated(X) :- node(X), not touched(X).",
            ],
        )
    )
    assert model.facts["isolated"] == {("c",)}


def test_swipl_oracle_handles_head_arithmetic() -> None:
    oracle = SwiPrologOracle()
    model = oracle.evaluate(
        Program(
            facts={"R": [(1, 2), (3, 5)]},
            rules=["A(a, b, a+b) :- R(a,b)."],
        )
    )
    assert model.facts["A"] == {(1, 2, 3), (3, 5, 8)}


def test_swipl_oracle_preserves_string_scalars() -> None:
    oracle = SwiPrologOracle()
    model = oracle.evaluate(
        Program(
            facts={"r": [(1, "one two"), (2, "42")]},
            rules=["s(Y, X) :- r(X, Y)."],
        )
    )
    assert model.facts["s"] == {("one two", 1), ("42", 2)}


def test_swipl_oracle_supports_zero_arity_predicates() -> None:
    oracle = SwiPrologOracle()
    model = oracle.evaluate(
        Program(
            facts={"seed": [("a",)]},
            rules=["nonempty() :- seed(_)."],
        )
    )
    assert model.facts["nonempty"] == {()}


def test_swipl_oracle_handles_comparison_guards() -> None:
    oracle = SwiPrologOracle()
    model = oracle.evaluate(
        Program(
            facts={"n": [(1,), (2,), (3,), (4,)]},
            rules=["small(X) :- n(X), (X <= 2)."],
        )
    )
    assert model.facts["small"] == {(1,), (2,)}
