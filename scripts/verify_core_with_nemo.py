"""Verify retained core program cases against nemo-cli.

The Nemo translation and invocation live in ``datalog_conformance.oracles.nemo``;
this script adds corpus discovery, per-program batching, live logging, failure
artifact persistence, and a machine-readable summary.
"""

from __future__ import annotations

import argparse
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

from datalog_conformance.oracles.nemo import (
    DEFAULT_NMO_CANDIDATES,
    RenderedNemoProgram,
    load_exported_rows,
    render_program,
)
from datalog_conformance.plugin import discover_yaml_tests
from datalog_conformance.schema import FactTuple, TestCase


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
    for candidate in DEFAULT_NMO_CANDIDATES:
        if candidate.exists():
            return candidate
    return DEFAULT_NMO_CANDIDATES[0]


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
    rendered = render_program(first_case.program, expected_predicates)
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
                predicate: load_exported_rows(
                    output_dir / f"{rendered.exports[predicate]}.csv"
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
    assert case.program is not None
    try:
        rendered: RenderedNemoProgram = render_program(
            case.program, sorted(case.expect or {})
        )
        return rendered.text
    except Exception as exc:  # noqa: BLE001
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
