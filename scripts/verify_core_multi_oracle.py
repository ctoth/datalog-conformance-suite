"""Verify core program cases against every available external oracle.

Runs each unique visible program through Nemo, Souffle, and clingo (whichever
are available), compares each case's expected rows against every engine, and
writes an agreement matrix. The point is independent external evidence: a
case is strong when engines from different lineages agree on it, and any
disagreement is either a corpus bug or an engine bug — both worth surfacing.

Usage:

    uv run --extra oracles scripts/verify_core_multi_oracle.py
    uv run scripts/verify_core_multi_oracle.py --oracles nemo,souffle
"""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, cast

from datalog_conformance.plugin import discover_yaml_tests
from datalog_conformance.schema import FactTuple, Model, Program, TestCase

_ORACLE_BUILDERS: dict[str, Callable[[int], object]] = {}


def _register_builders() -> None:
    from datalog_conformance.oracles import (
        ClingoOracle,
        NemoOracle,
        SouffleOracle,
        SwiPrologOracle,
    )

    _ORACLE_BUILDERS["nemo"] = lambda timeout: NemoOracle(timeout_seconds=timeout)
    _ORACLE_BUILDERS["souffle"] = lambda timeout: SouffleOracle(
        timeout_seconds=timeout
    )
    _ORACLE_BUILDERS["clingo"] = lambda timeout: ClingoOracle()
    _ORACLE_BUILDERS["swipl"] = lambda timeout: SwiPrologOracle(
        timeout_seconds=timeout
    )


