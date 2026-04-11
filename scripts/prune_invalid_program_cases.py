from __future__ import annotations

import argparse
from collections import defaultdict
from pathlib import Path

import yaml

from datalog_conformance.corpus_audit import audit_program_surface, format_findings


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Remove bundled program cases that require invisible runner semantics."
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

    findings = audit_program_surface(args.root)
    if not findings:
        print("No invalid program cases found.")
        return 0

    removals: dict[Path, set[str]] = defaultdict(set)
    strict_removals: dict[Path, set[str]] = defaultdict(set)
    for finding in findings:
        removals[finding.path].add(finding.case_name)
        strict_path = _strict_only_path(args.root, finding.path)
        if strict_path is not None:
            strict_removals[strict_path].add(f"strict_only_{finding.case_name}")

    print(format_findings(findings, root=Path.cwd()))
    print()
    print(
        f"Planned removals: {sum(len(names) for names in removals.values())} core case(s), "
        f"{sum(len(names) for names in strict_removals.values())} strict-only case(s)."
    )

    if not args.apply:
        print("Run with --apply to prune these cases.")
        return 1

    for path, case_names in sorted(removals.items()):
        _rewrite_file(path, case_names)
    for path, case_names in sorted(strict_removals.items()):
        if path.exists():
            _rewrite_file(path, case_names)

    print("Pruning complete.")
    return 0


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
