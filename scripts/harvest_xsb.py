"""Harvest the XSB ``wfs_tests`` slice into the negation suite.

Upstream: XSB Prolog's tabling test suite, SourceForge SVN repository
``xsb/src`` under ``trunk/xsbtests/wfs_tests`` (license: LGPL v2, recorded in
``docs/HARVESTING.md``). Every ``pNN.P`` program opens with a self-describing
oracle fact::

    query(Name, Query, AllAtoms, TrueAtoms, UndefinedAtoms).

which states, for the well-founded model, which queried atoms are true and
which are undefined. This harvester keeps only the TWO-VALUED slice
(``UndefinedAtoms == []``) whose clauses fit the suite's plain stratified
surface, because those are the cases all four integrated engines can answer.

Translation policy (also recorded in ``docs/HARVESTING.md``):
- ``:- table ...`` directives are dropped (tabling is an evaluation hint).
- ``tnot(A)`` becomes ``not A``.
- Rules containing a ``fail`` literal are dropped (their head contributes
  nothing to the model).
- Zero-arity atoms are lifted to unary atoms over the marker constant ``w``
  because Souffle has no zero-arity relations; the lift is a bijection on
  models.
- Rules whose body contains only negated literals (always ground after the
  lift) get the always-true positive guard ``guard_w(w)`` prepended, because
  Nemo rejects rules without positive body literals; the guard predicate is
  added as a fact and never asserted on.
- Ground unit clauses become suite facts; every other clause becomes a rule
  string in which uppercase identifiers stay variables and constant
  arguments are double-quoted (integers stay bare).
- Expected rows per predicate come from ``TrueAtoms``; predicates listed in
  ``AllAtoms`` with no true atom are asserted empty.

Each retained case is pre-validated by the local reference evaluator (which
rejects non-stratifiable programs and cross-checks the stored oracle), and
must then survive the four-engine agreement matrix before it may keep its
verification stamp:

    uv run --extra oracles scripts/verify_core_multi_oracle.py --case-filter xsb_wfs

Usage:

    uv run scripts/harvest_xsb.py
"""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path
from typing import TypeAlias

import yaml

from datalog_conformance.references import CoreReferenceEvaluator
from datalog_conformance.schema import Program, Scalar

SOURCE = (
    "xsb/src trunk/xsbtests/wfs_tests (SourceForge SVN, fetched 2026-07-09); "
    "expectations from each program's query/5 oracle fact"
)
BASE_TAGS = ["negation", "xsb", "wfs-two-valued"]
VERIFICATION = {"implementation": "nmo+souffle+clingo+swipl", "kind": "direct"}
DEFAULT_SOURCE_DIR = Path("C:/Users/Q/AppData/Local/Temp/datalog-harvest/xsbtests/wfs_tests")
DEFAULT_OUTPUT = Path("src/datalog_conformance/_tests/negation/xsb_wfs_two_valued.yaml")
MARKER = "w"

# Upstream programs excluded even though they are two-valued and parse into
# the plain surface. Kept explicit so regeneration stays deterministic.
SKIP_PROGRAMS: frozenset[str] = frozenset()

Atom: TypeAlias = tuple[str, tuple[Scalar, ...]]


class UnsupportedProgram(Exception):
    """Raised when an upstream program falls outside the portable surface."""


@dataclass(slots=True)
class HarvestedCase:
    name: str
    program: Program
    expect: dict[str, list[list[Scalar]]]
    rule_count: int
    negation_count: int


_ATOM_RE = re.compile(r"^([a-z][A-Za-z0-9_]*)(?:\((.*)\))?$", re.DOTALL)
_NAME_RE = re.compile(r"^[a-z][A-Za-z0-9_]*$")
_INT_RE = re.compile(r"^-?\d+$")
_VARIABLE_RE = re.compile(r"^(?:[A-Z][A-Za-z0-9_]*|_[A-Za-z0-9_]*)$")


