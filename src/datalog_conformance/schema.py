"""Dataclasses and YAML parsing for conformance tests."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, TypeAlias, cast

import yaml

try:  # libyaml is ~10x faster and matters at corpus scale
    from yaml import CSafeLoader as _SafeLoader
except ImportError:  # pragma: no cover - depends on wheel build
    from yaml import SafeLoader as _SafeLoader


def load_yaml_text(text: str) -> Any:
    """Parse YAML with the fastest available safe loader."""

    return yaml.load(text, Loader=_SafeLoader)


Scalar: TypeAlias = str | int | float | bool
FactTuple: TypeAlias = tuple[Scalar, ...]
PredicateFacts: TypeAlias = dict[str, list[FactTuple]]
DefeasibleSections: TypeAlias = dict[str, PredicateFacts]


def _predicate_facts_factory() -> PredicateFacts:
    return {}


def _string_list_factory() -> list[str]:
    return []


def _rule_list_factory() -> list["Rule"]:
    return []


def _pair_list_factory() -> list[tuple[str, str]]:
    return []


def _theory_property_case_list_factory() -> list["TheoryPropertyCase"]:
    return []


class SchemaError(ValueError):
    """Raised when YAML content violates the expected schema."""


class Policy(str, Enum):
    """Named evaluation policies for defeasible reasoning."""

    BLOCKING = "blocking"
    PROPAGATING = "propagating"
    RATIONAL_CLOSURE = "rational_closure"
    LEXICOGRAPHIC_CLOSURE = "lexicographic_closure"
    RELEVANT_CLOSURE = "relevant_closure"

    @classmethod
    def from_name(cls, name: str) -> "Policy":
        try:
            return cls(name)
        except ValueError as exc:
            raise SchemaError(f"Unknown policy: {name}") from exc


class VerificationKind(str, Enum):
    """How the retained YAML relates to the verified implementation input."""

    DIRECT = "direct"
    REDUCED = "reduced"

    @classmethod
    def from_name(cls, name: str) -> "VerificationKind":
        try:
            return cls(name)
        except ValueError as exc:
            raise SchemaError(f"Unknown verification kind: {name}") from exc


@dataclass(slots=True)
class Verification:
    """Concrete confirmation metadata for a retained case."""

    implementation: str
    kind: VerificationKind

    @classmethod
    def from_dict(cls, raw: Any) -> "Verification":
        data = _ensure_mapping(raw, "verification")
        return cls(
            implementation=_require_string(data, "implementation", "verification"),
            kind=VerificationKind.from_name(
                _require_string(data, "kind", "verification")
            ),
        )


@dataclass(slots=True)
class Program:
    """Core Datalog program."""

    facts: PredicateFacts = field(default_factory=_predicate_facts_factory)
    rules: list[str] = field(default_factory=_string_list_factory)

    @classmethod
    def from_dict(cls, raw: Any) -> "Program":
        data = _ensure_mapping(raw, "program")
        return cls(
            facts=_parse_predicate_facts(data.get("facts", {}), "program.facts"),
            rules=_parse_string_list(data.get("rules", []), "program.rules"),
        )


@dataclass(slots=True)
class Rule:
    """Shared rule structure for strict, defeasible, and defeater rules."""

    id: str
    head: str
    body: list[str] = field(default_factory=_string_list_factory)

    @classmethod
    def from_dict(cls, raw: Any, *, path: str) -> "Rule":
        data = _ensure_mapping(raw, path)
        return cls(
            id=_require_string(data, "id", path),
            head=_require_string(data, "head", path),
            body=_parse_string_list(data.get("body", []), f"{path}.body"),
        )


@dataclass(slots=True)
class DefeasibleTheory:
    """Defeasible Datalog theory."""

    facts: PredicateFacts = field(default_factory=_predicate_facts_factory)
    strict_rules: list[Rule] = field(default_factory=_rule_list_factory)
    defeasible_rules: list[Rule] = field(default_factory=_rule_list_factory)
    defeaters: list[Rule] = field(default_factory=_rule_list_factory)
    superiority: list[tuple[str, str]] = field(default_factory=_pair_list_factory)
    conflicts: list[tuple[str, str]] = field(default_factory=_pair_list_factory)

    @classmethod
    def from_dict(cls, raw: Any) -> "DefeasibleTheory":
        data = _ensure_mapping(raw, "theory")
        return cls(
            facts=_parse_predicate_facts(data.get("facts", {}), "theory.facts"),
            strict_rules=_parse_rules(data.get("strict_rules", []), "theory.strict_rules"),
            defeasible_rules=_parse_rules(
                data.get("defeasible_rules", []), "theory.defeasible_rules"
            ),
            defeaters=_parse_rules(data.get("defeaters", []), "theory.defeaters"),
            superiority=_parse_pairs(data.get("superiority", []), "theory.superiority"),
            conflicts=_parse_pairs(data.get("conflicts", []), "theory.conflicts"),
        )


@dataclass(slots=True)
class TheoryPropertyCase:
    """Single theory and property-satisfaction declaration for a KLM test."""

    theory: DefeasibleTheory
    satisfies: dict[str, bool]

    @classmethod
    def from_dict(cls, raw: Any, *, path: str) -> "TheoryPropertyCase":
        data = _ensure_mapping(raw, path)
        satisfies_raw = _ensure_mapping(data.get("satisfies", {}), f"{path}.satisfies")
        satisfies: dict[str, bool] = {}
        for key, value in satisfies_raw.items():
            if not isinstance(key, str):
                raise SchemaError(f"{path}.satisfies keys must be strings")
            if not isinstance(value, bool):
                raise SchemaError(f"{path}.satisfies[{key!r}] must be boolean")
            satisfies[key] = value
        return cls(
            theory=DefeasibleTheory.from_dict(data.get("theory", {})),
            satisfies=satisfies,
        )


@dataclass(slots=True)
class Model:
    """Standard Datalog model returned by evaluators."""

    facts: dict[str, set[FactTuple]]


@dataclass(slots=True)
class DefeasibleModel:
    """Defeasible model returned by evaluators."""

    sections: dict[str, dict[str, set[FactTuple]]]


@dataclass(slots=True)
class TestCase:
    """Top-level YAML test case."""

    name: str
    description: str
    source: str
    tags: list[str]
    verification: Verification | None = None
    skip: str | None = None
    program: Program | None = None
    theory: DefeasibleTheory | None = None
    expect: PredicateFacts | DefeasibleSections | None = None
    expect_error: str | None = None
    expect_per_policy: dict[str, DefeasibleSections] | None = None
    klm_property: str | None = None
    theories: list[TheoryPropertyCase] = field(
        default_factory=_theory_property_case_list_factory
    )

    @classmethod
    def from_dict(cls, raw: Any) -> "TestCase":
        data = _ensure_mapping(raw, "test_case")
        program = Program.from_dict(data["program"]) if "program" in data else None
        theory = DefeasibleTheory.from_dict(data["theory"]) if "theory" in data else None
        klm_property = _optional_string(data.get("klm_property"), "klm_property")
        theories = _parse_theory_cases(data.get("theories", []), "theories")

        expect = None
        if "expect" in data:
            if program is not None:
                expect = _parse_predicate_facts(data["expect"], "expect")
            else:
                expect = _parse_sections(data["expect"], "expect")

        expect_per_policy: dict[str, DefeasibleSections] | None = None
        if "expect_per_policy" in data:
            raw_policy_map = _ensure_mapping(data["expect_per_policy"], "expect_per_policy")
            expect_per_policy = {}
            for key, value in raw_policy_map.items():
                if not isinstance(key, str):
                    raise SchemaError("expect_per_policy keys must be strings")
                expect_per_policy[key] = _parse_sections(value, f"expect_per_policy.{key}")

        case = cls(
            name=_require_string(data, "name", "test_case"),
            description=_require_string(data, "description", "test_case"),
            source=_require_string(data, "source", "test_case"),
            tags=_parse_string_list(data.get("tags", []), "tags"),
            verification=(
                Verification.from_dict(data["verification"])
                if "verification" in data
                else None
            ),
            skip=_optional_string(data.get("skip"), "skip"),
            program=program,
            theory=theory,
            expect=expect,
            expect_error=_optional_string(data.get("expect_error"), "expect_error"),
            expect_per_policy=expect_per_policy,
            klm_property=klm_property,
            theories=theories,
        )
        case._validate()
        return case

    def _validate(self) -> None:
        shape_count = sum(
            value is not None
            for value in (self.program, self.theory, self.klm_property)
        )
        if shape_count != 1:
            raise SchemaError(
                "Exactly one of program, theory, or klm_property/theories must be present"
            )

        if self.program is not None:
            if self.expect is None and self.expect_error is None:
                raise SchemaError("Program tests require expect or expect_error")
            if self.expect_per_policy is not None:
                raise SchemaError("Program tests cannot use expect_per_policy")

        if self.theory is not None:
            if self.expect is None and self.expect_per_policy is None and self.expect_error is None:
                raise SchemaError("Theory tests require expect, expect_per_policy, or expect_error")

        if self.klm_property is not None:
            if not self.theories:
                raise SchemaError("KLM property tests require non-empty theories")
            if self.theory is not None or self.program is not None:
                raise SchemaError("KLM property tests cannot define program or theory")
            if self.expect is not None or self.expect_error is not None:
                raise SchemaError("KLM property tests do not use expect or expect_error")

    def to_dict(self) -> dict[str, Any]:
        raw = asdict(self)
        return cast(dict[str, Any], _strip_none(_yamlify(raw)))


def load_test_case(path: str | Path) -> TestCase:
    """Load a single YAML file into a validated test case."""

    raw = load_yaml_text(Path(path).read_text(encoding="utf-8"))
    return TestCase.from_dict(raw)


def _parse_theory_cases(raw: Any, path: str) -> list[TheoryPropertyCase]:
    items = _ensure_sequence(raw, path)
    return [
        TheoryPropertyCase.from_dict(item, path=f"{path}[{index}]")
        for index, item in enumerate(items)
    ]


def _parse_rules(raw: Any, path: str) -> list[Rule]:
    items = _ensure_sequence(raw, path)
    return [Rule.from_dict(item, path=f"{path}[{index}]") for index, item in enumerate(items)]


def _parse_pairs(raw: Any, path: str) -> list[tuple[str, str]]:
    items = _ensure_sequence(raw, path)
    pairs: list[tuple[str, str]] = []
    for index, item in enumerate(items):
        seq = _ensure_sequence(item, f"{path}[{index}]")
        if len(seq) != 2 or not all(isinstance(value, str) for value in seq):
            raise SchemaError(f"{path}[{index}] must be a two-item string pair")
        pairs.append((cast(str, seq[0]), cast(str, seq[1])))
    return pairs


def _parse_sections(raw: Any, path: str) -> DefeasibleSections:
    data = _ensure_mapping(raw, path)
    sections: DefeasibleSections = {}
    for key, value in data.items():
        if not isinstance(key, str):
            raise SchemaError(f"{path} section names must be strings")
        sections[key] = _parse_predicate_facts(value, f"{path}.{key}")
    return sections


def _parse_predicate_facts(raw: Any, path: str) -> PredicateFacts:
    data = _ensure_mapping(raw, path)
    result: PredicateFacts = {}
    for predicate, tuples in data.items():
        if not isinstance(predicate, str):
            raise SchemaError(f"{path} predicate names must be strings")
        tuple_rows = _ensure_sequence(tuples, f"{path}.{predicate}")
        parsed_rows: list[FactTuple] = []
        for index, row in enumerate(tuple_rows):
            row_values = _ensure_sequence(row, f"{path}.{predicate}[{index}]")
            if not all(_is_scalar(item) for item in row_values):
                raise SchemaError(f"{path}.{predicate}[{index}] must contain only scalar values")
            parsed_rows.append(tuple(cast(Scalar, item) for item in row_values))
        result[predicate] = parsed_rows
    return result


def _parse_string_list(raw: Any, path: str) -> list[str]:
    items = _ensure_sequence(raw, path)
    if not all(isinstance(item, str) for item in items):
        raise SchemaError(f"{path} must contain only strings")
    return [cast(str, item) for item in items]


def _ensure_mapping(raw: Any, path: str) -> dict[object, object]:
    if not isinstance(raw, dict):
        raise SchemaError(f"{path} must be a mapping")
    return cast(dict[object, object], raw)


def _ensure_sequence(raw: Any, path: str) -> list[object]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise SchemaError(f"{path} must be a list")
    return cast(list[object], raw)


def _require_string(data: dict[object, object], key: str, path: str) -> str:
    value = data.get(key)
    if not isinstance(value, str):
        raise SchemaError(f"{path}.{key} must be a string")
    return value


def _optional_string(value: Any, path: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise SchemaError(f"{path} must be a string or null")
    return value


def _is_scalar(value: Any) -> bool:
    return isinstance(value, (str, int, float, bool))


def _yamlify(value: Any) -> Any:
    if isinstance(value, tuple):
        items = cast(tuple[object, ...], value)
        return [_yamlify(item) for item in items]
    if isinstance(value, list):
        items = cast(list[object], value)
        return [_yamlify(item) for item in items]
    if isinstance(value, dict):
        items = cast(dict[object, object], value)
        return {key: _yamlify(item) for key, item in items.items()}
    if isinstance(value, Enum):
        return value.value
    return value


def _strip_none(value: Any) -> Any:
    if isinstance(value, list):
        items = cast(list[object], value)
        return [_strip_none(item) for item in items]
    if isinstance(value, dict):
        items = cast(dict[object, object], value)
        return {
            key: _strip_none(item)
            for key, item in items.items()
            if item is not None
        }
    return value
