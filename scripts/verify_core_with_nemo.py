from __future__ import annotations

import argparse
import csv
import json
import re
import shutil
import subprocess
import tempfile
import time
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from datalog_conformance.plugin import discover_yaml_tests
from datalog_conformance.schema import FactTuple, Scalar, TestCase

_SOURCE_NMO_ROOT = Path.home() / "src/nemo/target"
_HARVEST_NMO_ROOT = (
    Path.home() / "AppData/Local/Temp/datalog-harvest/nemo/target/x86_64-pc-windows-gnu"
)
_DEFAULT_NMO_CANDIDATES = [
    _SOURCE_NMO_ROOT / "x86_64-pc-windows-gnu/release/nmo.exe",
    _SOURCE_NMO_ROOT / "x86_64-pc-windows-gnu/debug/nmo.exe",
    _SOURCE_NMO_ROOT / "release/nmo",
    _SOURCE_NMO_ROOT / "debug/nmo",
    _HARVEST_NMO_ROOT / "release/nmo.exe",
    _HARVEST_NMO_ROOT / "debug/nmo.exe",
]
_ATOM_RE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*\((.*)\)\s*$")
_NUMERIC_RE = re.compile(r"-?\d+(?:\.\d+)?")
_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_WORD_RE = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\b")


@dataclass(slots=True)
class _InvocationArtifacts:
    command: list[str]
    program_text: str
    stdout: str = ""
    stderr: str = ""
    returncode: int | None = None
    exported_csvs: dict[str, str] | None = None


class _CaseVerificationError(RuntimeError):
    def __init__(self, message: str, *, artifacts: _InvocationArtifacts) -> None:
        super().__init__(message)
        self.artifacts = artifacts


@dataclass(slots=True)
class _RenderedProgram:
    text: str
    expected_exports: dict[str, str]


@dataclass(slots=True)
class _CaseTarget:
    index: int
    yaml_path: Path
    case: TestCase


@dataclass(slots=True)
class _ProgramBatch:
    yaml_path: Path
    program_key: str
    targets: list[_CaseTarget]


