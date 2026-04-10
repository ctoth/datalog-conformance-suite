"""Execution bridge from YAML test cases to evaluator implementations."""

from __future__ import annotations

from importlib import import_module
from typing import Any, Callable, cast

from .schema import (
    DefeasibleModel,
    DefeasibleSections,
    FactTuple,
    Model,
    Policy,
    PredicateFacts,
    Scalar,
    TestCase,
)


class ConformanceFailure(AssertionError):
    """Raised when an evaluator does not satisfy a test case."""


class YamlTestRunner:
    """Run validated test cases against an evaluator object."""

    def __init__(self, evaluator: object) -> None:
        self.evaluator = evaluator

    @classmethod
    def from_import_path(cls, import_path: str) -> "YamlTestRunner":
        """Resolve an evaluator class from an import path and instantiate it."""

        module_name, _, attr_name = import_path.rpartition(".")
        if not module_name or not attr_name:
            raise ValueError(f"Invalid evaluator import path: {import_path}")

        module = import_module(module_name)
        target = getattr(module, attr_name)
        evaluator = target() if isinstance(target, type) else target
        return cls(evaluator)

    def run_test_case(self, case: TestCase) -> None:
        """Dispatch a validated test case to the right evaluation path."""

        if case.program is not None:
            self._run_program_case(case)
            return
        if case.theory is not None:
            self._run_theory_case(case)
            return
        if case.klm_property is not None:
            self._run_klm_case(case)
            return
        raise ConformanceFailure(f"Unsupported test case shape for {case.name}")

    def _run_program_case(self, case: TestCase) -> None:
        assert case.program is not None
        evaluate = getattr(self.evaluator, "evaluate", None)
        if not callable(evaluate):
            raise ConformanceFailure("Evaluator does not expose an evaluate() method")

        if case.expect_error is not None:
            self._assert_expected_error(case, lambda: evaluate(case.program))
            return

        raw_model = evaluate(case.program)
        actual = _extract_model_facts(raw_model)
        expected = _as_predicate_facts(case.expect)
        self._assert_predicate_facts(case.name, expected, actual)

    def _run_theory_case(self, case: TestCase) -> None:
        assert case.theory is not None
        evaluate = getattr(self.evaluator, "evaluate", None)
        if not callable(evaluate):
            raise ConformanceFailure("Evaluator does not expose an evaluate() method")

        if case.expect_error is not None:
            self._assert_expected_error(case, lambda: evaluate(case.theory, Policy.BLOCKING))
            return

        if case.expect_per_policy:
            for policy_name, expectation in case.expect_per_policy.items():
                raw_model = evaluate(case.theory, Policy.from_name(policy_name))
                actual = _extract_defeasible_sections(raw_model)
                self._assert_sections(case.name, expectation, actual, policy=policy_name)
            return

        raw_model = evaluate(case.theory, Policy.BLOCKING)
        actual = _extract_defeasible_sections(raw_model)
        expected = _as_sections(case.expect)
        self._assert_sections(case.name, expected, actual, policy=Policy.BLOCKING.value)

    def _run_klm_case(self, case: TestCase) -> None:
        supports = getattr(self.evaluator, "satisfies_klm_property", None)
        if not callable(supports):
            raise ConformanceFailure(
                "KLM property tests require "
                "evaluator.satisfies_klm_property(theory, property_name, policy)"
            )

        assert case.klm_property is not None
        for item in case.theories:
            for policy_name, expected in item.satisfies.items():
                actual = supports(item.theory, case.klm_property, Policy.from_name(policy_name))
                if actual is not expected:
                    raise ConformanceFailure(
                        f"{case.name} expected {policy_name}={expected!r} for {case.klm_property}, "
                        f"got {actual!r}"
                    )

    def _assert_expected_error(self, case: TestCase, callback: Callable[[], Any]) -> None:
        try:
            callback()
        except Exception as exc:  # noqa: BLE001
            expected = case.expect_error
            assert expected is not None
            if _matches_expected_error(exc, expected):
                return
            raise ConformanceFailure(
                f"{case.name} expected error {expected!r}, got {type(exc).__name__}: {exc}"
            ) from exc
        raise ConformanceFailure(f"{case.name} expected error {case.expect_error!r}, got success")

    def _assert_predicate_facts(
        self,
        case_name: str,
        expected: PredicateFacts,
        actual: dict[str, set[FactTuple]],
    ) -> None:
        for predicate, expected_rows in expected.items():
            expected_set = set(expected_rows)
            actual_set = actual.get(predicate, set())
            if expected_set != actual_set:
                raise ConformanceFailure(
                    f"{case_name} predicate {predicate!r}: expected {sorted(expected_set)!r}, "
                    f"got {sorted(actual_set)!r}"
                )

    def _assert_sections(
        self,
        case_name: str,
        expected: DefeasibleSections,
        actual: dict[str, dict[str, set[FactTuple]]],
        *,
        policy: str,
    ) -> None:
        for section, predicates in expected.items():
            if section not in actual:
                raise ConformanceFailure(
                    f"{case_name} policy {policy!r}: missing section {section!r}"
                )
            for predicate, expected_rows in predicates.items():
                expected_set = set(expected_rows)
                actual_set = actual[section].get(predicate, set())
                if expected_set != actual_set:
                    raise ConformanceFailure(
                        f"{case_name} policy {policy!r} section {section!r} "
                        f"predicate {predicate!r}: "
                        f"expected {sorted(expected_set)!r}, got {sorted(actual_set)!r}"
                    )


