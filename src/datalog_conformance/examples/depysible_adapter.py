"""Optional adapter for running defeasible tests against DePYsible.

This adapter intentionally supports only the subset that DePYsible exposes directly:
- facts
- strict rules
- defeasible rules

It rejects explicit defeaters, superiority, and policy variants that were not verified here.
"""
# pyright: reportMissingImports=false, reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownArgumentType=false

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from datalog_conformance.schema import DefeasibleModel, DefeasibleTheory, Policy, Scalar


@dataclass(slots=True)
class DePYsibleAdapter:
    """Bridge the conformance protocol to a locally importable DePYsible checkout."""

    def evaluate(self, theory: DefeasibleTheory, policy: Policy) -> DefeasibleModel:
        if policy is not Policy.BLOCKING:
            raise ValueError(
                "DePYsible adapter only supports inferred blocking-style policy, "
                f"got {policy.value}"
            )
        if theory.defeaters:
            raise ValueError(
                "DePYsible adapter does not support explicit defeaters from this schema"
            )
        if theory.superiority:
            raise ValueError("DePYsible adapter does not support superiority declarations")
        if theory.conflicts:
            raise ValueError("DePYsible adapter does not support explicit conflict declarations")

        from depysible.domain.definitions import Program, RuleType
        from depysible.domain.interpretation import Answer, Interpreter

        program = Program.parse(_render_program(theory))
        interpreter = Interpreter(program)

        sections: dict[str, dict[str, set[tuple[Scalar, ...]]]] = {
            "definitely": {},
            "defeasibly": {},
            "not_defeasibly": {},
            "undecided": {},
        }

        for literal in interpreter.get_literals(RuleType.DEFEASIBLE):
            strict_answer, _ = interpreter.query(literal, RuleType.STRICT)
            defeasible_answer, _ = interpreter.query(literal, RuleType.DEFEASIBLE)
            predicate = _literal_predicate_name(literal)
            row = tuple(_normalize_term(term) for term in literal.terms)

            if strict_answer is Answer.YES:
                sections["definitely"].setdefault(predicate, set()).add(row)
            if defeasible_answer is Answer.YES:
                sections["defeasibly"].setdefault(predicate, set()).add(row)
            elif defeasible_answer is Answer.NO:
                sections["not_defeasibly"].setdefault(predicate, set()).add(row)
            elif defeasible_answer is Answer.UNDECIDED:
                sections["undecided"].setdefault(predicate, set()).add(row)

        return DefeasibleModel(sections={key: value for key, value in sections.items() if value})


def _render_program(theory: DefeasibleTheory) -> str:
    lines: list[str] = []
    for predicate, rows in theory.facts.items():
        for row in rows:
            lines.append(f"{predicate}({', '.join(_render_term(term) for term in row)}).")
    for rule in theory.strict_rules:
        lines.append(_render_rule(rule.head, rule.body, arrow="<-"))
    for rule in theory.defeasible_rules:
        lines.append(_render_rule(rule.head, rule.body, arrow="-<"))
    return "\n".join(lines)


def _render_rule(head: str, body: list[str], *, arrow: str) -> str:
    if not body:
        return f"{head}."
    return f"{head} {arrow} {', '.join(body)}."


def _render_term(term: Scalar) -> str:
    if isinstance(term, str):
        if term and term[0].isupper():
            return term
        return term if term.isidentifier() else repr(term)
    return str(term)


def _literal_predicate_name(literal: Any) -> str:
    prefix = "~" if getattr(literal, "negated", False) else ""
    return f"{prefix}{literal.functor}"


def _normalize_term(term: Any) -> Scalar:
    if isinstance(term, (str, int, float, bool)):
        return term
    return str(term)
