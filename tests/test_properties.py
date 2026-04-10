from __future__ import annotations

from dataclasses import dataclass
from itertools import product
from typing import cast

from hypothesis import given, settings
from hypothesis import strategies as st

from datalog_conformance.schema import (
    DefeasibleModel,
    DefeasibleTheory,
    FactTuple,
    Model,
    Program,
)
from datalog_conformance.strategies import (
    GeneratedDefeasibleTheory,
    GeneratedProgram,
    conflict_free_defeasible_theories,
    facts_only_programs,
    positive_programs,
    strict_only_defeasible_theories,
)

_PROPERTY_SETTINGS = settings(deadline=None, max_examples=40)
_KLM_SETTINGS = settings(deadline=None, max_examples=80)
_WORLD_COUNT = 8
_ALL_WORLDS_MASK = (1 << _WORLD_COUNT) - 1


@dataclass(frozen=True, slots=True)
class Atom:
    predicate: str
    arguments: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RankedModel:
    ranks: tuple[int, ...]


def _formulas() -> st.SearchStrategy[int]:
    return st.integers(min_value=0, max_value=_ALL_WORLDS_MASK)


def _ranked_models() -> st.SearchStrategy[RankedModel]:
    return st.builds(
        RankedModel,
        ranks=st.tuples(*[st.integers(min_value=0, max_value=3) for _ in range(_WORLD_COUNT)]),
    )


@given(positive_programs())
@_PROPERTY_SETTINGS
def test_reference_model_is_a_fixpoint(generated: GeneratedProgram) -> None:
    model = _evaluate_program(generated.program)
    one_step = _apply_rules_once(generated.program, model.facts)
    assert one_step == model.facts


@given(positive_programs())
@_PROPERTY_SETTINGS
def test_positive_programs_are_monotone_under_added_facts(
    generated: GeneratedProgram,
) -> None:
    baseline = _evaluate_program(generated.program).facts
    augmented_program = _with_extra_fact(generated)
    augmented = _evaluate_program(augmented_program).facts
    assert _is_model_subset(baseline, augmented)


@given(positive_programs())
@_PROPERTY_SETTINGS
def test_reference_evaluation_is_deterministic(generated: GeneratedProgram) -> None:
    assert _evaluate_program(generated.program) == _evaluate_program(generated.program)


@given(positive_programs())
@_PROPERTY_SETTINGS
def test_stratum_prefix_models_are_subsets_of_the_final_model(
    generated: GeneratedProgram,
) -> None:
    final_model = _evaluate_program(generated.program).facts
    prefix_rules: list[str] = []
    for group in generated.rule_groups:
        prefix_rules.extend(group)
        prefix_model = _evaluate_program(
            Program(facts=generated.program.facts, rules=prefix_rules)
        ).facts
        assert _is_model_subset(prefix_model, final_model)


def test_empty_program_evaluates_to_the_empty_model() -> None:
    model = _evaluate_program(Program(facts={}, rules=[]))
    assert model.facts == {}


@given(facts_only_programs())
@_PROPERTY_SETTINGS
def test_facts_only_programs_evaluate_to_their_input_facts(
    generated: GeneratedProgram,
) -> None:
    model = _evaluate_program(generated.program)
    assert model.facts == _normalize_fact_mapping(generated.program.facts)


@given(conflict_free_defeasible_theories())
@_PROPERTY_SETTINGS
def test_definite_conclusions_are_always_defeasible(
    generated: GeneratedDefeasibleTheory,
) -> None:
    model = _evaluate_conflict_free_theory(generated.theory)
    definitely = model.sections["definitely"]
    defeasibly = model.sections["defeasibly"]
    assert _is_model_subset(definitely, defeasibly)


@given(strict_only_defeasible_theories())
@_PROPERTY_SETTINGS
def test_strict_only_theories_match_standard_datalog(
    generated: GeneratedDefeasibleTheory,
) -> None:
    datalog_model = _evaluate_program(generated.strict_program).facts
    defeasible_model = _evaluate_conflict_free_theory(generated.theory).sections
    assert defeasible_model["definitely"] == datalog_model
    assert defeasible_model["defeasibly"] == datalog_model


@given(_ranked_models(), _formulas())
@_KLM_SETTINGS
def test_ranked_models_satisfy_reflexivity(
    model: RankedModel,
    alpha: int,
) -> None:
    assert _ranked_entails(model, alpha, alpha)


@given(_ranked_models(), _formulas(), _formulas())
@_KLM_SETTINGS
def test_ranked_models_satisfy_left_logical_equivalence(
    model: RankedModel,
    alpha: int,
    gamma: int,
) -> None:
    beta = alpha
    if _classically_equivalent(alpha, beta) and _ranked_entails(model, alpha, gamma):
        assert _ranked_entails(model, beta, gamma)


@given(_ranked_models(), _formulas(), _formulas(), _formulas())
@_KLM_SETTINGS
def test_ranked_models_satisfy_right_weakening(
    model: RankedModel,
    alpha: int,
    beta: int,
    gamma: int,
) -> None:
    if _ranked_entails(model, alpha, beta) and _classically_entails(beta, gamma):
        assert _ranked_entails(model, alpha, gamma)


@given(_ranked_models(), _formulas(), _formulas(), _formulas())
@_KLM_SETTINGS
def test_ranked_models_satisfy_conjunction(
    model: RankedModel,
    alpha: int,
    beta: int,
    gamma: int,
) -> None:
    if _ranked_entails(model, alpha, beta) and _ranked_entails(model, alpha, gamma):
        assert _ranked_entails(model, alpha, beta & gamma)


