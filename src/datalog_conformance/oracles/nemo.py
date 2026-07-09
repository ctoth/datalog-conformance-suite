"""Nemo (nmo) as a first-class conformance oracle.

This module packages the corpus-proven translation from the suite's visible
program surface to Nemo 0.10 rule files, plus a :class:`NemoOracle` that
implements the standard :class:`~datalog_conformance.protocol.DatalogEvaluator`
protocol by shelling out to a local ``nmo`` binary.

That makes a real external implementation directly runnable against every
bundled program case:

.. code-block:: powershell

    uv run pytest tests --datalog-evaluator=datalog_conformance.oracles.nemo.NemoOracle

The translation renames predicates to a collision-free namespace, prefixes
variables with ``?``, quotes head-only identifiers as constants, splits
disjunctive bodies, and maps ``not`` to Nemo negation. It is the same code
path exercised by ``scripts/verify_core_with_nemo.py`` across the whole
retained corpus.
"""

from __future__ import annotations

import csv
import re
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from ..schema import FactTuple, Model, Program, Scalar

_SOURCE_NMO_ROOT = Path.home() / "src/nemo/target"
_HARVEST_NMO_ROOT = (
    Path.home() / "AppData/Local/Temp/datalog-harvest/nemo/target/x86_64-pc-windows-gnu"
)
DEFAULT_NMO_CANDIDATES: tuple[Path, ...] = (
    _SOURCE_NMO_ROOT / "x86_64-pc-windows-gnu/release/nmo.exe",
    _SOURCE_NMO_ROOT / "x86_64-pc-windows-gnu/debug/nmo.exe",
    _SOURCE_NMO_ROOT / "release/nmo",
    _SOURCE_NMO_ROOT / "debug/nmo",
    _HARVEST_NMO_ROOT / "release/nmo.exe",
    _HARVEST_NMO_ROOT / "debug/nmo.exe",
)

_ATOM_RE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*\((.*)\)\s*$")
_NUMERIC_RE = re.compile(r"-?\d+(?:\.\d+)?")
_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_WORD_RE = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\b")


class NemoError(RuntimeError):
    """Raised when nmo fails, times out, or produces unusable output."""

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


class NemoUnavailableError(NemoError):
    """Raised when no nmo binary can be located."""


def find_nmo(explicit: Path | None = None) -> Path | None:
    """Return the first existing nmo binary, or None."""

    if explicit is not None:
        return explicit if explicit.exists() else None
    for candidate in DEFAULT_NMO_CANDIDATES:
        if candidate.exists():
            return candidate
    return None


@dataclass(slots=True)
class RenderedNemoProgram:
    """Translated Nemo program text and the predicate export mapping."""

    text: str
    exports: dict[str, str]


class NemoOracle:
    """DatalogEvaluator protocol implementation backed by a local nmo binary."""

    def __init__(
        self,
        nmo: Path | None = None,
        *,
        timeout_seconds: int = 120,
    ) -> None:
        resolved = find_nmo(nmo)
        if resolved is None:
            raise NemoUnavailableError(
                "No nmo binary found. Build one with "
                "`cargo build --release -p nemo-cli --target x86_64-pc-windows-gnu` "
                "in ~/src/nemo."
            )
        self.nmo = resolved
        self.timeout_seconds = timeout_seconds

    def evaluate(self, program: Program) -> Model:
        exports = sorted(collect_program_predicates(program))
        rendered = render_program(program, exports)
        rows_by_export = run_rendered_program(
            rendered,
            nmo=self.nmo,
            timeout_seconds=self.timeout_seconds,
        )
        return Model(
            facts={
                predicate: rows_by_export.get(rendered.exports[predicate], set())
                for predicate in exports
            }
        )


def collect_program_predicates(program: Program) -> set[str]:
    """All predicate names visible in a program's facts and rules."""

    predicates = set(program.facts)
    for rule in program.rules:
        predicates.update(_collect_rule_predicates(rule))
    return predicates


def render_program(program: Program, export_predicates: Sequence[str]) -> RenderedNemoProgram:
    """Translate a visible program surface into Nemo 0.10 syntax."""

    predicate_map = _build_predicate_map(program, export_predicates)
    lines: list[str] = []
    for predicate, rows in program.facts.items():
        translated_predicate = predicate_map[predicate]
        for row in rows:
            lines.append(
                f"{translated_predicate}({', '.join(_render_fact_term(term) for term in row)}) ."
            )
    for rule in program.rules:
        lines.extend(_translate_rule(rule, predicate_map))
    for predicate in export_predicates:
        lines.append(f"@export {predicate_map[predicate]} :- csv {{}}.")
    return RenderedNemoProgram(
        text="\n".join(lines) + "\n",
        exports={predicate: predicate_map[predicate] for predicate in export_predicates},
    )


