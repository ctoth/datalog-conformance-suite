"""Generate the feature-matrix corpus.

Enumerates the full cross product of semantic features — recursion shape
(none, linear, nonlinear, mutual), negation depth (0, 1, 2 strata),
comparison guards, head arithmetic, wildcards, constant filters, and
self-joins — and builds one deterministic program per feature bundle over
seeded pseudo-random base relations. These are the corners where engines
historically disagree.

Expected rows are computed by running each program through the local Nemo
build (an external implementation, not code in this repo), and the corpus
must then be cross-verified against Souffle, clingo, and SWI-Prolog via
``scripts/verify_core_multi_oracle.py`` before it may be committed.

Columns are kept single-typed (strings or ints, never mixed) so every
integrated engine can express every case.
"""

from __future__ import annotations

import argparse
import random
from dataclasses import dataclass
from itertools import product
from pathlib import Path
from typing import TypeAlias

import yaml

from datalog_conformance.oracles import NemoOracle
from datalog_conformance.schema import FactTuple, Program

Row: TypeAlias = FactTuple

OUTPUT_DIR = Path("src/datalog_conformance/_tests/generated")
SOURCE = "generated/feature-corpus-v1"
VERIFICATION = {"implementation": "nmo+souffle+clingo+swipl", "kind": "direct"}
BASE_TAGS = ["core", "generated", "feature-matrix", "oracle-tabular"]
SEED = 20260709
MAX_ROWS_PER_PREDICATE = 350
COLORS = ("red", "green", "blue")

RECURSION_SHAPES = ("none", "linear", "nonlinear", "mutual")
NEGATION_DEPTHS = (0, 1, 2)
FLAGS = (False, True)


@dataclass(frozen=True, slots=True)
class FeatureBundle:
    recursion: str
    negation: int
    guard: bool
    arithmetic: bool
    wildcard: bool
    constant_filter: bool
    self_join: bool

    def tags(self) -> list[str]:
        tags = [f"rec-{self.recursion}", f"neg-{self.negation}"]
        if self.guard:
            tags.append("guard")
        if self.arithmetic:
            tags.append("arithmetic")
        if self.wildcard:
            tags.append("wildcard")
        if self.constant_filter:
            tags.append("const-filter")
        if self.self_join:
            tags.append("self-join")
        return tags


def _bundles() -> list[FeatureBundle]:
    bundles: list[FeatureBundle] = []
    for recursion, negation, guard, arithmetic, wildcard, constant, self_join in product(
        RECURSION_SHAPES, NEGATION_DEPTHS, FLAGS, FLAGS, FLAGS, FLAGS, FLAGS
    ):
        bundles.append(
            FeatureBundle(
                recursion=recursion,
                negation=negation,
                guard=guard,
                arithmetic=arithmetic,
                wildcard=wildcard,
                constant_filter=constant,
                self_join=self_join,
            )
        )
    return bundles


