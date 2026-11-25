"""Exhaustive reference for the finite grounded García–Simari corpus.

Definitions 2.5, 3.1–3.5, 4.1–4.7 and 5.1–5.3 of García & Simari (2004),
pp. 100–120, doi:10.1017/S1471068403001674. The corpus uses strong negation,
strict rules and defeasible rules with generalized specificity.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from functools import cache
from itertools import combinations
from typing import TypeVar

from datalog_conformance.schema import DefeasibleModel, DefeasibleTheory, FactTuple, Program, Rule

from .core import CoreReferenceEvaluator, RuleAst, ground_positive_instances, parse_rules

Atom = tuple[str, FactTuple]
Atoms = frozenset[Atom]
_Item = TypeVar("_Item")


@dataclass(frozen=True, slots=True)
class GroundRule:
    head: Atom
    body: Atoms


@dataclass(frozen=True, slots=True)
class _Argument:
    head: Atom
    support: frozenset[GroundRule]


def evaluate_corpus_theory(theory: DefeasibleTheory) -> DefeasibleModel:
    """Ground the generated corpus's positive bodies using the core reference."""
    if theory.defeaters or theory.superiority or theory.conflicts:
        raise ValueError("The García corpus uses strict and defeasible rules only")
    facts = {_encode(predicate): rows for predicate, rows in theory.facts.items()}
    strict = [_rule_text(rule) for rule in theory.strict_rules]
    defeasible = [_rule_text(rule) for rule in theory.defeasible_rules]
    possible = CoreReferenceEvaluator().evaluate(Program(facts, strict + defeasible)).facts
    return evaluate_ground_program(
        frozenset((predicate, row) for predicate, rows in theory.facts.items() for row in rows),
        _ground(parse_rules(strict), possible),
        _ground(parse_rules(defeasible), possible),
    )


def _encode(literal: str) -> str:
    return f"n_{literal[1:]}" if literal.startswith("~") else f"p_{literal}"


def _decode(predicate: str) -> str:
    return "~" + predicate[2:] if predicate.startswith("n_") else predicate[2:]


def _rule_text(rule: Rule) -> str:
    head = _encode(rule.head)
    return f"{head} :- {', '.join(map(_encode, rule.body))}." if rule.body else f"{head}."


def _ground(rules: list[RuleAst], possible: dict[str, set[FactTuple]]) -> frozenset[GroundRule]:
    return frozenset(
        GroundRule((_decode(pred), row), frozenset((_decode(name), args) for name, args in body))
        for (pred, row), body in ground_positive_instances(rules, possible)
    )


def evaluate_ground_program(
    facts: Atoms,
    strict: frozenset[GroundRule],
    defeasible: frozenset[GroundRule],
) -> DefeasibleModel:
    """Report the four corpus sections over facts and grounded rule heads."""
    definite = _closure(facts, strict)
    if not _consistent(definite):
        raise ValueError("The strict part of a DeLP program must be consistent")
    rules = strict | defeasible
    warranted: set[Atom] = set()
    domain = facts | frozenset(rule.head for rule in rules)
    for component in _components(domain, rules):
        warranted.update(
            _warranted(
                facts & component,
                frozenset(rule for rule in strict if rule.head in component),
                frozenset(rule for rule in defeasible if rule.head in component),
            )
        )

    sections: dict[str, dict[str, set[FactTuple]]] = {}
    for predicate, row in definite:
        sections.setdefault("definitely", {}).setdefault(predicate, set()).add(row)
    for atom in domain:
        predicate, row = atom
        if atom in warranted:
            section = "defeasibly"
        elif _complement(atom) in warranted:
            section = "not_defeasibly"
        else:
            section = "undecided"
        sections.setdefault(section, {}).setdefault(predicate, set()).add(row)
    return DefeasibleModel(sections)


