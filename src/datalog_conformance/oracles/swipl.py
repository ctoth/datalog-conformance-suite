"""SWI-Prolog with tabling as an external conformance oracle.

SWI-Prolog evaluates top-down with SLG resolution (tabling), a genuinely
different strategy from the bottom-up engines already in the matrix, so its
agreement is strong independent evidence. Every derived predicate is tabled;
``not`` on derived predicates becomes ``tnot/1`` (well-founded semantics,
which coincides with stratified semantics on the corpus's stratified
programs) and ``\\+`` on fact-only predicates. Body literals are emitted
positives-first so negation and comparisons are always ground, matching the
suite's safety convention.

Arithmetic head terms are flattened into ``is/2`` goals. String scalars are
rendered as quoted atoms; booleans are outside the mapped term language and
raise :class:`SwiPrologUnsupportedError` (as in the other adapters, the
oracle refuses to guess).
"""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from itertools import count
from pathlib import Path
from typing import Sequence

from ..references.core import (
    Arithmetic,
    Comparison,
    Constant,
    RuleAst,
    Term,
    Variable,
    Wildcard,
    parse_rules,
)
from ..schema import FactTuple, Model, Program, Scalar

_INT_RE = re.compile(r"^-?\d+$")
_FLOAT_RE = re.compile(r"^-?\d+\.\d+(?:[eE][+-]?\d+)?$")


class SwiPrologError(RuntimeError):
    """Raised when swipl fails or produces unusable output."""

    def __init__(
        self,
        message: str,
        *,
        command: list[str] | None = None,
        stdout: str = "",
        stderr: str = "",
        returncode: int | None = None,
    ) -> None:
        super().__init__(message)
        self.command = command or []
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode


class SwiPrologUnavailableError(SwiPrologError):
    """Raised when no swipl invocation can be located."""


class SwiPrologUnsupportedError(SwiPrologError):
    """Raised when the visible program uses surface the mapping cannot express."""


