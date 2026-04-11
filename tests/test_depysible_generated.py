from __future__ import annotations

# pyright: reportMissingImports=false, reportUnknownMemberType=false, reportUnknownVariableType=false

import os
import sys
from dataclasses import dataclass
from itertools import product
from pathlib import Path
from typing import Any

from hypothesis import given, settings
from hypothesis import strategies as st

from datalog_conformance.schema import (
    DefeasibleTheory,
    FactTuple,
    Program as SuiteProgram,
    Scalar,
    Rule,
)
from datalog_conformance.strategies import (
    GeneratedDefeasibleTheory,
)

_TEMP_ROOT = os.environ.get("TEMP") or os.environ.get("TMP")
if _TEMP_ROOT is None:
    raise RuntimeError("TEMP is required to locate the local DePYsible checkout")

_DEPYSIBLE_SRC = Path(_TEMP_ROOT) / "depysible" / "src" / "main" / "python"
if not _DEPYSIBLE_SRC.is_dir():
    raise RuntimeError(f"Expected DePYsible sources at {_DEPYSIBLE_SRC}")

if str(_DEPYSIBLE_SRC) not in sys.path:
    sys.path.insert(0, str(_DEPYSIBLE_SRC))

from depysible.domain.definitions import Program as DepysibleProgram  # noqa: E402
from depysible.domain.definitions import RuleType  # noqa: E402
from depysible.domain.interpretation import Answer, Interpreter  # noqa: E402

_PROPERTY_SETTINGS = settings(deadline=None, max_examples=40)
_PREDICATE_NAMES = ("p", "q", "r", "s")
_VARIABLE_NAMES = ("X", "Y", "Z")
_CONSTANT_NAMES = ("a", "b", "c")


@dataclass(frozen=True, slots=True)
class Atom:
    predicate: str
    arguments: tuple[str, ...]


def _evaluate_depysible(theory: DefeasibleTheory) -> dict[str, dict[str, set[FactTuple]]]:
    program = DepysibleProgram.parse(_render_program(theory))
    interpreter = Interpreter(program)

    sections: dict[str, dict[str, set[FactTuple]]] = {
        "definitely": {},
        "defeasibly": {},
        "not_defeasibly": {},
        "undecided": {},
    }

    for literal in interpreter.get_literals(RuleType.DEFEASIBLE):
        strict_answer, _ = interpreter.query(literal, RuleType.STRICT)
        defeasible_answer, _ = interpreter.query(literal, RuleType.DEFEASIBLE)
        predicate = _literal_predicate_name(literal)
        row = tuple(_normalize_term(term) for term in literal.terms)

        if strict_answer is Answer.YES:
            sections["definitely"].setdefault(predicate, set()).add(row)
        if defeasible_answer is Answer.YES:
            sections["defeasibly"].setdefault(predicate, set()).add(row)
        elif defeasible_answer is Answer.NO:
            sections["not_defeasibly"].setdefault(predicate, set()).add(row)
        elif defeasible_answer is Answer.UNDECIDED:
            sections["undecided"].setdefault(predicate, set()).add(row)

    return {key: value for key, value in sections.items() if value}


def _reference_sections(generated: GeneratedDefeasibleTheory) -> dict[str, dict[str, set[FactTuple]]]:
    sections: dict[str, dict[str, set[FactTuple]]] = {
        "definitely": _evaluate_program(generated.strict_program),
        "defeasibly": _evaluate_program(generated.full_program),
    }
    return {key: value for key, value in sections.items() if value}


@dataclass(frozen=True, slots=True)
class PredicateSignature:
    name: str
    arity: int


