from __future__ import annotations

from pathlib import Path

from datalog_conformance.runner import YamlTestRunner

from .closure_test_support import PropositionalClosureEvaluator, load_suite_cases

_CLOSURE_FILE = Path("defeasible") / "closure" / "morris_core_examples.yaml"


def test_morris_closure_corpus_matches_local_reference() -> None:
    cases = load_suite_cases(_CLOSURE_FILE)

    assert [case.name for case in cases] == [
        "morris_example6_students_movies_distinguishes_closures",
        "morris_example6_people_defaults_stable_across_supported_closures",
    ]

    runner = YamlTestRunner(PropositionalClosureEvaluator())
    for case in cases:
        runner.run_test_case(case)