def _strip_comments(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", " ", text, flags=re.DOTALL)
    lines: list[str] = []
    for line in text.splitlines():
        # wfs_tests quote only the comma functor `','` in query terms, which
        # never contains a percent sign, so a plain split is safe here.
        position = line.find("%")
        lines.append(line if position < 0 else line[:position])
    return "\n".join(lines)


def _split_clauses(text: str) -> list[str]:
    clauses: list[str] = []
    current: list[str] = []
    depth = 0
    in_quote: str | None = None
    for index, character in enumerate(text):
        current.append(character)
        if in_quote is not None:
            if character == in_quote:
                in_quote = None
            continue
        if character in {"'", '"'}:
            in_quote = character
            continue
        if character in "([":
            depth += 1
        elif character in ")]":
            depth -= 1
        elif character == "." and depth == 0:
            following = text[index + 1 : index + 2]
            if following == "" or following.isspace():
                clause = "".join(current).strip().removesuffix(".")
                if clause:
                    clauses.append(clause)
                current = []
    remainder = "".join(current).strip()
    if remainder:
        raise UnsupportedProgram(f"trailing content without terminator: {remainder[:40]!r}")
    return clauses


def _split_top_level(text: str, separator: str) -> list[str]:
    parts: list[str] = []
    current: list[str] = []
    depth = 0
    in_quote: str | None = None
    for character in text:
        if in_quote is not None:
            current.append(character)
            if character == in_quote:
                in_quote = None
            continue
        if character in {"'", '"'}:
            in_quote = character
            current.append(character)
            continue
        if character in "([":
            depth += 1
        elif character in ")]":
            depth -= 1
        if character == separator and depth == 0:
            parts.append("".join(current).strip())
            current = []
            continue
        current.append(character)
    tail = "".join(current).strip()
    if tail:
        parts.append(tail)
    return parts


def _parse_ground_atom(text: str) -> Atom:
    match = _ATOM_RE.match(text.strip())
    if match is None:
        raise UnsupportedProgram(f"unsupported atom: {text!r}")
    name, arguments_text = match.group(1), match.group(2)
    if arguments_text is None:
        return name, ()
    arguments: list[Scalar] = []
    for argument in _split_top_level(arguments_text, ","):
        if _INT_RE.match(argument):
            arguments.append(int(argument))
        elif _NAME_RE.match(argument):
            arguments.append(argument)
        else:
            raise UnsupportedProgram(f"unsupported ground argument: {argument!r}")
    return name, tuple(arguments)


def _parse_atom_list(text: str) -> list[Atom]:
    inner = text.strip()
    if not (inner.startswith("[") and inner.endswith("]")):
        raise UnsupportedProgram(f"expected a list, got: {text!r}")
    inner = inner[1:-1].strip()
    if not inner:
        return []
    return [_parse_ground_atom(item) for item in _split_top_level(inner, ",")]


@dataclass(slots=True)
class _Oracle:
    name: str
    all_atoms: list[Atom]
    true_atoms: list[Atom]
    undefined_atoms: list[Atom]


def _parse_oracle(clause: str) -> _Oracle:
    match = _ATOM_RE.match(clause.strip())
    if match is None or match.group(1) != "query" or match.group(2) is None:
        raise UnsupportedProgram(f"missing query/5 oracle fact: {clause[:60]!r}")
    arguments = _split_top_level(match.group(2), ",")
    if len(arguments) != 5:
        raise UnsupportedProgram(f"query fact does not have five arguments: {clause[:60]!r}")
    return _Oracle(
        name=arguments[0],
        all_atoms=_parse_atom_list(arguments[2]),
        true_atoms=_parse_atom_list(arguments[3]),
        undefined_atoms=_parse_atom_list(arguments[4]),
    )


@dataclass(slots=True)
class _Literal:
    negated: bool
    predicate: str
    arguments: tuple[str, ...]

    def is_ground(self) -> bool:
        return not any(_VARIABLE_RE.match(argument) for argument in self.arguments)


def _parse_literal(text: str) -> _Literal | None:
    """Parse one body literal; ``None`` means the harmless ``true`` literal."""

    stripped = text.strip()
    if stripped == "true":
        return None
    negated = False
    if stripped.startswith("tnot(") and stripped.endswith(")"):
        negated = True
        stripped = stripped[len("tnot(") : -1].strip()
    match = _ATOM_RE.match(stripped)
    if match is None:
        raise UnsupportedProgram(f"unsupported literal: {text!r}")
    name, arguments_text = match.group(1), match.group(2)
    if arguments_text is None:
        return _Literal(negated=negated, predicate=name, arguments=())
    arguments: list[str] = []
    for argument in _split_top_level(arguments_text, ","):
        if _INT_RE.match(argument) or _NAME_RE.match(argument) or _VARIABLE_RE.match(argument):
            arguments.append(argument)
        else:
            raise UnsupportedProgram(f"unsupported argument: {argument!r}")
    return _Literal(negated=negated, predicate=name, arguments=tuple(arguments))


def _render_argument(argument: str) -> str:
    if _INT_RE.match(argument) or _VARIABLE_RE.match(argument):
        return argument
    return f'"{argument}"'


def _render_literal(literal: _Literal, nullary: set[str]) -> str:
    arguments = list(literal.arguments)
    if literal.predicate in nullary:
        arguments = [MARKER]
    rendered_arguments = ", ".join(_render_argument(argument) for argument in arguments)
    text = f"{literal.predicate}({rendered_arguments})"
    return f"not {text}" if literal.negated else text


def _harvest_file(path: Path) -> HarvestedCase:
    clauses = _split_clauses(_strip_comments(path.read_text(encoding="utf-8")))
    if not clauses:
        raise UnsupportedProgram("empty program")
    oracle = _parse_oracle(clauses[0])
    if oracle.undefined_atoms:
        raise UnsupportedProgram(
            f"three-valued well-founded model ({len(oracle.undefined_atoms)} undefined atom(s))"
        )

    facts: list[Atom] = []
    rules: list[tuple[_Literal, list[_Literal]]] = []
    arities: dict[str, int] = {}

    def _note_arity(predicate: str, arity: int) -> None:
        known = arities.setdefault(predicate, arity)
        if known != arity:
            raise UnsupportedProgram(f"inconsistent arity for {predicate!r}")

    for clause in clauses[1:]:
        stripped = clause.strip()
        if stripped.startswith(":-"):
            continue  # directives such as :- table p/1.
        head_text, _, body_text = stripped.partition(":-")
        head = _parse_literal(head_text)
        if head is None or head.negated:
            raise UnsupportedProgram(f"unsupported head: {head_text!r}")
        if head.predicate in {"query", "test"}:
            continue
        if not body_text:
            if not head.is_ground():
                raise UnsupportedProgram(f"non-ground fact: {clause!r}")
            facts.append(_parse_ground_atom(stripped))
            _note_arity(head.predicate, len(head.arguments))
            continue
        body_literals: list[_Literal] = []
        drop_rule = False
        for part in _split_top_level(body_text, ","):
            if part.strip() == "fail":
                drop_rule = True
                break
            literal = _parse_literal(part)
            if literal is not None:
                body_literals.append(literal)
        _note_arity(head.predicate, len(head.arguments))
        for literal in body_literals:
            _note_arity(literal.predicate, len(literal.arguments))
        if drop_rule:
            continue
        rules.append((head, body_literals))

    for atom in oracle.all_atoms + oracle.true_atoms:
        _note_arity(atom[0], len(atom[1]))

    nullary = {predicate for predicate, arity in arities.items() if arity == 0}

    fact_map: dict[str, list[tuple[Scalar, ...]]] = {}
    for predicate, arguments in facts:
        row: tuple[Scalar, ...] = (MARKER,) if predicate in nullary else arguments
        rows = fact_map.setdefault(predicate, [])
        if row not in rows:
            rows.append(row)
    for rows in fact_map.values():
        rows.sort(key=repr)

    guard_predicate = "guard_w"
    if guard_predicate in arities:
        raise UnsupportedProgram(f"guard predicate name {guard_predicate!r} collides")

    rule_texts: list[str] = []
    negation_count = 0
    needs_guard = False
    for head, body_literals in rules:
        head_text = _render_literal(head, nullary)
        rendered_body = [_render_literal(literal, nullary) for literal in body_literals]
        if body_literals and all(literal.negated for literal in body_literals):
            # Nemo rejects rules without positive body literals; these bodies
            # are ground after the nullary lift, so an always-true guard
            # preserves the model exactly.
            rendered_body.insert(0, f'{guard_predicate}("{MARKER}")')
            needs_guard = True
        negation_count += sum(1 for literal in body_literals if literal.negated)
        rule_texts.append(f"{head_text} :- {', '.join(rendered_body)}.")
    if needs_guard:
        fact_map[guard_predicate] = [(MARKER,)]

    expect: dict[str, list[list[Scalar]]] = {}
    for predicate, _ in oracle.all_atoms:
        expect.setdefault(predicate, [])
    for predicate, arguments in oracle.true_atoms:
        expect_row: list[Scalar] = [MARKER] if predicate in nullary else list(arguments)
        if expect_row not in expect.setdefault(predicate, []):
            expect[predicate].append(expect_row)
    for rows_list in expect.values():
        rows_list.sort(key=repr)

    return HarvestedCase(
        name=f"xsb_wfs_{oracle.name}",
        program=Program(
            facts={predicate: rows for predicate, rows in sorted(fact_map.items())},
            rules=rule_texts,
        ),
        expect=dict(sorted(expect.items())),
        rule_count=len(rule_texts),
        negation_count=negation_count,
    )


def _reference_validates(case: HarvestedCase) -> str | None:
    """Return None when the local reference reproduces the stored oracle."""

    try:
        model = CoreReferenceEvaluator().evaluate(case.program)
    except Exception as exc:  # noqa: BLE001 - rejection reasons vary
        return f"reference rejected: {type(exc).__name__}: {exc}"
    for predicate, rows in case.expect.items():
        expected = {tuple(row) for row in rows}
        actual = model.facts.get(predicate, set())
        if expected != actual:
            return (
                f"reference mismatch on {predicate!r}: "
                f"expected {sorted(expected, key=repr)!r} got {sorted(actual, key=repr)!r}"
            )
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Harvest the XSB wfs_tests slice.")
    parser.add_argument("--source-dir", type=Path, default=DEFAULT_SOURCE_DIR)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--max-cases", type=int, default=50)
    args = parser.parse_args()

    kept: list[HarvestedCase] = []
    skipped: list[tuple[str, str]] = []
    for path in sorted(args.source_dir.glob("p*.P")):
        if path.stem in SKIP_PROGRAMS:
            skipped.append((path.stem, "explicitly excluded"))
            continue
        try:
            case = _harvest_file(path)
        except UnsupportedProgram as exc:
            skipped.append((path.stem, str(exc)))
            continue
        reason = _reference_validates(case)
        if reason is not None:
            skipped.append((path.stem, reason))
            continue
        kept.append(case)

    kept = kept[: args.max_cases]

    tests: list[dict[str, object]] = []
    for case in kept:
        tests.append(
            {
                "name": case.name,
                "description": (
                    f"XSB wfs_tests program {case.name.removeprefix('xsb_wfs_')}: "
                    f"{case.rule_count} rule(s), {case.negation_count} negated body "
                    "literal(s); two-valued well-founded model taken from the "
                    "upstream query/5 oracle fact and cross-checked against the "
                    "local reference evaluator."
                ),
                "tags": [f"rules-{case.rule_count}", f"negations-{case.negation_count}"],
                "program": {
                    "facts": {
                        predicate: [list(row) for row in rows]
                        for predicate, rows in case.program.facts.items()
                    },
                    "rules": list(case.program.rules),
                },
                "expect": case.expect,
            }
        )

    document = {
        "source": SOURCE,
        "tags": BASE_TAGS,
        "verification": VERIFICATION,
        "tests": tests,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        "# Generated by scripts/harvest_xsb.py; do not edit by hand.\n"
        + yaml.safe_dump(document, sort_keys=False, width=100),
        encoding="utf-8",
    )

    print(f"{args.output.as_posix()}: {len(tests)} cases")
    for name, reason in skipped:
        print(f"skipped {name}: {reason}")
    print(f"kept {len(tests)}, skipped {len(skipped)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