@given(_ranked_models(), _formulas(), _formulas(), _formulas())
@_KLM_SETTINGS
def test_ranked_models_satisfy_disjunction(
    model: RankedModel,
    alpha: int,
    beta: int,
    gamma: int,
) -> None:
    if _ranked_entails(model, alpha, gamma) and _ranked_entails(model, beta, gamma):
        assert _ranked_entails(model, alpha | beta, gamma)


@given(_ranked_models(), _formulas(), _formulas(), _formulas())
@_KLM_SETTINGS
def test_ranked_models_satisfy_cautious_monotonicity(
    model: RankedModel,
    alpha: int,
    beta: int,
    gamma: int,
) -> None:
    if _ranked_entails(model, alpha, beta) and _ranked_entails(model, alpha, gamma):
        assert _ranked_entails(model, alpha & beta, gamma)


@given(_ranked_models(), _formulas(), _formulas(), _formulas())
@_KLM_SETTINGS
def test_ranked_models_satisfy_rational_monotonicity(
    model: RankedModel,
    alpha: int,
    beta: int,
    gamma: int,
) -> None:
    if _ranked_entails(model, alpha, beta) and not _ranked_entails(
        model, alpha, _negate(gamma)
    ):
        assert _ranked_entails(model, alpha & gamma, beta)


def _evaluate_program(program: Program) -> Model:
    facts = _normalize_fact_mapping(program.facts)
    while True:
        next_facts = _apply_rules_once(program, facts)
        if next_facts == facts:
            return Model(facts=next_facts)
        facts = next_facts


def _evaluate_conflict_free_theory(theory: DefeasibleTheory) -> DefeasibleModel:
    strict_program = Program(
        facts=theory.facts,
        rules=[_render_rule(rule.head, rule.body) for rule in theory.strict_rules],
    )
    combined_program = Program(
        facts=theory.facts,
        rules=[
            _render_rule(rule.head, rule.body)
            for rule in [*theory.strict_rules, *theory.defeasible_rules]
        ],
    )
    definitely = _evaluate_program(strict_program).facts
    defeasibly = _evaluate_program(combined_program).facts
    return DefeasibleModel(
        sections={
            "definitely": definitely,
            "defeasibly": defeasibly,
        }
    )


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
    domain: tuple[str, ...],
) -> list[dict[str, str]]:
    if not body:
        return [{}]

    variables = sorted({item for atom in body for item in atom.arguments if _is_variable(item)})
    if not variables:
        return [{}] if _body_holds(body, facts, {}) else []

    matches: list[dict[str, str]] = []
    for values in product(domain, repeat=len(variables)):
        substitution = dict(zip(variables, values, strict=True))
        if _body_holds(body, facts, substitution):
            matches.append(substitution)
    return matches


def _body_holds(
    body: list[Atom],
    facts: dict[str, set[FactTuple]],
    substitution: dict[str, str],
) -> bool:
    for atom in body:
        instantiated = _instantiate_atom(atom, substitution)
        if instantiated.arguments not in facts.get(instantiated.predicate, set()):
            return False
    return True


def _instantiate_atom(atom: Atom, substitution: dict[str, str]) -> Atom:
    arguments = tuple(substitution.get(argument, argument) for argument in atom.arguments)
    return Atom(predicate=atom.predicate, arguments=arguments)


def _active_domain(facts: dict[str, set[FactTuple]]) -> tuple[str, ...]:
    values = {cast(str, value) for rows in facts.values() for row in rows for value in row}
    if not values:
        return ("a",)
    return tuple(sorted(values))


def _with_extra_fact(generated: GeneratedProgram) -> Program:
    signature = generated.signatures[0]
    facts = {
        predicate: [tuple(row) for row in rows]
        for predicate, rows in generated.program.facts.items()
    }
    facts.setdefault(signature.name, []).append(tuple("d" for _ in range(signature.arity)))
    return Program(facts=facts, rules=list(generated.program.rules))


def _normalize_fact_mapping(
    raw_facts: dict[str, list[FactTuple]],
) -> dict[str, set[FactTuple]]:
    return {predicate: set(rows) for predicate, rows in raw_facts.items()}


def _is_model_subset(
    left: dict[str, set[FactTuple]],
    right: dict[str, set[FactTuple]],
) -> bool:
    return all(rows <= right.get(predicate, set()) for predicate, rows in left.items())


def _render_rule(head: str, body: list[str]) -> str:
    return f"{head} :- {', '.join(body)}."


def _is_variable(value: str) -> bool:
    return value[:1].isupper()


def _ranked_entails(model: RankedModel, alpha: int, beta: int) -> bool:
    alpha_worlds = _worlds(alpha)
    if not alpha_worlds:
        return True
    best_rank = min(model.ranks[index] for index in alpha_worlds)
    best_worlds = [index for index in alpha_worlds if model.ranks[index] == best_rank]
    return all(_contains_world(beta, index) for index in best_worlds)


def _classically_entails(alpha: int, beta: int) -> bool:
    return alpha & _negate(beta) == 0


def _classically_equivalent(alpha: int, beta: int) -> bool:
    return alpha == beta


def _negate(formula: int) -> int:
    return _ALL_WORLDS_MASK ^ formula


def _worlds(formula: int) -> list[int]:
    return [index for index in range(_WORLD_COUNT) if _contains_world(formula, index)]


def _contains_world(formula: int, world_index: int) -> bool:
    return (formula & (1 << world_index)) != 0
