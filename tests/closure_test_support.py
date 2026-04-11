from __future__ import annotations

from dataclasses import dataclass
from itertools import product
from pathlib import Path
from typing import cast

import yaml

from datalog_conformance.schema import DefeasibleModel, DefeasibleTheory, Policy, Rule, TestCase

World = frozenset[str]


@dataclass(frozen=True, slots=True)
class RankedDefaults:
    atoms: tuple[str, ...]
    worlds: tuple[World, ...]
    finite_ranks: tuple[tuple[Rule, ...], ...]
    infinite_rank: tuple[Rule, ...]


class PropositionalClosureEvaluator:
    """Reduced ranked-worlds reference for zero-arity closure examples."""

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


def load_suite_cases(relative_path: Path) -> list[TestCase]:
    repo_tests_dir = Path(__file__).resolve().parents[1] / "src" / "datalog_conformance" / "_tests"
    yaml_path = repo_tests_dir / relative_path
    raw = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    assert isinstance(raw, dict)
    data = cast(dict[object, object], raw)

    raw_base_tags = data.get("tags", [])
    base_tags = list(cast(list[object], raw_base_tags)) if isinstance(raw_base_tags, list) else []
    base_source = data.get("source")
    base_verification = data.get("verification")
    entries_obj = data.get("tests", [])
    assert isinstance(entries_obj, list)
    entries = cast(list[object], entries_obj)

    cases: list[TestCase] = []
    for entry in entries:
        assert isinstance(entry, dict)
        merged = dict(cast(dict[object, object], entry))
        if "source" not in merged and base_source is not None:
            merged["source"] = base_source
        if "verification" not in merged and base_verification is not None:
            merged["verification"] = base_verification
        if base_tags:
            local_tags_obj = merged.get("tags", [])
            assert isinstance(local_tags_obj, list)
            local_tags = cast(list[object], local_tags_obj)
            merged["tags"] = [*base_tags, *local_tags]
        cases.append(TestCase.from_dict(merged))
    return cases


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
        current_rank_items: list[Rule] = [
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
    context_worlds = [
        world
        for world in ranked.worlds
        if _world_satisfies_literals(world, facts)
        and _world_satisfies_rules(world, theory.strict_rules)
    ]
    if not context_worlds:
        return False

    if policy is Policy.RATIONAL_CLOSURE:
        best_score = min(_rational_score(ranked, world) for world in context_worlds)
        preferred = [
            world
            for world in context_worlds
            if _rational_score(ranked, world) == best_score
        ]
    else:
        best_score = min(_lexicographic_score(ranked, world) for world in context_worlds)
        preferred = [
            world
            for world in context_worlds
            if _lexicographic_score(ranked, world) == best_score
        ]

    return all(_literal_holds(world, query) for world in preferred)


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
