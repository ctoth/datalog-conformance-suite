"""Generate the closed-form family corpus.

Each family instance is one visible program (graph facts plus rules) shared
by many query cases. Expected rows are computed from the structure itself —
combinatorics and plain breadth-first search, never a Datalog engine — and
the emitted corpus is then confirmed against the four external oracles via
``scripts/verify_core_multi_oracle.py`` before it may be committed.

Families:

- ``chain``/``cycle``/``complete``/``star``/``grid``: transitive closure
  dumps plus per-source reachability queries.
- ``tree``: ancestor closure, per-node descendants, same-generation, and
  leaf detection through stratified negation.
- ``parity``: even/odd mutual recursion over successor chains, with
  comparison-guard slices.
- ``altpath``: even-/odd-length path mutual recursion on chains and cycles.
- ``cutchain``: reachable/unreachable split via stratified negation.
- ``diff``: edge-set difference via negation between two graphs.
- ``plus``: head arithmetic over guarded number pairs.
"""

from __future__ import annotations

import argparse
from collections import deque
from pathlib import Path
from typing import Iterable, TypeAlias

import yaml

Scalar: TypeAlias = str | int
Row: TypeAlias = tuple[Scalar, ...]

OUTPUT_DIR = Path("src/datalog_conformance/_tests/generated")
SOURCE = "generated/family-corpus-v1"
VERIFICATION = {"implementation": "nmo+souffle+clingo+swipl", "kind": "direct"}
BASE_TAGS = ["core", "generated", "family", "oracle-tabular"]


def _node(index: int) -> str:
    return f"n{index}"


def _bfs(edges: dict[str, list[str]], start: str) -> set[str]:
    seen: set[str] = set()
    queue: deque[str] = deque([start])
    while queue:
        current = queue.popleft()
        for target in edges.get(current, []):
            if target not in seen:
                seen.add(target)
                queue.append(target)
    return seen


def _adjacency(edge_rows: Iterable[tuple[str, str]]) -> dict[str, list[str]]:
    adjacency: dict[str, list[str]] = {}
    for source, target in edge_rows:
        adjacency.setdefault(source, []).append(target)
    return adjacency


def _closure(edge_rows: list[tuple[str, str]]) -> set[tuple[str, str]]:
    adjacency = _adjacency(edge_rows)
    sources = set(adjacency)
    pairs: set[tuple[str, str]] = set()
    for source in sources:
        for target in _bfs(adjacency, source):
            pairs.add((source, target))
    return pairs


class _InstanceBuilder:
    """One shared program plus its query cases."""

    def __init__(self, family: str, instance: str) -> None:
        self.family = family
        self.instance = instance
        self.facts: dict[str, list[Row]] = {}
        self.rules: list[str] = []
        self.cases: list[dict[str, object]] = []

    def add_case(
        self,
        query: str,
        predicate: str,
        rows: Iterable[Row],
        extra_tags: list[str] | None = None,
    ) -> None:
        self.cases.append(
            {
                "name": f"family_{self.family}_{self.instance}_{query}",
                "description": (
                    f"Closed-form {self.family} family case ({self.instance}); "
                    f"expected rows derived from the structure, confirmed against "
                    f"external engines."
                ),
                "tags": [f"family-{self.family}", *(extra_tags or [])],
                "program": {
                    "facts": {
                        name: [list(row) for row in rows_]
                        for name, rows_ in sorted(self.facts.items())
                    },
                    "rules": list(self.rules),
                },
                "expect": {predicate: sorted([list(row) for row in rows])},
            }
        )


def _path_rules() -> list[str]:
    return [
        "path(X,Y) :- edge(X,Y).",
        "path(X,Z) :- path(X,Y), edge(Y,Z).",
    ]


def _reach_rules(nodes: list[str]) -> list[str]:
    return [f'reach_{node}(Y) :- path("{node}", Y).' for node in nodes]


def _graph_instance(
    family: str,
    instance: str,
    nodes: list[str],
    edge_rows: list[tuple[str, str]],
) -> _InstanceBuilder:
    builder = _InstanceBuilder(family, instance)
    builder.facts["edge"] = [tuple(edge) for edge in edge_rows]
    builder.rules = [*_path_rules(), *_reach_rules(nodes)]
    closure = _closure(edge_rows)
    builder.add_case("path", "path", closure)
    adjacency = _adjacency(edge_rows)
    for node in nodes:
        builder.add_case(
            f"reach_{node}",
            f"reach_{node}",
            {(target,) for target in _bfs(adjacency, node)},
        )
    return builder