def _build_program(
    bundle: FeatureBundle,
    rng: random.Random,
) -> tuple[Program, list[str]]:
    """Build the program for a bundle plus the list of query predicates."""

    node_count = rng.randint(4, 8)
    nodes = [f"v{index}" for index in range(node_count)]
    edge_rows: set[tuple[str, str]] = set()
    edge_count = rng.randint(node_count, node_count + 6)
    while len(edge_rows) < edge_count:
        source = rng.choice(nodes)
        target = rng.choice(nodes)
        if source != target:
            edge_rows.add((source, target))
    mark_rows = {(node,) for node in nodes if rng.random() < 0.45}
    if not mark_rows:
        mark_rows = {(nodes[0],)}
    color_rows = {(node, rng.choice(COLORS)) for node in nodes}
    num_rows = {
        (rng.randint(0, 9), rng.randint(0, 9))
        for _ in range(rng.randint(4, 9))
    }

    facts: dict[str, list[Row]] = {
        "edge": sorted(edge_rows),
        "mark": sorted(mark_rows),
        "color": sorted(color_rows),
        "nums": sorted(num_rows),
    }

    wild = "_" if bundle.wildcard else "W"
    rules: list[str] = [
        f"node(X) :- edge(X, {wild}).",
        f"node(Y) :- edge({wild}, Y).",
        "hop2(X, Z) :- edge(X, Y), edge(Y, Z).",
    ]
    queries: list[str] = ["node", "hop2"]

    if bundle.self_join:
        rules.append("same_color(X, Y) :- color(X, C), color(Y, C).")
        queries.append("same_color")

    if bundle.recursion == "linear":
        rules.append("tc(X, Y) :- edge(X, Y).")
        rules.append("tc(X, Z) :- tc(X, Y), edge(Y, Z).")
        queries.append("tc")
    elif bundle.recursion == "nonlinear":
        rules.append("tc(X, Y) :- edge(X, Y).")
        rules.append("tc(X, Z) :- tc(X, Y), tc(Y, Z).")
        queries.append("tc")
    elif bundle.recursion == "mutual":
        rules.append("odd_walk(X, Y) :- edge(X, Y).")
        rules.append("odd_walk(X, Z) :- even_walk(X, Y), edge(Y, Z).")
        rules.append("even_walk(X, Z) :- odd_walk(X, Y), edge(Y, Z).")
        queries.extend(["odd_walk", "even_walk"])

    reachable_pair = "tc" if bundle.recursion in {"linear", "nonlinear"} else "hop2"

    if bundle.negation >= 1:
        rules.append("unmarked(X) :- node(X), not mark(X).")
        queries.append("unmarked")
    if bundle.negation >= 2:
        rules.append(
            f"far(X, Y) :- {reachable_pair}(X, Y), not hop2(X, Y)."
        )
        rules.append("lonely(X) :- node(X), not covered(X).")
        rules.append(f"covered(X) :- {reachable_pair}(X, {wild if bundle.wildcard else 'Z'}).")
        queries.extend(["far", "lonely", "covered"])

    if bundle.guard:
        rules.append("low(A, B) :- nums(A, B), (A < B).")
        queries.append("low")
    if bundle.arithmetic:
        rules.append("sums(A, B, A+B) :- nums(A, B).")
        queries.append("sums")
    if bundle.guard and bundle.arithmetic:
        rules.append("bounded(A, B) :- nums(A, B), (A + B <= 9).")
        queries.append("bounded")

    if bundle.constant_filter:
        rules.append('reds(X) :- color(X, "red").')
        queries.append("reds")
        if bundle.negation >= 1:
            rules.append('nonred(X) :- node(X), not color(X, "red").')
            queries.append("nonred")

    # Projections and a cross-derived join widen the query surface.
    rules.append(f"src(X) :- edge(X, {wild}).")
    rules.append("linked_mark(X, Y) :- hop2(X, Y), mark(X).")
    queries.extend(["src", "linked_mark"])
    if bundle.self_join and bundle.recursion in {"linear", "nonlinear"}:
        rules.append("kin(X, Y) :- tc(X, Y), same_color(X, Y).")
        queries.append("kin")

    return Program(facts=facts, rules=rules), queries


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate the feature corpus.")
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    parser.add_argument("--chunk-size", type=int, default=100)
    parser.add_argument(
        "--variants",
        type=int,
        default=2,
        help="Deterministic base-relation variants per feature bundle.",
    )
    args = parser.parse_args()

    oracle = NemoOracle()
    rng = random.Random(SEED)
    bundles = _bundles()
    cases: list[dict[str, object]] = []
    programs = 0
    skipped = 0

    for variant in range(args.variants):
        for bundle_index, bundle in enumerate(bundles):
            program, queries = _build_program(bundle, rng)
            model = oracle.evaluate(program)
            if any(
                len(rows) > MAX_ROWS_PER_PREDICATE for rows in model.facts.values()
            ):
                skipped += 1
                continue
            non_empty = sum(1 for query in queries if model.facts.get(query))
            if non_empty < max(2, len(queries) // 2):
                skipped += 1
                continue
            programs += 1
            program_yaml = {
                "facts": {
                    name: [list(row) for row in rows]
                    for name, rows in sorted(program.facts.items())
                },
                "rules": list(program.rules),
            }
            identifier = f"{variant}{bundle_index:03d}"
            for query in queries:
                rows = sorted(
                    [list(row) for row in model.facts.get(query, set())]
                )
                cases.append(
                    {
                        "name": f"feature_{identifier}_{query}",
                        "description": (
                            "Feature-matrix case "
                            f"({', '.join(bundle.tags())}); expected rows "
                            "computed by the Nemo implementation and "
                            "cross-verified against Souffle, clingo, and "
                            "SWI-Prolog."
                        ),
                        "tags": [*bundle.tags(), "empty-result"]
                        if not rows
                        else list(bundle.tags()),
                        "program": program_yaml,
                        "expect": {query: rows},
                    }
                )

    args.output_dir.mkdir(parents=True, exist_ok=True)
    chunk_count = 0
    for start in range(0, len(cases), args.chunk_size * 20):
        chunk = cases[start : start + args.chunk_size * 20]
        document = {
            "source": SOURCE,
            "tags": BASE_TAGS,
            "verification": VERIFICATION,
            "tests": chunk,
        }
        output_path = args.output_dir / f"feature_{chunk_count:02d}.yaml"
        rendered = yaml.safe_dump(document, sort_keys=False, width=100)
        output_path.write_text(
            "# Generated by scripts/generate_feature_corpus.py; do not edit by hand.\n"
            + rendered,
            encoding="utf-8",
        )
        print(f"{output_path.as_posix()}: {len(chunk)} cases")
        chunk_count += 1

    print(
        f"programs: {programs} (skipped {skipped}); total cases: {len(cases)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
