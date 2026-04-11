from __future__ import annotations

import yaml

from datalog_conformance.schema import TestCase as SuiteCase


def test_core_case_round_trips_through_yaml() -> None:
    raw = {
        "name": "joins",
        "description": "Join on a shared variable.",
        "source": "manual/test",
        "tags": ["basic", "joins"],
        "verification": {
            "implementation": "nmo",
            "kind": "direct",
        },
        "program": {
            "facts": {
                "parent": [["ada", "bob"], ["bob", "cora"]],
                "female": [["ada"], ["cora"]],
            },
            "rules": ["grandmother(X, Z) :- parent(X, Y), parent(Y, Z), female(X)."],
        },
        "expect": {"grandmother": [["ada", "cora"]]},
    }

    case = SuiteCase.from_dict(raw)
    encoded = yaml.safe_dump(case.to_dict(), sort_keys=True)
    decoded = SuiteCase.from_dict(yaml.safe_load(encoded))

    assert decoded == case


def test_core_case_with_reduced_verification_round_trips() -> None:
    raw = {
        "name": "portable_subset",
        "description": "Reduced surrogate with recorded runtime confirmation.",
        "source": "manual/test",
        "tags": ["basic"],
        "verification": {
            "implementation": "nmo",
            "kind": "reduced",
        },
        "program": {
            "facts": {"edge": [["a", "b"]]},
            "rules": ["path(X, Y) :- edge(X, Y)."],
        },
        "expect": {"path": [["a", "b"]]},
    }

    case = SuiteCase.from_dict(raw)
    encoded = yaml.safe_dump(case.to_dict(), sort_keys=True)
    decoded = SuiteCase.from_dict(yaml.safe_load(encoded))

    assert decoded == case


def test_defeasible_case_round_trips_through_yaml() -> None:
    raw = {
        "name": "defeasible_only",
        "description": "Simple defeasible theory.",
        "source": "manual/test",
        "tags": ["defeasible", "basic"],
        "theory": {
            "facts": {"bird": [["tweety"]]},
            "strict_rules": [],
            "defeasible_rules": [{"id": "r1", "head": "flies(X)", "body": ["bird(X)"]}],
            "defeaters": [],
            "superiority": [],
        },
        "expect": {"defeasibly": {"flies": [["tweety"]]}},
    }

    case = SuiteCase.from_dict(raw)
    encoded = yaml.safe_dump(case.to_dict(), sort_keys=True)
    decoded = SuiteCase.from_dict(yaml.safe_load(encoded))

    assert decoded == case
