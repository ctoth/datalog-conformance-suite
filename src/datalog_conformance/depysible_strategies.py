"""Hypothesis strategies for the DePYsible-supported defeasible fragment.

The generator stays on the conservative surface confirmed for the local adapter:
- facts
- strict rules
- defeasible rules

It never emits defeaters, superiority declarations, or explicit conflicts.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

from hypothesis import strategies as st

from .schema import DefeasibleTheory, PredicateFacts, Program, Rule

_PREDICATES = (
    "bird",
    "chicken",
    "penguin",
    "scared",
    "flies",
    "nests_in_trees",
)
_CONSTANTS = ("tina", "tweety", "henrietta")
_SEED_PREDICATES = ("chicken", "penguin", "scared")
_MAX_FACT_ROWS_PER_PREDICATE = 2


@dataclass(frozen=True, slots=True)
class RuleTemplate:
    """Small positive rule shape used by the DePYsible fragment generator."""

    head: str
    body: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class GeneratedDePYsibleTheory:
    """Generated defeasible theory plus rendered strict/full program views."""

    theory: DefeasibleTheory
    strict_program: Program
    full_program: Program
    strict_rule_texts: tuple[str, ...]
    defeasible_rule_texts: tuple[str, ...]
    constants: tuple[str, ...]


_RULE_TEMPLATES = (
    RuleTemplate(head="bird(X)", body=("chicken(X)",)),
    RuleTemplate(head="bird(X)", body=("penguin(X)",)),
    RuleTemplate(head="bird(X)", body=("chicken(X)", "scared(X)")),
    RuleTemplate(head="bird(X)", body=("chicken(X)", "penguin(X)")),
    RuleTemplate(head="flies(X)", body=("bird(X)",)),
    RuleTemplate(head="flies(X)", body=("bird(X)", "scared(X)")),
    RuleTemplate(head="flies(X)", body=("chicken(X)", "scared(X)")),
    RuleTemplate(head="nests_in_trees(X)", body=("flies(X)",)),
)


def depysible_theories() -> st.SearchStrategy[GeneratedDePYsibleTheory]:
    """Generate small, stable DePYsible theories with only supported features."""

    return _generated_depysible_theories()


@st.composite
def _generated_depysible_theories(draw: Any) -> GeneratedDePYsibleTheory:
    constants = tuple(
        draw(
            st.lists(
                st.sampled_from(_CONSTANTS),
                min_size=1,
                max_size=len(_CONSTANTS),
                unique=True,
            )
        )
    )
    facts = _draw_facts(draw, constants)
    _ensure_seed_fact(facts, constants)

    selected_templates = draw(
        st.lists(
            st.sampled_from(_RULE_TEMPLATES),
            min_size=0,
            max_size=len(_RULE_TEMPLATES),
            unique=True,
        )
    )
    selected_kinds = _draw_rule_kinds(draw, len(selected_templates))
    selected_specs = list(zip(selected_kinds, selected_templates, strict=True))

    strict_rules: list[Rule] = []
    defeasible_rules: list[Rule] = []
    strict_rule_texts: list[str] = []
    defeasible_rule_texts: list[str] = []

    for index, (is_strict, template) in enumerate(selected_specs, start=1):
        rule = Rule(id=f"r{index}", head=template.head, body=list(template.body))
        rule_text = _render_rule(template.head, list(template.body))
        if is_strict:
            strict_rules.append(rule)
            strict_rule_texts.append(rule_text)
        else:
            defeasible_rules.append(rule)
            defeasible_rule_texts.append(rule_text)

    theory = DefeasibleTheory(
        facts=cast(PredicateFacts, facts),
        strict_rules=strict_rules,
        defeasible_rules=defeasible_rules,
        defeaters=[],
        superiority=[],
        conflicts=[],
    )
    strict_program = Program(facts=cast(PredicateFacts, facts), rules=strict_rule_texts)
    full_program = Program(
        facts=cast(PredicateFacts, facts),
        rules=[*strict_rule_texts, *defeasible_rule_texts],
    )
    return GeneratedDePYsibleTheory(
        theory=theory,
        strict_program=strict_program,
        full_program=full_program,
        strict_rule_texts=tuple(strict_rule_texts),
        defeasible_rule_texts=tuple(defeasible_rule_texts),
        constants=constants,
    )


def _draw_facts(draw: Any, constants: tuple[str, ...]) -> dict[str, list[tuple[str, ...]]]:
    facts: dict[str, list[tuple[str, ...]]] = {}
    row_strategy = st.tuples(st.sampled_from(constants))

    for predicate in _PREDICATES:
        rows = draw(st.sets(row_strategy, max_size=_MAX_FACT_ROWS_PER_PREDICATE))
        if rows:
            facts[predicate] = sorted(rows)
    return facts


def _ensure_seed_fact(facts: dict[str, list[tuple[str, ...]]], constants: tuple[str, ...]) -> None:
    if any(facts.get(predicate) for predicate in _SEED_PREDICATES):
        return

    facts.setdefault("chicken", []).append((constants[0],))
    facts["chicken"] = sorted(set(facts["chicken"]))


def _draw_rule_kinds(draw: Any, count: int) -> list[bool]:
    if count == 0:
        return []

    kinds = [draw(st.booleans()) for _ in range(count)]
    if count > 1 and (all(kinds) or not any(kinds)):
        kinds[-1] = not kinds[-1]
    return kinds


def _render_rule(head: str, body: list[str]) -> str:
    return f"{head} :- {', '.join(body)}."
