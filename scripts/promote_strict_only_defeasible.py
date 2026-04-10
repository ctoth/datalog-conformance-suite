from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


def main() -> None:
    source_root = Path("src/datalog_conformance/_tests")
    dest_root = source_root / "defeasible" / "strict_only"
    dest_root.mkdir(parents=True, exist_ok=True)

    generated_files = 0
    generated_cases = 0
    for category in ("basic", "recursion", "negation"):
        category_dir = source_root / category
        if not category_dir.exists():
            continue
        for yaml_file in sorted(category_dir.glob("*.yaml")):
            data = yaml.safe_load(yaml_file.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                continue

            source = data.get("source")
            tags = list(data.get("tags", [])) if isinstance(data.get("tags", []), list) else []
            cases = list(_iter_cases(data))
            strict_cases = [
                _convert_case(case, source, tags)
                for case in cases
                if _is_convertible(case)
            ]
            if not strict_cases:
                continue

            output = {
                "source": f"derived/strict-only/{yaml_file.relative_to(source_root).as_posix()}",
                "tags": ["defeasible", "strict-only", *tags],
                "tests": strict_cases,
            }
            dest_path = dest_root / f"strict_only_{category}_{yaml_file.stem}.yaml"
            dest_path.write_text(
                yaml.safe_dump(output, sort_keys=False, allow_unicode=False),
                encoding="utf-8",
            )
            generated_files += 1
            generated_cases += len(strict_cases)

    print(f"Generated {generated_cases} strict-only defeasible cases in {generated_files} files")


def _iter_cases(data: dict[str, Any]) -> list[dict[str, Any]]:
    if "tests" in data and isinstance(data["tests"], list):
        return [case for case in data["tests"] if isinstance(case, dict)]
    return [data]


def _is_convertible(case: dict[str, Any]) -> bool:
    if "program" not in case or "expect" not in case:
        return False
    if "expect_error" in case:
        return False
    program = case.get("program")
    expect = case.get("expect")
    return isinstance(program, dict) and isinstance(expect, dict)


def _convert_case(case: dict[str, Any], source: Any, inherited_tags: list[Any]) -> dict[str, Any]:
    program = case["program"]
    facts = dict(program.get("facts", {}))
    rules = list(program.get("rules", []))
    strict_rules = []
    for index, rule in enumerate(rules, start=1):
        strict_rules.append(
            {
                "id": f"r{index}",
                "head": _rule_head(rule),
                "body": _rule_body(rule),
            }
        )

    expect = case["expect"]
    raw_tags = [*inherited_tags, *case.get("tags", []), "defeasible", "strict-only"]
    tags = [tag for tag in raw_tags if isinstance(tag, str)]
    return {
        "name": f"strict_only_{case['name']}",
        "description": f"Strict-only defeasible form of {case['name']}.",
        "source": source if isinstance(source, str) else case.get("source", "derived/strict-only"),
        "tags": sorted(set(tags)),
        "theory": {
            "facts": facts,
            "strict_rules": strict_rules,
            "defeasible_rules": [],
            "defeaters": [],
            "superiority": [],
        },
        "expect": {
            "definitely": expect,
            "defeasibly": expect,
        },
    }


def _rule_head(rule: Any) -> str:
    text = _normalize_rule_text(rule)
    return text.split(":-", 1)[0].strip()


def _rule_body(rule: Any) -> list[str]:
    text = _normalize_rule_text(rule)
    if ":-" not in text:
        return []
    body = text.split(":-", 1)[1].strip()
    if not body:
        return []
    return _split_body_atoms(body)


def _normalize_rule_text(rule: Any) -> str:
    if not isinstance(rule, str):
        raise TypeError(f"Rule must be a string, got {type(rule).__name__}")
    return rule.strip().removesuffix(".").strip()


def _split_body_atoms(body: str) -> list[str]:
    atoms: list[str] = []
    current: list[str] = []
    depth = 0

    for char in body:
        if char == "," and depth == 0:
            atom = "".join(current).strip()
            if atom:
                atoms.append(atom)
            current = []
            continue
        if char == "(":
            depth += 1
        elif char == ")" and depth > 0:
            depth -= 1
        current.append(char)

    atom = "".join(current).strip()
    if atom:
        atoms.append(atom)
    return atoms


if __name__ == "__main__":
    main()
