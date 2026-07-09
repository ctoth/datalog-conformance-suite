"""Generate the DePYsible-verified defeasible corpus.

Builds deterministic (seeded) defeasible theories inside the fragment the
bundled DePYsible adapter supports — facts, strict rules, and defeasible
rules with strong negation, under the inferred blocking-style policy. The
adapter rejects defeaters, superiority declarations, and explicit conflict
sets, so those features are deliberately absent here; priority-like effects
are exercised through strict-versus-defeasible layering instead.

Expected sections are computed by RUNNING each theory through the live
DePYsible implementation (an external system, not code in this repo).
DePYsible's answers can vary with the Python hash seed (set iteration order
steers its dialectical search), so every candidate theory is evaluated in
several subprocesses with different ``PYTHONHASHSEED`` values, and only
theories whose sections agree across all runs are retained. Theories that
DePYsible rejects, that produce an incoherent strict layer, or that yield
trivial output are also dropped, so every emitted case is externally
verified and replay-stable by construction. Replay the whole corpus with:

    uv run --with arpeggio --with colorama pytest tests/test_generated_defeasible_corpus.py

Run the generator itself with:

    uv run --with arpeggio --with colorama scripts/generate_defeasible_corpus.py
"""

from __future__ import annotations

import argparse
import json
import os
import random
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypeAlias

import yaml

from datalog_conformance.schema import DefeasibleTheory, PredicateFacts, Rule

CanonicalSections: TypeAlias = dict[str, dict[str, list[list[str]]]]

OUTPUT_DIR = Path("src/datalog_conformance/_tests/generated")
SOURCE = "generated/depysible-defeasible-corpus-v1"
VERIFICATION = {"implementation": "depysible", "kind": "direct"}
BASE_TAGS = ["defeasible", "generated"]
SEED = 20260709
CHUNK_SIZE = 400
HASH_SEEDS = tuple(
    str(value)
    for value in (0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 17, 19, 23, 42, 20260709, 424242)
)

# Theory keys (as produced by ``_theory_key``) that agreed across every
# HASH_SEEDS run at some point but still replayed unstably under other hash
# seeds. Found by repeatedly replaying the emitted corpus; excluded here so
# regeneration stays deterministic and every retained case replays reliably.
KNOWN_UNSTABLE_THEORY_KEYS: frozenset[str] = frozenset()

_CONSTANTS = ("ann", "bob", "cyd")
_BATCH_SCRIPT = Path(__file__).with_name("eval_depysible_batch.py")


@dataclass(frozen=True, slots=True)
class ShapedTheory:
    """A generated theory plus its shape metadata."""

    shape: str
    tags: tuple[str, ...]
    description: str
    theory: DefeasibleTheory


def _facts(pairs: dict[str, list[tuple[str, ...]]]) -> PredicateFacts:
    return {predicate: [tuple(row) for row in rows] for predicate, rows in sorted(pairs.items())}


def _rules(specs: list[tuple[str, list[str]]], prefix: str) -> list[Rule]:
    return [
        Rule(id=f"{prefix}{index}", head=head, body=list(body))
        for index, (head, body) in enumerate(specs, start=1)
    ]


def _negate(literal: str) -> str:
    return literal[1:] if literal.startswith("~") else f"~{literal}"


def _chain_theories(rng: random.Random) -> list[ShapedTheory]:
    """Linear derivation chains with every strict/defeasible link pattern."""

    shaped: list[ShapedTheory] = []
    for depth in range(2, 6):
        for pattern in range(2**depth):
            kinds = [(pattern >> level) & 1 == 1 for level in range(depth)]
            constants = _CONSTANTS[: rng.randint(1, 3)]
            negated_tail = rng.random() < 0.3
            strict_specs: list[tuple[str, list[str]]] = []
            defeasible_specs: list[tuple[str, list[str]]] = []
            for level, defeasible in enumerate(kinds):
                head = f"q{level + 1}(X)"
                if negated_tail and level == depth - 1:
                    head = f"~q{level + 1}(X)"
                body = [f"q{level}(X)"]
                if defeasible:
                    defeasible_specs.append((head, body))
                else:
                    strict_specs.append((head, body))
            theory = DefeasibleTheory(
                facts=_facts({"q0": [(constant,) for constant in constants]}),
                strict_rules=_rules(strict_specs, "s"),
                defeasible_rules=_rules(defeasible_specs, "d"),
            )
            defeasible_count = sum(kinds)
            shaped.append(
                ShapedTheory(
                    shape="chain",
                    tags=(
                        f"depth-{depth}",
                        f"defeasible-links-{defeasible_count}",
                    ),
                    description=(
                        f"Derivation chain of depth {depth} with "
                        f"{defeasible_count} defeasible link(s) "
                        f"(pattern {pattern:0{depth}b}) over {len(constants)} constant(s)."
                    ),
                    theory=theory,
                )
            )
    return shaped


