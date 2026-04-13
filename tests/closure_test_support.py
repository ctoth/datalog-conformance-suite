from __future__ import annotations

from pathlib import Path
from typing import cast

import yaml

from datalog_conformance.schema import TestCase


def load_suite_cases(relative_path: Path) -> list[TestCase]:
    repo_tests_dir = Path(__file__).resolve().parents[1] / "src" / "datalog_conformance" / "_tests"
    yaml_path = repo_tests_dir / relative_path
    raw = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    assert isinstance(raw, dict)
    data = cast(dict[object, object], raw)

    raw_base_tags = data.get("tags", [])
    base_tags = list(cast(list[object], raw_base_tags)) if isinstance(raw_base_tags, list) else []
    base_source = data.get("source")
    base_verification = data.get("verification")
    entries_obj = data.get("tests", [])
    assert isinstance(entries_obj, list)
    entries = cast(list[object], entries_obj)

    cases: list[TestCase] = []
    for entry in entries:
        assert isinstance(entry, dict)
        merged = dict(cast(dict[object, object], entry))
        if "source" not in merged and base_source is not None:
            merged["source"] = base_source
        if "verification" not in merged and base_verification is not None:
            merged["verification"] = base_verification
        if base_tags:
            local_tags_obj = merged.get("tags", [])
            assert isinstance(local_tags_obj, list)
            local_tags = cast(list[object], local_tags_obj)
            merged["tags"] = [*base_tags, *local_tags]
        cases.append(TestCase.from_dict(merged))
    return cases
