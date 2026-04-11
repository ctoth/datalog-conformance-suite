"""Support helpers for generated DePYsible-backed tests.

This module keeps the surface narrow:
- locate the local DePYsible checkout under the Windows temp directory
- add its Python source tree to ``sys.path``
- instantiate and run the repository's existing DePYsible adapter
- provide a tiny local reference evaluator for the supported positive fragment
"""

from __future__ import annotations

import importlib
import sys
import tempfile
from itertools import product
from pathlib import Path
from typing import cast

import pytest

from datalog_conformance.examples.depysible_adapter import DePYsibleAdapter
from datalog_conformance.schema import (
    DefeasibleModel,
    DefeasibleTheory,
    FactTuple,
    Model,
    Policy,
    PredicateFacts,
    Program,
)

_DEPYSIBLE_SOURCE_ROOT = Path(tempfile.gettempdir()) / "depysible" / "src" / "main" / "python"


def depysible_source_root() -> Path:
    """Return the expected root of the local DePYsible checkout."""

    return _DEPYSIBLE_SOURCE_ROOT


def depysible_source_available() -> bool:
    """Return whether the local DePYsible checkout exists."""

    return _DEPYSIBLE_SOURCE_ROOT.exists()


def depysible_runtime_available() -> bool:
    """Return whether the local DePYsible checkout and its imports are usable."""

    if not depysible_source_available():
        return False
    ensure_depysible_source_on_path()
    try:
        importlib.import_module("arpeggio")
        importlib.import_module("colorama")
    except ImportError:
        return False
    return True


def ensure_depysible_source_on_path() -> Path:
    """Add the local DePYsible source tree to ``sys.path`` if it exists."""

    source_root = depysible_source_root()
    if source_root.exists():
        source_root_str = str(source_root)
        if source_root_str not in sys.path:
            sys.path.insert(0, source_root_str)
        return source_root
    return source_root


def require_depysible_source() -> Path:
    """Return the DePYsible source root or skip the calling test."""

    source_root = ensure_depysible_source_on_path()
    if not source_root.exists():
        pytest.skip(f"DePYsible checkout not found at {source_root}")
    return source_root


def instantiate_depysible_adapter() -> DePYsibleAdapter:
    """Create the repository's DePYsible adapter after verifying the checkout."""

    require_depysible_source()
    if not depysible_runtime_available():
        pytest.skip("DePYsible dependencies are unavailable")
    return DePYsibleAdapter()


def run_depysible_adapter(
    theory: DefeasibleTheory,
    policy: Policy = Policy.BLOCKING,
) -> DefeasibleModel:
    """Run the live DePYsible adapter, skipping cleanly when it is unavailable."""

    adapter = instantiate_depysible_adapter()
    return adapter.evaluate(theory, policy)


def evaluate_supported_program_locally(program: Program) -> Model:
    """Evaluate a positive Datalog program with a small local reference closure."""

    facts = _normalize_fact_mapping(program.facts)
    while True:
        next_facts = _apply_rules_once(program, facts)
        if next_facts == facts:
            return Model(facts=next_facts)
        facts = next_facts


def evaluate_supported_theory_locally(theory: DefeasibleTheory) -> DefeasibleModel:
    """Evaluate the supported defeasible fragment with local reference semantics."""

    _ensure_supported_fragment(theory)

    strict_program = Program(
        facts=theory.facts,
        rules=[_render_rule(rule.head, rule.body) for rule in theory.strict_rules],
    )
    full_program = Program(
        facts=theory.facts,
        rules=[
            _render_rule(rule.head, rule.body)
            for rule in [*theory.strict_rules, *theory.defeasible_rules]
        ],
    )
    return DefeasibleModel(
        sections={
            "definitely": evaluate_supported_program_locally(strict_program).facts,
            "defeasibly": evaluate_supported_program_locally(full_program).facts,
        }
    )