def _ambiguity_theories(rng: random.Random) -> list[ShapedTheory]:
    """Competing defeasible conclusions, with downstream propagation."""

    shaped: list[ShapedTheory] = []
    for pro_depth in range(1, 4):
        for con_depth in range(1, 4):
            for downstream in range(3):
                constants = _CONSTANTS[: rng.randint(1, 2)]
                fact_rows = [(constant,) for constant in constants]
                defeasible_specs: list[tuple[str, list[str]]] = []
                for level in range(pro_depth):
                    head = "goal(X)" if level == pro_depth - 1 else f"p{level + 1}(X)"
                    body = ["pro0(X)"] if level == 0 else [f"p{level}(X)"]
                    defeasible_specs.append((head, body))
                for level in range(con_depth):
                    head = "~goal(X)" if level == con_depth - 1 else f"c{level + 1}(X)"
                    body = ["con0(X)"] if level == 0 else [f"c{level}(X)"]
                    defeasible_specs.append((head, body))
                for level in range(downstream):
                    body = ["goal(X)"] if level == 0 else [f"after{level}(X)"]
                    defeasible_specs.append((f"after{level + 1}(X)", body))
                theory = DefeasibleTheory(
                    facts=_facts({"pro0": fact_rows, "con0": fact_rows}),
                    defeasible_rules=_rules(defeasible_specs, "d"),
                )
                shaped.append(
                    ShapedTheory(
                        shape="ambiguity",
                        tags=(
                            f"pro-depth-{pro_depth}",
                            f"con-depth-{con_depth}",
                            f"downstream-{downstream}",
                        ),
                        description=(
                            "Ambiguous goal supported through a "
                            f"{pro_depth}-step chain and attacked through a "
                            f"{con_depth}-step chain, with {downstream} downstream "
                            "conclusion(s) hanging off the ambiguous literal."
                        ),
                        theory=theory,
                    )
                )
    return shaped


def _strict_override_theories(rng: random.Random) -> list[ShapedTheory]:
    """Strict conclusions overriding defeasible ones (and the reverse layering)."""

    shaped: list[ShapedTheory] = []
    for strict_side in ("negative", "positive"):
        for strict_depth in range(1, 4):
            for defeasible_depth in range(1, 4):
                for downstream in range(2):
                    constants = _CONSTANTS[: rng.randint(1, 3)]
                    fact_rows = [(constant,) for constant in constants]
                    strict_goal = "~goal(X)" if strict_side == "negative" else "goal(X)"
                    defeasible_goal = "goal(X)" if strict_side == "negative" else "~goal(X)"
                    strict_specs: list[tuple[str, list[str]]] = []
                    for level in range(strict_depth):
                        head = strict_goal if level == strict_depth - 1 else f"s{level + 1}(X)"
                        body = ["base_s(X)"] if level == 0 else [f"s{level}(X)"]
                        strict_specs.append((head, body))
                    defeasible_specs: list[tuple[str, list[str]]] = []
                    for level in range(defeasible_depth):
                        head = (
                            defeasible_goal
                            if level == defeasible_depth - 1
                            else f"w{level + 1}(X)"
                        )
                        body = ["base_w(X)"] if level == 0 else [f"w{level}(X)"]
                        defeasible_specs.append((head, body))
                    for level in range(downstream):
                        source = defeasible_goal if level == 0 else f"then{level}(X)"
                        defeasible_specs.append((f"then{level + 1}(X)", [source]))
                    theory = DefeasibleTheory(
                        facts=_facts({"base_s": fact_rows, "base_w": fact_rows}),
                        strict_rules=_rules(strict_specs, "s"),
                        defeasible_rules=_rules(defeasible_specs, "d"),
                    )
                    shaped.append(
                        ShapedTheory(
                            shape="strict_override",
                            tags=(
                                f"strict-side-{strict_side}",
                                f"strict-depth-{strict_depth}",
                                f"defeasible-depth-{defeasible_depth}",
                                f"downstream-{downstream}",
                            ),
                            description=(
                                f"A {strict_depth}-step strict chain concludes "
                                f"{strict_goal.replace('(X)', '')} while a "
                                f"{defeasible_depth}-step defeasible chain argues the "
                                "complement; strict knowledge must win under the "
                                "blocking-style policy."
                            ),
                            theory=theory,
                        )
                    )
    return shaped