def run_rendered_program(
    rendered: RenderedNemoProgram,
    *,
    nmo: Path,
    timeout_seconds: int = 120,
) -> dict[str, set[FactTuple]]:
    """Run a rendered program and return rows keyed by translated predicate."""

    with tempfile.TemporaryDirectory(prefix="nemo-oracle-") as temp_dir:
        root = Path(temp_dir)
        program_path = root / "program.rls"
        output_dir = root / "results"
        output_dir.mkdir(parents=True, exist_ok=True)
        program_path.write_text(rendered.text, encoding="utf-8")
        command = [
            str(nmo),
            str(program_path),
            "-D",
            str(output_dir),
            "-o",
            "--report",
            "none",
        ]
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                check=False,
                timeout=timeout_seconds,
            )
        except subprocess.TimeoutExpired as exc:
            raise NemoError(
                f"nmo timed out after {timeout_seconds}s",
                command=command,
                stdout=_coerce_stream_text(exc.stdout),
                stderr=_coerce_stream_text(exc.stderr),
            ) from exc
        if result.returncode != 0:
            raise NemoError(
                result.stderr.strip() or result.stdout.strip() or "nmo failed",
                command=command,
                stdout=result.stdout,
                stderr=result.stderr,
                returncode=result.returncode,
            )
        return {
            translated: load_exported_rows(output_dir / f"{translated}.csv")
            for translated in rendered.exports.values()
        }


def _translate_rule(rule_text: str, predicate_map: dict[str, str]) -> list[str]:
    text = rule_text.strip().removesuffix(".")
    if ":-" not in text:
        context = _RuleContext()
        return [f"{_translate_atom(text, context, predicate_map, is_head=True)} ."]
    head_text, body_text = text.split(":-", 1)
    translated_rules: list[str] = []
    for body_alternative in _split_body_alternatives(body_text):
        body_atoms = _split_atoms(body_alternative)
        context = _RuleContext()
        context.body_identifiers = _collect_body_identifiers(body_atoms)
        body = ", ".join(
            _translate_atom(atom, context, predicate_map) for atom in body_atoms
        )
        for head_atom in _split_atoms(head_text):
            translated_rules.append(
                f"{_translate_atom(head_atom, context, predicate_map, is_head=True)} :- {body} ."
            )
    return translated_rules


def _translate_atom(
    atom_text: str,
    context: "_RuleContext",
    predicate_map: dict[str, str],
    *,
    is_head: bool = False,
) -> str:
    text = atom_text.strip()
    negated = False
    if text.startswith("not "):
        negated = True
        text = text[4:].strip()
    match = _ATOM_RE.match(text)
    if match is None:
        raise ValueError(f"Unsupported atom syntax for Nemo translation: {atom_text}")
    predicate = match.group(1)
    raw_args = match.group(2)
    translated_terms: list[str] = []
    for term in _split_terms(raw_args):
        try:
            translated_terms.append(
                _translate_rule_term(term, context, is_head=is_head)
            )
        except ValueError as exc:
            raise ValueError(
                f"{exc} in atom {atom_text!r} with term {term!r}"
            ) from exc
    translated_args = ", ".join(translated_terms)
    prefix = "~" if negated else ""
    return f"{prefix}{predicate_map.get(predicate, predicate)}({translated_args})"


def _render_fact_term(term: Scalar) -> str:
    if isinstance(term, bool):
        return "true" if term else "false"
    if isinstance(term, (int, float)):
        return str(term)
    return _quote_string(term)


def _translate_rule_term(term: str, context: "_RuleContext", *, is_head: bool = False) -> str:
    stripped = term.strip()
    if not stripped:
        raise ValueError("Empty term")
    if stripped.startswith('"') and stripped.endswith('"'):
        return stripped
    if _NUMERIC_RE.fullmatch(stripped):
        return stripped
    if stripped == "_":
        return context.fresh_anonymous()
    if _IDENTIFIER_RE.fullmatch(stripped):
        if is_head and stripped not in context.body_identifiers:
            return _quote_string(stripped)
        if stripped.startswith("_"):
            return f"?anon{stripped}"
        return f"?{stripped}"
    return _replace_words_outside_quotes(stripped, context, is_head=is_head)


def _replace_words_outside_quotes(
    text: str,
    context: "_RuleContext",
    *,
    is_head: bool = False,
) -> str:
    result: list[str] = []
    current: list[str] = []
    in_quotes = False
    for char in text:
        if char == '"':
            if current:
                result.append(_prefix_words("".join(current), context, is_head=is_head))
                current = []
            in_quotes = not in_quotes
            result.append(char)
            continue
        if in_quotes:
            result.append(char)
            continue
        current.append(char)
    if current:
        result.append(_prefix_words("".join(current), context, is_head=is_head))
    return "".join(result)


def _prefix_words(fragment: str, context: "_RuleContext", *, is_head: bool = False) -> str:
    def replace(match: re.Match[str]) -> str:
        word = match.group(1)
        if word == "_":
            return context.fresh_anonymous()
        if is_head and word not in context.body_identifiers:
            return _quote_string(word)
        if word.startswith("_"):
            return f"?anon{word}"
        return f"?{word}"

    return _WORD_RE.sub(replace, fragment)


