"""Packaged reference evaluator for the core Datalog conformance fragment.

This module gives the suite an internal oracle that can execute every bundled
core program case: positive rules, stratified ``not`` negation, ``_``
wildcards, quoted-string and numeric constants, head arithmetic (``a+b``),
and parenthesized comparison guards (``(n <= 25)``).

The evaluator enforces the same rejection surface the ``errors/`` corpus
expects. Every rejection raises a subclass of :class:`ReferenceEvaluationError`
whose ``code`` (and class name) line up with the ``expect_error`` values used
by harvested cases:

- ``arity_mismatch``: a predicate is used with inconsistent arities.
- ``safety_violations``: a wildcard appears in a rule head.
- ``unbound_variable``: a head, guard, or arithmetic variable is not bound by
  a positive body atom.
- ``SafetyViolationError`` (class) / ``safety_violations`` (code): a variable
  occurs only in a negated literal.
- ``cyclic_negation``: negation is not stratifiable.

Evaluation is semi-naive within each stratum, with per-predicate tuple sets.
Bare identifiers in rules are always variables regardless of case; constants
inside rules must be quoted strings or numeric literals. This matches the
conventions used by the harvested corpus and the Nemo verification
translator in ``scripts/verify_core_with_nemo.py``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from itertools import count
from typing import Iterator, Union

from ..schema import FactTuple, Model, Program, Scalar

_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_ATOM_RE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*(?:\((.*)\))?\s*$", re.DOTALL)
_INT_RE = re.compile(r"^-?\d+$")
_FLOAT_RE = re.compile(r"^-?\d+\.\d+$")
_COMPARISON_OPS = ("<=", ">=", "!=", "<", ">", "=")
_OPERAND_TAIL_CHARS = frozenset(
    '")_' + "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
)


class ReferenceEvaluationError(ValueError):
    """Base error for reference-evaluator rejections; carries a stable code."""

    code = "reference_evaluation_error"

    def __init__(self, message: str) -> None:
        super().__init__(message)


class ArityMismatchError(ReferenceEvaluationError):
    code = "arity_mismatch"


class SafetyViolationError(ReferenceEvaluationError):
    code = "safety_violations"


class UnboundVariableError(ReferenceEvaluationError):
    code = "unbound_variable"


class CyclicNegationError(ReferenceEvaluationError):
    code = "cyclic_negation"


class RuleSyntaxError(ReferenceEvaluationError):
    code = "rule_syntax_error"


@dataclass(frozen=True, slots=True)
class Variable:
    name: str


@dataclass(frozen=True, slots=True)
class Constant:
    value: Scalar


@dataclass(frozen=True, slots=True)
class Wildcard:
    token: int


@dataclass(frozen=True, slots=True)
class Arithmetic:
    op: str
    left: "Term"
    right: "Term"


Term = Union[Variable, Constant, Wildcard, Arithmetic]


@dataclass(frozen=True, slots=True)
class AtomAst:
    predicate: str
    terms: tuple[Term, ...]


@dataclass(frozen=True, slots=True)
class Comparison:
    op: str
    left: Term
    right: Term


@dataclass(frozen=True, slots=True)
class RuleAst:
    head: AtomAst
    positive: tuple[AtomAst, ...]
    negative: tuple[AtomAst, ...]
    comparisons: tuple[Comparison, ...]
    text: str


@dataclass(slots=True)
class _ParseContext:
    wildcard_counter: Iterator[int] = field(default_factory=count)


class CoreReferenceEvaluator:
    """Reference implementation of the core conformance evaluator protocol."""

    def evaluate(self, program: Program) -> Model:
        rules = parse_rules(program.rules)
        _validate(program, rules)
        strata = _stratify(rules)
        facts: dict[str, set[FactTuple]] = {
            predicate: set(rows) for predicate, rows in program.facts.items()
        }
        for stratum in strata:
            _evaluate_stratum(stratum, facts)
        return Model(facts=facts)


def parse_rules(rule_texts: list[str]) -> list[RuleAst]:
    """Parse rule strings, expanding conjunctive heads and `;` alternatives."""

    rules: list[RuleAst] = []
    for rule_text in rule_texts:
        rules.extend(_parse_rule(rule_text))
    return rules


def _parse_rule(rule_text: str) -> list[RuleAst]:
    text = rule_text.strip().removesuffix(".").strip()
    if not text:
        raise RuleSyntaxError(f"Empty rule text: {rule_text!r}")
    context = _ParseContext()
    if ":-" not in text:
        return [
            RuleAst(
                head=_parse_atom(head_text, context),
                positive=(),
                negative=(),
                comparisons=(),
                text=rule_text,
            )
            for head_text in _split_top_level(text, ",")
        ]

    head_text, body_text = text.split(":-", 1)
    heads = [_parse_atom(item, context) for item in _split_top_level(head_text, ",")]
    rules: list[RuleAst] = []
    for body_alternative in _split_top_level(body_text, ";"):
        positive: list[AtomAst] = []
        negative: list[AtomAst] = []
        comparisons: list[Comparison] = []
        for item in _split_top_level(body_alternative, ","):
            stripped = item.strip()
            if stripped.startswith("not "):
                negative.append(_parse_atom(stripped[4:], context))
                continue
            comparison = _try_parse_comparison(stripped, context)
            if comparison is not None:
                comparisons.append(comparison)
                continue
            positive.append(_parse_atom(stripped, context))
        for head in heads:
            rules.append(
                RuleAst(
                    head=head,
                    positive=tuple(positive),
                    negative=tuple(negative),
                    comparisons=tuple(comparisons),
                    text=rule_text,
                )
            )
    return rules


def _try_parse_comparison(text: str, context: _ParseContext) -> Comparison | None:
    stripped = text.strip()
    while stripped.startswith("(") and stripped.endswith(")") and _balanced(stripped[1:-1]):
        stripped = stripped[1:-1].strip()
    for op in _COMPARISON_OPS:
        parts = _split_top_level_operator(stripped, op)
        if parts is not None:
            left, right = parts
            return Comparison(
                op=op,
                left=_parse_term(left, context),
                right=_parse_term(right, context),
            )
    return None


def _parse_atom(atom_text: str, context: _ParseContext) -> AtomAst:
    match = _ATOM_RE.match(atom_text.strip())
    if match is None:
        raise RuleSyntaxError(f"Unsupported atom syntax: {atom_text!r}")
    predicate = match.group(1)
    raw_arguments = match.group(2)
    if raw_arguments is None or not raw_arguments.strip():
        return AtomAst(predicate=predicate, terms=())
    terms = tuple(
        _parse_term(item, context) for item in _split_top_level(raw_arguments, ",")
    )
    return AtomAst(predicate=predicate, terms=terms)


def _parse_term(term_text: str, context: _ParseContext) -> Term:
    stripped = term_text.strip()
    if not stripped:
        raise RuleSyntaxError(f"Empty term in {term_text!r}")
    while stripped.startswith("(") and stripped.endswith(")") and _balanced(stripped[1:-1]):
        stripped = stripped[1:-1].strip()
    if stripped.startswith('"') and stripped.endswith('"') and len(stripped) >= 2:
        return Constant(value=stripped[1:-1].replace('\\"', '"').replace("\\\\", "\\"))
    if _INT_RE.match(stripped):
        return Constant(value=int(stripped))
    if _FLOAT_RE.match(stripped):
        return Constant(value=float(stripped))
    if stripped == "_":
        return Wildcard(token=next(context.wildcard_counter))
    if _IDENTIFIER_RE.match(stripped):
        return Variable(name=stripped)
    split = _split_last_arithmetic(stripped)
    if split is not None:
        op, left, right = split
        return Arithmetic(
            op=op,
            left=_parse_term(left, context),
            right=_parse_term(right, context),
        )
    raise RuleSyntaxError(f"Unsupported term syntax: {term_text!r}")


def _split_last_arithmetic(text: str) -> tuple[str, str, str] | None:
    """Split at the last top-level + or - so chains stay left-associative."""

    depth = 0
    in_quotes = False
    best: tuple[str, str, str] | None = None
    for index, character in enumerate(text):
        if character == '"':
            in_quotes = not in_quotes
            continue
        if in_quotes:
            continue
        if character == "(":
            depth += 1
        elif character == ")":
            depth = max(depth - 1, 0)
        elif character in "+-" and depth == 0:
            before = text[:index].rstrip()
            # Only treat +/- as binary when it follows a complete operand;
            # otherwise it is a sign (e.g. the minus in "a + -3").
            if not before or before[-1] not in _OPERAND_TAIL_CHARS:
                continue
            best = (character, text[:index], text[index + 1:])
    return best


def _split_top_level(text: str, separator: str) -> list[str]:
    items: list[str] = []
    current: list[str] = []
    depth = 0
    in_quotes = False
    for character in text:
        if character == '"':
            in_quotes = not in_quotes
            current.append(character)
            continue
        if in_quotes:
            current.append(character)
            continue
        if character == separator and depth == 0:
            item = "".join(current).strip()
            if item:
                items.append(item)
            current = []
            continue
        if character == "(":
            depth += 1
        elif character == ")" and depth > 0:
            depth -= 1
        current.append(character)
    item = "".join(current).strip()
    if item:
        items.append(item)
    return items


def _split_top_level_operator(text: str, op: str) -> tuple[str, str] | None:
    depth = 0
    in_quotes = False
    index = 0
    while index < len(text):
        character = text[index]
        if character == '"':
            in_quotes = not in_quotes
        elif not in_quotes:
            if character == "(":
                depth += 1
            elif character == ")":
                depth = max(depth - 1, 0)
            elif depth == 0 and text.startswith(op, index):
                before = text[:index]
                after = text[index + len(op):]
                if op == "-" and not before.strip():
                    index += 1
                    continue
                if op in {"<", ">"} and after.startswith("="):
                    index += 1
                    continue
                return before, after
        index += 1
    return None


def _balanced(text: str) -> bool:
    depth = 0
    in_quotes = False
    for character in text:
        if character == '"':
            in_quotes = not in_quotes
            continue
        if in_quotes:
            continue
        if character == "(":
            depth += 1
        elif character == ")":
            depth -= 1
            if depth < 0:
                return False
    return depth == 0


def _validate(program: Program, rules: list[RuleAst]) -> None:
    _check_arities(program, rules)
    for rule in rules:
        _check_rule_safety(rule)
    _check_stratifiable(rules)


def _check_arities(program: Program, rules: list[RuleAst]) -> None:
    arities: dict[str, int] = {}

    def observe(predicate: str, arity: int, where: str) -> None:
        known = arities.setdefault(predicate, arity)
        if known != arity:
            raise ArityMismatchError(
                f"Predicate {predicate!r} used with arity {arity} in {where}, "
                f"but previously with arity {known}"
            )

    for predicate, rows in program.facts.items():
        for row in rows:
            observe(predicate, len(row), "facts")
    for rule in rules:
        observe(rule.head.predicate, len(rule.head.terms), rule.text)
        for atom in (*rule.positive, *rule.negative):
            observe(atom.predicate, len(atom.terms), rule.text)


def _check_rule_safety(rule: RuleAst) -> None:
    if any(isinstance(term, Wildcard) for term in _walk_terms(rule.head.terms)):
        raise SafetyViolationError(
            f"Wildcard in rule head is not allowed: {rule.text!r}"
        )

    bound = _positively_bound_variables(rule)

    for atom in rule.negative:
        for term in _walk_terms(atom.terms):
            if isinstance(term, Variable) and term.name not in bound:
                raise SafetyViolationError(
                    f"Variable {term.name!r} appears only under negation "
                    f"in rule: {rule.text!r}"
                )

    for comparison in rule.comparisons:
        for term in _walk_terms((comparison.left, comparison.right)):
            if isinstance(term, Variable) and term.name not in bound:
                raise UnboundVariableError(
                    f"Variable {term.name!r} in comparison is not bound by a "
                    f"positive body atom in rule: {rule.text!r}"
                )

    for term in _walk_terms(rule.head.terms):
        if isinstance(term, Variable) and term.name not in bound:
            raise UnboundVariableError(
                f"Head variable {term.name!r} is not bound by a positive body "
                f"atom in rule: {rule.text!r}"
            )


def _positively_bound_variables(rule: RuleAst) -> set[str]:
    bound: set[str] = set()
    for atom in rule.positive:
        for term in atom.terms:
            if isinstance(term, Variable):
                bound.add(term.name)
    return bound


def _walk_terms(terms: tuple[Term, ...]) -> Iterator[Term]:
    for term in terms:
        yield term
        if isinstance(term, Arithmetic):
            yield from _walk_terms((term.left, term.right))


def _dependencies(rules: list[RuleAst]) -> dict[str, set[tuple[str, bool]]]:
    dependencies: dict[str, set[tuple[str, bool]]] = {}
    for rule in rules:
        edges = dependencies.setdefault(rule.head.predicate, set())
        for atom in rule.positive:
            edges.add((atom.predicate, False))
        for atom in rule.negative:
            edges.add((atom.predicate, True))
    return dependencies


def _check_stratifiable(rules: list[RuleAst]) -> None:
    dependencies = _dependencies(rules)
    predicates = set(dependencies)
    for edges in dependencies.values():
        predicates.update(predicate for predicate, _ in edges)

    # A program is stratifiable iff no cycle contains a negative edge. We
    # detect this by checking whether any negative edge closes a path back to
    # its source through the dependency graph.
    reachable = _transitive_reachability(dependencies, predicates)
    for head, edges in dependencies.items():
        for target, negated in edges:
            if negated and (head == target or head in reachable.get(target, set())):
                raise CyclicNegationError(
                    f"Negation of {target!r} participates in a recursive cycle "
                    f"with {head!r}"
                )


def _transitive_reachability(
    dependencies: dict[str, set[tuple[str, bool]]],
    predicates: set[str],
) -> dict[str, set[str]]:
    reachable: dict[str, set[str]] = {}
    for start in predicates:
        seen: set[str] = set()
        stack = [target for target, _ in dependencies.get(start, set())]
        while stack:
            item = stack.pop()
            if item in seen:
                continue
            seen.add(item)
            stack.extend(target for target, _ in dependencies.get(item, set()))
        reachable[start] = seen
    return reachable


def _stratify(rules: list[RuleAst]) -> list[list[RuleAst]]:
    dependencies = _dependencies(rules)
    predicates = set(dependencies)
    for edges in dependencies.values():
        predicates.update(predicate for predicate, _ in edges)

    stratum: dict[str, int] = {predicate: 0 for predicate in predicates}
    changed = True
    iterations = 0
    limit = max(len(predicates) * len(predicates), 16)
    while changed:
        changed = False
        iterations += 1
        if iterations > limit:
            raise CyclicNegationError("Stratification did not converge")
        for head, edges in dependencies.items():
            for target, negated in edges:
                required = stratum[target] + 1 if negated else stratum[target]
                if stratum[head] < required:
                    stratum[head] = required
                    changed = True

    grouped: dict[int, list[RuleAst]] = {}
    for rule in rules:
        grouped.setdefault(stratum[rule.head.predicate], []).append(rule)
    return [grouped[level] for level in sorted(grouped)]


class _FactStore:
    """Predicate-keyed tuple sets with lazily built hash indexes.

    Indexes are keyed by the tuple of bound argument positions used at lookup
    time and kept current as rows are added, so semi-naive rounds over large
    relations (points-to-analysis harvests run to ~10^5 rows) stay usable in
    pure Python.
    """

    __slots__ = ("rows", "indexes")

    def __init__(self, facts: dict[str, set[FactTuple]]) -> None:
        self.rows: dict[str, set[FactTuple]] = facts
        self.indexes: dict[
            str, dict[tuple[int, ...], dict[tuple[Scalar, ...], list[FactTuple]]]
        ] = {}

    def add(self, predicate: str, row: FactTuple) -> bool:
        existing = self.rows.setdefault(predicate, set())
        if row in existing:
            return False
        existing.add(row)
        for positions, buckets in self.indexes.get(predicate, {}).items():
            key = tuple(row[position] for position in positions)
            buckets.setdefault(key, []).append(row)
        return True

    def lookup(
        self,
        predicate: str,
        positions: tuple[int, ...],
        values: tuple[Scalar, ...],
    ) -> list[FactTuple]:
        predicate_indexes = self.indexes.setdefault(predicate, {})
        buckets = predicate_indexes.get(positions)
        if buckets is None:
            fresh: dict[tuple[Scalar, ...], list[FactTuple]] = {}
            buckets = fresh
            for row in self.rows.get(predicate, set()):
                key = tuple(row[position] for position in positions)
                buckets.setdefault(key, []).append(row)
            predicate_indexes[positions] = buckets
        return buckets.get(values, [])

    def all_rows(self, predicate: str) -> set[FactTuple]:
        return self.rows.get(predicate, set())


def _evaluate_stratum(rules: list[RuleAst], facts: dict[str, set[FactTuple]]) -> None:
    stratum_predicates = {rule.head.predicate for rule in rules}
    store = _FactStore(facts)

    delta: dict[str, set[FactTuple]] = {}
    for rule in rules:
        ordered = _order_positive_literals(rule, pinned=None)
        # Materialize before inserting: insertion mutates the same relation
        # sets the join is iterating when a rule is recursive.
        for derived_predicate, derived_row in list(
            _apply_rule(rule, ordered, store, delta_rows=None)
        ):
            if store.add(derived_predicate, derived_row):
                delta.setdefault(derived_predicate, set()).add(derived_row)

    while delta:
        next_delta: dict[str, set[FactTuple]] = {}
        for rule in rules:
            for position, atom in enumerate(rule.positive):
                if atom.predicate not in stratum_predicates:
                    continue
                delta_rows = delta.get(atom.predicate)
                if not delta_rows:
                    continue
                ordered = _order_positive_literals(rule, pinned=position)
                for derived_predicate, derived_row in list(
                    _apply_rule(rule, ordered, store, delta_rows=delta_rows)
                ):
                    if store.add(derived_predicate, derived_row):
                        next_delta.setdefault(derived_predicate, set()).add(derived_row)
        delta = next_delta


def _order_positive_literals(rule: RuleAst, *, pinned: int | None) -> tuple[AtomAst, ...]:
    """Order body literals greedily so bound arguments come early.

    When ``pinned`` names a literal index, that literal goes first (it will be
    restricted to the semi-naive delta); the rest are chosen by how many of
    their variables are already bound, breaking ties toward fewer new
    variables.
    """

    remaining = list(range(len(rule.positive)))
    ordered: list[AtomAst] = []
    bound: set[str] = set()

    def atom_variables(atom: AtomAst) -> set[str]:
        return {
            term.name
            for term in _walk_terms(atom.terms)
            if isinstance(term, Variable)
        }

    if pinned is not None:
        remaining.remove(pinned)
        pinned_atom = rule.positive[pinned]
        ordered.append(pinned_atom)
        bound.update(atom_variables(pinned_atom))

    while remaining:
        def score(index: int) -> tuple[int, int]:
            variables = atom_variables(rule.positive[index])
            bound_count = len(variables & bound)
            new_count = len(variables - bound)
            return (bound_count, -new_count)

        best = max(remaining, key=score)
        remaining.remove(best)
        best_atom = rule.positive[best]
        ordered.append(best_atom)
        bound.update(atom_variables(best_atom))

    return tuple(ordered)


def _apply_rule(
    rule: RuleAst,
    ordered_body: tuple[AtomAst, ...],
    store: _FactStore,
    *,
    delta_rows: set[FactTuple] | None,
) -> Iterator[tuple[str, FactTuple]]:
    for bindings in _match_positive(ordered_body, 0, store, {}, delta_rows):
        if not _comparisons_hold(rule.comparisons, bindings):
            continue
        if not _negations_hold(rule.negative, bindings, store.rows):
            continue
        row = tuple(_evaluate_term(term, bindings) for term in rule.head.terms)
        yield rule.head.predicate, row


def _match_positive(
    body: tuple[AtomAst, ...],
    index: int,
    store: _FactStore,
    bindings: dict[str, Scalar],
    delta_rows: set[FactTuple] | None,
) -> Iterator[dict[str, Scalar]]:
    if index == len(body):
        yield bindings
        return
    atom = body[index]
    if index == 0 and delta_rows is not None:
        candidates: list[FactTuple] | set[FactTuple] = delta_rows
    else:
        candidates = _candidate_rows(atom, store, bindings)
    for row in candidates:
        extended = _unify(atom.terms, row, bindings)
        if extended is not None:
            yield from _match_positive(body, index + 1, store, extended, delta_rows)


def _candidate_rows(
    atom: AtomAst,
    store: _FactStore,
    bindings: dict[str, Scalar],
) -> list[FactTuple] | set[FactTuple]:
    positions: list[int] = []
    values: list[Scalar] = []
    for position, term in enumerate(atom.terms):
        resolved = _evaluate_term_or_none(term, bindings)
        if resolved is not None:
            positions.append(position)
            values.append(resolved)
    if not positions:
        return store.all_rows(atom.predicate)
    return store.lookup(atom.predicate, tuple(positions), tuple(values))


def _unify(
    terms: tuple[Term, ...],
    row: FactTuple,
    bindings: dict[str, Scalar],
) -> dict[str, Scalar] | None:
    if len(terms) != len(row):
        return None
    extended = bindings
    copied = False
    for term, value in zip(terms, row, strict=True):
        if isinstance(term, Wildcard):
            continue
        if isinstance(term, Variable):
            known = extended.get(term.name, _MISSING)
            if known is _MISSING:
                if not copied:
                    extended = dict(extended)
                    copied = True
                extended[term.name] = value
                continue
            if known != value or type(known) is not type(value):
                return None
            continue
        resolved = _evaluate_term_or_none(term, extended)
        if resolved is None or resolved != value or type(resolved) is not type(value):
            return None
    return extended


class _Missing:
    __slots__ = ()


_MISSING = _Missing()


def _comparisons_hold(
    comparisons: tuple[Comparison, ...],
    bindings: dict[str, Scalar],
) -> bool:
    for comparison in comparisons:
        left = _evaluate_term(comparison.left, bindings)
        right = _evaluate_term(comparison.right, bindings)
        if not _compare(comparison.op, left, right):
            return False
    return True


def _compare(op: str, left: Scalar, right: Scalar) -> bool:
    if op == "=":
        return left == right and type(left) is type(right)
    if op == "!=":
        return not (left == right and type(left) is type(right))
    if not isinstance(left, (int, float)) or not isinstance(right, (int, float)):
        raise ReferenceEvaluationError(
            f"Ordered comparison {op!r} requires numeric operands, "
            f"got {left!r} and {right!r}"
        )
    if op == "<":
        return left < right
    if op == "<=":
        return left <= right
    if op == ">":
        return left > right
    if op == ">=":
        return left >= right
    raise ReferenceEvaluationError(f"Unsupported comparison operator: {op!r}")


def _negations_hold(
    negative: tuple[AtomAst, ...],
    bindings: dict[str, Scalar],
    facts: dict[str, set[FactTuple]],
) -> bool:
    for atom in negative:
        rows = facts.get(atom.predicate, set())
        if _ground_row_or_none(atom.terms, bindings) is not None:
            if _ground_row(atom.terms, bindings) in rows:
                return False
            continue
        # Wildcards under negation: fail if any matching row exists.
        if any(_unify(atom.terms, row, bindings) is not None for row in rows):
            return False
    return True


def _ground_row_or_none(
    terms: tuple[Term, ...],
    bindings: dict[str, Scalar],
) -> FactTuple | None:
    values: list[Scalar] = []
    for term in terms:
        resolved = _evaluate_term_or_none(term, bindings)
        if resolved is None:
            return None
        values.append(resolved)
    return tuple(values)


def _ground_row(terms: tuple[Term, ...], bindings: dict[str, Scalar]) -> FactTuple:
    row = _ground_row_or_none(terms, bindings)
    assert row is not None
    return row


def _evaluate_term(term: Term, bindings: dict[str, Scalar]) -> Scalar:
    resolved = _evaluate_term_or_none(term, bindings)
    if resolved is None:
        raise UnboundVariableError(f"Term {term!r} is not fully bound")
    return resolved


def _evaluate_term_or_none(term: Term, bindings: dict[str, Scalar]) -> Scalar | None:
    if isinstance(term, Constant):
        return term.value
    if isinstance(term, Variable):
        value = bindings.get(term.name, _MISSING)
        return None if isinstance(value, _Missing) else value
    if isinstance(term, Arithmetic):
        left = _evaluate_term_or_none(term.left, bindings)
        right = _evaluate_term_or_none(term.right, bindings)
        if left is None or right is None:
            return None
        if not isinstance(left, (int, float)) or not isinstance(right, (int, float)):
            raise ReferenceEvaluationError(
                f"Arithmetic requires numeric operands, got {left!r} and {right!r}"
            )
        if isinstance(left, bool) or isinstance(right, bool):
            raise ReferenceEvaluationError(
                f"Arithmetic requires numeric operands, got {left!r} and {right!r}"
            )
        return left + right if term.op == "+" else left - right
    return None