def _team_theories(rng: random.Random) -> list[ShapedTheory]:
    """Teams of independent defeasible reasons for and against one literal."""

    shaped: list[ShapedTheory] = []
    for pro_team in range(1, 4):
        for con_team in range(0, 4):
            for shared_premise in (False, True):
                for downstream in range(2):
                    constants = _CONSTANTS[: rng.randint(1, 2)]
                    fact_pairs: dict[str, list[tuple[str, ...]]] = {}
                    fact_rows = [(constant,) for constant in constants]
                    premise_style = (
                        "one shared premise" if shared_premise else "distinct premises"
                    )
                    defeasible_specs: list[tuple[str, list[str]]] = []
                    for member in range(pro_team):
                        premise = "shared" if shared_premise else f"pro{member}"
                        fact_pairs[premise] = fact_rows
                        defeasible_specs.append(("goal(X)", [f"{premise}(X)"]))
                    for member in range(con_team):
                        premise = "shared" if shared_premise else f"con{member}"
                        fact_pairs[premise] = fact_rows
                        defeasible_specs.append(("~goal(X)", [f"{premise}(X)"]))
                    for level in range(downstream):
                        source = "goal(X)" if level == 0 else f"next{level}(X)"
                        defeasible_specs.append((f"next{level + 1}(X)", [source]))
                    theory = DefeasibleTheory(
                        facts=_facts(fact_pairs),
                        defeasible_rules=_rules(defeasible_specs, "d"),
                    )
                    shaped.append(
                        ShapedTheory(
                            shape="team",
                            tags=(
                                f"team-{pro_team}v{con_team}",
                                "shared-premise" if shared_premise else "distinct-premises",
                                f"downstream-{downstream}",
                            ),
                            description=(
                                f"{pro_team} defeasible reason(s) for goal versus "
                                f"{con_team} against, drawn from {premise_style}."
                            ),
                            theory=theory,
                        )
                    )
    return shaped


