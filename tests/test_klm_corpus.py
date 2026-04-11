from __future__ import annotations

from pathlib import Path

import yaml

from datalog_conformance.runner import YamlTestRunner
from datalog_conformance.schema import TestCase as SuiteCase

from .closure_test_support import PropositionalClosureEvaluator

_KLM_FILE = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "datalog_conformance"
    / "_tests"
    / "defeasible"
    / "klm"
    / "morris_relevant_counterexamples.yaml"
)


def test_morris_klm_corpus_matches_local_reference() -> None:
    raw = yaml.safe_load(_KLM_FILE.read_text(encoding="utf-8"))
    assert isinstance(raw, dict)
    case = SuiteCase.from_dict(raw)

    assert case.name == "morris_relevant_or_counterexamples"
    assert case.klm_property == "Or"
    assert len(case.theories) == 2

    YamlTestRunner(PropositionalClosureEvaluator()).run_test_case(case)
