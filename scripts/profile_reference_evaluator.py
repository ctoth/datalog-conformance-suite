"""Profile the reference evaluator across unique corpus programs.

Reports per-program wall time so pathological cases are visible. Intended for
suite maintenance, not CI.
"""

from __future__ import annotations

import json
import time

from datalog_conformance.plugin import discover_yaml_tests
from datalog_conformance.references import CoreReferenceEvaluator, ReferenceEvaluationError


def main() -> int:
    seen: set[str] = set()
    timings: list[tuple[float, str]] = []
    evaluator = CoreReferenceEvaluator()
    for yaml_path, case in discover_yaml_tests():
        if case.program is None or case.expect is None:
            continue
        key = json.dumps(
            {"facts": case.program.facts, "rules": case.program.rules}, sort_keys=True
        )
        if key in seen:
            continue
        seen.add(key)
        label = f"{yaml_path.stem}::{case.name}"
        print(f"START {label}", flush=True)
        started = time.perf_counter()
        try:
            evaluator.evaluate(case.program)
            status = "ok"
        except ReferenceEvaluationError as exc:
            status = f"error:{exc.code}"
        except Exception as exc:  # noqa: BLE001
            status = f"crash:{type(exc).__name__}"
        elapsed = time.perf_counter() - started
        timings.append((elapsed, f"{label} [{status}]"))
        if elapsed > 1.0:
            print(f"SLOW {elapsed:8.2f}s {label} [{status}]", flush=True)

    timings.sort(reverse=True)
    print(f"\nunique programs: {len(timings)}")
    print(f"total seconds: {sum(item[0] for item in timings):.1f}")
    print("slowest 15:")
    for elapsed, label in timings[:15]:
        print(f"  {elapsed:8.3f}s {label}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