@dataclass(slots=True)
class _BatchRun:
    artifacts: _InvocationArtifacts
    actual_rows_by_predicate: dict[str, set[FactTuple]]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify retained core program cases against nemo-cli."
    )
    parser.add_argument(
        "--nmo",
        type=Path,
        default=_resolve_default_nmo(),
        help="Path to nmo.exe.",
    )
    parser.add_argument(
        "--test-dir",
        type=Path,
        default=Path("src/datalog_conformance/_tests"),
        help="Directory containing YAML tests.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Optional cap on program cases to verify.",
    )
    parser.add_argument(
        "--case-filter",
        default=None,
        help="Optional substring filter on case names.",
    )
    parser.add_argument(
        "--report-dir",
        type=Path,
        default=None,
        help="Directory for this verification run's logs, summaries, and artifacts.",
    )
    parser.add_argument(
        "--log-path",
        type=Path,
        default=None,
        help="Optional path to the live verification log file.",
    )
    parser.add_argument(
        "--case-timeout-seconds",
        type=int,
        default=120,
        help="Per nemo-cli invocation timeout. Shared visible programs are grouped into one run.",
    )
    parser.add_argument(
        "--summary-path",
        type=Path,
        default=None,
        help="Optional path to the machine-readable verification summary.",
    )
    args = parser.parse_args()

    if not args.nmo.exists():
        raise FileNotFoundError(args.nmo)

    report_dir = args.report_dir
    if report_dir is None:
        report_dir = Path("reports/verify_core_with_nemo") / time.strftime("%Y%m%d-%H%M%S")
    log_path = args.log_path or (report_dir / "verify_core_with_nemo.log")
    summary_path = args.summary_path or (report_dir / "verify_core_with_nemo_summary.json")
    failure_dir = report_dir / "failures"

    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text("", encoding="utf-8")
    failure_dir.mkdir(parents=True, exist_ok=True)
    summary_path.parent.mkdir(parents=True, exist_ok=True)

    selected_targets = _select_targets(
        args.test_dir,
        case_filter=args.case_filter,
        limit=args.limit,
    )
    attempted = len(selected_targets)
    program_batches = _group_program_batches(selected_targets)
    succeeded = 0
    failures: list[str] = []
    started_at = time.perf_counter()
    _log(
        log_path,
        (
            f"starting nemo verification: nmo={args.nmo} test_dir={args.test_dir} "
            f"limit={args.limit or 'all'} case_filter={args.case_filter or '<none>'} "
            f"case_timeout_seconds={args.case_timeout_seconds} "
            f"selected_cases={attempted} grouped_batches={len(program_batches)} "
            f"log_path={log_path} summary_path={summary_path} "
            f"failure_dir={failure_dir}"
        ),
    )
    try:
        for batch_index, batch in enumerate(program_batches, start=1):
            _log(
                log_path,
                (
                    f"[batch {batch_index}/{len(program_batches)}] START "
                    f"{batch.yaml_path.as_posix()} cases={len(batch.targets)} "
                    f"case_ids={','.join(str(target.index) for target in batch.targets)}"
                ),
            )
            try:
                batch_run = _run_batch(
                    batch,
                    args.nmo,
                    case_timeout_seconds=args.case_timeout_seconds,
                )
            except _CaseVerificationError as exc:
                for target in batch.targets:
                    failure = (
                        f"{target.yaml_path.as_posix()}::{target.case.name}: "
                        f"{type(exc).__name__}: {exc}"
                    )
                    failures.append(failure)
                    _persist_failure_artifacts(
                        failure_dir,
                        yaml_path=target.yaml_path,
                        case=target.case,
                        failure=failure,
                        artifacts=exc.artifacts,
                    )
                    _log(log_path, f"[{target.index}] FAIL {failure}")
                continue
            except Exception as exc:  # noqa: BLE001
                traceback_text = traceback.format_exc()
                for target in batch.targets:
                    failure = (
                        f"{target.yaml_path.as_posix()}::{target.case.name}: "
                        f"{type(exc).__name__}: {exc}"
                    )
                    failures.append(failure)
                    _persist_failure_artifacts(
                        failure_dir,
                        yaml_path=target.yaml_path,
                        case=target.case,
                        failure=failure,
                        traceback_text=traceback_text,
                    )
                    _log(log_path, f"[{target.index}] FAIL {failure}")
                continue

            for target in batch.targets:
                mismatch = _find_case_mismatch(target.case, batch_run.actual_rows_by_predicate)
                if mismatch is not None:
                    failure = f"{target.yaml_path.as_posix()}::{target.case.name}: {mismatch}"
                    failures.append(failure)
                    _persist_failure_artifacts(
                        failure_dir,
                        yaml_path=target.yaml_path,
                        case=target.case,
                        failure=failure,
                        artifacts=batch_run.artifacts,
                    )
                    _log(log_path, f"[{target.index}] FAIL {failure}")
                    continue
                succeeded += 1
                _log(
                    log_path,
                    f"[{target.index}] OK {target.yaml_path.as_posix()}::{target.case.name}",
                )
    except Exception as exc:  # noqa: BLE001
        _log(log_path, f"FATAL {type(exc).__name__}: {exc}")
        _log(log_path, traceback.format_exc().rstrip())
        failures.append(f"__fatal__: {type(exc).__name__}: {exc}")

    elapsed = time.perf_counter() - started_at
    _log(
        log_path,
        (
            f"completed nemo verification in {elapsed:.1f}s: "
            f"attempted={attempted} succeeded={succeeded} failures={len(failures)}"
        ),
    )
    _write_summary(
        summary_path,
        nmo=args.nmo,
        test_dir=args.test_dir,
        log_path=log_path,
        failure_dir=failure_dir,
        attempted=attempted,
        batches_attempted=len(program_batches),
        succeeded=succeeded,
        failures=failures,
        elapsed_seconds=elapsed,
        case_filter=args.case_filter,
        case_timeout_seconds=args.case_timeout_seconds,
    )
    print(f"log_path: {log_path.as_posix()}")
    print(f"summary_path: {summary_path.as_posix()}")
    print(f"failure_dir: {failure_dir.as_posix()}")
    print(f"verified_cases_attempted: {attempted}")
    if failures:
        print(f"failures: {len(failures)}")
        for item in failures:
            print(f"- {item}")
        return 1

    print("all requested core cases verified against nemo-cli")
    return 0


def _resolve_default_nmo() -> Path:
    for candidate in _DEFAULT_NMO_CANDIDATES:
        if candidate.exists():
            return candidate
    return _DEFAULT_NMO_CANDIDATES[0]