def _split_atoms(body_text: str) -> list[str]:
    atoms: list[str] = []
    current: list[str] = []
    depth = 0
    in_quotes = False
    for char in body_text:
        if char == '"':
            in_quotes = not in_quotes
            current.append(char)
            continue
        if char == "," and depth == 0 and not in_quotes:
            atom = "".join(current).strip()
            if atom:
                atoms.append(atom)
            current = []
            continue
        if char == "(" and not in_quotes:
            depth += 1
        elif char == ")" and depth > 0 and not in_quotes:
            depth -= 1
        current.append(char)
    atom = "".join(current).strip()
    if atom:
        atoms.append(atom)
    return atoms


def _split_body_alternatives(body_text: str) -> list[str]:
    alternatives: list[str] = []
    current: list[str] = []
    depth = 0
    in_quotes = False
    for char in body_text:
        if char == '"':
            in_quotes = not in_quotes
            current.append(char)
            continue
        if char == ";" and depth == 0 and not in_quotes:
            alternative = "".join(current).strip()
            if alternative:
                alternatives.append(alternative)
            current = []
            continue
        if char == "(" and not in_quotes:
            depth += 1
        elif char == ")" and depth > 0 and not in_quotes:
            depth -= 1
        current.append(char)
    alternative = "".join(current).strip()
    if alternative:
        alternatives.append(alternative)
    return alternatives


def _split_terms(raw: str) -> list[str]:
    terms: list[str] = []
    current: list[str] = []
    depth = 0
    in_quotes = False
    for char in raw:
        if char == '"':
            in_quotes = not in_quotes
            current.append(char)
            continue
        if char == "," and depth == 0 and not in_quotes:
            terms.append("".join(current).strip())
            current = []
            continue
        if char == "(" and not in_quotes:
            depth += 1
        elif char == ")" and depth > 0 and not in_quotes:
            depth -= 1
        current.append(char)
    terms.append("".join(current).strip())
    return terms


def load_exported_rows(path: Path) -> set[FactTuple]:
    if not path.exists():
        return set()
    rows: set[FactTuple] = set()
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle)
        for row in reader:
            if not row:
                continue
            rows.add(tuple(_parse_scalar(item) for item in row))
    return rows


def _parse_scalar(token: str) -> Scalar:
    stripped = token.strip()
    if stripped.startswith('"') and stripped.endswith('"'):
        return stripped[1:-1].replace('\\"', '"').replace("\\\\", "\\")
    if stripped == "true":
        return True
    if stripped == "false":
        return False
    if re.fullmatch(r"-?\d+", stripped):
        return int(stripped)
    if re.fullmatch(r"-?\d+\.\d+", stripped):
        return float(stripped)
    return stripped


def _quote_string(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


class _RuleContext:
    def __init__(self) -> None:
        self.anonymous_counter = 0
        self.body_identifiers: set[str] = set()

    def fresh_anonymous(self) -> str:
        self.anonymous_counter += 1
        return f"?anon_{self.anonymous_counter}"


def _collect_body_identifiers(body_atoms: list[str]) -> set[str]:
    identifiers: set[str] = set()
    for atom in body_atoms:
        match = _ATOM_RE.match(atom.strip().removeprefix("not ").strip())
        if match is None:
            continue
        for term in _split_terms(match.group(2)):
            stripped = term.strip()
            if _IDENTIFIER_RE.fullmatch(stripped):
                identifiers.add(stripped)
    return identifiers


def _build_predicate_map(
    program: Program,
    export_predicates: Sequence[str],
) -> dict[str, str]:
    predicate_names = set(program.facts)
    predicate_names.update(export_predicates)
    for rule in program.rules:
        predicate_names.update(_collect_rule_predicates(rule))
    predicate_map: dict[str, str] = {}
    for index, predicate in enumerate(sorted(predicate_names), start=1):
        sanitized = re.sub(r"[^A-Za-z0-9_]+", "_", predicate).strip("_") or "predicate"
        translated = f"p_{index}_{sanitized}"
        if translated[0].isdigit():
            translated = f"p_{translated}"
        predicate_map[predicate] = translated
    return predicate_map


def _collect_rule_predicates(rule_text: str) -> set[str]:
    text = rule_text.strip().removesuffix(".")
    atoms: list[str] = []
    if ":-" not in text:
        atoms.extend(_split_atoms(text))
    else:
        head_text, body_text = text.split(":-", 1)
        atoms.extend(_split_atoms(head_text))
        for body_alternative in _split_body_alternatives(body_text):
            atoms.extend(_split_atoms(body_alternative))
    predicates: set[str] = set()
    for atom in atoms:
        candidate = atom.strip().removeprefix("not ").strip()
        match = _ATOM_RE.match(candidate)
        if match is not None:
            predicates.add(match.group(1))
    return predicates


def _coerce_stream_text(value: bytes | str | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value
