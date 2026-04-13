"""Reduced ranked-world closure reference for Morris 2020 conformance cases.

This module keeps the exact world-enumerating reference used for the current
zero-arity closure corpus. It mirrors the ranking and entailment structure of
Morris, Ross, and Meyer 2020 for the reduced propositional fragment covered by
the local page-image-derived cases:

- Algorithm 3 / BaseRankDatalog (p. 150, local ``page-009.png``)
- Algorithm 4 / RationalClosureDatalog (p. 151, local ``page-010.png``)
- Algorithm 6 / RelevantClosureDatalog (p. 153, local ``page-012.png``)
- Example 6 and the subset-ranking discussion (pp. 156-158, local
  ``page-015.png`` through ``page-017.png``)
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations, product
from typing import Callable

from ..schema import DefeasibleModel, DefeasibleTheory, Policy, Rule

World = frozenset[str]


@dataclass(frozen=True, slots=True)
class RankedDefaults:
    atoms: tuple[str, ...]
    worlds: tuple[World, ...]
    finite_ranks: tuple[tuple[Rule, ...], ...]
    infinite_rank: tuple[Rule, ...]


@dataclass(frozen=True, slots=True)
class Formula:
    kind: str
    literal: str | None = None
    left: "Formula | None" = None
    right: "Formula | None" = None


class PropositionalClosureEvaluator:
    """Exact ranked-worlds reference for the supported zero-arity closure fragment."""

    def evaluate(self, theory: DefeasibleTheory, policy: Policy) -> DefeasibleModel:
        if policy not in {
            Policy.RATIONAL_CLOSURE,
            Policy.LEXICOGRAPHIC_CLOSURE,
        }:
            raise ValueError(f"Unsupported closure policy for reduced reference: {policy.value}")

        _ensure_propositional(theory)
        ranked = _ranked_defaults(theory)
        facts = _fact_literals(theory)
        definite = _strict_closure(facts, theory.strict_rules)
        literals = _literal_universe(theory)

        defeasible = {
            literal
            for literal in literals
            if _closure_entails(ranked, theory, facts, literal, policy)
        }
        defeasible.update(definite)
        not_defeasible = literals - defeasible

        sections: dict[str, dict[str, set[tuple[()]]]] = {}
        if definite:
            sections["definitely"] = _atoms_to_section(definite)
        if defeasible:
            sections["defeasibly"] = _atoms_to_section(defeasible)
        if not_defeasible:
            sections["not_defeasibly"] = _atoms_to_section(not_defeasible)
        return DefeasibleModel(sections=sections)

    def satisfies_klm_property(
        self,
        theory: DefeasibleTheory,
        property_name: str,
        policy: Policy,
    ) -> bool:
        if property_name != "Or":
            raise ValueError(f"Unsupported KLM property for reduced reference: {property_name}")

        if policy not in {
            Policy.RATIONAL_CLOSURE,
            Policy.LEXICOGRAPHIC_CLOSURE,
            Policy.RELEVANT_CLOSURE,
        }:
            raise ValueError(f"Unsupported closure policy for reduced reference: {policy.value}")

        _ensure_propositional(theory)
        ranked = _ranked_defaults(theory)
        literals = sorted(_literal_universe(theory))

        for left_literal in literals:
            left = _literal_formula(left_literal)
            for right_literal in literals:
                right = _literal_formula(right_literal)
                disjunction = _or_formula(left, right)
                for consequent_literal in literals:
                    consequent = _literal_formula(consequent_literal)
                    if not _formula_entails(ranked, theory, left, consequent, policy):
                        continue
                    if not _formula_entails(ranked, theory, right, consequent, policy):
                        continue
                    if not _formula_entails(ranked, theory, disjunction, consequent, policy):
                        return False
        return True


def _ensure_propositional(theory: DefeasibleTheory) -> None:
    if theory.defeaters:
        raise ValueError("Reduced closure reference does not support defeaters")
    if theory.superiority:
        raise ValueError("Reduced closure reference does not support superiority")
    if theory.conflicts:
        raise ValueError("Reduced closure reference does not support explicit conflict sets")

    for predicate, rows in theory.facts.items():
        for row in rows:
            if tuple(row) != ():
                raise ValueError(
                    "Reduced closure reference expects zero-arity facts, "
                    f"got {predicate}{tuple(row)!r}"
                )
    for collection in (theory.strict_rules, theory.defeasible_rules):
        for rule in collection:
            _ensure_zero_arity_literal(rule.head)
            for item in rule.body:
                _ensure_zero_arity_literal(item)


def _ensure_zero_arity_literal(text: str) -> None:
    if "(" in text or ")" in text:
        raise ValueError(f"Reduced closure reference expects zero-arity literals, got {text!r}")


def _ranked_defaults(theory: DefeasibleTheory) -> RankedDefaults:
    atoms = tuple(sorted(_positive_atoms(theory)))
    worlds = tuple(_all_worlds(atoms))

    remaining: list[Rule] = list(theory.defeasible_rules)
    finite_ranks: list[tuple[Rule, ...]] = []
    while remaining:
        active_rules: list[Rule] = [*theory.strict_rules, *remaining]
        current_rank_items = [
            rule
            for rule in remaining
            if _has_supporting_world(worlds, active_rules, set(rule.body))
        ]
        current_rank = tuple(current_rank_items)
        if not current_rank:
            break
        current_ids = {rule.id for rule in current_rank}
        finite_ranks.append(current_rank)
        remaining = [rule for rule in remaining if rule.id not in current_ids]

    return RankedDefaults(
        atoms=atoms,
        worlds=worlds,
        finite_ranks=tuple(finite_ranks),
        infinite_rank=tuple(remaining),
    )


def _positive_atoms(theory: DefeasibleTheory) -> set[str]:
    atoms = {_positive_atom(predicate) for predicate, rows in theory.facts.items() if rows}
    for collection in (theory.strict_rules, theory.defeasible_rules):
        for rule in collection:
            atoms.add(_positive_atom(rule.head))
            atoms.update(_positive_atom(item) for item in rule.body)
    return atoms


def _literal_universe(theory: DefeasibleTheory) -> set[str]:
    atoms = _positive_atoms(theory)
    return {literal for atom in atoms for literal in (atom, _complement(atom))}


def _all_worlds(atoms: tuple[str, ...]) -> list[World]:
    worlds: list[World] = []
    for truth_values in product((False, True), repeat=len(atoms)):
        worlds.append(
            frozenset(atom for atom, truthy in zip(atoms, truth_values, strict=True) if truthy)
        )
    return worlds


def _has_supporting_world(worlds: tuple[World, ...], rules: list[Rule], body: set[str]) -> bool:
    return any(
        _world_satisfies_literals(world, body) and _world_satisfies_rules(world, rules)
        for world in worlds
    )


def _fact_literals(theory: DefeasibleTheory) -> set[str]:
    return {predicate for predicate, rows in theory.facts.items() if rows}


def _strict_closure(facts: set[str], strict_rules: list[Rule]) -> set[str]:
    closure = set(facts)
    changed = True
    while changed:
        changed = False
        for rule in strict_rules:
            if rule.head in closure:
                continue
            if set(rule.body) <= closure:
                closure.add(rule.head)
                changed = True
    return closure


def _closure_entails(
    ranked: RankedDefaults,
    theory: DefeasibleTheory,
    facts: set[str],
    query: str,
    policy: Policy,
) -> bool:
    antecedent = _conjunction_formula(sorted(facts))
    consequent = _literal_formula(query)
    return _formula_entails(ranked, theory, antecedent, consequent, policy)


def _formula_entails(
    ranked: RankedDefaults,
    theory: DefeasibleTheory,
    antecedent: Formula,
    consequent: Formula,
    policy: Policy,
) -> bool:
    if policy is Policy.RATIONAL_CLOSURE:
        return _ranked_formula_entails(
            ranked,
            theory,
            antecedent,
            consequent,
            score=_rational_score,
        )
    if policy is Policy.LEXICOGRAPHIC_CLOSURE:
        return _ranked_formula_entails(
            ranked,
            theory,
            antecedent,
            consequent,
            score=_lexicographic_score,
        )
    if policy is Policy.RELEVANT_CLOSURE:
        return _relevant_formula_entails(ranked, theory, antecedent, consequent)
    raise ValueError(f"Unsupported closure policy for reduced reference: {policy.value}")


def _ranked_formula_entails(
    ranked: RankedDefaults,
    theory: DefeasibleTheory,
    antecedent: Formula,
    consequent: Formula,
    *,
    score: Callable[[RankedDefaults, World], int | tuple[int, ...]],
) -> bool:
    context_worlds = [
        world
        for world in ranked.worlds
        if _formula_holds(world, antecedent) and _world_satisfies_rules(world, theory.strict_rules)
    ]
    if not context_worlds:
        # Morris 2020 Algorithms 4 and 6 reduce the final step to classical
        # implication of alpha -> beta after exceptional levels are removed.
        # When alpha is impossible the implication is vacuously true, so the
        # reference must not treat the empty context as an automatic failure.
        return _classically_entails(
            ranked.worlds,
            theory.strict_rules,
            list(theory.defeasible_rules),
            antecedent,
            consequent,
        )

    best_score = min(score(ranked, world) for world in context_worlds)
    preferred = [world for world in context_worlds if score(ranked, world) == best_score]
    return all(_formula_holds(world, consequent) for world in preferred)


def _relevant_formula_entails(
    ranked: RankedDefaults,
    theory: DefeasibleTheory,
    antecedent: Formula,
    consequent: Formula,
) -> bool:
    relevant_ids = _minimal_relevant_rule_ids(ranked, theory, antecedent)
    active_defaults = list(theory.defeasible_rules)

    for level in ranked.finite_ranks:
        if not _is_exceptional(ranked.worlds, theory.strict_rules, active_defaults, antecedent):
            break
        active_defaults = [
            rule
            for rule in active_defaults
            if rule.id not in relevant_ids or rule not in level
        ]

    return _classically_entails(
        ranked.worlds,
        theory.strict_rules,
        active_defaults,
        antecedent,
        consequent,
    )


def _minimal_relevant_rule_ids(
    ranked: RankedDefaults,
    theory: DefeasibleTheory,
    antecedent: Formula,
) -> set[str]:
    defaults = list(theory.defeasible_rules)
    justifications: list[tuple[Rule, ...]] = []

    for size in range(1, len(defaults) + 1):
        for subset in combinations(defaults, size):
            subset_ids = {rule.id for rule in subset}
            if any(
                {rule.id for rule in existing}.issubset(subset_ids)
                for existing in justifications
            ):
                continue
            if not _is_exceptional(ranked.worlds, theory.strict_rules, list(subset), antecedent):
                continue
            justifications.append(subset)

    relevant_ids: set[str] = set()
    for justification in justifications:
        min_rank = min(_rule_rank(ranked, rule) for rule in justification)
        relevant_ids.update(
            rule.id
            for rule in justification
            if _rule_rank(ranked, rule) == min_rank
        )
    return relevant_ids


def _rule_rank(ranked: RankedDefaults, target: Rule) -> int:
    for index, level in enumerate(ranked.finite_ranks):
        if any(rule.id == target.id for rule in level):
            return index
    return len(ranked.finite_ranks)


def _is_exceptional(
    worlds: tuple[World, ...],
    strict_rules: list[Rule],
    defaults: list[Rule],
    antecedent: Formula,
) -> bool:
    return not any(
        _formula_holds(world, antecedent)
        and _world_satisfies_rules(world, [*strict_rules, *defaults])
        for world in worlds
    )


def _classically_entails(
    worlds: tuple[World, ...],
    strict_rules: list[Rule],
    defaults: list[Rule],
    antecedent: Formula,
    consequent: Formula,
) -> bool:
    rules = [*strict_rules, *defaults]
    return all(
        not _formula_holds(world, antecedent) or _formula_holds(world, consequent)
        for world in worlds
        if _world_satisfies_rules(world, rules)
    )


def _literal_formula(literal: str) -> Formula:
    return Formula(kind="literal", literal=literal)


def _conjunction_formula(literals: list[str]) -> Formula:
    if not literals:
        return Formula(kind="true")
    formula = _literal_formula(literals[0])
    for literal in literals[1:]:
        formula = Formula(kind="and", left=formula, right=_literal_formula(literal))
    return formula


def _or_formula(left: Formula, right: Formula) -> Formula:
    return Formula(kind="or", left=left, right=right)


def _formula_holds(world: World, formula: Formula) -> bool:
    if formula.kind == "true":
        return True
    if formula.kind == "literal":
        assert formula.literal is not None
        return _literal_holds(world, formula.literal)
    if formula.kind == "and":
        assert formula.left is not None
        assert formula.right is not None
        return _formula_holds(world, formula.left) and _formula_holds(world, formula.right)
    if formula.kind == "or":
        assert formula.left is not None
        assert formula.right is not None
        return _formula_holds(world, formula.left) or _formula_holds(world, formula.right)
    raise ValueError(f"Unsupported reduced formula kind: {formula.kind}")


def _rational_score(ranked: RankedDefaults, world: World) -> int:
    if any(_violates(world, rule) for rule in ranked.infinite_rank):
        return len(ranked.finite_ranks) + 1

    worst_rank = -1
    for index, level in enumerate(ranked.finite_ranks):
        if any(_violates(world, rule) for rule in level):
            worst_rank = index
    return worst_rank + 1


def _lexicographic_score(ranked: RankedDefaults, world: World) -> tuple[int, ...]:
    if any(_violates(world, rule) for rule in ranked.infinite_rank):
        width = max(len(ranked.finite_ranks), 1)
        worst = len(ranked.infinite_rank) + sum(len(level) for level in ranked.finite_ranks) + 1
        return tuple(worst for _ in range(width))

    return tuple(
        sum(1 for rule in level if _violates(world, rule))
        for level in reversed(ranked.finite_ranks)
    )


def _world_satisfies_rules(world: World, rules: list[Rule]) -> bool:
    return all(
        not _world_satisfies_literals(world, set(rule.body)) or _literal_holds(world, rule.head)
        for rule in rules
    )


def _world_satisfies_literals(world: World, literals: set[str]) -> bool:
    return all(_literal_holds(world, literal) for literal in literals)


def _literal_holds(world: World, literal: str) -> bool:
    positive = _positive_atom(literal)
    if literal.startswith("~"):
        return positive not in world
    return positive in world


def _violates(world: World, rule: Rule) -> bool:
    return _world_satisfies_literals(world, set(rule.body)) and not _literal_holds(world, rule.head)


def _atoms_to_section(atoms: set[str]) -> dict[str, set[tuple[()]]]:
    return {atom: {()} for atom in sorted(atoms)}


def _positive_atom(literal: str) -> str:
    return literal[1:] if literal.startswith("~") else literal


def _complement(literal: str) -> str:
    if literal.startswith("~"):
        return literal[1:]
    return f"~{literal}"
