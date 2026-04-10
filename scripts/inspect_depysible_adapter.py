from __future__ import annotations

from pprint import pprint

from datalog_conformance.examples.depysible_adapter import DePYsibleAdapter
from datalog_conformance.schema import DefeasibleTheory, Policy

THEORIES = {
    "baseline_birds": DefeasibleTheory.from_dict(
        {
            "facts": {
                "chicken": [["tina"]],
                "penguin": [["tweety"]],
                "scared": [["tina"]],
            },
            "strict_rules": [
                {"id": "r1", "head": "bird(X)", "body": ["chicken(X)"]},
                {"id": "r2", "head": "bird(X)", "body": ["penguin(X)"]},
                {"id": "r3", "head": "~flies(X)", "body": ["penguin(X)"]},
            ],
            "defeasible_rules": [
                {"id": "r4", "head": "flies(X)", "body": ["bird(X)"]},
                {"id": "r5", "head": "flies(X)", "body": ["chicken(X)", "scared(X)"]},
                {"id": "r6", "head": "~flies(X)", "body": ["chicken(X)"]},
                {"id": "r7", "head": "nests_in_trees(X)", "body": ["flies(X)"]},
            ],
            "defeaters": [],
            "superiority": [],
        }
    ),
    "positive_chicken": DefeasibleTheory.from_dict(
        {
            "facts": {
                "chicken": [["henrietta"]],
                "scared": [["henrietta"]],
            },
            "strict_rules": [
                {"id": "r1", "head": "bird(X)", "body": ["chicken(X)"]},
            ],
            "defeasible_rules": [
                {"id": "r2", "head": "flies(X)", "body": ["bird(X)"]},
                {"id": "r3", "head": "flies(X)", "body": ["chicken(X)", "scared(X)"]},
                {"id": "r4", "head": "nests_in_trees(X)", "body": ["flies(X)"]},
            ],
            "defeaters": [],
            "superiority": [],
        }
    ),
}


def main() -> None:
    adapter = DePYsibleAdapter()
    for name, theory in THEORIES.items():
        print(f"== {name} ==")
        model = adapter.evaluate(theory, Policy.BLOCKING)
        pprint(model.sections)


if __name__ == "__main__":
    main()
