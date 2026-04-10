from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

SOURCE_ROOT = Path(os.environ.get("TEMP", str(Path.home() / "AppData" / "Local" / "Temp")))
SPINDLE_ROOT = SOURCE_ROOT / "datalog-harvest" / "spindle-racket"
THEORY_ROOT = SPINDLE_ROOT / "src" / "test-theories"
TEST_ROOT = SPINDLE_ROOT / "tests"
DEST_ROOT = Path("src") / "datalog_conformance" / "_tests" / "defeasible" / "basic"


def main() -> None:
    if not THEORY_ROOT.exists():
        raise SystemExit(f"Missing spindle-racket theory directory: {THEORY_ROOT}")
    if not TEST_ROOT.exists():
        raise SystemExit(f"Missing spindle-racket test directory: {TEST_ROOT}")

    _write_yaml(
        DEST_ROOT / "spindle_racket_test_theories.yaml",
        {
            "source": "spindle-racket/src/test-theories",
            "tags": ["defeasible", "spindle-racket"],
            "tests": [
                _case_from_source(
                    THEORY_ROOT / "penguin.dfl",
                    name="spindle_racket_penguin_exception",
                    description="Penguin non-flight defeats generic bird flight.",
                    tags=["basic", "superiority", "exceptions"],
                    expect={
                        "definitely": {"tweety": [[]], "penguin": [[]]},
                        "defeasibly": {"bird": [[]], "~flies": [[]]},
                        "not_defeasibly": {"flies": [[]]},
                    },
                ),
                _case_from_source(
                    THEORY_ROOT / "basicConflict.dfl",
                    name="spindle_racket_basic_conflict",
                    description="Superiority resolves two conflicting defeasible rules.",
                    tags=["basic", "superiority", "conflicts"],
                    expect={
                        "definitely": {"bird": [[]]},
                        "defeasibly": {"flies": [[]]},
                        "not_defeasibly": {"~flies": [[]]},
                    },
                ),
                _case_from_source(
                    THEORY_ROOT / "defeater.dfl",
                    name="spindle_racket_defeater_blocks",
                    description="A defeater blocks q without proving ~q.",
                    tags=["basic", "defeater"],
                    expect={
                        "definitely": {"p": [[]]},
                        "not_defeasibly": {"q": [[]], "~q": [[]]},
                    },
                ),
                _case_from_source(
                    THEORY_ROOT / "chain.dfl",
                    name="spindle_racket_chain_forward",
                    description="Defeasible forward chaining derives all downstream literals.",
                    tags=["basic", "chaining"],
                    expect={
                        "definitely": {"start": [[]]},
                        "defeasibly": {
                            "step1": [[]],
                            "step2": [[]],
                            "step3": [[]],
                            "end": [[]],
                        },
                    },
                ),
                _case_from_source(
                    THEORY_ROOT / "factConflict.dfl",
                    name="spindle_racket_fact_conflict",
                    description=(
                        "Conflicting facts remain definitely provable in the inconsistent theory."
                    ),
                    tags=["basic", "inconsistency"],
                    expect={"definitely": {"p": [[]], "~p": [[]]}},
                ),
                _case_from_source(
                    THEORY_ROOT / "sdlTestTheory.dfl",
                    name="spindle_racket_strict_beats_defeasible",
                    description="A strict rule for c blocks a competing defeasible rule for ~c.",
                    tags=["basic", "strict-only", "superiority"],
                    expect={
                        "definitely": {"a": [[]], "b": [[]], "c": [[]]},
                        "not_defeasibly": {"~c": [[]]},
                    },
                ),
                _case_from_source(
                    TEST_ROOT / "birds-fly.dfl",
                    name="spindle_racket_birds_fly",
                    description="A bird fact supports the default that birds fly.",
                    tags=["basic", "facts"],
                    expect={
                        "definitely": {"bird": [[]]},
                        "defeasibly": {"flies": [[]]},
                    },
                ),
                _case_from_source(
                    TEST_ROOT / "penguin-exception.dfl",
                    name="spindle_racket_penguin_exception_test",
                    description="A penguin exception blocks flight while still deriving swimming.",
                    tags=["basic", "exceptions", "superiority"],
                    expect={
                        "definitely": {"bird": [[]], "penguin": [[]]},
                        "defeasibly": {"swims": [[]], "~flies": [[]]},
                        "not_defeasibly": {"flies": [[]]},
                    },
                ),
                _case_from_source(
                    TEST_ROOT / "medical-treatment.dfl",
                    name="spindle_racket_medical_treatment",
                    description=(
                        "A contraindication defeats the first treatment and enables "
                        "the fallback."
                    ),
                    tags=["basic", "superiority", "safety"],
                    expect={
                        "definitely": {"hasConditionX": [[]], "allergicToA": [[]]},
                        "defeasibly": {
                            "~recommendTreatmentA": [[]],
                            "recommendTreatmentB": [[]],
                        },
                        "not_defeasibly": {"recommendTreatmentA": [[]]},
                    },
                ),
            ],
        },
    )

    _write_yaml(
        DEST_ROOT / "spindle_racket_inline_tests.yaml",
        {
            "source": "spindle-racket/tests/spindle-tests.rkt",
            "tags": ["defeasible", "spindle-racket"],
            "tests": [
                _inline_case(
                    name="spindle_racket_fact_vs_strict_rule_conflict",
                    description=(
                        "A fact and a conflicting strict-rule conclusion are both "
                        "definitely provable."
                    ),
                    source=(
                        "spindle-racket/tests/spindle-tests.rkt::"
                        "Fact conflicting with strict rule conclusion"
                    ),
                    tags=["basic", "inconsistency", "strict"],
                    theory={
                        "facts": {"p": [[]], "q": [[]]},
                        "strict_rules": [
                            {"id": "r1", "head": "~p", "body": ["q"]},
                        ],
                        "defeasible_rules": [],
                        "defeaters": [],
                        "superiority": [],
                        "conflicts": [["p", "~p"]],
                    },
                    expect={"definitely": {"p": [[]], "q": [[]], "~p": [[]]}},
                ),
                _inline_case(
                    name="spindle_racket_multiple_antecedents",
                    description="A defeasible rule fires when all three antecedents are present.",
                    source="spindle-racket/tests/spindle-tests.rkt::Rule with multiple antecedents",
                    tags=["basic", "chaining"],
                    theory={
                        "facts": {"p": [[]], "q": [[]], "r": [[]]},
                        "strict_rules": [],
                        "defeasible_rules": [
                            {"id": "r1", "head": "s", "body": ["p", "q", "r"]},
                        ],
                        "defeaters": [],
                        "superiority": [],
                    },
                    expect={
                        "definitely": {"p": [[]], "q": [[]], "r": [[]]},
                        "defeasibly": {"s": [[]]},
                    },
                ),
                _inline_case(
                    name="spindle_racket_mixed_strict_defeasible_conflict",
                    description="A strict rule for c blocks a competing defeasible rule for ~c.",
                    source=(
                        "spindle-racket/tests/spindle-tests.rkt::"
                        "Interaction between strict and defeasible rules"
                    ),
                    tags=["basic", "strict", "conflicts"],
                    theory={
                        "facts": {"a": [[]], "b": [[]]},
                        "strict_rules": [
                            {"id": "r1", "head": "c", "body": ["a"]},
                        ],
                        "defeasible_rules": [
                            {"id": "r2", "head": "~c", "body": ["b"]},
                        ],
                        "defeaters": [],
                        "superiority": [],
                        "conflicts": [["c", "~c"]],
                    },
                    expect={
                        "definitely": {"a": [[]], "b": [[]], "c": [[]]},
                        "not_defeasibly": {"~c": [[]]},
                    },
                ),
                _inline_case(
                    name="spindle_racket_defeater_negative_conclusions",
                    description="A defeater blocks q and still does not prove ~q.",
                    source=(
                        "spindle-racket/tests/spindle-tests.rkt::"
                        "Defeater produces non-provability conclusions"
                    ),
                    tags=["basic", "defeater"],
                    theory={
                        "facts": {"p": [[]]},
                        "strict_rules": [],
                        "defeasible_rules": [
                            {"id": "r1", "head": "q", "body": ["p"]},
                        ],
                        "defeaters": [
                            {"id": "r2", "head": "~q", "body": ["p"]},
                        ],
                        "superiority": [],
                        "conflicts": [["q", "~q"]],
                    },
                    expect={
                        "definitely": {"p": [[]]},
                        "not_defeasibly": {"q": [[]], "~q": [[]]},
                    },
                ),
                _inline_case(
                    name="spindle_racket_simple_fact",
                    description="A simple fact is definitely provable.",
                    source=(
                        "spindle-racket/tests/spindle-tests.rkt::"
                        "Simple fact should be definitely provable"
                    ),
                    tags=["basic", "facts"],
                    theory={
                        "facts": {"p": [[]]},
                        "strict_rules": [],
                        "defeasible_rules": [],
                        "defeaters": [],
                        "superiority": [],
                    },
                    expect={"definitely": {"p": [[]]}},
                ),
                _inline_case(
                    name="spindle_racket_negated_fact",
                    description="A negated fact is definitely provable.",
                    source=(
                        "spindle-racket/tests/spindle-tests.rkt::"
                        "Negated fact should be definitely provable"
                    ),
                    tags=["basic", "facts", "negation"],
                    theory={
                        "facts": {"~q": [[]]},
                        "strict_rules": [],
                        "defeasible_rules": [],
                        "defeaters": [],
                        "superiority": [],
                    },
                    expect={"definitely": {"~q": [[]]}},
                ),
                _inline_case(
                    name="spindle_racket_strict_rule_with_fact",
                    description=(
                        "A strict rule with a satisfied antecedent derives its head "
                        "definitely."
                    ),
                    source=(
                        "spindle-racket/tests/spindle-tests.rkt::"
                        "Strict rule with satisfied antecedent"
                    ),
                    tags=["basic", "strict"],
                    theory={
                        "facts": {"p": [[]]},
                        "strict_rules": [
                            {"id": "r1", "head": "q", "body": ["p"]},
                        ],
                        "defeasible_rules": [],
                        "defeaters": [],
                        "superiority": [],
                    },
                    expect={"definitely": {"p": [[]], "q": [[]]}},
                ),
                _inline_case(
                    name="spindle_racket_defeasible_rule_with_fact",
                    description=(
                        "A defeasible rule with a satisfied antecedent derives its "
                        "head defeasibly."
                    ),
                    source=(
                        "spindle-racket/tests/spindle-tests.rkt::"
                        "Defeasible rule with satisfied antecedent"
                    ),
                    tags=["basic", "defeasible"],
                    theory={
                        "facts": {"p": [[]]},
                        "strict_rules": [],
                        "defeasible_rules": [
                            {"id": "r1", "head": "q", "body": ["p"]},
                        ],
                        "defeaters": [],
                        "superiority": [],
                    },
                    expect={
                        "definitely": {"p": [[]]},
                        "defeasibly": {"q": [[]]},
                    },
                ),
            ],
        },
    )

    print(
        f"Wrote {_count_cases(DEST_ROOT / 'spindle_racket_test_theories.yaml')} "
        "SPINdle theory cases"
    )
    print(
        f"Wrote {_count_cases(DEST_ROOT / 'spindle_racket_inline_tests.yaml')} "
        "SPINdle inline cases"
    )


