from __future__ import annotations

import pytest

from datalog_conformance.runner import YamlTestRunner
from datalog_conformance.schema import TestCase as SuiteCase


@pytest.mark.conformance
def test_yaml_conformance(
    runner: YamlTestRunner,
    yaml_test_case: tuple[object, SuiteCase],
) -> None:
    yaml_path, case = yaml_test_case
    del yaml_path

    if case.skip is not None:
        pytest.skip(case.skip)

    runner.run_test_case(case)
