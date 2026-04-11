from __future__ import annotations

from collections import Counter

from datalog_conformance.plugin import discover_yaml_tests


def main() -> int:
    counts: Counter[str] = Counter()
    for _, case in discover_yaml_tests():
        if case.program is not None:
            counts["core"] += 1
        elif case.theory is not None:
            counts["defeasible"] += 1
        elif case.klm_property is not None:
            counts["property"] += 1

    counts["total"] = counts["core"] + counts["defeasible"] + counts["property"]
    for key in ("core", "defeasible", "property", "total"):
        print(f"{key}: {counts[key]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
