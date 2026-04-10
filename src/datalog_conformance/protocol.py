"""Protocols implemented by evaluator packages under test."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from .schema import DefeasibleModel, DefeasibleTheory, Model, Policy, Program


@runtime_checkable
class DatalogEvaluator(Protocol):
    """Evaluates a standard Datalog program."""

    def evaluate(self, program: Program) -> Model: ...


@runtime_checkable
class DefeasibleEvaluator(Protocol):
    """Evaluates a defeasible theory under a given policy."""

    def evaluate(self, theory: DefeasibleTheory, policy: Policy) -> DefeasibleModel: ...
