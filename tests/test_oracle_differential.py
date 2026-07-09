"""Differential property testing across real external engines.

Hypothesis generates small Datalog programs; every available external oracle
(Nemo, Souffle, clingo) evaluates each one; the property is pairwise model
agreement. Nothing here checks itself: disagreement means a translation bug,
a corpus-convention ambiguity, or an engine bug — all of which we want to
know about.

These tests skip when fewer than two external oracles are available.
"""

from __future__ import annotations

import pytest
from hypothesis import HealthCheck, given, settings

from datalog_conformance.protocol import DatalogEvaluator
from datalog_conformance.schema import FactTuple, Model, Program
from datalog_conformance.strategies import GeneratedProgram, positive_programs

_ORACLES: dict[str, DatalogEvaluator] = {}


def _available_oracles() -> dict[str, DatalogEvaluator]:
    if _ORACLES:
        return dict(_ORACLES)
    from datalog_conformance.oracles import (
        ClingoOracle,
        NemoOracle,
        SouffleOracle,
    )

    builders: tuple[tuple[str, type], ...] = (
        ("nemo", NemoOracle),
        ("souffle", SouffleOracle),
        ("clingo", ClingoOracle),
    )
    for name, builder in builders:
        try:
            _ORACLES[name] = builder()
        except Exception:  # noqa: BLE001 - availability probe
            continue
    return dict(_ORACLES)


_AVAILABLE = _available_oracles()

pytestmark = pytest.mark.skipif(
    len(_AVAILABLE) < 2,
    reason="differential testing needs at least two external oracles",
)

_DIFFERENTIAL_SETTINGS = settings(
    deadline=None,
    max_examples=25,
    suppress_health_check=[HealthCheck.too_slow],
)


def _normalized(model: Model, predicates: set[str]) -> dict[str, set[FactTuple]]:
    return {predicate: model.facts.get(predicate, set()) for predicate in predicates}


def _program_predicates(program: Program) -> set[str]:
    from datalog_conformance.oracles.nemo import collect_program_predicates

    return collect_program_predicates(program)


@given(positive_programs())
@_DIFFERENTIAL_SETTINGS
def test_external_oracles_agree_on_positive_programs(
    generated: GeneratedProgram,
) -> None:
    program = generated.program
    predicates = _program_predicates(program)
    models = {
        name: _normalized(oracle.evaluate(program), predicates)
        for name, oracle in _AVAILABLE.items()
    }
    names = sorted(models)
    baseline_name = names[0]
    baseline = models[baseline_name]
    for other_name in names[1:]:
        assert models[other_name] == baseline, (
            f"{other_name} disagrees with {baseline_name} on {program!r}"
        )


@given(positive_programs())
@_DIFFERENTIAL_SETTINGS
def test_external_oracles_agree_after_rule_reversal(
    generated: GeneratedProgram,
) -> None:
    # Rule order must be semantically irrelevant; engines must agree with
    # themselves across a reordering.
    program = generated.program
    reversed_program = Program(
        facts=program.facts, rules=list(reversed(program.rules))
    )
    predicates = _program_predicates(program)
    for name, oracle in _AVAILABLE.items():
        original = _normalized(oracle.evaluate(program), predicates)
        reordered = _normalized(oracle.evaluate(reversed_program), predicates)
        assert original == reordered, f"{name} is sensitive to rule order"
