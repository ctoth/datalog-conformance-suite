from __future__ import annotations

import argparse
from pathlib import Path

from datalog_conformance.corpus_audit import audit_program_surface, format_findings


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fail if retained program cases require invisible runner semantics."
    )
    parser.add_argument(
        "--test-dir",
        type=Path,
        default=Path("src/datalog_conformance/_tests"),
        help="Directory containing YAML test cases to audit.",
    )
    args = parser.parse_args()

    findings = audit_program_surface(args.test_dir)
    if findings:
        print(format_findings(findings, root=Path.cwd()))
        return 1

    print(f"Program-surface audit passed for {args.test_dir.as_posix()}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
