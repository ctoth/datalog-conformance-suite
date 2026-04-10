"""pytest plugin for bundled datalog conformance YAML suites."""

from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest
import yaml

from .runner import YamlTestRunner
from .schema import SchemaError, TestCase


def get_tests_dir() -> Path:
    """Return the bundled `_tests` directory."""

    return Path(__file__).parent / "_tests"


def pytest_addoption(parser: pytest.Parser) -> None:
    """Register datalog-conformance CLI flags."""

    parser.addoption(
        "--datalog-evaluator",
        default=None,
        help="Import path to an evaluator class or instance, e.g. mypkg.MyEvaluator",
    )
    parser.addoption(
        "--datalog-tags",
        default=None,
        help="Comma-separated tag filter. All listed tags must be present on the test case.",
    )


def discover_yaml_tests(test_dir: Path | None = None) -> list[tuple[Path, TestCase]]:
    """Discover and validate bundled YAML test cases."""

    root = test_dir or get_tests_dir()
    if not root.exists():
        return []

    cases: list[tuple[Path, TestCase]] = []
    for yaml_file in sorted(root.rglob("*.yaml")):
        raw = yaml.safe_load(yaml_file.read_text(encoding="utf-8"))
        if raw is None:
            continue
        if isinstance(raw, dict) and "tests" in raw:
            suite_cases = _load_multi_case_file(cast(dict[object, object], raw), yaml_file)
            cases.extend((yaml_file, case) for case in suite_cases)
            continue
        cases.append((yaml_file, TestCase.from_dict(raw)))
    return cases


def pytest_generate_tests(metafunc: pytest.Metafunc) -> None:
    """Parametrize `yaml_test_case` from bundled YAML files."""

    if "yaml_test_case" not in metafunc.fixturenames:
        return

    requested_tags = _parse_requested_tags(metafunc.config.getoption("--datalog-tags"))
    tests_dir = get_tests_dir()
    params: list[tuple[Path, TestCase]] = []
    ids: list[str] = []

    for yaml_path, case in discover_yaml_tests():
        if requested_tags and not requested_tags.issubset(set(case.tags)):
            continue
        try:
            relative = yaml_path.relative_to(tests_dir).with_suffix("")
            case_id = f"{relative.as_posix()}::{case.name}"
        except ValueError:
            case_id = f"{yaml_path.stem}::{case.name}"
        params.append((yaml_path, case))
        ids.append(case_id)

    metafunc.parametrize("yaml_test_case", params, ids=ids)


@pytest.fixture
def yaml_test_case(request: pytest.FixtureRequest) -> tuple[Path, TestCase]:
    """Placeholder fixture populated by `pytest_generate_tests`."""

    return request.param


@pytest.fixture
def runner(request: pytest.FixtureRequest) -> YamlTestRunner:
    """Instantiate a runner from the configured evaluator import path."""

    import_path = request.config.getoption("--datalog-evaluator")
    if import_path is None:
        pytest.skip("Provide --datalog-evaluator=package.Class to run conformance suites")
    return YamlTestRunner.from_import_path(import_path)


def pytest_configure(config: pytest.Config) -> None:
    """Register the package marker."""

    config.addinivalue_line("markers", "conformance: bundled datalog conformance suite")


def _parse_requested_tags(raw: str | None) -> set[str]:
    if raw is None:
        return set()
    return {item.strip() for item in raw.split(",") if item.strip()}


def _load_multi_case_file(raw: dict[object, object], yaml_path: Path) -> list[TestCase]:
    base_tags = raw.get("tags", [])
    base_source = raw.get("source")
    test_entries = raw.get("tests")
    if not isinstance(test_entries, list):
        raise SchemaError(f"{yaml_path}: tests must be a list")
    entries = cast(list[object], test_entries)

    cases: list[TestCase] = []
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise SchemaError(f"{yaml_path}: tests[{index}] must be a mapping")
        merged = dict(cast(dict[object, object], entry))
        if "source" not in merged and base_source is not None:
            merged["source"] = base_source
        if base_tags:
            inherited_tags = list(cast(list[object], base_tags))
            local_tags = list(cast(list[object], merged.get("tags", [])))
            merged["tags"] = [*inherited_tags, *local_tags]
        cases.append(TestCase.from_dict(merged))
    return cases