def _matches_expected_error(exc: Exception, expected: str) -> bool:
    if exc.__class__.__name__ == expected:
        return True
    if str(exc) == expected:
        return True
    code = getattr(exc, "code", None)
    return isinstance(code, str) and code == expected


def _as_predicate_facts(expectation: Any) -> PredicateFacts:
    if not isinstance(expectation, dict):
        raise ConformanceFailure("Expected predicate facts mapping")
    return cast(PredicateFacts, expectation)


def _as_sections(expectation: Any) -> DefeasibleSections:
    if not isinstance(expectation, dict):
        raise ConformanceFailure("Expected defeasible sections mapping")
    return cast(DefeasibleSections, expectation)


def _extract_model_facts(raw_model: Any) -> dict[str, set[FactTuple]]:
    if isinstance(raw_model, Model):
        return raw_model.facts
    mapping = getattr(raw_model, "facts", raw_model)
    return _normalize_predicate_mapping(mapping)


def _extract_defeasible_sections(raw_model: Any) -> dict[str, dict[str, set[FactTuple]]]:
    if isinstance(raw_model, DefeasibleModel):
        return raw_model.sections
    sections = getattr(raw_model, "sections", raw_model)
    if not isinstance(sections, dict):
        raise ConformanceFailure("Defeasible model must be a mapping or expose .sections")
    section_map = cast(dict[object, object], sections)
    result: dict[str, dict[str, set[FactTuple]]] = {}
    for section, predicates in section_map.items():
        if not isinstance(section, str):
            raise ConformanceFailure("Defeasible model section names must be strings")
        result[section] = _normalize_predicate_mapping(predicates)
    return result


def _normalize_predicate_mapping(raw_mapping: Any) -> dict[str, set[FactTuple]]:
    if not isinstance(raw_mapping, dict):
        raise ConformanceFailure("Model facts must be a mapping from predicate to tuples")
    mapping = cast(dict[object, object], raw_mapping)
    normalized: dict[str, set[FactTuple]] = {}
    for predicate, rows in mapping.items():
        if not isinstance(predicate, str):
            raise ConformanceFailure("Predicate names must be strings")
        normalized[predicate] = {_normalize_row(row) for row in _iter_rows(rows)}
    return normalized


def _iter_rows(rows: Any) -> list[object]:
    if isinstance(rows, (list, set, tuple)):
        return list(cast(list[object] | set[object] | tuple[object, ...], rows))
    raise ConformanceFailure("Predicate rows must be an iterable of tuples")


def _normalize_row(row: Any) -> FactTuple:
    if isinstance(row, (list, tuple)):
        values = cast(list[object] | tuple[object, ...], row)
        return tuple(_normalize_scalar(item) for item in values)
    raise ConformanceFailure(f"Fact rows must be tuples or lists, got {type(row).__name__}")


def _normalize_scalar(value: Any) -> Scalar:
    if isinstance(value, (str, int, float, bool)):
        return value
    return str(value)