def _chain_instances() -> list[_InstanceBuilder]:
    builders: list[_InstanceBuilder] = []
    for size in (2, 3, 4, 6, 8, 12, 16, 24, 32):
        nodes = [_node(index) for index in range(size)]
        edges = [(nodes[index], nodes[index + 1]) for index in range(size - 1)]
        builders.append(_graph_instance("chain", f"{size:02d}", nodes, edges))
    return builders


def _cycle_instances() -> list[_InstanceBuilder]:
    builders: list[_InstanceBuilder] = []
    for size in (3, 4, 6, 8, 12, 16, 20):
        nodes = [_node(index) for index in range(size)]
        edges = [(nodes[index], nodes[(index + 1) % size]) for index in range(size)]
        builders.append(_graph_instance("cycle", f"{size:02d}", nodes, edges))
    return builders


def _complete_instances() -> list[_InstanceBuilder]:
    builders: list[_InstanceBuilder] = []
    for size in (2, 3, 4, 5, 6):
        nodes = [_node(index) for index in range(size)]
        edges = [
            (left, right) for left in nodes for right in nodes if left != right
        ]
        builders.append(_graph_instance("complete", f"{size:02d}", nodes, edges))
    return builders


def _star_instances() -> list[_InstanceBuilder]:
    builders: list[_InstanceBuilder] = []
    for leaves in (1, 2, 4, 8, 16):
        nodes = ["hub", *(_node(index) for index in range(leaves))]
        edges = [("hub", _node(index)) for index in range(leaves)]
        builders.append(_graph_instance("star", f"{leaves:02d}", nodes, edges))
    return builders


def _grid_instances() -> list[_InstanceBuilder]:
    builders: list[_InstanceBuilder] = []
    for width, height in ((2, 2), (3, 2), (3, 3), (4, 3), (4, 4), (5, 4)):
        def cell(x: int, y: int) -> str:
            return f"c{x}_{y}"

        nodes = [cell(x, y) for x in range(width) for y in range(height)]
        edges: list[tuple[str, str]] = []
        for x in range(width):
            for y in range(height):
                if x + 1 < width:
                    edges.append((cell(x, y), cell(x + 1, y)))
                if y + 1 < height:
                    edges.append((cell(x, y), cell(x, y + 1)))
        builders.append(
            _graph_instance("grid", f"{width}x{height}", nodes, edges)
        )
    return builders


