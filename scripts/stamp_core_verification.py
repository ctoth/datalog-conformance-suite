from __future__ import annotations

import argparse
from pathlib import Path

import yaml


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Stamp retained core YAML suites with direct Nemo verification metadata."
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path("src/datalog_conformance/_tests"),
        help="Corpus root containing basic/, negation/, and recursion/.",
    )
    args = parser.parse_args()

    updated = 0
    for category in ("basic", "negation", "recursion"):
        for path in sorted((args.root / category).glob("*.yaml")):
            raw = yaml.safe_load(path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                continue
            raw["verification"] = {"implementation": "nmo", "kind": "direct"}
            path.write_text(
                yaml.safe_dump(raw, sort_keys=False, allow_unicode=False),
                encoding="utf-8",
            )
            updated += 1

    print(f"Stamped {updated} core YAML file(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
