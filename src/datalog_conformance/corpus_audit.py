"""Static audits for runner-visible corpus validity."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .plugin import discover_yaml_tests
from .schema import Policy, TestCase, VerificationKind

_HEAD_RE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*(?:\(|$)")


@dataclass(frozen=True, slots=True)
class AuditFinding:
    """A concrete corpus problem tied to a specific test case."""

    path: Path
    case_name: str
    code: str
    message: str


def audit_program_surface(test_dir: Path | None = None) -> list[AuditFinding]:
    """Find program cases whose expectations are impossible from visible YAML alone."""

    findings: list[AuditFinding] = []
    for yaml_path, case in discover_yaml_tests(test_dir):
        if case.program is None or case.expect is None:
            continue

        facts = case.program.facts
        fact_sets = {predicate: set(rows) for predicate, rows in facts.items()}
        rule_heads = {_rule_head(rule) for rule in case.program.rules}

        for predicate, rows in case.expect.items():
            if not rows:
                continue
            expected_rows = set(rows)
            if predicate not in facts and predicate not in rule_heads:
                findings.append(
                    AuditFinding(
                        path=yaml_path,
                        case_name=case.name,
                        code="missing_visible_derivation",
                        message=(
                            f"expected predicate {predicate!r} has rows but is absent from visible "
                            "facts and visible rule heads"
                        ),
                    )
                )
                continue

            if not case.program.rules:
                missing_rows = expected_rows - fact_sets.get(predicate, set())
                if missing_rows:
                    findings.append(
                        AuditFinding(
                            path=yaml_path,
                            case_name=case.name,
                            code="facts_only_mismatch",
                            message=(
                                f"expected predicate {predicate!r} has non-fact rows in a "
                                f"facts-only case: {sorted(missing_rows)!r}"
                            ),
                        )
                    )
                continue

            if predicate not in rule_heads:
                missing_rows = expected_rows - fact_sets.get(predicate, set())
                if missing_rows:
                    findings.append(
                        AuditFinding(
                            path=yaml_path,
                            case_name=case.name,
                            code="missing_visible_rule_head",
                            message=(
                                f"expected predicate {predicate!r} has rows not present in facts, "
                                "but no visible rule head derives that predicate"
                            ),
                        )
                    )
                continue

    return findings


def audit_policy_closure_verification(test_dir: Path | None = None) -> list[AuditFinding]:
    """Find policy, closure, and KLM cases without an auditable verification path."""

    findings: list[AuditFinding] = []
    for yaml_path, case in discover_yaml_tests(test_dir):
        if not _requires_policy_closure_verification(case):
            continue

        if case.verification is None:
            findings.append(
                AuditFinding(
                    path=yaml_path,
                    case_name=case.name,
                    code="missing_verification_path",
                    message=(
                        "policy, closure, and KLM cases require verification metadata "
                        "recording a direct implementation or paper-image-backed reduced path"
                    ),
                )
            )
            continue

        if case.verification.kind is VerificationKind.REDUCED and not _has_paper_image_citation(
            case
        ):
            findings.append(
                AuditFinding(
                    path=yaml_path,
                    case_name=case.name,
                    code="missing_paper_image_citation",
                    message=(
                        "reduced policy, closure, and KLM cases must cite an exact "
                        "paper-image-backed source"
                    ),
                )
            )

    return findings


def format_findings(findings: list[AuditFinding], *, root: Path | None = None) -> str:
    """Render findings for CLI or test output."""

    lines = [f"Program-surface audit failed with {len(findings)} finding(s):"]
    for finding in findings:
        display_path = _display_path(finding.path, root)
        lines.append(f"- {display_path}::{finding.case_name} [{finding.code}] {finding.message}")
    return "\n".join(lines)


def _rule_head(rule_text: str) -> str:
    head_text = rule_text.strip().split(":-", 1)[0].strip().removesuffix(".")
    match = _HEAD_RE.match(head_text)
    if match is None:
        raise ValueError(f"Unsupported rule head syntax: {rule_text}")
    return match.group(1)


def _requires_policy_closure_verification(case: TestCase) -> bool:
    tags = set(case.tags)
    if tags & {"ambiguity", "closure", "klm"}:
        return True
    if case.klm_property is not None:
        return True
    if case.expect_per_policy is None:
        return False
    policy_names = {policy.value for policy in Policy}
    return any(name in policy_names for name in case.expect_per_policy)


def _has_paper_image_citation(case: TestCase) -> bool:
    tags = set(case.tags)
    return (
        case.source.startswith("paper/")
        and "paper" in tags
        and "page-image-derived" in tags
        and "page" in case.source
    )


def _display_path(path: Path, root: Path | None) -> str:
    if root is None:
        return path.as_posix()
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()
