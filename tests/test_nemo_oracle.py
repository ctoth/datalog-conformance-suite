"""Tests for the packaged Nemo oracle.

These run only when a local nmo binary is available; the suite must stay
usable on machines without a Nemo build.
"""

from __future__ import annotations

import pytest

from datalog_conformance.oracles import NemoOracle, find_nmo
from datalog_conformance.schema import Program

pytestmark = pytest.mark.skipif(
    find_nmo() is None,
    reason="no local nmo binary; build nemo-cli to enable Nemo oracle tests",
)


def test_nemo_oracle_computes_transitive_closure() -> None:
    oracle = NemoOracle()
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


def test_nemo_oracle_preserves_scalar_types() -> None:
    oracle = NemoOracle()
    model = oracle.evaluate(
        Program(
            facts={"r": [(1, "one"), (2, "two")]},
            rules=["s(Y, X) :- r(X, Y)."],
        )
    )
    assert model.facts["s"] == {("one", 1), ("two", 2)}


def test_nemo_oracle_handles_stratified_negation() -> None:
    oracle = NemoOracle()
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


def test_nemo_oracle_agrees_with_reference_on_head_arithmetic() -> None:
    from datalog_conformance.references import CoreReferenceEvaluator

    program = Program(
        facts={"R": [(1, 2), (2, 3), (3, 5)]},
        rules=["A(a, b, a+b) :- R(a,b)."],
    )
    nemo_model = NemoOracle().evaluate(program)
    reference_model = CoreReferenceEvaluator().evaluate(program)
    assert nemo_model.facts["A"] == reference_model.facts["A"]