def _select_targets(
    test_dir: Path,
    *,
    case_filter: str | None,
    limit: int,
) -> list[_CaseTarget]:
    targets: list[_CaseTarget] = []
    for yaml_path, case in discover_yaml_tests(test_dir):
        if case.program is None or case.expect is None:
            continue
        if case_filter and case_filter not in case.name:
            continue
        targets.append(_CaseTarget(index=len(targets) + 1, yaml_path=yaml_path, case=case))
        if limit and len(targets) >= limit:
            break
    return targets


def _group_program_batches(targets: list[_CaseTarget]) -> list[_ProgramBatch]:
    grouped: dict[str, _ProgramBatch] = {}
    for target in targets:
        assert target.case.program is not None
        serialized_program = json.dumps(
            {
                "facts": target.case.program.facts,
                "rules": target.case.program.rules,
            },
            sort_keys=True,
        )
        program_key = f"{target.yaml_path.as_posix()}::{serialized_program}"
        batch = grouped.get(program_key)
        if batch is None:
            batch = _ProgramBatch(
                yaml_path=target.yaml_path,
                program_key=program_key,
                targets=[],
            )
            grouped[program_key] = batch
        batch.targets.append(target)
    return list(grouped.values())


def _run_batch(
    batch: _ProgramBatch,
    nmo: Path,
    *,
    case_timeout_seconds: int,
) -> _BatchRun:
    first_case = batch.targets[0].case
    assert first_case.program is not None
    expected_predicates = sorted(
        {
            predicate
            for target in batch.targets
            for predicate in _case_expectations(target.case)
        }
    )
    rendered = _render_program(first_case, expected_predicates)
    program_text = rendered.text

    with tempfile.TemporaryDirectory(prefix="nemo-verify-") as temp_dir:
        root = Path(temp_dir)
        program_path = root / "program.rls"
        output_dir = root / "results"
        output_dir.mkdir(parents=True, exist_ok=True)
        program_path.write_text(program_text, encoding="utf-8")
        command = [
            str(nmo),
            str(program_path),
            "-D",
            str(output_dir),
            "-o",
            "--report",
            "none",
        ]
        artifacts = _InvocationArtifacts(command=command, program_text=program_text)
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                check=False,
                timeout=case_timeout_seconds,
            )
        except subprocess.TimeoutExpired as exc:
            artifacts.stdout = _coerce_stream_text(exc.stdout)
            artifacts.stderr = _coerce_stream_text(exc.stderr)
            artifacts.exported_csvs = _collect_exported_csvs(output_dir)
            raise _CaseVerificationError(
                (
                    f"nmo timed out after {case_timeout_seconds}s "
                    f"for batch with {len(batch.targets)} case(s)"
                ),
                artifacts=artifacts,
            ) from exc
        artifacts.returncode = result.returncode
        artifacts.stdout = result.stdout
        artifacts.stderr = result.stderr
        artifacts.exported_csvs = _collect_exported_csvs(output_dir)
        if result.returncode != 0:
            raise _CaseVerificationError(
                result.stderr.strip() or result.stdout.strip() or "nmo failed",
                artifacts=artifacts,
            )
        return _BatchRun(
            artifacts=artifacts,
            actual_rows_by_predicate={
                predicate: _load_exported_rows(
                    output_dir / f"{rendered.expected_exports[predicate]}.csv"
                )
                for predicate in expected_predicates
            },
        )


def _find_case_mismatch(
    case: TestCase,
    actual_rows_by_predicate: dict[str, set[FactTuple]],
) -> str | None:
    assert case.program is not None
    assert case.expect is not None
    for predicate, expected_rows in _case_expectations(case).items():
        actual_rows = actual_rows_by_predicate.get(predicate, set())
        if set(expected_rows) != actual_rows:
            return (
                f"predicate {predicate!r}: expected {_sorted_fact_rows(set(expected_rows))!r}, "
                f"got {_sorted_fact_rows(actual_rows)!r}"
            )
    return None


def _case_expectations(case: TestCase) -> dict[str, list[FactTuple]]:
    assert case.program is not None
    assert case.expect is not None
    return cast(dict[str, list[FactTuple]], case.expect)


def _render_program(case: TestCase, expected_predicates: list[str]) -> _RenderedProgram:
    assert case.program is not None
    predicate_map = _build_predicate_map(case, expected_predicates)
    lines: list[str] = []
    for predicate, rows in case.program.facts.items():
        translated_predicate = predicate_map[predicate]
        for row in rows:
            lines.append(
                f"{translated_predicate}({', '.join(_render_fact_term(term) for term in row)}) ."
            )
    for rule in case.program.rules:
        lines.extend(_translate_rule(rule, predicate_map))
    for predicate in expected_predicates:
        lines.append(f"@export {predicate_map[predicate]} :- csv {{}}.")
    return _RenderedProgram(
        text="\n".join(lines) + "\n",
        expected_exports={predicate: predicate_map[predicate] for predicate in expected_predicates},
    )


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


