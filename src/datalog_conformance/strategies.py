"""Hypothesis strategies for generated Datalog and defeasible theories."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

from hypothesis import strategies as st

from .schema import DefeasibleTheory, PredicateFacts, Program, Rule

_PREDICATE_NAMES = ("p", "q", "r", "s")
_VARIABLE_NAMES = ("X", "Y", "Z")
_CONSTANT_NAMES = ("a", "b", "c")


@dataclass(frozen=True, slots=True)
class PredicateSignature:
    """Predicate name and fixed arity for generated programs."""

    name: str
    arity: int


@dataclass(frozen=True, slots=True)
class GeneratedProgram:
    """Generated positive Datalog program with grouped rule strata."""

    program: Program
    signatures: tuple[PredicateSignature, ...]
    rule_groups: tuple[tuple[str, ...], ...]
    constants: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class GeneratedDefeasibleTheory:
    """Generated conflict-free defeasible theory and its program views."""

    theory: DefeasibleTheory
    strict_program: Program
    full_program: Program


def facts_only_programs() -> st.SearchStrategy[GeneratedProgram]:
    """Generate small facts-only programs."""

    return _generated_programs(include_rules=False)


def positive_programs() -> st.SearchStrategy[GeneratedProgram]:
    """Generate small positive range-restricted Datalog programs."""

    return _generated_programs(include_rules=True)


def conflict_free_defeasible_theories() -> st.SearchStrategy[GeneratedDefeasibleTheory]:
    """Generate conflict-free theories where defeasible closure extends strict closure."""

    return _generated_defeasible_theories(strict_only=False)


def strict_only_defeasible_theories() -> st.SearchStrategy[GeneratedDefeasibleTheory]:
    """Generate strict-only defeasible theories equivalent to standard Datalog."""

    return _generated_defeasible_theories(strict_only=True)


@st.composite
def _generated_programs(
    draw: Any,
    *,
    include_rules: bool,
) -> GeneratedProgram:
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

    rule_groups: list[tuple[str, ...]] = []
    if include_rules:
        rule_groups = _draw_rule_groups(draw, signatures)

    rules = [rule for group in rule_groups for rule in group]
    program = Program(facts=cast(PredicateFacts, facts), rules=rules)
    return GeneratedProgram(
        program=program,
        signatures=signatures,
        rule_groups=tuple(rule_groups),
        constants=constants,
    )


@st.composite
def _generated_defeasible_theories(
    draw: Any,
    *,
    strict_only: bool,
) -> GeneratedDefeasibleTheory:
    generated = draw(_generated_programs(include_rules=True))

    strict_rules: list[Rule] = []
    defeasible_rules: list[Rule] = []
    for index, rule_text in enumerate(generated.program.rules, start=1):
        head, body = _split_rule_text(rule_text)
        rule = Rule(id=f"r{index}", head=head, body=body)
        if strict_only or draw(st.booleans()):
            strict_rules.append(rule)
        else:
            defeasible_rules.append(rule)

    theory = DefeasibleTheory(
        facts=cast(PredicateFacts, generated.program.facts),
        strict_rules=strict_rules,
        defeasible_rules=defeasible_rules,
        defeaters=[],
        superiority=[],
        conflicts=[],
    )
    strict_program = Program(
        facts=cast(PredicateFacts, generated.program.facts),
        rules=[_render_rule(rule.head, rule.body) for rule in strict_rules],
    )
    full_program = Program(
        facts=cast(PredicateFacts, generated.program.facts),
        rules=[
            _render_rule(rule.head, rule.body)
            for rule in [*strict_rules, *defeasible_rules]
        ],
    )
    return GeneratedDefeasibleTheory(
        theory=theory,
        strict_program=strict_program,
        full_program=full_program,
    )


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
        row_strategy = st.tuples(
            *[st.sampled_from(constants) for _ in range(signature.arity)]
        )
        rows = draw(st.sets(row_strategy, max_size=3))
        if rows:
            facts[signature.name] = sorted(rows)
    return facts


def _draw_rule_groups(
    draw: Any,
    signatures: tuple[PredicateSignature, ...],
) -> list[tuple[str, ...]]:
    stratum_count = draw(st.integers(min_value=1, max_value=len(signatures)))
    signature_strata = [
        draw(st.integers(min_value=0, max_value=stratum_count - 1))
        for _ in signatures
    ]
    groups: list[tuple[str, ...]] = []
    for stratum in range(stratum_count):
        head_signatures = [
            signature
            for signature, signature_stratum in zip(signatures, signature_strata, strict=True)
            if signature_stratum == stratum
        ]
        allowed_body = [
            signature
            for signature, signature_stratum in zip(signatures, signature_strata, strict=True)
            if signature_stratum <= stratum
        ]
        rule_count = draw(st.integers(min_value=0, max_value=3))
        rules = [
            _draw_rule(draw, head_signatures, allowed_body)
            for _ in range(rule_count)
            if head_signatures
        ]
        if rules:
            groups.append(tuple(rules))
    return groups


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
    return _render_rule(_render_atom(head_signature.name, head_arguments), body_atoms)


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


def _render_atom(predicate: str, arguments: list[str] | tuple[str, ...]) -> str:
    return f"{predicate}({', '.join(arguments)})"


def _render_rule(head: str, body: list[str]) -> str:
    return f"{head} :- {', '.join(body)}."
