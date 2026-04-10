"""Public package surface for datalog-conformance."""

from .plugin import discover_yaml_tests, get_tests_dir
from .protocol import DatalogEvaluator, DefeasibleEvaluator
from .runner import ConformanceFailure, YamlTestRunner
from .schema import (
    DefeasibleTheory,
    Model,
    Policy,
    Program,
    TestCase,
    load_test_case,
)

__all__ = [
    "ConformanceFailure",
    "DatalogEvaluator",
    "DefeasibleEvaluator",
    "DefeasibleTheory",
    "Model",
    "Policy",
    "Program",
    "TestCase",
    "YamlTestRunner",
    "discover_yaml_tests",
    "get_tests_dir",
    "load_test_case",
]
