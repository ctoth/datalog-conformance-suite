"""Clingo (Potassco ASP) as an external conformance oracle.

For stratified Datalog programs the unique stable model coincides with the
standard stratified semantics, so clingo — an entirely independent lineage
from Nemo and Souffle — is a strong third witness for core cases.

The adapter renders the visible program surface to ASP: predicates are
renamed into a lowercase-safe namespace, rule variables become uppercase,
string scalars become clingo strings, ``not`` becomes default negation, and
comparison guards and integer arithmetic pass through. Floats and booleans
are outside clingo's term language and raise
:class:`ClingoUnsupportedError`.

Requires the ``oracles`` extra (``uv sync --extra oracles``).
"""

from __future__ import annotations

import re
from typing import Any, cast

from ..references.core import (
    AtomAst,
    Comparison,
    Constant,
    RuleAst,
    Term,
    Variable,
    Wildcard,
    parse_rules,
)
from ..schema import FactTuple, Model, Program, Scalar


class ClingoError(RuntimeError):
    """Raised when clingo fails or produces unusable output."""


class ClingoUnavailableError(ClingoError):
    """Raised when the clingo Python package is not installed."""


class ClingoUnsupportedError(ClingoError):
    """Raised when the visible program uses surface ASP cannot express."""


def _import_clingo() -> Any:
    try:
        import clingo
    except ImportError as exc:  # pragma: no cover - environment-specific
        raise ClingoUnavailableError(
            "The clingo package is not installed; install the 'oracles' extra."
        ) from exc
    return clingo


class ClingoOracle:
    """DatalogEvaluator protocol implementation backed by clingo."""

    def __init__(self) -> None:
        self._clingo = _import_clingo()

    def evaluate(self, program: Program) -> Model:
        rules = parse_rules(program.rules)
        predicate_map = _build_predicate_map(program, rules)
        text = _render_asp_program(program, rules, predicate_map)

        control = self._clingo.Control(["--warn=none"])
        control.add("base", [], text)
        control.ground([("base", [])])

        reverse_map = {value: key for key, value in predicate_map.items()}
        facts: dict[str, set[FactTuple]] = {
            predicate: set() for predicate in predicate_map
        }
        captured: list[list[tuple[str, FactTuple]]] = []

        def on_model(model: Any) -> None:
            rows: list[tuple[str, FactTuple]] = []
            for symbol in cast("list[Any]", model.symbols(atoms=True)):
                predicate = reverse_map.get(cast(str, symbol.name))
                if predicate is None:
                    continue
                arguments = cast("list[Any]", symbol.arguments)
                rows.append(
                    (predicate, tuple(_from_symbol(item) for item in arguments))
                )
            captured.append(rows)

        result = control.solve(on_model=on_model)
        if not result.satisfiable:
            raise ClingoError("clingo found no stable model for a stratified program")
        if not captured:
            raise ClingoError("clingo reported satisfiable but yielded no model")
        for predicate, row in captured[-1]:
            facts[predicate].add(row)
        return Model(facts=facts)


def _from_symbol(symbol: Any) -> Scalar:
    if symbol.type.name == "Number":
        return int(symbol.number)
    if symbol.type.name == "String":
        return str(symbol.string)
    raise ClingoError(f"Unexpected clingo term in model: {symbol!r}")


def _build_predicate_map(program: Program, rules: list[RuleAst]) -> dict[str, str]:
    predicates = set(program.facts)
    for rule in rules:
        predicates.add(rule.head.predicate)
        for atom in (*rule.positive, *rule.negative):
            predicates.add(atom.predicate)
    mapping: dict[str, str] = {}
    for index, predicate in enumerate(sorted(predicates), start=1):
        sanitized = re.sub(r"[^A-Za-z0-9_]+", "_", predicate).strip("_").lower()
        mapping[predicate] = f"p_{index}_{sanitized or 'predicate'}"
    return mapping


def _render_asp_program(
    program: Program,
    rules: list[RuleAst],
    predicate_map: dict[str, str],
) -> str:
    lines: list[str] = []
    for predicate, rows in program.facts.items():
        translated = predicate_map[predicate]
        for row in rows:
            if row:
                rendered = ", ".join(_render_scalar(value) for value in row)
                lines.append(f"{translated}({rendered}).")
            else:
                lines.append(f"{translated}.")
    for rule in rules:
        lines.append(_render_rule(rule, predicate_map))
    return "\n".join(lines) + "\n"


def _render_scalar(value: Scalar) -> str:
    if isinstance(value, bool):
        raise ClingoUnsupportedError("Boolean scalars are not supported for clingo")
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        raise ClingoUnsupportedError("Float scalars are not supported for clingo")
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _render_rule(rule: RuleAst, predicate_map: dict[str, str]) -> str:
    head = _render_atom(rule.head, predicate_map)
    parts: list[str] = []
    parts.extend(_render_atom(atom, predicate_map) for atom in rule.positive)
    parts.extend(_render_comparison(item) for item in rule.comparisons)
    parts.extend(
        f"not {_render_atom(atom, predicate_map)}" for atom in rule.negative
    )
    if not parts:
        return f"{head}."
    return f"{head} :- {', '.join(parts)}."


def _render_comparison(comparison: Comparison) -> str:
    return (
        f"{_render_term(comparison.left)} {comparison.op} "
        f"{_render_term(comparison.right)}"
    )


def _render_atom(atom: AtomAst, predicate_map: dict[str, str]) -> str:
    if not atom.terms:
        return predicate_map[atom.predicate]
    rendered = ", ".join(_render_term(term) for term in atom.terms)
    return f"{predicate_map[atom.predicate]}({rendered})"


def _render_term(term: Term) -> str:
    if isinstance(term, Constant):
        return _render_scalar(term.value)
    if isinstance(term, Variable):
        return f"V_{term.name}"
    if isinstance(term, Wildcard):
        return "_"
    return f"({_render_term(term.left)} {term.op} {_render_term(term.right)})"