def _case_from_source(
    path: Path,
    *,
    name: str,
    description: str,
    tags: list[str],
    expect: dict[str, Any],
) -> dict[str, Any]:
    parsed = _parse_dfl(path.read_text(encoding="utf-8"))
    source_root = (
        "spindle-racket/src/test-theories"
        if path.parent == THEORY_ROOT
        else "spindle-racket/tests"
    )
    return {
        "name": name,
        "description": description,
        "source": f"{source_root}/{path.name}",
        "tags": tags,
        "theory": parsed,
        "expect": expect,
    }


def _inline_case(
    *,
    name: str,
    description: str,
    source: str,
    tags: list[str],
    theory: dict[str, Any],
    expect: dict[str, Any],
) -> dict[str, Any]:
    return {
        "name": name,
        "description": description,
        "source": source,
        "tags": tags,
        "theory": theory,
        "expect": expect,
    }


def _count_cases(path: Path) -> int:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    tests = data.get("tests", [])
    return len(tests)


def _write_yaml(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(payload, sort_keys=False, allow_unicode=False),
        encoding="utf-8",
    )


def _parse_dfl(text: str) -> dict[str, Any]:
    theory: dict[str, Any] = {
        "facts": {},
        "strict_rules": [],
        "defeasible_rules": [],
        "defeaters": [],
        "superiority": [],
    }

    unlabeled_fact_index = 0
    for raw_line in text.splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line:
            continue

        if ">" in line and ":" not in line and ">>" not in line:
            left, right = [part.strip() for part in line.split(">", 1)]
            theory["superiority"].append([left, right])
            continue

        label: str | None = None
        payload = line
        if ":" in line:
            possible_label, remainder = [part.strip() for part in line.split(":", 1)]
            if possible_label:
                label = possible_label
                payload = remainder

        if payload.startswith(">>"):
            literal = _normalize_literal(payload.removeprefix(">>").strip())
            theory["facts"].setdefault(literal, []).append([])
            unlabeled_fact_index += 1
            continue

        if " ~> " in payload:
            head, body = _split_rule(payload, "~>")
            theory["defeaters"].append(
                {"id": label or f"d{unlabeled_fact_index}", "head": head, "body": body}
            )
            continue

        if " => " in payload:
            head, body = _split_rule(payload, "=>")
            theory["defeasible_rules"].append(
                {"id": label or f"r{unlabeled_fact_index}", "head": head, "body": body}
            )
            continue

        if " -> " in payload:
            head, body = _split_rule(payload, "->")
            theory["strict_rules"].append(
                {"id": label or f"s{unlabeled_fact_index}", "head": head, "body": body}
            )
            continue

    return theory


def _split_rule(payload: str, operator: str) -> tuple[str, list[str]]:
    left, right = [part.strip() for part in payload.split(operator, 1)]
    body = [_normalize_literal(item.strip()) for item in left.split(",") if item.strip()]
    head = _normalize_literal(right)
    return head, body


def _normalize_literal(literal: str) -> str:
    return literal.replace("¬", "~")


if __name__ == "__main__":
    main()