@st.composite
def _acyclic_conflict_free_defeasible_theories(
    draw: Any,
) -> GeneratedDefeasibleTheory:
    signatures = draw(_predicate_signatures())
    constants = tuple(
        draw(
            st.lists(
                st.sampled_from(_CONSTANT_NAMES),
                min_size=1,
                max_size=len(_CONSTANT_NAMES),
                unique=True,
            )
        )
    )
    facts = _draw_facts(draw, signatures, constants)

    strict_rules: list[Rule] = []
    defeasible_rules: list[Rule] = []
    strict_rule_texts: list[str] = []
    full_rule_texts: list[str] = []

    rule_index = 1
    for head_index, head_signature in enumerate(signatures):
        allowed_body = signatures[:head_index]
        rule_count = draw(st.integers(min_value=0, max_value=3))
        for _ in range(rule_count):
            if not allowed_body:
                continue
            rule_text = _draw_rule(draw, [head_signature], allowed_body)
            head, body = _split_rule_text(rule_text)
            rule = Rule(id=f"r{rule_index}", head=head, body=body)
            rule_index += 1

            full_rule_texts.append(rule_text)
            if draw(st.booleans()):
                strict_rules.append(rule)
                strict_rule_texts.append(rule_text)
            else:
                defeasible_rules.append(rule)

    theory = DefeasibleTheory(
        facts=facts,
        strict_rules=strict_rules,
        defeasible_rules=defeasible_rules,
        defeaters=[],
        superiority=[],
        conflicts=[],
    )
    strict_program = SuiteProgram(facts=facts, rules=strict_rule_texts)
    full_program = SuiteProgram(facts=facts, rules=full_rule_texts)
    return GeneratedDefeasibleTheory(
        theory=theory,
        strict_program=strict_program,
        full_program=full_program,
    )


@given(_acyclic_conflict_free_defeasible_theories())
@_PROPERTY_SETTINGS
def test_depysible_conflict_free_fragment_matches_reference_semantics(
    generated: GeneratedDefeasibleTheory,
) -> None:
    actual = _evaluate_depysible(generated.theory)
    reference = _reference_sections(generated)

    assert actual == reference


def _predicate_signatures() -> st.SearchStrategy[tuple[PredicateSignature, ...]]:
    return st.lists(
        st.builds(
            PredicateSignature,
            name=st.sampled_from(_PREDICATE_NAMES),
            arity=st.integers(min_value=1, max_value=2),
        ),
        min_size=1,
        max_size=len(_PREDICATE_NAMES),
        unique_by=lambda item: item.name,
    ).map(tuple)


def _draw_facts(
    draw: Any,
    signatures: tuple[PredicateSignature, ...],
    constants: tuple[str, ...],
) -> dict[str, list[tuple[str, ...]]]:
    facts: dict[str, list[tuple[str, ...]]] = {}
    for signature in signatures:
        row_strategy = st.tuples(*[st.sampled_from(constants) for _ in range(signature.arity)])
        rows = draw(st.sets(row_strategy, max_size=3))
        if rows:
            facts[signature.name] = sorted(rows)
    return facts


def _draw_rule(
    draw: Any,
    head_signatures: list[PredicateSignature],
    allowed_body: list[PredicateSignature],
) -> str:
    head_signature = draw(st.sampled_from(head_signatures))
    body_size = draw(st.integers(min_value=1, max_value=3))
    body_atoms: list[str] = []
    body_vars: list[str] = []

    for _ in range(body_size):
        signature = draw(st.sampled_from(allowed_body))
        arguments = draw(
            st.lists(
                st.sampled_from(_VARIABLE_NAMES),
                min_size=signature.arity,
                max_size=signature.arity,
            )
        )
        body_atoms.append(_render_atom(signature.name, arguments))
        for argument in arguments:
            if argument not in body_vars:
                body_vars.append(argument)

    head_arguments = draw(
        st.lists(
            st.sampled_from(body_vars),
            min_size=head_signature.arity,
            max_size=head_signature.arity,
        )
    )
    return _render_datalog_rule(_render_atom(head_signature.name, head_arguments), body_atoms)


def _split_rule_text(rule_text: str) -> tuple[str, list[str]]:
    text = rule_text.strip().removesuffix(".")
    if ":-" not in text:
        return text.strip(), []
    head, body = text.split(":-", 1)
    return head.strip(), _split_atoms(body.strip())


def _split_atoms(body: str) -> list[str]:
    atoms: list[str] = []
    current: list[str] = []
    depth = 0

    for character in body:
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


def _render_datalog_rule(head: str, body: list[str]) -> str:
    return f"{head} :- {', '.join(body)}."


def _evaluate_program(program: SuiteProgram) -> dict[str, set[FactTuple]]:
    facts = _normalize_fact_mapping(program.facts)
    while True:
        next_facts = _apply_rules_once(program, facts)
        if next_facts == facts:
            return next_facts
        facts = next_facts


