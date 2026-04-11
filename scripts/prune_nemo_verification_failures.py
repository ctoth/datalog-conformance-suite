from __future__ import annotations

import argparse
import re
from collections import defaultdict
from pathlib import Path

import yaml

_FAILURE_RE = re.compile(r"^(?P<path>.+?\.yaml)::(?P<case>[^:]+): ")
_LOG_FAILURE_RE = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} \[\d+\] FAIL (?P<failure>.+)$")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Remove bundled program cases that fail concrete Nemo verification."
    )
    parser.add_argument(
        "--summary-path",
        type=Path,
        default=None,
        help="Optional summary JSON emitted by verify_core_with_nemo.py.",
    )
    parser.add_argument(
        "--log-path",
        type=Path,
        default=None,
        help="Optional live verifier log to prune from before a summary exists.",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path("src/datalog_conformance/_tests"),
        help="Corpus root to prune.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write the removals instead of only printing the plan.",
    )
    args = parser.parse_args()

    failures = _load_failures(args.summary_path, args.log_path)

    removals: dict[Path, set[str]] = defaultdict(set)
    strict_removals: dict[Path, set[str]] = defaultdict(set)
    unparsable: list[str] = []
    for failure in failures:
        if not isinstance(failure, str) or failure.startswith("__fatal__:"):
            continue
        match = _FAILURE_RE.match(failure)
        if match is None:
            unparsable.append(failure)
            continue
        path = Path(match.group("path"))
        case_name = match.group("case")
        removals[path].add(case_name)
        strict_path = _strict_only_path(args.root, path)
        if strict_path is not None:
            strict_removals[strict_path].add(f"strict_only_{case_name}")

    print(
        f"Planned removals from Nemo verification: "
        f"{sum(len(names) for names in removals.values())} core case(s), "
        f"{sum(len(names) for names in strict_removals.values())} strict-only case(s)."
    )
    for path, case_names in sorted(removals.items()):
        rel = path.as_posix()
        names = ", ".join(sorted(case_names))
        print(f"- {rel}: {names}")
    if unparsable:
        print("Unparsed failure lines:")
        for item in unparsable:
            print(f"- {item}")

    if not args.apply:
        print("Run with --apply to prune these cases.")
        return 1

    for path, case_names in sorted(removals.items()):
        if path.exists():
            _rewrite_file(path, case_names)
    for path, case_names in sorted(strict_removals.items()):
        if path.exists():
            _rewrite_file(path, case_names)

    print("Pruning complete.")
    return 0


def _load_failures(summary_path: Path | None, log_path: Path | None) -> list[str]:
    if summary_path is not None:
        summary = yaml.safe_load(summary_path.read_text(encoding="utf-8"))
        if isinstance(summary, dict):
            failures = summary.get("failures", [])
            if isinstance(failures, list):
                return [item for item in failures if isinstance(item, str)]
    if log_path is not None:
        failures: list[str] = []
        for line in log_path.read_text(encoding="utf-8").splitlines():
            match = _LOG_FAILURE_RE.match(line)
            if match is not None:
                failures.append(match.group("failure"))
        return failures
    raise ValueError("Provide either --summary-path or --log-path.")


def _strict_only_path(root: Path, core_path: Path) -> Path | None:
    try:
        relative = core_path.relative_to(root)
    except ValueError:
        return None
    if relative.parts[0] not in {"basic", "negation", "recursion"}:
        return None
    category = relative.parts[0]
    return root / "defeasible" / "strict_only" / f"strict_only_{category}_{relative.stem}.yaml"


def _rewrite_file(path: Path, case_names: set[str]) -> None:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        path.unlink()
        return

    if "tests" in raw and isinstance(raw["tests"], list):
        kept = [
            case
            for case in raw["tests"]
            if isinstance(case, dict) and case.get("name") not in case_names
        ]
        if not kept:
            path.unlink()
            return
        raw["tests"] = kept
        path.write_text(
            yaml.safe_dump(raw, sort_keys=False, allow_unicode=False),
            encoding="utf-8",
        )
        return

    if raw.get("name") in case_names:
        path.unlink()
        return

    path.write_text(
        yaml.safe_dump(raw, sort_keys=False, allow_unicode=False),
        encoding="utf-8",
    )


if __name__ == "__main__":
    raise SystemExit(main())
