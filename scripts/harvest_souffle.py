from __future__ import annotations

import argparse
import csv
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import yaml

DECL_RE = re.compile(r"^\.?decl\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(")
INPUT_RE = re.compile(r"^\.?input\s+([A-Za-z_][A-Za-z0-9_]*)")
OUTPUT_RE = re.compile(r"^\.?output\s+([A-Za-z_][A-Za-z0-9_]*)")
HEAD_RE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*\(")
BODY_ATOM_RE = re.compile(r"!?([A-Za-z_][A-Za-z0-9_]*)\s*\(")

FORBIDDEN_TOKENS = (
    "$",
    "[",
    "]",
    "{",
    "}",
    "choice-domain",
    "match(",
    "contains(",
    "substr(",
    "cat(",
    "range(",
    ".comp",
    ".plan",
    ".pragma",
    ".limitsize",
    ".printsize",
    ".number_type",
    ".symbol_type",
    ".float_type",
    " count ",
    " sum ",
    " mean ",
    " min ",
    " max ",
)

ARITHMETIC_RE = re.compile(r"\b(?:[A-Za-z_][A-Za-z0-9_]*|\d+)\s*[+\-*/]\s*(?:[A-Za-z_][A-Za-z0-9_]*|\d+)\b")
FORBIDDEN_WORD_RE = re.compile(r"\b(count|sum|mean|min|max)\b")
FORBIDDEN_CALL_RE = re.compile(r"\b(choice-domain|match|contains|substr|cat|range)\s*\(")


def main() -> None:
    parser = argparse.ArgumentParser(description="Harvest portable Souffle tests into YAML.")
    parser.add_argument(
        "--source",
        type=Path,
        default=Path.home() / "AppData/Local/Temp/datalog-harvest/souffle/tests",
        help="Path to Souffle tests directory",
    )
    parser.add_argument(
        "--dest",
        type=Path,
        default=Path("src/datalog_conformance/_tests"),
        help="Destination root for generated YAML files",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Optional cap on harvested directories after filtering",
    )
    args = parser.parse_args()

    harvested = 0
    skipped = 0
    skip_reasons: Counter[str] = Counter()
    candidates = list(iter_candidate_dirs(args.source))
    for directory in candidates:
        try:
            suite = convert_directory(directory, args.source)
        except UnsupportedSouffleCase as exc:
            skipped += 1
            skip_reasons[str(exc)] += 1
            continue

        relative = directory.relative_to(args.source)
        category = infer_category(suite["tests"])
        destination = args.dest / category / f"souffle_{'_'.join(relative.parts)}.yaml"
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(
            yaml.safe_dump(suite, sort_keys=False, allow_unicode=False),
            encoding="utf-8",
        )
        harvested += len(suite["tests"])
        if args.limit and harvested >= args.limit:
            break

    print(f"Harvested {harvested} Souffle test cases; skipped {skipped} directories")
    for reason, count in skip_reasons.most_common(20):
        print(f"SKIP {count}: {reason}")


def iter_candidate_dirs(source_root: Path) -> list[Path]:
    roots = [source_root / "evaluation", source_root / "example", source_root / "provenance"]
    candidates: list[Path] = []
    for root in roots:
        if not root.exists():
            continue
        for directory in sorted(path for path in root.iterdir() if path.is_dir()):
            dl_files = sorted(directory.glob("*.dl"))
            if dl_files:
                candidates.append(directory)
    return candidates


def convert_directory(directory: Path, source_root: Path) -> dict[str, Any]:
    dl_files = sorted(directory.glob("*.dl"))
    if len(dl_files) != 1:
        raise UnsupportedSouffleCase("requires exactly one .dl file")
    dl_file = dl_files[0]

    statements = parse_statements(dl_file)
    declared: set[str] = set()
    inputs: set[str] = set()
    outputs: list[str] = []
    inline_facts: dict[str, list[list[str | int]]] = defaultdict(list)
    rules: list[str] = []
    retained_rule_heads: set[str] = set()
    dropped_relations: set[str] = set()

    for statement in statements:
        if is_unsupported_statement(statement):
            relation = statement_relation(statement)
            if relation is not None:
                dropped_relations.add(relation)
            continue
        if statement.startswith((".type", "type ")):
            continue
        match = DECL_RE.match(statement)
        if match:
            declared.add(match.group(1))
            continue
        match = INPUT_RE.match(statement)
        if match:
            inputs.add(match.group(1))
            continue
        match = OUTPUT_RE.match(statement)
        if match:
            outputs.append(match.group(1))
            continue
        if ":-" in statement:
            head_match = HEAD_RE.match(statement)
            if head_match is not None:
                retained_rule_heads.add(head_match.group(1))
            rules.append(normalize_rule(statement))
            continue
        predicate, row = parse_fact_statement(statement)
        inline_facts[predicate].append(row)

    if not outputs:
        raise UnsupportedSouffleCase("missing outputs")

    facts = dict(inline_facts)
    for relation in inputs:
        facts[relation] = load_input_relation(directory, relation)

    exports = load_output_relations(directory, outputs)
    if not exports:
        raise UnsupportedSouffleCase("missing relation outputs")
    for rule in rules:
        body = rule.split(":-", 1)[1] if ":-" in rule else ""
        if any(atom in dropped_relations for atom in BODY_ATOM_RE.findall(body)):
            raise UnsupportedSouffleCase("retained rule depends on dropped semantics")
    for relation in outputs:
        if relation in dropped_relations:
            raise UnsupportedSouffleCase(f"exported relation {relation} depends on dropped semantics")
        if relation not in facts and relation not in retained_rule_heads:
            raise UnsupportedSouffleCase(f"exported relation {relation} has no retained derivation")

    tests: list[dict[str, Any]] = []
    suite_tags = {"souffle", relative_source(directory, source_root).split("/")[1]}
    for relation, rows in exports.items():
        case_tags = sorted({*suite_tags, *classify_relation_tags(relation, rules)})
        tests.append(
            {
                "name": f"souffle_{directory.name}_{relation}",
                "description": (
                    f"Harvested from Souffle testcase {directory.name}, "
                    f"asserting exported relation {relation}."
                ),
                "tags": case_tags,
                "program": {
                    "facts": facts,
                    "rules": rules,
                },
                "expect": {
                    relation: rows,
                },
            }
        )

    return {
        "source": relative_source(directory, source_root),
        "tags": sorted(suite_tags),
        "tests": tests,
    }


def parse_statements(dl_file: Path) -> list[str]:
    content = dl_file.read_text(encoding="utf-8")
    content = re.sub(r"//.*", "", content)
    statements: list[str] = []
    current: list[str] = []
    in_string = False
    for char in content:
        if char == '"':
            in_string = not in_string
            current.append(char)
            continue
        if char == "." and not in_string:
            if not "".join(current).strip():
                current.append(char)
                continue
            statement = "".join(current).strip()
            if statement:
                statements.append(statement + ".")
            current = []
            continue
        current.append(char)
    if "".join(current).strip():
        raise UnsupportedSouffleCase("unterminated statement")
    return statements


def is_unsupported_statement(statement: str) -> bool:
    stripped = strip_strings(statement)
    compact = f" {statement} "
    if statement.startswith((".input", "input ", ".output", "output ", ".decl", "decl ")):
        return False
    if statement.startswith((".type", "type ")):
        return "[" in statement or "$" in statement or "record" in statement
    for token in FORBIDDEN_TOKENS:
        if token in compact or token in statement:
            return True
    if FORBIDDEN_WORD_RE.search(stripped) or FORBIDDEN_CALL_RE.search(stripped):
        return True
    if ":-" in statement and ARITHMETIC_RE.search(stripped):
        return True
    blocked_ops = ("!=", "<=", ">=", " < ", " > ", " = ", " + ", " - ", " * ", " / ")
    if any(op in statement for op in blocked_ops):
        return True
    return False


def strip_strings(statement: str) -> str:
    result: list[str] = []
    in_string = False
    for char in statement:
        if char == '"':
            in_string = not in_string
            continue
        if not in_string:
            result.append(char)
    return "".join(result)


def statement_relation(statement: str) -> str | None:
    head_match = HEAD_RE.match(statement)
    if head_match is not None:
        return head_match.group(1)
    fact_match = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)\s*\(", statement)
    if fact_match is not None:
        return fact_match.group(1)
    return None


def normalize_rule(statement: str) -> str:
    normalized = statement.rstrip(".")
    normalized = re.sub(r"!\s*([A-Za-z_][A-Za-z0-9_]*)\(", r"not \1(", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return f"{normalized}."


def parse_fact_statement(statement: str) -> tuple[str, list[str | int]]:
    match = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)\((.*)\)\.$", statement)
    if match is None:
        raise UnsupportedSouffleCase(f"unsupported fact statement: {statement}")
    predicate = match.group(1)
    values = split_terms(match.group(2))
    return predicate, [convert_scalar(value) for value in values]


def load_input_relation(directory: Path, relation: str) -> list[list[str | int]]:
    candidates = [
        directory / f"{relation}.facts",
        directory / "facts" / f"{relation}.facts",
        directory / f"{relation}.csv",
        directory / "facts" / f"{relation}.csv",
    ]
    for candidate in candidates:
        if candidate.exists():
            return read_table(candidate)
    raise UnsupportedSouffleCase(f"missing input file for {relation}")


def load_output_relations(directory: Path, outputs: list[str]) -> dict[str, list[list[str | int]]]:
    exported: dict[str, list[list[str | int]]] = {}
    for relation in outputs:
        candidates = [
            directory / f"{relation}.csv",
            directory / f"{relation}.facts",
        ]
        for candidate in candidates:
            if candidate.exists():
                exported[relation] = read_table(candidate)
                break
    return exported


def read_table(path: Path) -> list[list[str | int]]:
    rows: list[list[str | int]] = []
    with path.open("r", encoding="utf-8", newline="") as handle:
        sample = handle.read(2048)
        handle.seek(0)
        delimiter = "\t" if "\t" in sample else ","
        reader = csv.reader(handle, delimiter=delimiter)
        for row in reader:
            if not row:
                continue
            rows.append([convert_scalar(cell) for cell in row])
    return rows


def split_terms(raw: str) -> list[str]:
    reader = csv.reader([raw], skipinitialspace=True)
    return [item.strip() for item in next(reader) if item.strip()]


def convert_scalar(token: str) -> str | int:
    stripped = token.strip()
    if stripped.startswith('"') and stripped.endswith('"'):
        return stripped[1:-1]
    if re.fullmatch(r"-?\d+", stripped):
        return int(stripped)
    return stripped


def relative_source(directory: Path, source_root: Path) -> str:
    return f"souffle/{directory.relative_to(source_root).as_posix()}"


def classify_relation_tags(relation: str, rules: list[str]) -> set[str]:
    tags = {"basic"}
    if any("not " in rule for rule in rules):
        tags = {"negation"}
    if is_recursive_relation(relation, rules):
        tags = {"recursion"}
    return tags


def infer_category(tests: list[dict[str, Any]]) -> str:
    tag_priority = ("negation", "recursion", "basic")
    available = {tag for test in tests for tag in test["tags"]}
    for tag in tag_priority:
        if tag in available:
            return tag
    return "basic"


def is_recursive_relation(target: str, rules: list[str]) -> bool:
    graph: dict[str, set[str]] = defaultdict(set)
    for rule in rules:
        head_match = HEAD_RE.match(rule)
        if head_match is None:
            continue
        head = head_match.group(1)
        body = rule.split(":-", 1)[1]
        for atom in BODY_ATOM_RE.findall(body):
            graph[head].add(atom)
    seen: set[str] = set()
    stack = [target]
    while stack:
        current = stack.pop()
        if current in seen:
            continue
        seen.add(current)
        for child in graph.get(current, set()):
            if child == target and current != target:
                return True
            stack.append(child)
    return target in graph.get(target, set())


class UnsupportedSouffleCase(ValueError):
    pass


if __name__ == "__main__":
    main()