def _apply_rules_once(
    program: SuiteProgram,
    facts: dict[str, set[FactTuple]],
) -> dict[str, set[FactTuple]]:
    next_facts = {predicate: set(rows) for predicate, rows in facts.items()}
    domain = _active_domain(facts)
    for rule_text in program.rules:
        head, body = _parse_rule(rule_text)
        for substitution in _matching_substitutions(body, next_facts, domain):
            derived = _instantiate_atom(head, substitution)
            next_facts.setdefault(derived.predicate, set()).add(derived.arguments)
    return next_facts


def _parse_rule(rule_text: str) -> tuple[Atom, list[Atom]]:
    text = rule_text.strip().removesuffix(".")
    if ":-" not in text:
        return _parse_atom(text), []
    head_text, body_text = text.split(":-", 1)
    return _parse_atom(head_text), [_parse_atom(item) for item in _split_atoms(body_text)]


def _parse_atom(atom_text: str) -> Atom:
    predicate, _, tail = atom_text.strip().partition("(")
    arguments = tail.removesuffix(")")
    if not predicate or not arguments:
        raise ValueError(f"Unsupported atom syntax: {atom_text}")
    return Atom(
        predicate=predicate.strip(),
        arguments=tuple(argument.strip() for argument in arguments.split(",") if argument.strip()),
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
    body: list[Atom],
    facts: dict[str, set[FactTuple]],
    domain: tuple[Scalar, ...],
) -> list[dict[str, Scalar]]:
    if not body:
        return [{}]

    variables = sorted({item for atom in body for item in atom.arguments if _is_variable(item)})
    if not variables:
        return [{}] if _body_holds(body, facts, {}) else []

    matches: list[dict[str, Scalar]] = []
    for values in product(domain, repeat=len(variables)):
        substitution = dict(zip(variables, values, strict=True))
        if _body_holds(body, facts, substitution):
            matches.append(substitution)
    return matches


def _body_holds(
    body: list[Atom],
    facts: dict[str, set[FactTuple]],
    substitution: dict[str, Scalar],
) -> bool:
    for atom in body:
        instantiated = _instantiate_atom(atom, substitution)
        if instantiated.arguments not in facts.get(instantiated.predicate, set()):
            return False
    return True


def _instantiate_atom(atom: Atom, substitution: dict[str, Scalar]) -> Atom:
    arguments = tuple(substitution.get(argument, argument) for argument in atom.arguments)
    return Atom(predicate=atom.predicate, arguments=arguments)


def _active_domain(facts: dict[str, set[FactTuple]]) -> tuple[Scalar, ...]:
    values = {value for rows in facts.values() for row in rows for value in row}
    if not values:
        return ("a",)
    return tuple(sorted(values, key=str))


def _render_program(theory: DefeasibleTheory) -> str:
    lines: list[str] = []
    for predicate, rows in theory.facts.items():
        for row in rows:
            lines.append(f"{predicate}({', '.join(_render_term(term) for term in row)}).")
    for rule in theory.strict_rules:
        lines.append(_render_rule(rule.head, rule.body, arrow="<-"))
    for rule in theory.defeasible_rules:
        lines.append(_render_rule(rule.head, rule.body, arrow="-<"))
    return "\n".join(lines)


def _render_rule(head: str, body: list[str], *, arrow: str) -> str:
    if not body:
        return f"{head}."
    return f"{head} {arrow} {', '.join(body)}."


def _render_atom(predicate: str, arguments: list[str] | tuple[str, ...]) -> str:
    return f"{predicate}({', '.join(arguments)})"


def _render_term(term: Scalar) -> str:
    if isinstance(term, str):
        if term and term[0].isupper():
            return term
        return term if term.isidentifier() else repr(term)
    return str(term)


def _literal_predicate_name(literal: Any) -> str:
    prefix = "~" if getattr(literal, "negated", False) else ""
    return f"{prefix}{literal.functor}"


def _normalize_term(term: Any) -> Scalar:
    if isinstance(term, (str, int, float, bool)):
        return term
    return str(term)


def _normalize_fact_mapping(raw_facts: dict[str, list[FactTuple]]) -> dict[str, set[FactTuple]]:
    return {predicate: set(rows) for predicate, rows in raw_facts.items()}


def _is_variable(value: str) -> bool:
    return value[:1].isupper()
