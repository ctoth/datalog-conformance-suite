"""Tests for the clingo oracle.

Skipped when the clingo package (the ``oracles`` extra) is not installed.
"""

from __future__ import annotations

import pytest

from datalog_conformance.schema import Program

clingo = pytest.importorskip("clingo")

from datalog_conformance.oracles import ClingoOracle  # noqa: E402


def test_clingo_oracle_computes_transitive_closure() -> None:
    oracle = ClingoOracle()
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


def test_clingo_oracle_handles_integer_arithmetic() -> None:
    oracle = ClingoOracle()
    model = oracle.evaluate(
        Program(
            facts={"R": [(1, 2), (3, 5)]},
            rules=["A(a, b, a+b) :- R(a,b)."],
        )
    )
    assert model.facts["A"] == {(1, 2, 3), (3, 5, 8)}


def test_clingo_oracle_handles_negation_and_guards() -> None:
    oracle = ClingoOracle()
    model = oracle.evaluate(
        Program(
            facts={
                "n": [(1,), (2,), (3,), (4,)],
                "banned": [(2,)],
            },
            rules=["ok(X) :- n(X), not banned(X), (X <= 3)."],
        )
    )
    assert model.facts["ok"] == {(1,), (3,)}


def test_clingo_oracle_preserves_string_scalars() -> None:
    oracle = ClingoOracle()
    model = oracle.evaluate(
        Program(
            facts={"r": [(1, "one"), (2, "two")]},
            rules=["s(Y, X) :- r(X, Y)."],
        )
    )
    assert model.facts["s"] == {("one", 1), ("two", 2)}