def _mixed_theories(rng: random.Random, count: int) -> list[ShapedTheory]:
    """Seeded random strict/defeasible mixes over a small acyclic vocabulary."""

    shaped: list[ShapedTheory] = []
    for index in range(count):
        constants = _CONSTANTS[: rng.randint(1, 3)]
        base_predicates = [f"b{position}" for position in range(rng.randint(2, 3))]
        derived_predicates = [f"d{position}" for position in range(rng.randint(2, 4))]

        fact_pairs: dict[str, list[tuple[str, ...]]] = {}
        for predicate in base_predicates:
            rows = {
                (rng.choice(constants),)
                for _ in range(rng.randint(1, len(constants)))
            }
            fact_pairs[predicate] = sorted(rows)

        strict_specs: list[tuple[str, list[str]]] = []
        defeasible_specs: list[tuple[str, list[str]]] = []
        rule_count = rng.randint(3, 7)
        strict_heads: set[str] = set()
        for _ in range(rule_count):
            head_index = rng.randrange(len(derived_predicates))
            head_predicate = derived_predicates[head_index]
            negate_head = rng.random() < 0.35
            head_literal = f"~{head_predicate}" if negate_head else head_predicate
            # Bodies draw only from base predicates and strictly earlier
            # derived predicates, which keeps every theory acyclic.
            candidates = base_predicates + derived_predicates[:head_index]
            body_size = rng.randint(1, min(2, len(candidates)))
            body_predicates = rng.sample(candidates, body_size)
            body = [
                f"~{predicate}(X)"
                if predicate.startswith("d") and rng.random() < 0.2
                else f"{predicate}(X)"
                for predicate in body_predicates
            ]
            head = f"{head_literal}(X)"
            if rng.random() < 0.3:
                # Guard the strict layer against deriving both a literal and
                # its complement from the same premises.
                if _negate(head_literal) not in strict_heads:
                    strict_specs.append((head, body))
                    strict_heads.add(head_literal)
            else:
                defeasible_specs.append((head, body))
        if not defeasible_specs:
            defeasible_specs.append(
                (f"{derived_predicates[0]}(X)", [f"{base_predicates[0]}(X)"])
            )

        theory = DefeasibleTheory(
            facts=_facts(fact_pairs),
            strict_rules=_rules(strict_specs, "s"),
            defeasible_rules=_rules(defeasible_specs, "d"),
        )
        shaped.append(
            ShapedTheory(
                shape="mixed",
                tags=(
                    f"strict-rules-{len(strict_specs)}",
                    f"defeasible-rules-{len(defeasible_specs)}",
                ),
                description=(
                    f"Seeded random mix #{index} of {len(strict_specs)} strict and "
                    f"{len(defeasible_specs)} defeasible rule(s) with strong negation "
                    "over an acyclic vocabulary."
                ),
                theory=theory,
            )
        )
    return shaped


def _theory_key(theory: DefeasibleTheory) -> str:
    parts: list[str] = []
    for predicate, rows in sorted(theory.facts.items()):
        parts.append(f"{predicate}={sorted(rows)!r}")
    for label, rules in (("s", theory.strict_rules), ("d", theory.defeasible_rules)):
        for rule in rules:
            parts.append(f"{label}:{rule.head}<-{','.join(rule.body)}")
    return ";".join(parts)


def _strict_layer_is_coherent(sections: CanonicalSections) -> bool:
    definitely = sections.get("definitely", {})
    for predicate, rows in definitely.items():
        complement = definitely.get(_negate(predicate), [])
        if any(row in complement for row in rows):
            return False
    return True


def _evaluate_across_hash_seeds(
    theories: list[DefeasibleTheory],
    work_dir: Path,
) -> list[CanonicalSections | None]:
    """Run every theory through DePYsible once per hash seed.

    Returns one entry per theory: its canonical sections when every run
    succeeded with identical output, otherwise ``None``.
    """

    input_path = work_dir / "theories.json"
    input_path.write_text(
        json.dumps([_theory_to_yaml(theory) for theory in theories]),
        encoding="utf-8",
    )

    runs: list[list[dict[str, Any]]] = []
    for hash_seed in HASH_SEEDS:
        output_path = work_dir / f"results_{hash_seed}.json"
        subprocess.run(
            [sys.executable, str(_BATCH_SCRIPT), str(input_path), str(output_path)],
            env={**os.environ, "PYTHONHASHSEED": hash_seed},
            check=True,
        )
        run_results: list[dict[str, Any]] = json.loads(
            output_path.read_text(encoding="utf-8")
        )
        if len(run_results) != len(theories):
            raise RuntimeError(
                f"hash seed {hash_seed} returned {len(run_results)} results "
                f"for {len(theories)} theories"
            )
        runs.append(run_results)

    combined: list[CanonicalSections | None] = []
    for index in range(len(theories)):
        outcomes = [run[index] for run in runs]
        first = outcomes[0]
        if "error" in first or any(outcome != first for outcome in outcomes[1:]):
            combined.append(None)
            continue
        combined.append(first["sections"])
    return combined