def _load_exported_rows(path: Path) -> set[FactTuple]:
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


def _build_predicate_map(case: TestCase, expected_predicates: list[str]) -> dict[str, str]:
    assert case.program is not None
    predicate_names = set(case.program.facts)
    predicate_names.update(expected_predicates)
    for rule in case.program.rules:
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


def _persist_failure_artifacts(
    failure_dir: Path,
    *,
    yaml_path: Path,
    case: TestCase,
    failure: str,
    artifacts: _InvocationArtifacts | None = None,
    traceback_text: str | None = None,
) -> None:
    safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", case.name)
    base = failure_dir / safe_name
    if base.exists():
        shutil.rmtree(base)
    base.mkdir(parents=True, exist_ok=True)
    if artifacts is not None:
        program_text = artifacts.program_text
    else:
        program_text = _safe_render_program(case)
    (base / "program.rls").write_text(program_text, encoding="utf-8")
    (base / "failure.txt").write_text(failure + "\n", encoding="utf-8")
    if traceback_text:
        (base / "traceback.txt").write_text(traceback_text, encoding="utf-8")
    metadata: dict[str, object] = {
        "yaml_path": yaml_path.as_posix(),
        "case_name": case.name,
        "failure": failure,
        "traceback_path": "traceback.txt" if traceback_text else None,
    }
    if artifacts is not None:
        metadata["command"] = artifacts.command
        metadata["returncode"] = artifacts.returncode
        (base / "command.txt").write_text(" ".join(artifacts.command) + "\n", encoding="utf-8")
        (base / "stdout.txt").write_text(artifacts.stdout, encoding="utf-8")
        (base / "stderr.txt").write_text(artifacts.stderr, encoding="utf-8")
        exports_dir = base / "exports"
        exports_dir.mkdir(parents=True, exist_ok=True)
        for file_name, content in sorted((artifacts.exported_csvs or {}).items()):
            (exports_dir / file_name).write_text(content, encoding="utf-8")
    (base / "metadata.json").write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _collect_exported_csvs(output_dir: Path) -> dict[str, str]:
    exported: dict[str, str] = {}
    if not output_dir.exists():
        return exported
    for path in sorted(output_dir.glob("*.csv")):
        exported[path.name] = path.read_text(encoding="utf-8")
    return exported


def _coerce_stream_text(value: bytes | str | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def _write_summary(
    summary_path: Path,
    *,
    nmo: Path,
    test_dir: Path,
    log_path: Path,
    failure_dir: Path,
    attempted: int,
    batches_attempted: int,
    succeeded: int,
    failures: list[str],
    elapsed_seconds: float,
    case_filter: str | None,
    case_timeout_seconds: int,
) -> None:
    summary: dict[str, object] = {
        "nmo": nmo.as_posix(),
        "test_dir": test_dir.as_posix(),
        "log_path": log_path.as_posix(),
        "failure_dir": failure_dir.as_posix(),
        "attempted": attempted,
        "batches_attempted": batches_attempted,
        "succeeded": succeeded,
        "failed": len(failures),
        "elapsed_seconds": elapsed_seconds,
        "case_filter": case_filter,
        "case_timeout_seconds": case_timeout_seconds,
        "failures": failures,
    }
    summary_path.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _sorted_fact_rows(rows: set[FactTuple]) -> list[FactTuple]:
    return sorted(
        rows,
        key=lambda row: tuple((type(value).__name__, repr(value)) for value in row),
    )


def _safe_render_program(case: TestCase) -> str:
    try:
        return _render_program(case, sorted(case.expect or {})).text
    except Exception as exc:  # noqa: BLE001
        assert case.program is not None
        fallback = [
            f"# failed to render translated program: {type(exc).__name__}: {exc}",
            "# raw facts",
        ]
        for predicate, rows in case.program.facts.items():
            for row in rows:
                fallback.append(f"{predicate}{tuple(row)!r}")
        fallback.append("# raw rules")
        fallback.extend(case.program.rules)
        return "\n".join(fallback) + "\n"


def _log(log_path: Path, message: str) -> None:
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} {message}"
    print(line, flush=True)
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


if __name__ == "__main__":
    raise SystemExit(main())
