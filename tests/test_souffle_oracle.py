"""Tests for the Souffle oracle (native binary or WSL bridge).

Skipped when no souffle invocation is available; the suite must stay usable
on machines without Souffle.
"""

from __future__ import annotations

import pytest

from datalog_conformance.oracles import SouffleOracle, find_souffle
from datalog_conformance.schema import Program

pytestmark = pytest.mark.skipif(
    find_souffle() is None,
    reason="no souffle invocation available (native or WSL)",
)


def test_souffle_oracle_computes_transitive_closure() -> None:
    oracle = SouffleOracle()
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


def test_souffle_oracle_infers_number_columns() -> None:
    oracle = SouffleOracle()
    model = oracle.evaluate(
        Program(
            facts={"R": [(1, 2), (2, 3), (3, 5)]},
            rules=["A(a, b, a+b) :- R(a,b)."],
        )
    )
    assert model.facts["A"] == {(1, 2, 3), (2, 3, 5), (3, 5, 8)}


def test_souffle_oracle_handles_negation() -> None:
    oracle = SouffleOracle()
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