def _tree_instances() -> list[_InstanceBuilder]:
    builders: list[_InstanceBuilder] = []
    for depth in (1, 2, 3, 4, 5):
        total = 2 ** (depth + 1) - 1
        nodes = [_node(value) for value in range(1, total + 1)]
        parent_rows = [
            (_node(child // 2), _node(child)) for child in range(2, total + 1)
        ]
        builder = _InstanceBuilder("tree", f"d{depth}")
        builder.facts["node"] = [(node,) for node in nodes]
        builder.facts["parent"] = [tuple(row) for row in parent_rows]
        builder.rules = [
            "anc(X,Y) :- parent(X,Y).",
            "anc(X,Z) :- anc(X,Y), parent(Y,Z).",
            "sg(X,X) :- node(X).",
            "sg(X,Y) :- parent(XP,X), parent(YP,Y), sg(XP,YP).",
            "haschild(X) :- parent(X, _).",
            "leaf(X) :- node(X), not haschild(X).",
        ]
        for value in range(1, total + 1):
            builder.rules.append(
                f'desc_{_node(value)}(Y) :- anc("{_node(value)}", Y).'
            )

        ancestors: set[tuple[str, str]] = set()
        for child in range(2, total + 1):
            walker = child // 2
            while walker >= 1:
                ancestors.add((_node(walker), _node(child)))
                walker //= 2
        builder.add_case("anc", "anc", ancestors)

        def depth_of(value: int) -> int:
            return value.bit_length() - 1

        same_generation = {
            (_node(left), _node(right))
            for left in range(1, total + 1)
            for right in range(1, total + 1)
            if depth_of(left) == depth_of(right)
        }
        builder.add_case("sg", "sg", same_generation)

        leaves = {
            (_node(value),)
            for value in range(1, total + 1)
            if 2 * value > total
        }
        builder.add_case("leaf", "leaf", leaves, extra_tags=["negation"])

        for value in range(1, total + 1):
            descendants = {
                (_node(other),)
                for other in range(1, total + 1)
                if other != value and (_node(value), _node(other)) in ancestors
            }
            builder.add_case(
                f"desc_{_node(value)}", f"desc_{_node(value)}", descendants
            )
        builders.append(builder)
    return builders


def _parity_instances() -> list[_InstanceBuilder]:
    builders: list[_InstanceBuilder] = []
    for size in (1, 2, 3, 5, 9, 16, 24, 32):
        builder = _InstanceBuilder("parity", f"{size:02d}")
        builder.facts["succ"] = [(index, index + 1) for index in range(size)]
        builder.facts["zero"] = [(0,)]
        builder.rules = [
            "even(X) :- zero(X).",
            "odd(Y) :- succ(X,Y), even(X).",
            "even(Y) :- succ(X,Y), odd(X).",
            f"even_small(X) :- even(X), (X <= {size // 2}).",
            f"odd_small(X) :- odd(X), (X <= {size // 2}).",
        ]
        evens = {(value,) for value in range(size + 1) if value % 2 == 0}
        odds = {(value,) for value in range(size + 1) if value % 2 == 1}
        builder.add_case("even", "even", evens)
        builder.add_case("odd", "odd", odds)
        builder.add_case(
            "even_small",
            "even_small",
            {row for row in evens if int(row[0]) <= size // 2},
            extra_tags=["guard"],
        )
        builder.add_case(
            "odd_small",
            "odd_small",
            {row for row in odds if int(row[0]) <= size // 2},
            extra_tags=["guard"],
        )
        builders.append(builder)
    return builders


def _altpath_instances() -> list[_InstanceBuilder]:
    builders: list[_InstanceBuilder] = []
    shapes: list[tuple[str, int]] = [
        ("chain", 2),
        ("chain", 4),
        ("chain", 8),
        ("chain", 16),
        ("cycle", 3),
        ("cycle", 4),
        ("cycle", 6),
        ("cycle", 8),
    ]
    for shape, size in shapes:
        nodes = [_node(index) for index in range(size)]
        if shape == "chain":
            edges = [(nodes[index], nodes[index + 1]) for index in range(size - 1)]
        else:
            edges = [(nodes[index], nodes[(index + 1) % size]) for index in range(size)]
        builder = _InstanceBuilder("altpath", f"{shape}{size:02d}")
        builder.facts["edge"] = [tuple(edge) for edge in edges]
        builder.rules = [
            "odd_path(X,Y) :- edge(X,Y).",
            "odd_path(X,Z) :- even_path(X,Y), edge(Y,Z).",
            "even_path(X,Z) :- odd_path(X,Y), edge(Y,Z).",
        ]
        odd_pairs, even_pairs = _walk_parities(nodes, edges)
        builder.add_case("odd_path", "odd_path", odd_pairs)
        builder.add_case("even_path", "even_path", even_pairs)
        builders.append(builder)
    return builders


def _walk_parities(
    nodes: list[str],
    edges: list[tuple[str, str]],
) -> tuple[set[tuple[str, str]], set[tuple[str, str]]]:
    # Reachability over the parity-annotated product graph; walks of length
    # >= 1 with odd/even length respectively.
    adjacency = _adjacency(edges)
    odd_pairs: set[tuple[str, str]] = set()
    even_pairs: set[tuple[str, str]] = set()
    for start in nodes:
        seen: set[tuple[str, int]] = set()
        queue: deque[tuple[str, int]] = deque()
        for target in adjacency.get(start, []):
            state = (target, 1)
            if state not in seen:
                seen.add(state)
                queue.append(state)
        while queue:
            current, parity = queue.popleft()
            if parity == 1:
                odd_pairs.add((start, current))
            else:
                even_pairs.add((start, current))
            for target in adjacency.get(current, []):
                state = (target, 1 - parity)
                if state not in seen:
                    seen.add(state)
                    queue.append(state)
    return odd_pairs, even_pairs


def _cutchain_instances() -> list[_InstanceBuilder]:
    builders: list[_InstanceBuilder] = []
    for size, cut in (
        (6, 0),
        (6, 2),
        (6, 4),
        (10, 0),
        (10, 4),
        (10, 8),
        (14, 0),
        (14, 6),
        (14, 12),
    ):
        nodes = [_node(index) for index in range(size)]
        edges = [
            (nodes[index], nodes[index + 1])
            for index in range(size - 1)
            if index != cut
        ]
        builder = _InstanceBuilder("cutchain", f"{size:02d}c{cut:02d}")
        builder.facts["node"] = [(node,) for node in nodes]
        builder.facts["edge"] = [tuple(edge) for edge in edges]
        builder.facts["root"] = [(nodes[0],)]
        builder.rules = [
            "reach(X) :- root(X).",
            "reach(Y) :- reach(X), edge(X,Y).",
            "unreached(X) :- node(X), not reach(X).",
        ]
        reached = {(nodes[index],) for index in range(cut + 1)}
        unreached = {(nodes[index],) for index in range(cut + 1, size)}
        builder.add_case("reach", "reach", reached)
        builder.add_case("unreached", "unreached", unreached, extra_tags=["negation"])
        builders.append(builder)
    return builders


def _diff_instances() -> list[_InstanceBuilder]:
    builders: list[_InstanceBuilder] = []
    for size, keep_every in ((4, 2), (8, 2), (8, 3), (12, 2), (12, 3), (12, 4)):
        nodes = [_node(index) for index in range(size)]
        full = [(nodes[index], nodes[index + 1]) for index in range(size - 1)]
        sparse = [
            edge for index, edge in enumerate(full) if index % keep_every == 0
        ]
        builder = _InstanceBuilder("diff", f"{size:02d}k{keep_every}")
        builder.facts["edge_full"] = [tuple(edge) for edge in full]
        builder.facts["edge_sparse"] = [tuple(edge) for edge in sparse]
        builder.rules = [
            "only_full(X,Y) :- edge_full(X,Y), not edge_sparse(X,Y).",
            "shared(X,Y) :- edge_full(X,Y), edge_sparse(X,Y).",
        ]
        sparse_set = set(sparse)
        builder.add_case(
            "only_full",
            "only_full",
            {edge for edge in full if edge not in sparse_set},
            extra_tags=["negation"],
        )
        builder.add_case("shared", "shared", sparse_set)
        builders.append(builder)
    return builders


def _plus_instances() -> list[_InstanceBuilder]:
    builders: list[_InstanceBuilder] = []
    for size in (4, 8, 12):
        builder = _InstanceBuilder("plus", f"{size:02d}")
        builder.facts["pair"] = [
            (left, right)
            for left in range(size)
            for right in range(size)
            if left <= right
        ]
        builder.rules = [
            "total(A, B, A+B) :- pair(A, B).",
            f"capped(A, B) :- pair(A, B), (A + B <= {size}).",
        ]
        builder.add_case(
            "total",
            "total",
            {
                (left, right, left + right)
                for left in range(size)
                for right in range(size)
                if left <= right
            },
            extra_tags=["arithmetic"],
        )
        builder.add_case(
            "capped",
            "capped",
            {
                (left, right)
                for left in range(size)
                for right in range(size)
                if left <= right and left + right <= size
            },
            extra_tags=["arithmetic", "guard"],
        )
        builders.append(builder)
    return builders


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate the family corpus.")
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    args = parser.parse_args()

    family_builders: dict[str, list[_InstanceBuilder]] = {}
    for builders in (
        _chain_instances(),
        _cycle_instances(),
        _complete_instances(),
        _star_instances(),
        _grid_instances(),
        _tree_instances(),
        _parity_instances(),
        _altpath_instances(),
        _cutchain_instances(),
        _diff_instances(),
        _plus_instances(),
    ):
        for builder in builders:
            family_builders.setdefault(builder.family, []).append(builder)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    total = 0
    for family, builders in sorted(family_builders.items()):
        cases: list[dict[str, object]] = []
        for builder in builders:
            cases.extend(builder.cases)
        document = {
            "source": SOURCE,
            "tags": BASE_TAGS,
            "verification": VERIFICATION,
            "tests": cases,
        }
        output_path = args.output_dir / f"family_{family}.yaml"
        rendered = yaml.safe_dump(document, sort_keys=False, width=100)
        output_path.write_text(
            "# Generated by scripts/generate_family_corpus.py; do not edit by hand.\n"
            + rendered,
            encoding="utf-8",
        )
        total += len(cases)
        print(f"{output_path.as_posix()}: {len(cases)} cases")
    print(f"total: {total} cases")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
