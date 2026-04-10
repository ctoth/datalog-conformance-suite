from __future__ import annotations

import pytest

from datalog_conformance.runner import ConformanceFailure, YamlTestRunner
from datalog_conformance.schema import DefeasibleModel
from datalog_conformance.schema import TestCase as SuiteCase


class MockDatalogEvaluator:
    def evaluate(self, program: object) -> dict[str, set[tuple[str, ...]]]:
        rules = getattr(program, "rules", [])
        if any("q(Y)" in rule for rule in rules):
            error = ValueError("unsafe")
            setattr(error, "code", "unbound_variable")
            raise error
        return {
            "edge": {("a", "b"), ("b", "c")},
            "path": {("a", "b"), ("b", "c"), ("a", "c")},
        }


class MockDefeasibleEvaluator:
    def evaluate(self, theory: object, policy: object) -> DefeasibleModel:
        del theory
        if str(policy) == "Policy.PROPAGATING":
            return DefeasibleModel(
                sections={
                    "ambiguous": {"flies": {("opus",)}},
                    "defeasibly": {"flies": {("tweety",)}},
                }
            )
        return DefeasibleModel(
            sections={
                "defeasibly": {"flies": {("tweety",)}},
                "not_defeasibly": {"flies": {("opus",)}},
            }
        )


def test_runner_checks_positive_program_expectations() -> None:
    case = SuiteCase.from_dict(
        {
            "name": "transitive",
            "description": "Simple closure.",
            "source": "manual/test",
            "tags": ["basic", "recursion"],
            "program": {
                "facts": {"edge": [["a", "b"], ["b", "c"]]},
                "rules": [
                    "path(X, Y) :- edge(X, Y).",
                    "path(X, Y) :- edge(X, Z), path(Z, Y).",
                ],
            },
            "expect": {"path": [["a", "b"], ["b", "c"], ["a", "c"]]},
        }
    )

    YamlTestRunner(MockDatalogEvaluator()).run_test_case(case)


def test_runner_checks_expected_errors() -> None:
    case = SuiteCase.from_dict(
        {
            "name": "unsafe",
            "description": "Unsafe rule.",
            "source": "manual/test",
            "tags": ["errors"],
            "program": {
                "facts": {},
                "rules": ["p(X) :- q(Y)."],
            },
            "expect_error": "unbound_variable",
        }
    )

    YamlTestRunner(MockDatalogEvaluator()).run_test_case(case)


def test_runner_checks_defeasible_policies() -> None:
    case = SuiteCase.from_dict(
        {
            "name": "blocking_vs_propagating",
            "description": "Different policies produce different sections.",
            "source": "manual/test",
            "tags": ["defeasible", "ambiguity"],
            "theory": {
                "facts": {"bird": [["tweety"]], "penguin": [["opus"]]},
                "strict_rules": [{"id": "r1", "head": "bird(X)", "body": ["penguin(X)"]}],
                "defeasible_rules": [{"id": "r2", "head": "flies(X)", "body": ["bird(X)"]}],
                "defeaters": [{"id": "r3", "head": "~flies(X)", "body": ["penguin(X)"]}],
                "superiority": [["r3", "r2"]],
            },
            "expect_per_policy": {
                "blocking": {
                    "defeasibly": {"flies": [["tweety"]]},
                    "not_defeasibly": {"flies": [["opus"]]},
                },
                "propagating": {
                    "defeasibly": {"flies": [["tweety"]]},
                    "ambiguous": {"flies": [["opus"]]},
                },
            },
        }
    )

    YamlTestRunner(MockDefeasibleEvaluator()).run_test_case(case)


def test_runner_raises_on_mismatch() -> None:
    case = SuiteCase.from_dict(
        {
            "name": "bad_expectation",
            "description": "Intentional mismatch.",
            "source": "manual/test",
            "tags": ["basic"],
            "program": {
                "facts": {"edge": [["a", "b"], ["b", "c"]]},
                "rules": ["path(X, Y) :- edge(X, Y)."],
            },
            "expect": {"path": [["a", "b"]]},
        }
    )

    with pytest.raises(ConformanceFailure):
        YamlTestRunner(MockDatalogEvaluator()).run_test_case(case)