def find_swipl() -> list[str] | None:
    """Return the swipl invocation prefix, preferring a native binary."""

    native = shutil.which("swipl")
    if native is not None:
        return [native]
    wsl = shutil.which("wsl")
    if wsl is None:
        return None
    probe = subprocess.run(
        [wsl, "swipl", "--version"],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    if probe.returncode == 0:
        return [wsl, "swipl"]
    return None


def _to_wsl_path(path: Path) -> str:
    resolved = path.resolve()
    drive = resolved.drive.rstrip(":").lower()
    tail = str(resolved)[len(resolved.drive):].replace("\\", "/")
    return f"/mnt/{drive}{tail}"


class SwiPrologOracle:
    """DatalogEvaluator protocol implementation backed by tabled SWI-Prolog."""

    def __init__(
        self,
        command: Sequence[str] | None = None,
        *,
        timeout_seconds: int = 120,
    ) -> None:
        resolved = list(command) if command is not None else find_swipl()
        if not resolved:
            raise SwiPrologUnavailableError(
                "No swipl binary found (native or via WSL). In WSL Debian: "
                "`apt install swi-prolog`."
            )
        self.command = resolved
        self.uses_wsl = Path(resolved[0]).stem.lower() == "wsl"
        self.timeout_seconds = timeout_seconds

    def evaluate(self, program: Program) -> Model:
        rules = parse_rules(program.rules)
        predicate_map = _build_predicate_map(program, rules)
        arities = _predicate_arities(program, rules)
        text = _render_prolog_program(program, rules, predicate_map, arities)

        with tempfile.TemporaryDirectory(prefix="swipl-oracle-") as temp_dir:
            root = Path(temp_dir)
            program_path = root / "program.pl"
            program_path.write_text(text, encoding="utf-8")
            program_argument = (
                _to_wsl_path(program_path) if self.uses_wsl else str(program_path)
            )
            command = [
                *self.command,
                "-q",
                "--on-error=halt",
                # Points-to-analysis harvests (~10^5 facts) overflow the
                # default table space.
                "--table-space=4g",
                "-g",
                "conformance_main",
                "-t",
                "halt",
                program_argument,
            ]
            try:
                result = subprocess.run(
                    command,
                    capture_output=True,
                    text=True,
                    check=False,
                    timeout=self.timeout_seconds,
                )
            except subprocess.TimeoutExpired as exc:
                raise SwiPrologError(
                    f"swipl timed out after {self.timeout_seconds}s",
                    command=command,
                ) from exc
            if result.returncode != 0:
                raise SwiPrologError(
                    result.stderr.strip() or result.stdout.strip() or "swipl failed",
                    command=command,
                    stdout=result.stdout,
                    stderr=result.stderr,
                    returncode=result.returncode,
                )
            reverse_map = {value: key for key, value in predicate_map.items()}
            facts: dict[str, set[FactTuple]] = {
                predicate: set() for predicate in predicate_map
            }
            for line in result.stdout.splitlines():
                if not line.strip():
                    continue
                fields = line.split("\t")
                predicate = reverse_map.get(fields[0])
                if predicate is None:
                    raise SwiPrologError(
                        f"Unexpected output predicate {fields[0]!r}",
                        command=command,
                        stdout=result.stdout,
                        stderr=result.stderr,
                    )
                facts[predicate].add(
                    tuple(_parse_term_text(item) for item in fields[1:])
                )
            return Model(facts=facts)


def _build_predicate_map(program: Program, rules: list[RuleAst]) -> dict[str, str]:
    predicates = set(program.facts)
    for rule in rules:
        predicates.add(rule.head.predicate)
        for atom in (*rule.positive, *rule.negative):
            predicates.add(atom.predicate)
    mapping: dict[str, str] = {}
    for index, predicate in enumerate(sorted(predicates), start=1):
        sanitized = re.sub(r"[^A-Za-z0-9_]+", "_", predicate).strip("_").lower()
        mapping[predicate] = f"p_{index}_{sanitized or 'predicate'}"
    return mapping


def _predicate_arities(program: Program, rules: list[RuleAst]) -> dict[str, int]:
    arities: dict[str, int] = {}
    for predicate, rows in program.facts.items():
        if rows:
            arities.setdefault(predicate, len(rows[0]))
        else:
            arities.setdefault(predicate, 0)
    for rule in rules:
        arities.setdefault(rule.head.predicate, len(rule.head.terms))
        for atom in (*rule.positive, *rule.negative):
            arities.setdefault(atom.predicate, len(atom.terms))
    return arities


def _render_prolog_program(
    program: Program,
    rules: list[RuleAst],
    predicate_map: dict[str, str],
    arities: dict[str, int],
) -> str:
    derived = {rule.head.predicate for rule in rules}
    lines: list[str] = [
        ":- style_check(-discontiguous).",
        ":- style_check(-singleton).",
    ]
    for predicate in sorted(derived):
        lines.append(
            f":- table {predicate_map[predicate]}/{arities[predicate]}."
        )
    for predicate in sorted(predicate_map):
        if predicate in derived:
            continue
        # Prolog throws existence errors for clause-less predicates; dynamic
        # declarations make empty relations fail instead, like empty EDB.
        lines.append(f":- dynamic {predicate_map[predicate]}/{arities[predicate]}.")

    for predicate, rows in program.facts.items():
        translated = predicate_map[predicate]
        for row in rows:
            if row:
                rendered = ", ".join(_render_scalar(value) for value in row)
                lines.append(f"{translated}({rendered}).")
            else:
                lines.append(f"{translated}.")

    for rule in rules:
        lines.append(_render_rule(rule, predicate_map, derived))

    lines.append("conformance_print_row(Name, Args) :-")
    lines.append("    write(Name),")
    lines.append("    forall(member(Arg, Args), (put_char('\\t'), writeq(Arg))),")
    lines.append("    nl.")

    body: list[str] = []
    for predicate in sorted(predicate_map):
        translated = predicate_map[predicate]
        arity = arities[predicate]
        if arity == 0:
            body.append(
                f"    ({translated} -> conformance_print_row({translated}, []) ; true)"
            )
            continue
        variables = ", ".join(f"A{position}" for position in range(arity))
        body.append(
            f"    forall({translated}({variables}), "
            f"conformance_print_row({translated}, [{variables}]))"
        )
    if body:
        lines.append("conformance_main :-")
        lines.append(",\n".join(body) + ".")
    else:
        lines.append("conformance_main.")
    return "\n".join(lines) + "\n"


def _render_rule(
    rule: RuleAst,
    predicate_map: dict[str, str],
    derived: set[str],
) -> str:
    fresh = count()
    is_goals: list[str] = []

    def flatten(term: Term) -> str:
        if isinstance(term, Arithmetic):
            variable = f"C{next(fresh)}"
            is_goals.append(f"{variable} is {_render_expression(term)}")
            return variable
        return _render_term(term)

    goals: list[str] = []
    for atom in rule.positive:
        arguments = [flatten(term) for term in atom.terms]
        goals.extend(is_goals)
        is_goals = []
        goals.append(_render_goal(atom.predicate, arguments, predicate_map))
    for comparison in rule.comparisons:
        goals.append(_render_comparison(comparison))
    for atom in rule.negative:
        arguments = [flatten(term) for term in atom.terms]
        goals.extend(is_goals)
        is_goals = []
        inner = _render_goal(atom.predicate, arguments, predicate_map)
        negation = "tnot" if atom.predicate in derived else "\\+"
        goals.append(f"{negation}({inner})")

    head_arguments = [flatten(term) for term in rule.head.terms]
    goals.extend(is_goals)
    head = _render_goal(rule.head.predicate, head_arguments, predicate_map)
    if not goals:
        return f"{head}."
    return f"{head} :- {', '.join(goals)}."


def _render_goal(
    predicate: str,
    arguments: list[str],
    predicate_map: dict[str, str],
) -> str:
    translated = predicate_map[predicate]
    if not arguments:
        return translated
    return f"{translated}({', '.join(arguments)})"


def _render_comparison(comparison: Comparison) -> str:
    left = _render_operand(comparison.left)
    right = _render_operand(comparison.right)
    operator = {
        "<": "<",
        ">": ">",
        "<=": "=<",
        ">=": ">=",
        "=": "==",
        "!=": "\\==",
    }[comparison.op]
    return f"{left} {operator} {right}"


def _render_operand(term: Term) -> str:
    if isinstance(term, Arithmetic):
        return f"({_render_expression(term)})"
    return _render_term(term)


def _render_expression(term: Term) -> str:
    if isinstance(term, Arithmetic):
        return (
            f"({_render_expression(term.left)} {term.op} "
            f"{_render_expression(term.right)})"
        )
    return _render_term(term)


def _render_term(term: Term) -> str:
    if isinstance(term, Constant):
        return _render_scalar(term.value)
    if isinstance(term, Variable):
        return f"V_{term.name}"
    if isinstance(term, Wildcard):
        return "_"
    raise SwiPrologUnsupportedError(f"Unsupported term for swipl: {term!r}")


def _render_scalar(value: Scalar) -> str:
    if isinstance(value, bool):
        raise SwiPrologUnsupportedError("Boolean scalars are not supported for swipl")
    if isinstance(value, (int, float)):
        return repr(value)
    escaped = value.replace("\\", "\\\\").replace("'", "\\'")
    return f"'{escaped}'"


def _parse_term_text(text: str) -> Scalar:
    stripped = text.strip()
    if stripped.startswith("'") and stripped.endswith("'") and len(stripped) >= 2:
        return (
            stripped[1:-1]
            .replace("\\'", "'")
            .replace("\\\\", "\\")
        )
    if _INT_RE.match(stripped):
        return int(stripped)
    if _FLOAT_RE.match(stripped):
        return float(stripped)
    return stripped