def _theory_to_yaml(theory: DefeasibleTheory) -> dict[str, object]:
    rendered: dict[str, object] = {
        "facts": {
            predicate: [[str(value) for value in row] for row in rows]
            for predicate, rows in sorted(theory.facts.items())
        }
    }
    if theory.strict_rules:
        rendered["strict_rules"] = [
            {"id": rule.id, "head": rule.head, "body": list(rule.body)}
            for rule in theory.strict_rules
        ]
    if theory.defeasible_rules:
        rendered["defeasible_rules"] = [
            {"id": rule.id, "head": rule.head, "body": list(rule.body)}
            for rule in theory.defeasible_rules
        ]
    return rendered


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate the defeasible corpus.")
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    parser.add_argument("--chunk-size", type=int, default=CHUNK_SIZE)
    parser.add_argument(
        "--mixed-count",
        type=int,
        default=620,
        help="Number of seeded random mixed-shape theories to attempt.",
    )
    args = parser.parse_args()

    rng = random.Random(SEED)

    shaped_theories: list[ShapedTheory] = [
        *_chain_theories(rng),
        *_ambiguity_theories(rng),
        *_strict_override_theories(rng),
        *_team_theories(rng),
        *_mixed_theories(rng, args.mixed_count),
    ]

    unique_theories: list[ShapedTheory] = []
    seen_theories: set[str] = set()
    skipped_duplicate = 0
    skipped_blocklisted = 0
    for shaped in shaped_theories:
        key = _theory_key(shaped.theory)
        if key in seen_theories:
            skipped_duplicate += 1
            continue
        seen_theories.add(key)
        if key in KNOWN_UNSTABLE_THEORY_KEYS:
            skipped_blocklisted += 1
            continue
        unique_theories.append(shaped)

    with tempfile.TemporaryDirectory(prefix="defeasible-corpus-") as temp_name:
        section_results = _evaluate_across_hash_seeds(
            [shaped.theory for shaped in unique_theories],
            Path(temp_name),
        )

    cases: list[dict[str, object]] = []
    shape_counters: dict[str, int] = {}
    skipped_unstable = 0
    skipped_incoherent = 0
    skipped_trivial = 0

    for shaped, sections in zip(unique_theories, section_results, strict=True):
        if sections is None:
            skipped_unstable += 1
            continue
        if not _strict_layer_is_coherent(sections):
            skipped_incoherent += 1
            continue
        if not sections.get("defeasibly") and not sections.get("undecided"):
            skipped_trivial += 1
            continue

        index = shape_counters.get(shaped.shape, 0)
        shape_counters[shaped.shape] = index + 1
        cases.append(
            {
                "name": f"defeasible_gen_{shaped.shape}_{index:04d}",
                "description": (
                    f"{shaped.description} Expected sections computed by running "
                    "the DePYsible implementation under the blocking-style policy, "
                    f"stable across {len(HASH_SEEDS)} hash-seed-varied runs."
                ),
                "tags": [f"shape-{shaped.shape}", *shaped.tags],
                "theory": _theory_to_yaml(shaped.theory),
                "expect": sections,
            }
        )

    args.output_dir.mkdir(parents=True, exist_ok=True)
    chunk_count = 0
    for start in range(0, len(cases), args.chunk_size):
        chunk = cases[start : start + args.chunk_size]
        document = {
            "source": SOURCE,
            "tags": BASE_TAGS,
            "verification": VERIFICATION,
            "tests": chunk,
        }
        output_path = args.output_dir / f"defeasible_gen_{chunk_count:02d}.yaml"
        rendered = yaml.safe_dump(document, sort_keys=False, width=100)
        output_path.write_text(
            "# Generated by scripts/generate_defeasible_corpus.py; do not edit by hand.\n"
            + rendered,
            encoding="utf-8",
        )
        print(f"{output_path.as_posix()}: {len(chunk)} cases")
        chunk_count += 1

    print(
        f"cases: {len(cases)} by shape {dict(sorted(shape_counters.items()))}; "
        f"skipped duplicate={skipped_duplicate} blocklisted={skipped_blocklisted} "
        f"unstable={skipped_unstable} "
        f"incoherent={skipped_incoherent} trivial={skipped_trivial}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