def _ensure_supported_fragment(theory: DefeasibleTheory) -> None:
    if theory.defeaters:
        raise ValueError("Local DePYsible reference helper does not support defeaters")
    if theory.superiority:
        raise ValueError("Local DePYsible reference helper does not support superiority")
    if theory.conflicts:
        raise ValueError("Local DePYsible reference helper does not support conflicts")


def _apply_rules_once(
    program: Program,
    facts: dict[str, set[FactTuple]],
) -> dict[str, set[FactTuple]]:
    next_facts = {predicate: set(rows) for predicate, rows in facts.items()}
    domain = _active_domain(facts)
    for rule_text in program.rules:
        head, body = _parse_rule(rule_text)
        for substitution in _matching_substitutions(body, next_facts, domain):
            derived = _instantiate_atom(head, substitution)
            next_facts.setdefault(derived[0], set()).add(derived[1])
    return next_facts


def _parse_rule(
    rule_text: str,
) -> tuple[tuple[str, tuple[str, ...]], list[tuple[str, tuple[str, ...]]]]:
    text = rule_text.strip().removesuffix(".")
    if ":-" not in text:
        return _parse_atom(text), []
    head_text, body_text = text.split(":-", 1)
    return _parse_atom(head_text), [_parse_atom(item) for item in _split_atoms(body_text)]


def _parse_atom(atom_text: str) -> tuple[str, tuple[str, ...]]:
    predicate, _, tail = atom_text.strip().partition("(")
    arguments = tail.removesuffix(")")
    if not predicate or not arguments:
        raise ValueError(f"Unsupported atom syntax: {atom_text}")
    return (
        predicate.strip(),
        tuple(
            argument.strip()
            for argument in arguments.split(",")
            if argument.strip()
        ),
    )


def _split_atoms(body_text: str) -> list[str]:
    atoms: list[str] = []
    current: list[str] = []
    depth = 0

    for character in body_text:
        if character == "," and depth == 0:
            atom = "".join(current).strip()
            if atom:
                atoms.append(atom)
            current = []
            continue
        if character == "(":
            depth += 1
        elif character == ")" and depth > 0:
            depth -= 1
        current.append(character)

    atom = "".join(current).strip()
    if atom:
        atoms.append(atom)
    return atoms


def _matching_substitutions(
    body: list[tuple[str, tuple[str, ...]]],
    facts: dict[str, set[FactTuple]],
    domain: tuple[str, ...],
) -> list[dict[str, str]]:
    if not body:
        return [{}]

    variables = sorted({item for atom in body for item in atom[1] if _is_variable(item)})
    if not variables:
        return [{}] if _body_holds(body, facts, {}) else []

    matches: list[dict[str, str]] = []
    for values in product(domain, repeat=len(variables)):
        substitution = dict(zip(variables, values, strict=True))
        if _body_holds(body, facts, substitution):
            matches.append(substitution)
    return matches


def _body_holds(
    body: list[tuple[str, tuple[str, ...]]],
    facts: dict[str, set[FactTuple]],
    substitution: dict[str, str],
) -> bool:
    for atom in body:
        instantiated = _instantiate_atom(atom, substitution)
        if instantiated[1] not in facts.get(instantiated[0], set()):
            return False
    return True


def _instantiate_atom(
    atom: tuple[str, tuple[str, ...]],
    substitution: dict[str, str],
) -> tuple[str, tuple[str, ...]]:
    predicate, arguments = atom
    return predicate, tuple(substitution.get(argument, argument) for argument in arguments)


def _active_domain(facts: dict[str, set[FactTuple]]) -> tuple[str, ...]:
    values = {cast(str, value) for rows in facts.values() for row in rows for value in row}
    if not values:
        return ("a",)
    return tuple(sorted(values))


def _normalize_fact_mapping(raw_facts: PredicateFacts) -> dict[str, set[FactTuple]]:
    return {predicate: set(rows) for predicate, rows in raw_facts.items()}


def _render_rule(head: str, body: list[str]) -> str:
    return f"{head} :- {', '.join(body)}."


def _is_variable(value: str) -> bool:
    return value[:1].isupper()
