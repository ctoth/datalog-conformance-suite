"""Replay every generated defeasible case against the live DePYsible engine.

This is the external-verification gate for the ``defeasible_gen_`` corpus:
each retained case's expected sections must reproduce through the bundled
DePYsible adapter via the standard YAML runner. Run with:

    uv run --with arpeggio --with colorama pytest tests/test_generated_defeasible_corpus.py
"""

from __future__ import annotations

import pytest

from datalog_conformance.plugin import discover_yaml_tests, get_tests_dir
from datalog_conformance.runner import YamlTestRunner
from datalog_conformance.schema import TestCase
from tests.depysible_test_support import (
    depysible_runtime_available,
    depysible_source_available,
    instantiate_depysible_adapter,
)

if not depysible_source_available():
    pytest.skip(
        "DePYsible checkout not found under the expected temp directory",
        allow_module_level=True,
    )

if not depysible_runtime_available():
    pytest.skip(
        "DePYsible dependencies are unavailable in the local checkout",
        allow_module_level=True,
    )

_GENERATED_DIR = get_tests_dir() / "generated"


def _generated_defeasible_cases() -> list[TestCase]:
    return [
        case
        for yaml_path, case in discover_yaml_tests(_GENERATED_DIR)
        if yaml_path.name.startswith("defeasible_gen_")
    ]


@pytest.fixture(scope="module")
def depysible_runner() -> YamlTestRunner:
    return YamlTestRunner(instantiate_depysible_adapter())


@pytest.mark.parametrize(
    "case",
    _generated_defeasible_cases(),
    ids=lambda case: case.name,
)
def test_generated_defeasible_case_replays_on_depysible(
    case: TestCase,
    depysible_runner: YamlTestRunner,
) -> None:
    depysible_runner.run_test_case(case)
