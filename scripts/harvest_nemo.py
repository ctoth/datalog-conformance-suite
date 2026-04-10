from __future__ import annotations

import argparse
import csv
import re
from pathlib import Path
from typing import Any

import yaml

SUPPORTED_CASES: dict[str, tuple[str, list[str]]] = {
    "basic/join.rls": ("basic", ["basic", "joins", "nemo"]),
    "basic/projection.rls": ("basic", ["basic", "projection", "nemo"]),
    "basic/union.rls": ("basic", ["basic", "union", "nemo"]),
    "basic/negation.rls": ("negation", ["basic", "negation", "nemo"]),
}

IMPORT_RE = re.compile(
    r'^@import\s+(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*:-\s*csv\s*\{[^}]*resource\s*=\s*"(?P<resource>[^"]+)"[^}]*\}\s*\.\s*$'
)
EXPORT_RE = re.compile(
    r"^@export\s+(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*:-\s*csv\s*\{[^}]*\}\s*\.\s*$"
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Harvest Nemo portable testcases into YAML.")
    parser.add_argument(
        "--source",
        type=Path,
        default=Path.home() / "AppData/Local/Temp/datalog-harvest/nemo/resources/testcases",
        help="Path to Nemo resources/testcases directory",
    )
    parser.add_argument(
        "--dest",
        type=Path,
        default=Path("src/datalog_conformance/_tests"),
        help="Destination root for generated YAML files",
    )
    args = parser.parse_args()

    harvested = 0
    for relative_name, (category, tags) in SUPPORTED_CASES.items():
        source_file = args.source / relative_name
        if not source_file.exists():
            raise FileNotFoundError(source_file)
        test_case = convert_nemo_case(source_file, tags)
        destination = args.dest / category / f"nemo_{source_file.stem}.yaml"
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(
            yaml.safe_dump(test_case, sort_keys=False, allow_unicode=False),
            encoding="utf-8",
        )
        harvested += 1

    print(f"Harvested {harvested} Nemo test files into {args.dest}")


def convert_nemo_case(source_file: Path, tags: list[str]) -> dict[str, Any]:
    lines = source_file.read_text(encoding="utf-8").splitlines()
    imports: dict[str, str] = {}
    exports: list[str] = []
    rules: list[str] = []
    inline_facts: dict[str, list[list[str | int]]] = {}

    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("%"):
            continue

        import_match = IMPORT_RE.match(line)
        if import_match:
            imports[import_match.group("name")] = import_match.group("resource")
            continue

        export_match = EXPORT_RE.match(line)
        if export_match:
            exports.append(export_match.group("name"))
            continue

        if line.startswith("@"):
            continue

        if _looks_like_fact(line):
            name, row = _parse_fact(line)
            inline_facts.setdefault(name, []).append(row)
            continue

        if line.endswith("."):
            rules.append(_normalize_rule(line))

    facts = {**_load_imported_facts(source_file, imports), **inline_facts}
    expect = _load_exports(source_file, exports)
    source_name = f"nemo/{source_file.relative_to(source_file.parents[2]).as_posix()}"

    tests: list[dict[str, Any]] = []
    for relation_name, rows in expect.items():
        tests.append(
            {
                "name": f"nemo_{source_file.stem}_{relation_name}",
                "description": (
                    f"Harvested from Nemo testcase {source_file.stem}, "
                    f"asserting exported relation {relation_name}."
                ),
                "tags": [*tags, relation_name.lower()],
                "program": {
                    "facts": facts,
                    "rules": rules,
                },
                "expect": {
                    relation_name: rows,
                },
            }
        )

    return {
        "source": source_name,
        "tags": tags,
        "tests": tests,
    }


def _load_imported_facts(
    source_file: Path, imports: dict[str, str]
) -> dict[str, list[list[str | int]]]:
    loaded: dict[str, list[list[str | int]]] = {}
    for relation, resource in imports.items():
        data_path = (source_file.parent / resource).resolve()
        if not data_path.exists():
            raise FileNotFoundError(data_path)
        loaded[relation] = _read_table(data_path)
    return loaded


def _load_exports(source_file: Path, exports: list[str]) -> dict[str, list[list[str | int]]]:
    output_dir = source_file.parent / source_file.stem
    if not output_dir.exists():
        raise FileNotFoundError(output_dir)

    expected: dict[str, list[list[str | int]]] = {}
    for relation in exports:
        csv_path = output_dir / f"{relation}.csv"
        tsv_path = output_dir / f"{relation}.tsv"
        if csv_path.exists():
            expected[relation] = _read_table(csv_path)
            continue
        if tsv_path.exists():
            expected[relation] = _read_table(tsv_path)
            continue
        raise FileNotFoundError(f"Missing exported output for {relation} under {output_dir}")
    return expected


def _read_table(path: Path) -> list[list[str | int]]:
    delimiter = "\t" if path.suffix == ".tsv" else ","
    rows: list[list[str | int]] = []
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle, delimiter=delimiter)
        for row in reader:
            if not row:
                continue
            rows.append([_convert_scalar(item) for item in row])
    return rows


def _normalize_rule(line: str) -> str:
    trimmed = line.rstrip(".")
    trimmed = re.sub(r"\?([A-Za-z_][A-Za-z0-9_]*)", r"\1", trimmed)
    trimmed = re.sub(r"~\s*([A-Za-z_][A-Za-z0-9_]*)\(", r"not \1(", trimmed)
    trimmed = re.sub(r"\s+", " ", trimmed).strip()
    return f"{trimmed}."


def _looks_like_fact(line: str) -> bool:
    return ":-" not in line and line.endswith(".") and "(" in line and line[0].isalpha()


def _parse_fact(line: str) -> tuple[str, list[str | int]]:
    fact_match = re.match(r"^(?P<name>[A-Za-z_][A-Za-z0-9_]*)\((?P<body>.*)\)\.$", line.strip())
    if fact_match is None:
        raise ValueError(f"Unsupported inline fact syntax: {line}")
    name = fact_match.group("name")
    body = fact_match.group("body")
    values = [item.strip() for item in body.split(",") if item.strip()]
    return name, [_convert_scalar(item) for item in values]


def _convert_scalar(token: str) -> str | int:
    stripped = token.strip()
    if stripped.startswith('"') and stripped.endswith('"'):
        return stripped[1:-1]
    if re.fullmatch(r"-?\d+", stripped):
        return int(stripped)
    return stripped


if __name__ == "__main__":
    main()
