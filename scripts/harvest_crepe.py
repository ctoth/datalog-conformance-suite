from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Any

import yaml

SUPPORTED_CASES: dict[str, str] = {
    "invalid_arity.rs": "arity_mismatch",
    "recursive_negation.rs": "cyclic_negation",
    "unbound_variable.rs": "unbound_variable",
    "underscore_in_goal.rs": "safety_violations",
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Harvest portable Crepe UI error tests into YAML.")
    parser.add_argument(
        "--source",
        type=Path,
        default=Path.home() / "AppData/Local/Temp/datalog-harvest/crepe/tests/ui",
        help="Path to Crepe tests/ui directory",
    )
    parser.add_argument(
        "--dest",
        type=Path,
        default=Path("src/datalog_conformance/_tests/errors"),
        help="Destination directory for generated YAML files",
    )
    args = parser.parse_args()

    harvested = 0
    for filename, error_code in SUPPORTED_CASES.items():
        source_file = args.source / filename
        if not source_file.exists():
            raise FileNotFoundError(source_file)
        case = convert_crepe_case(source_file, error_code)
        destination = args.dest / f"crepe_{source_file.stem}.yaml"
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(
            yaml.safe_dump(case, sort_keys=False, allow_unicode=False),
            encoding="utf-8",
        )
        harvested += 1

    print(f"Harvested {harvested} Crepe error tests into {args.dest}")


def convert_crepe_case(source_file: Path, error_code: str) -> dict[str, Any]:
    source_text = source_file.read_text(encoding="utf-8")
    description = _extract_description(source_text)
    program_lines = _extract_crepe_body_lines(source_text)

    facts: dict[str, list[list[str | int]]] = {}
    rules: list[str] = []
    for line in program_lines:
        if line.startswith("@") or line.startswith("struct "):
            continue
        if "<-" in line:
            rules.append(_normalize_rule(line))
            continue
        if line.endswith(";"):
            predicate, row = _parse_fact(line)
            facts.setdefault(predicate, []).append(row)

    return {
        "name": f"crepe_{source_file.stem}",
        "description": description,
        "source": f"crepe/tests/ui/{source_file.name}",
        "tags": ["errors", "crepe"],
        "program": {
            "facts": facts,
            "rules": rules,
        },
        "expect_error": error_code,
    }


def _extract_description(source_text: str) -> str:
    for line in source_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("//"):
            return stripped.removeprefix("//").strip()
    return "Harvested from Crepe UI test."


def _extract_crepe_body_lines(source_text: str) -> list[str]:
    inside = False
    body: list[str] = []
    for raw_line in source_text.splitlines():
        line = raw_line.strip()
        if line.startswith("crepe!"):
            inside = True
            continue
        if inside and line == "}":
            break
        if inside and line:
            body.append(line)
    return body


def _normalize_rule(line: str) -> str:
    normalized = line.rstrip(";")
    normalized = normalized.replace("<-", ":-")
    normalized = re.sub(r"!\s*([A-Za-z_][A-Za-z0-9_]*)\(", r"not \1(", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def _parse_fact(line: str) -> tuple[str, list[str | int]]:
    fact_match = re.match(r"^(?P<name>[A-Za-z_][A-Za-z0-9_]*)\((?P<body>.*)\);$", line)
    if fact_match is None:
        raise ValueError(f"Unsupported Crepe fact syntax: {line}")
    predicate = fact_match.group("name")
    terms = [item.strip() for item in fact_match.group("body").split(",") if item.strip()]
    return predicate, [_convert_scalar(term) for term in terms]


def _convert_scalar(token: str) -> str | int:
    if re.fullmatch(r"-?\d+", token):
        return int(token)
    return token


if __name__ == "__main__":
    main()
