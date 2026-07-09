"""Souffle as an external conformance oracle, invoked through WSL or natively.

Souffle is the upstream origin of most harvested core cases, so agreement
here checks the harvest against its own source-of-truth engine. The adapter
renders the visible program surface to a typed ``.dl`` file (Souffle requires
``.decl`` type declarations, so column types are inferred from fact scalars
and propagated through rules), runs ``souffle``, and reads the TSV outputs.

Unsupported surface (raises :class:`SouffleUnsupportedError` rather than
guessing): zero-arity predicates, boolean scalars, and columns that mix
numbers with symbols.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Sequence

from ..references.core import (
    Arithmetic,
    AtomAst,
    Constant,
    RuleAst,
    Term,
    Variable,
    Wildcard,
    parse_rules,
)
from ..schema import FactTuple, Model, Program, Scalar

_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class SouffleError(RuntimeError):
    """Raised when souffle fails or produces unusable output."""

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


class SouffleUnavailableError(SouffleError):
    """Raised when no souffle invocation can be located."""


class SouffleUnsupportedError(SouffleError):
    """Raised when the visible program uses surface souffle cannot express."""


def find_souffle() -> list[str] | None:
    """Return the souffle invocation prefix, preferring a native binary."""

    native = shutil.which("souffle")
    if native is not None:
        return [native]
    wsl = shutil.which("wsl")
    if wsl is None:
        return None
    probe = subprocess.run(
        [wsl, "souffle", "--version"],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    if probe.returncode == 0:
        return [wsl, "souffle"]
    return None


def _to_wsl_path(path: Path) -> str:
    resolved = path.resolve()
    drive = resolved.drive.rstrip(":").lower()
    tail = str(resolved)[len(resolved.drive):].replace("\\", "/")
    return f"/mnt/{drive}{tail}"


class SouffleOracle:
    """DatalogEvaluator protocol implementation backed by souffle."""

    def __init__(
        self,
        command: Sequence[str] | None = None,
        *,
        timeout_seconds: int = 120,
    ) -> None:
        resolved = list(command) if command is not None else find_souffle()
        if not resolved:
            raise SouffleUnavailableError(
                "No souffle binary found (native or via WSL). In WSL Debian: "
                "add the souffle-lang apt repo and `apt install souffle`."
            )
        self.command = resolved
        self.uses_wsl = Path(resolved[0]).stem.lower() == "wsl"
        self.timeout_seconds = timeout_seconds

    def evaluate(self, program: Program) -> Model:
        rules = parse_rules(program.rules)
        predicate_map = _build_predicate_map(program, rules)
        column_types = _infer_column_types(program, rules)
        text = _render_souffle_program(program, rules, predicate_map, column_types)

        with tempfile.TemporaryDirectory(prefix="souffle-oracle-") as temp_dir:
            root = Path(temp_dir)
            program_path = root / "program.dl"
            output_dir = root / "results"
            output_dir.mkdir(parents=True, exist_ok=True)
            program_path.write_text(text, encoding="utf-8")
            if self.uses_wsl:
                program_argument = _to_wsl_path(program_path)
                output_argument = _to_wsl_path(output_dir)
            else:
                program_argument = str(program_path)
                output_argument = str(output_dir)
            command = [*self.command, program_argument, "-D", output_argument]
            try:
                result = subprocess.run(
                    command,
                    capture_output=True,
                    text=True,
                    check=False,
                    timeout=self.timeout_seconds,
                )
            except subprocess.TimeoutExpired as exc:
                raise SouffleError(
                    f"souffle timed out after {self.timeout_seconds}s",
                    command=command,
                ) from exc
            if result.returncode != 0:
                raise SouffleError(
                    result.stderr.strip() or result.stdout.strip() or "souffle failed",
                    command=command,
                    stdout=result.stdout,
                    stderr=result.stderr,
                    returncode=result.returncode,
                )
            facts: dict[str, set[FactTuple]] = {}
            for predicate, translated in predicate_map.items():
                arity = _predicate_arity(predicate, program, rules)
                types = [
                    column_types.get((predicate, column), "symbol")
                    for column in range(arity)
                ]
                facts[predicate] = _read_output(
                    output_dir / f"{translated}.csv", types
                )
            return Model(facts=facts)


def _predicate_arity(predicate: str, program: Program, rules: list[RuleAst]) -> int:
    rows = program.facts.get(predicate)
    if rows:
        return len(rows[0])
    for rule in rules:
        if rule.head.predicate == predicate:
            return len(rule.head.terms)
        for atom in (*rule.positive, *rule.negative):
            if atom.predicate == predicate:
                return len(atom.terms)
    return 0


def _build_predicate_map(program: Program, rules: list[RuleAst]) -> dict[str, str]:
    predicates = set(program.facts)
    for rule in rules:
        predicates.add(rule.head.predicate)
        for atom in (*rule.positive, *rule.negative):
            predicates.add(atom.predicate)
    mapping: dict[str, str] = {}
    for index, predicate in enumerate(sorted(predicates), start=1):
        sanitized = re.sub(r"[^A-Za-z0-9_]+", "_", predicate).strip("_") or "predicate"
        mapping[predicate] = f"p_{index}_{sanitized}"
    return mapping


def _scalar_type(value: Scalar) -> str:
    if isinstance(value, bool):
        raise SouffleUnsupportedError("Boolean scalars are not supported for souffle")
    if isinstance(value, int):
        return "number"
    if isinstance(value, float):
        return "float"
    return "symbol"


def _infer_column_types(
    program: Program,
    rules: list[RuleAst],
) -> dict[tuple[str, int], str]:
    types: dict[tuple[str, int], str] = {}

    def observe(predicate: str, column: int, kind: str) -> None:
        key = (predicate, column)
        known = types.get(key)
        if known is None:
            types[key] = kind
        elif known != kind:
            raise SouffleUnsupportedError(
                f"Column {column} of predicate {predicate!r} mixes {known} and {kind}"
            )

    for predicate, rows in program.facts.items():
        for row in rows:
            for column, value in enumerate(row):
                observe(predicate, column, _scalar_type(value))

    changed = True
    guard = 0
    while changed:
        changed = False
        guard += 1
        if guard > max(len(rules) * 4, 16):
            break
        for rule in rules:
            variable_types: dict[str, str] = {}
            for atom in rule.positive:
                for column, term in enumerate(atom.terms):
                    known = types.get((atom.predicate, column))
                    if isinstance(term, Variable) and known is not None:
                        variable_types.setdefault(term.name, known)
            for atom in (*rule.positive, *rule.negative, rule.head):
                for column, term in enumerate(atom.terms):
                    kind = _term_type(term, variable_types)
                    if kind is None:
                        continue
                    key = (atom.predicate, column)
                    if types.get(key) != kind:
                        observe(atom.predicate, column, kind)
                        changed = True
    return types


def _term_type(term: Term, variable_types: dict[str, str]) -> str | None:
    if isinstance(term, Constant):
        return _scalar_type(term.value)
    if isinstance(term, Variable):
        return variable_types.get(term.name)
    if isinstance(term, Arithmetic):
        return "number"
    return None


def _render_souffle_program(
    program: Program,
    rules: list[RuleAst],
    predicate_map: dict[str, str],
    column_types: dict[tuple[str, int], str],
) -> str:
    lines: list[str] = []
    for predicate, translated in sorted(predicate_map.items()):
        arity = _predicate_arity(predicate, program, rules)
        if arity == 0:
            raise SouffleUnsupportedError(
                f"Zero-arity predicate {predicate!r} is not supported for souffle"
            )
        columns = ", ".join(
            f"c{column}:{column_types.get((predicate, column), 'symbol')}"
            for column in range(arity)
        )
        lines.append(f".decl {translated}({columns})")
        lines.append(f".output {translated}")

    for predicate, rows in program.facts.items():
        translated = predicate_map[predicate]
        for row in rows:
            rendered = ", ".join(_render_scalar(value) for value in row)
            lines.append(f"{translated}({rendered}).")

    for rule in rules:
        lines.append(_render_rule(rule, predicate_map))

    return "\n".join(lines) + "\n"


def _render_scalar(value: Scalar) -> str:
    if isinstance(value, bool):
        raise SouffleUnsupportedError("Boolean scalars are not supported for souffle")
    if isinstance(value, (int, float)):
        return str(value)
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _render_rule(rule: RuleAst, predicate_map: dict[str, str]) -> str:
    head = _render_atom(rule.head, predicate_map)
    parts: list[str] = []
    parts.extend(_render_atom(atom, predicate_map) for atom in rule.positive)
    parts.extend(
        f"{comparison_left} {op} {comparison_right}"
        for op, comparison_left, comparison_right in (
            (item.op, _render_term(item.left), _render_term(item.right))
            for item in rule.comparisons
        )
    )
    parts.extend(f"!{_render_atom(atom, predicate_map)}" for atom in rule.negative)
    if not parts:
        return f"{head}."
    return f"{head} :- {', '.join(parts)}."


def _render_atom(atom: AtomAst, predicate_map: dict[str, str]) -> str:
    rendered = ", ".join(_render_term(term) for term in atom.terms)
    return f"{predicate_map[atom.predicate]}({rendered})"


def _render_term(term: Term) -> str:
    if isinstance(term, Constant):
        return _render_scalar(term.value)
    if isinstance(term, Variable):
        return term.name if _IDENTIFIER_RE.match(term.name) else f"v_{term.name}"
    if isinstance(term, Wildcard):
        return "_"
    return f"({_render_term(term.left)} {term.op} {_render_term(term.right)})"


def _read_output(path: Path, types: list[str]) -> set[FactTuple]:
    if not path.exists():
        return set()
    rows: set[FactTuple] = set()
    content = path.read_text(encoding="utf-8")
    for line in content.splitlines():
        if not line:
            continue
        fields = line.split("\t")
        if len(fields) != len(types):
            raise SouffleError(
                f"Unexpected column count in {path.name}: "
                f"expected {len(types)}, got {len(fields)}"
            )
        row: list[Scalar] = []
        for value, kind in zip(fields, types, strict=True):
            if kind == "number":
                row.append(int(value))
            elif kind == "float":
                row.append(float(value))
            else:
                row.append(value)
        rows.add(tuple(row))
    return rows
