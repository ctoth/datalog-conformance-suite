"""Evaluate a batch of defeasible theories through DePYsible in one process.

Helper for ``scripts/generate_defeasible_corpus.py``. DePYsible's answers can
depend on Python's per-process hash seed (set iteration order steers its
dialectical search), so the generator launches this script several times with
different ``PYTHONHASHSEED`` values and only keeps theories whose sections
agree across every run.

Usage: this script is spawned by the generator with two arguments — the input
JSON path (a list of theory mappings in the YAML schema shape) and the output
JSON path (a list of ``{"sections": ...}`` or ``{"error": ...}`` entries).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from datalog_conformance.examples.depysible_adapter import DePYsibleAdapter
from datalog_conformance.schema import DefeasibleTheory, FactTuple, Policy


def canonical_sections(
    sections: dict[str, dict[str, set[FactTuple]]],
) -> dict[str, dict[str, list[list[str]]]]:
    """Render adapter sections as sorted, JSON/YAML-stable nested lists."""

    return {
        section: {
            predicate: sorted([str(value) for value in row] for row in rows)
            for predicate, rows in sorted(predicates.items())
        }
        for section, predicates in sorted(sections.items())
    }


def main() -> int:
    input_path = Path(sys.argv[1])
    output_path = Path(sys.argv[2])
    raw_theories: list[dict[str, Any]] = json.loads(input_path.read_text(encoding="utf-8"))

    adapter = DePYsibleAdapter()
    results: list[dict[str, Any]] = []
    for raw_theory in raw_theories:
        theory = DefeasibleTheory.from_dict(raw_theory)
        try:
            model = adapter.evaluate(theory, Policy.BLOCKING)
        except Exception as exc:  # noqa: BLE001 - a rejection is data, not a crash
            results.append({"error": f"{type(exc).__name__}: {exc}"})
            continue
        results.append({"sections": canonical_sections(model.sections)})

    output_path.write_text(json.dumps(results), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
