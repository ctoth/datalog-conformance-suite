from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from pprint import pprint

from datalog_conformance.examples.depysible_adapter import DePYsibleAdapter
from datalog_conformance.schema import DefeasibleTheory, Policy

_DEPYSIBLE_SOURCE_ROOT = Path(tempfile.gettempdir()) / "depysible" / "src" / "main" / "python"

THEORIES = {
    "morris_example5_birds": DefeasibleTheory.from_dict(
        {
            "facts": {
                "bird": [["tweety"], ["chirpy"]],
                "~fly": [["tweety"]],
            },
            "strict_rules": [],
            "defeasible_rules": [
                {"id": "r1", "head": "fly(X)", "body": ["bird(X)"]},
            ],
            "defeaters": [],
            "superiority": [],
        }
    ),
    "bozzato_example1_bob": DefeasibleTheory.from_dict(
        {
            "facts": {
                "phd_member": [["bob"]],
            },
            "strict_rules": [
                {"id": "r1", "head": "dept_member(X)", "body": ["phd_member(X)"]},
            ],
            "defeasible_rules": [
                {"id": "r2", "head": "teach_course(X)", "body": ["dept_member(X)"]},
                {"id": "r3", "head": "~teach_course(X)", "body": ["phd_member(X)"]},
            ],
            "defeaters": [],
            "superiority": [],
        }
    ),
    "goldszmidt_example1_nixon": DefeasibleTheory.from_dict(
        {
            "facts": {
                "nixonian": [["nixon"]],
                "quaker": [["nixon"]],
            },
            "strict_rules": [],
            "defeasible_rules": [
                {"id": "r1", "head": "republican(X)", "body": ["nixonian(X)"]},
                {"id": "r2", "head": "pacifist(X)", "body": ["quaker(X)"]},
                {"id": "r3", "head": "~pacifist(X)", "body": ["republican(X)"]},
            ],
            "defeaters": [],
            "superiority": [],
        }
    ),
}


def main() -> None:
    if str(_DEPYSIBLE_SOURCE_ROOT) not in sys.path:
        sys.path.insert(0, str(_DEPYSIBLE_SOURCE_ROOT))
    adapter = DePYsibleAdapter()
    for name, theory in THEORIES.items():
        print(f"== {name} ==")
        model = adapter.evaluate(theory, Policy.BLOCKING)
        pprint(model.sections)


if __name__ == "__main__":
    main()