def _warranted(
    facts: Atoms,
    strict: frozenset[GroundRule],
    defeasible: frozenset[GroundRule],
) -> set[Atom]:
    @cache
    def closure(seeds: Atoms, support: frozenset[GroundRule] = frozenset()) -> Atoms:
        return _closure(seeds, strict | support)

    possible = closure(facts, defeasible)
    arguments: set[_Argument] = set()
    # Def. 3.1. Enumerating the powerset by size admits minimal consistent supports.
    for support in _subsets(defeasible):
        consequences = closure(facts, support)
        if not _consistent(consequences):
            continue
        for head in consequences:
            if not any(arg.head == head and arg.support <= support for arg in arguments):
                arguments.add(_Argument(head, support))

    @cache
    def activations(argument: _Argument) -> tuple[Atoms, ...]:
        # Def. 3.5. Facts outside the backward dependency cone cannot affect
        # derivability of the head. Enumerate the possible facts inside it.
        ancestors = {argument.head}
        while True:
            extended = ancestors.union(
                *(rule.body for rule in strict | argument.support if rule.head in ancestors)
            )
            if extended == ancestors:
                break
            ancestors = extended
        return tuple(
            seeds
            for seeds in _subsets(possible & ancestors)
            if argument.head not in closure(seeds)
            and argument.head in closure(seeds, argument.support)
        )

    @cache
    def prefers(left: _Argument, right: _Argument) -> bool:
        return all(right.head in closure(h, right.support) for h in activations(left)) and any(
            left.head not in closure(h, left.support) for h in activations(right)
        )

    @cache
    def defeat(attacker: _Argument, target: _Argument) -> str | None:
        # Defs. 3.2–3.4 and 4.1–4.3. Test every disagreement subargument.
        blocking = False
        for subargument in arguments:
            if not subargument.support <= target.support:
                continue
            if _consistent(closure(facts | {attacker.head, subargument.head})):
                continue
            if prefers(attacker, subargument):
                return "proper"
            blocking |= not prefers(subargument, attacker)
        return "blocking" if blocking else None

    @cache
    def undefeated(line: tuple[_Argument, ...], previous: str | None) -> bool:
        # Def. 4.7 and Procedure 5.1. Track same-side agreement and line use.
        same_side = frozenset(rule for arg in line[len(line) % 2 :: 2] for rule in arg.support)
        for attacker in arguments:
            if any(attacker.support <= earlier.support for earlier in line):
                continue
            kind = defeat(attacker, line[-1])
            if kind is None or (previous == "blocking" and kind != "proper"):
                continue
            if not _consistent(closure(facts, same_side | attacker.support)):
                continue
            if undefeated((*line, attacker), kind):
                return False
        return True

    return {arg.head for arg in arguments if undefeated((arg,), None)}


def _closure(seeds: Atoms, rules: frozenset[GroundRule]) -> Atoms:
    current = seeds
    while True:
        updated = current | frozenset(rule.head for rule in rules if rule.body <= current)
        if updated == current:
            return current
        current = updated


def _consistent(atoms: Atoms) -> bool:
    return all(_complement(atom) not in atoms for atom in atoms)


def _complement(atom: Atom) -> Atom:
    predicate, row = atom
    return (predicate[1:] if predicate.startswith("~") else f"~{predicate}"), row


def _subsets(items: Iterable[_Item]) -> Iterator[frozenset[_Item]]:
    ordered = tuple(items)
    for size in range(len(ordered) + 1):
        for subset in combinations(ordered, size):
            yield frozenset(subset)


def _components(domain: Atoms, rules: frozenset[GroundRule]) -> Iterator[Atoms]:
    """Split only where neither derivability nor disagreement crosses the split."""
    adjacent: dict[Atom, set[Atom]] = {atom: {_complement(atom)} for atom in domain}
    for rule in rules:
        adjacent.setdefault(rule.head, {_complement(rule.head)}).update(rule.body)
        for premise in rule.body:
            adjacent.setdefault(premise, {_complement(premise)}).add(rule.head)
    remaining = set(domain)
    while remaining:
        seen: set[Atom] = set()
        pending = [remaining.pop()]
        while pending:
            atom = pending.pop()
            if atom not in seen:
                seen.add(atom)
                pending.extend(adjacent.get(atom, {_complement(atom)}) - seen)
        remaining.difference_update(seen)
        yield frozenset(seen)