@dataclass(slots=True)
class _CaseResult:
    yaml_path: str
    case_name: str
    outcomes: dict[str, str]
    details: dict[str, str]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify core cases against all available external oracles."
    )
    parser.add_argument(
        "--test-dir",
        type=Path,
        default=Path("src/datalog_conformance/_tests"),
    )
    parser.add_argument(
        "--oracles",
        default="nemo,souffle,clingo,swipl",
        help="Comma-separated oracle names to attempt.",
    )
    parser.add_argument("--case-filter", default=None)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=120,
        help="Per-invocation timeout for subprocess-backed oracles.",
    )
    parser.add_argument(
        "--report-dir",
        type=Path,
        default=None,
    )
    args = parser.parse_args()

    _register_builders()
    report_dir = args.report_dir or (
        Path("reports/verify_core_multi_oracle") / time.strftime("%Y%m%d-%H%M%S")
    )
    report_dir.mkdir(parents=True, exist_ok=True)

    oracles: dict[str, object] = {}
    unavailable: dict[str, str] = {}
    for name in [item.strip() for item in args.oracles.split(",") if item.strip()]:
        builder = _ORACLE_BUILDERS.get(name)
        if builder is None:
            unavailable[name] = "unknown oracle name"
            continue
        try:
            oracles[name] = builder(args.timeout_seconds)
        except Exception as exc:  # noqa: BLE001 - availability probe
            unavailable[name] = f"{type(exc).__name__}: {exc}"

    if not oracles:
        print("no oracles available:")
        for name, reason in unavailable.items():
            print(f"- {name}: {reason}")
        return 2

    started = time.perf_counter()
    batches = _group_batches(args.test_dir, args.case_filter, args.limit)
    results: list[_CaseResult] = []
    model_cache: dict[tuple[str, str], tuple[str, Model | None, str]] = {}

    for batch_index, (program_key, yaml_path, program, cases) in enumerate(
        batches, start=1
    ):
        print(
            f"[{batch_index}/{len(batches)}] {yaml_path.name} ({len(cases)} case(s))",
            flush=True,
        )
        per_oracle: dict[str, tuple[str, Model | None, str]] = {}
        for name, oracle in oracles.items():
            cache_key = (name, program_key)
            if cache_key not in model_cache:
                model_cache[cache_key] = _evaluate(oracle, program)
            per_oracle[name] = model_cache[cache_key]

        for case in cases:
            outcomes: dict[str, str] = {}
            details: dict[str, str] = {}
            for name, (status, model, message) in per_oracle.items():
                if status != "ok":
                    outcomes[name] = status
                    details[name] = message
                    continue
                assert model is not None
                mismatch = _compare(case, model)
                if mismatch is None:
                    outcomes[name] = "ok"
                else:
                    outcomes[name] = "mismatch"
                    details[name] = mismatch
            results.append(
                _CaseResult(
                    yaml_path=yaml_path.as_posix(),
                    case_name=case.name,
                    outcomes=outcomes,
                    details=details,
                )
            )

    elapsed = time.perf_counter() - started
    summary = _summarize(results, list(oracles), unavailable, elapsed)
    (report_dir / "matrix.json").write_text(
        json.dumps(
            [
                {
                    "yaml_path": item.yaml_path,
                    "case": item.case_name,
                    "outcomes": item.outcomes,
                    "details": item.details,
                }
                for item in results
            ],
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    (report_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    print(json.dumps(summary, indent=2, sort_keys=True))
    print(f"matrix: {(report_dir / 'matrix.json').as_posix()}")
    disagreements = [
        item
        for item in results
        if "mismatch" in item.outcomes.values()
    ]
    if disagreements:
        print(f"MISMATCHES: {len(disagreements)}")
        for item in disagreements[:20]:
            print(f"- {item.yaml_path}::{item.case_name}: {item.outcomes}")
        return 1
    return 0


def _evaluate(oracle: object, program: Program) -> tuple[str, Model | None, str]:
    evaluate = getattr(oracle, "evaluate")
    try:
        model = evaluate(program)
    except Exception as exc:  # noqa: BLE001 - engines fail in engine-specific ways
        kind = type(exc).__name__
        status = "unsupported" if "Unsupported" in kind else "error"
        return (status, None, f"{kind}: {exc}")
    return ("ok", cast(Model, model), "")


def _compare(case: TestCase, model: Model) -> str | None:
    assert case.expect is not None
    expected_map = cast(dict[str, list[FactTuple]], case.expect)
    for predicate, expected_rows in expected_map.items():
        actual = model.facts.get(predicate, set())
        if set(expected_rows) != actual:
            missing = set(expected_rows) - actual
            extra = actual - set(expected_rows)
            return (
                f"predicate {predicate!r}: missing={sorted(missing)!r} "
                f"extra={sorted(extra)!r}"
            )
    return None


def _group_batches(
    test_dir: Path,
    case_filter: str | None,
    limit: int,
) -> list[tuple[str, Path, Program, list[TestCase]]]:
    grouped: dict[str, tuple[str, Path, Program, list[TestCase]]] = {}
    count = 0
    for yaml_path, case in discover_yaml_tests(test_dir):
        if case.program is None or case.expect is None:
            continue
        if case_filter and case_filter not in case.name:
            continue
        count += 1
        if limit and count > limit:
            break
        key = (
            yaml_path.as_posix()
            + "::"
            + json.dumps(
                {"facts": case.program.facts, "rules": case.program.rules},
                sort_keys=True,
            )
        )
        if key not in grouped:
            grouped[key] = (key, yaml_path, case.program, [])
        grouped[key][3].append(case)
    return list(grouped.values())


def _summarize(
    results: list[_CaseResult],
    oracle_names: list[str],
    unavailable: dict[str, str],
    elapsed: float,
) -> dict[str, object]:
    per_oracle: dict[str, dict[str, int]] = {
        name: {"ok": 0, "mismatch": 0, "unsupported": 0, "error": 0}
        for name in oracle_names
    }
    agreement_counts: dict[str, int] = {}
    for item in results:
        ok_count = 0
        for name, outcome in item.outcomes.items():
            per_oracle[name][outcome] = per_oracle[name].get(outcome, 0) + 1
            if outcome == "ok":
                ok_count += 1
        bucket = f"verified_by_{ok_count}"
        agreement_counts[bucket] = agreement_counts.get(bucket, 0) + 1
    return {
        "cases": len(results),
        "oracles": oracle_names,
        "unavailable": unavailable,
        "per_oracle": per_oracle,
        "agreement": agreement_counts,
        "elapsed_seconds": round(elapsed, 1),
    }


if __name__ == "__main__":
    raise SystemExit(main())
