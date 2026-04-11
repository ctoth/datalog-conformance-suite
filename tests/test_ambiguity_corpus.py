from __future__ import annotations

from pathlib import Path
from typing import cast

import yaml

from datalog_conformance.plugin import get_tests_dir
from datalog_conformance.runner import YamlTestRunner
from datalog_conformance.schema import DefeasibleModel, DefeasibleTheory, Policy, Rule, TestCase

_AMBIGUITY_FILE = Path("defeasible") / "ambiguity" / "antoniou_basic_ambiguity.yaml"


class AntoniouReferenceEvaluator:
    """Small propositional reference for the Antoniou ambiguity-policy fragment."""

    def evaluate(self, theory: DefeasibleTheory, policy: Policy) -> DefeasibleModel:
        _ensure_propositional(theory)

        atoms = _atom_universe(theory)
        definite = _definite_closure(theory)
        supported, defeasible = _supported_and_defeasible(theory, policy, atoms, definite)

        sections = {
            "definitely": _atoms_to_section(definite),
            "defeasibly": _atoms_to_section(defeasible),
            "undecided": _atoms_to_section(supported - defeasible),
            "not_defeasibly": _atoms_to_section(atoms - supported),
        }
        return DefeasibleModel(
            sections={name: facts for name, facts in sections.items() if facts}
        )


def test_antoniou_ambiguity_corpus_matches_local_reference() -> None:
    yaml_path = get_tests_dir() / _AMBIGUITY_FILE
    raw = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    assert isinstance(raw, dict)
    cases = _load_suite_cases(cast(dict[object, object], raw))

    assert [case.name for case in cases] == [
        "antoniou_ambiguous_attacker_blocks_only_in_propagating",
        "antoniou_ambiguity_propagates_to_downstream_rule",
    ]

    runner = YamlTestRunner(AntoniouReferenceEvaluator())
    for case in cases:
        runner.run_test_case(case)


def _ensure_propositional(theory: DefeasibleTheory) -> None:
    for predicate, rows in theory.facts.items():
        if any(row for row in rows):
            raise ValueError(f"Antoniou reference expects zero-arity facts, got {predicate}")
    for collection in (theory.strict_rules, theory.defeasible_rules, theory.defeaters):
        for rule in collection:
            _ensure_zero_arity_literal(rule.head)
            for item in rule.body:
                _ensure_zero_arity_literal(item)


def _ensure_zero_arity_literal(text: str) -> None:
    if "(" in text or ")" in text:
        raise ValueError(f"Antoniou reference expects zero-arity literals, got {text!r}")


def _atom_universe(theory: DefeasibleTheory) -> set[str]:
    atoms = set(theory.facts)
    for collection in (theory.strict_rules, theory.defeasible_rules, theory.defeaters):
        for rule in collection:
            atoms.add(rule.head)
            atoms.update(rule.body)
    expanded = set(atoms)
    for atom in atoms:
        expanded.add(_complement(atom))
    return expanded


def _definite_closure(theory: DefeasibleTheory) -> set[str]:
    definite = set(theory.facts)
    strict_rules = list(theory.strict_rules)
    changed = True
    while changed:
        changed = False
        for rule in strict_rules:
            if rule.head in definite:
                continue
            if set(rule.body) <= definite:
                definite.add(rule.head)
                changed = True
    return definite


def _supported_and_defeasible(
    theory: DefeasibleTheory,
    policy: Policy,
    atoms: set[str],
    definite: set[str],
) -> tuple[set[str], set[str]]:
    supportive_rules = [*theory.strict_rules, *theory.defeasible_rules]
    superiority = set(theory.superiority)
    supported = set(definite)
    defeasible = set(definite)

    changed = True
    while changed:
        changed = False

        for atom in atoms:
            if atom in supported or _complement(atom) in definite:
                continue
            if _can_support(
                atom,
                supportive_rules,
                superiority,
                supported,
                defeasible,
            ):
                supported.add(atom)
                changed = True

        for atom in atoms:
            if atom in defeasible or _complement(atom) in definite:
                continue
            if _can_prove(
                atom,
                supportive_rules,
                superiority,
                supported,
                defeasible,
                policy,
            ):
                defeasible.add(atom)
                changed = True

    return supported, defeasible


def _can_support(
    atom: str,
    supportive_rules: list[Rule],
    superiority: set[tuple[str, str]],
    supported: set[str],
    defeasible: set[str],
) -> bool:
    return any(
        rule.head == atom
        and set(rule.body) <= supported
        and not _is_defeated(rule, supportive_rules, superiority, defeasible)
        for rule in supportive_rules
    )


def _can_prove(
    atom: str,
    supportive_rules: list[Rule],
    superiority: set[tuple[str, str]],
    supported: set[str],
    defeasible: set[str],
    policy: Policy,
) -> bool:
    return any(
        rule.head == atom
        and set(rule.body) <= defeasible
        and not _is_overruled(
            rule,
            supportive_rules,
            superiority,
            supported,
            defeasible,
            policy,
        )
        for rule in supportive_rules
    )


def _is_overruled(
    target_rule: Rule,
    supportive_rules: list[Rule],
    superiority: set[tuple[str, str]],
    supported: set[str],
    defeasible: set[str],
    policy: Policy,
) -> bool:
    attacker_basis = supported if policy is Policy.PROPAGATING else defeasible
    target_atom = target_rule.head
    for rule in supportive_rules:
        if rule.head != _complement(target_atom):
            continue
        if set(rule.body) <= attacker_basis and not _is_defeated(
            rule,
            supportive_rules,
            superiority,
            defeasible,
        ):
            return True
    return False


def _is_defeated(
    target_rule: Rule,
    supportive_rules: list[Rule],
    superiority: set[tuple[str, str]],
    defeasible: set[str],
) -> bool:
    target_atom = target_rule.head
    for rule in supportive_rules:
        if rule.head != _complement(target_atom):
            continue
        if (rule.id, target_rule.id) not in superiority:
            continue
        if set(rule.body) <= defeasible:
            return True
    return False


def _atoms_to_section(atoms: set[str]) -> dict[str, set[tuple[()]]]:
    return {atom: {()} for atom in sorted(atoms)}


def _complement(atom: str) -> str:
    if atom.startswith("~"):
        return atom[1:]
    return f"~{atom}"


def _load_suite_cases(raw: dict[object, object]) -> list[TestCase]:
    raw_base_tags = raw.get("tags", [])
    base_tags = list(cast(list[object], raw_base_tags)) if isinstance(raw_base_tags, list) else []
    base_source = raw.get("source")
    base_verification = raw.get("verification")
    entries_obj = raw.get("tests", [])
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
