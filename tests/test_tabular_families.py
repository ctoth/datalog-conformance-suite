"""Tabular algorithmic families with closed-form expected models.

Each family builds a graph with known structure (chain, cycle, complete,
star, binary tree, grid) and asserts the full derived relation against an
expectation computed from the structure itself — combinatorics, not another
Datalog engine. The same families run through the packaged reference
evaluator and, when a binary is available, through the Nemo oracle, giving a
three-way agreement check: formula vs reference vs real implementation.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from datalog_conformance.oracles import NemoOracle, find_nmo
from datalog_conformance.references import CoreReferenceEvaluator
from datalog_conformance.schema import FactTuple, Program

_TC_RULES = [
    "path(X,Y) :- edge(X,Y).",
    "path(X,Z) :- path(X,Y), edge(Y,Z).",
]


@dataclass(frozen=True, slots=True)
class ClosureFamily:
    """A graph instance whose transitive closure has a closed-form answer."""

    name: str
    edges: tuple[tuple[str, str], ...]
    expected_paths: frozenset[tuple[str, str]]
    expected_count: int


def _node(index: int) -> str:
    return f"n{index}"


def _chain(size: int) -> ClosureFamily:
    edges = tuple((_node(i), _node(i + 1)) for i in range(size - 1))
    paths = frozenset(
        (_node(i), _node(j)) for i in range(size) for j in range(size) if i < j
    )
    return ClosureFamily(
        name=f"chain_{size}",
        edges=edges,
        expected_paths=paths,
        expected_count=size * (size - 1) // 2,
    )


def _cycle(size: int) -> ClosureFamily:
    edges = tuple((_node(i), _node((i + 1) % size)) for i in range(size))
    paths = frozenset((_node(i), _node(j)) for i in range(size) for j in range(size))
    return ClosureFamily(
        name=f"cycle_{size}",
        edges=edges,
        expected_paths=paths,
        expected_count=size * size,
    )


def _complete(size: int) -> ClosureFamily:
    edges = tuple(
        (_node(i), _node(j)) for i in range(size) for j in range(size) if i != j
    )
    # With size >= 2 every ordered pair (including loops through a detour)
    # is reachable.
    paths = frozenset((_node(i), _node(j)) for i in range(size) for j in range(size))
    return ClosureFamily(
        name=f"complete_{size}",
        edges=edges,
        expected_paths=paths,
        expected_count=size * size,
    )


def _star(leaves: int) -> ClosureFamily:
    center = "hub"
    edges = tuple((center, _node(i)) for i in range(leaves))
    paths = frozenset((center, _node(i)) for i in range(leaves))
    return ClosureFamily(
        name=f"star_{leaves}",
        edges=edges,
        expected_paths=paths,
        expected_count=leaves,
    )


def _binary_tree(depth: int) -> ClosureFamily:
    # Heap-numbered complete binary tree; edges parent -> child.
    total = 2 ** (depth + 1) - 1
    edges: list[tuple[str, str]] = []
    for parent in range(1, total + 1):
        for child in (2 * parent, 2 * parent + 1):
            if child <= total:
                edges.append((_node(parent), _node(child)))
    paths: set[tuple[str, str]] = set()
    for descendant in range(2, total + 1):
        ancestor = descendant // 2
        while ancestor >= 1:
            paths.add((_node(ancestor), _node(descendant)))
            ancestor //= 2
    # Each node at heap index v has exactly floor(log2(v)) ancestors.
    expected_count = sum(v.bit_length() - 1 for v in range(1, total + 1))
    return ClosureFamily(
        name=f"binary_tree_depth_{depth}",
        edges=tuple(edges),
        expected_paths=frozenset(paths),
        expected_count=expected_count,
    )


def _grid(width: int, height: int) -> ClosureFamily:
    # Right/down lattice: reachability is the coordinate dominance order.
    def cell(x: int, y: int) -> str:
        return f"c{x}_{y}"

    edges: list[tuple[str, str]] = []
    for x in range(width):
        for y in range(height):
            if x + 1 < width:
                edges.append((cell(x, y), cell(x + 1, y)))
            if y + 1 < height:
                edges.append((cell(x, y), cell(x, y + 1)))
    paths: set[tuple[str, str]] = set()
    count = 0
    for x1 in range(width):
        for y1 in range(height):
            for x2 in range(width):
                for y2 in range(height):
                    if (x2, y2) != (x1, y1) and x2 >= x1 and y2 >= y1:
                        paths.add((cell(x1, y1), cell(x2, y2)))
                        count += 1
    return ClosureFamily(
        name=f"grid_{width}x{height}",
        edges=tuple(edges),
        expected_paths=frozenset(paths),
        expected_count=count,
    )


_CLOSURE_FAMILIES = [
    _chain(2),
    _chain(5),
    _chain(17),
    _cycle(3),
    _cycle(8),
    _complete(4),
    _complete(6),
    _star(6),
    _binary_tree(3),
    _binary_tree(4),
    _grid(3, 3),
    _grid(4, 3),
]


def _closure_program(family: ClosureFamily) -> Program:
    return Program(
        facts={"edge": [tuple(edge) for edge in family.edges]},
        rules=list(_TC_RULES),
    )


@pytest.mark.parametrize(
    "family", _CLOSURE_FAMILIES, ids=[family.name for family in _CLOSURE_FAMILIES]
)
def test_reference_transitive_closure_matches_closed_form(
    family: ClosureFamily,
) -> None:
    model = CoreReferenceEvaluator().evaluate(_closure_program(family))
    actual = model.facts.get("path", set())
    assert actual == family.expected_paths
    assert len(actual) == family.expected_count


@pytest.mark.skipif(find_nmo() is None, reason="no local nmo binary")
@pytest.mark.parametrize(
    "family", _CLOSURE_FAMILIES, ids=[family.name for family in _CLOSURE_FAMILIES]
)
def test_nemo_transitive_closure_matches_closed_form(family: ClosureFamily) -> None:
    model = NemoOracle().evaluate(_closure_program(family))
    actual = model.facts.get("path", set())
    assert actual == family.expected_paths
    assert len(actual) == family.expected_count


def _parity_program(size: int) -> Program:
    facts: dict[str, list[FactTuple]] = {
        "succ": [(i, i + 1) for i in range(size)],
        "zero": [(0,)],
    }
    rules = [
        "even(X) :- zero(X).",
        "odd(Y) :- succ(X,Y), even(X).",
        "even(Y) :- succ(X,Y), odd(X).",
    ]
    return Program(facts=facts, rules=rules)


@pytest.mark.parametrize("size", [1, 2, 9, 24])
def test_reference_mutual_recursion_matches_parity(size: int) -> None:
    model = CoreReferenceEvaluator().evaluate(_parity_program(size))
    assert model.facts.get("even", set()) == {(i,) for i in range(size + 1) if i % 2 == 0}
    assert model.facts.get("odd", set()) == {(i,) for i in range(size + 1) if i % 2 == 1}


@pytest.mark.skipif(find_nmo() is None, reason="no local nmo binary")
@pytest.mark.parametrize("size", [9, 24])
def test_nemo_mutual_recursion_matches_parity(size: int) -> None:
    model = NemoOracle().evaluate(_parity_program(size))
    assert model.facts.get("even", set()) == {(i,) for i in range(size + 1) if i % 2 == 0}
    assert model.facts.get("odd", set()) == {(i,) for i in range(size + 1) if i % 2 == 1}


def _same_generation_program(depth: int) -> Program:
    total = 2 ** (depth + 1) - 1
    parent_rows: list[FactTuple] = []
    for child in range(2, total + 1):
        parent_rows.append((_node(child // 2), _node(child)))
    node_rows: list[FactTuple] = [(_node(v),) for v in range(1, total + 1)]
    rules = [
        "sg(X,X) :- node(X).",
        "sg(X,Y) :- parent(XP,X), parent(YP,Y), sg(XP,YP).",
    ]
    return Program(facts={"node": node_rows, "parent": parent_rows}, rules=rules)


def _same_generation_expected(depth: int) -> set[tuple[str, str]]:
    pairs: set[tuple[str, str]] = set()
    for level in range(depth + 1):
        level_nodes = [_node(v) for v in range(2**level, 2 ** (level + 1))]
        for left in level_nodes:
            for right in level_nodes:
                pairs.add((left, right))
    return pairs


@pytest.mark.parametrize("depth", [0, 1, 3])
def test_reference_same_generation_matches_levels(depth: int) -> None:
    model = CoreReferenceEvaluator().evaluate(_same_generation_program(depth))
    assert model.facts.get("sg", set()) == _same_generation_expected(depth)


@pytest.mark.skipif(find_nmo() is None, reason="no local nmo binary")
@pytest.mark.parametrize("depth", [3])
def test_nemo_same_generation_matches_levels(depth: int) -> None:
    model = NemoOracle().evaluate(_same_generation_program(depth))
    assert model.facts.get("sg", set()) == _same_generation_expected(depth)


def _unreachable_program(size: int, cut: int) -> Program:
    # Chain with the edge after `cut` removed; nodes beyond stay unreachable.
    edges = [
        (_node(i), _node(i + 1))
        for i in range(size - 1)
        if i != cut
    ]
    nodes: list[FactTuple] = [(_node(i),) for i in range(size)]
    rules = [
        "reach(X) :- root(X).",
        "reach(Y) :- reach(X), edge(X,Y).",
        "unreached(X) :- node(X), not reach(X).",
    ]
    return Program(
        facts={
            "node": nodes,
            "edge": [tuple(edge) for edge in edges],
            "root": [(_node(0),)],
        },
        rules=rules,
    )


@pytest.mark.parametrize(("size", "cut"), [(6, 2), (10, 0), (10, 8)])
def test_reference_negation_finds_unreachable_suffix(size: int, cut: int) -> None:
    model = CoreReferenceEvaluator().evaluate(_unreachable_program(size, cut))
    expected = {(_node(i),) for i in range(cut + 1, size)}
    assert model.facts.get("unreached", set()) == expected


@pytest.mark.skipif(find_nmo() is None, reason="no local nmo binary")
@pytest.mark.parametrize(("size", "cut"), [(6, 2), (10, 8)])
def test_nemo_negation_finds_unreachable_suffix(size: int, cut: int) -> None:
    model = NemoOracle().evaluate(_unreachable_program(size, cut))
    expected = {(_node(i),) for i in range(cut + 1, size)}
    assert model.facts.get("unreached", set()) == expected
