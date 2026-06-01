"""DAG topology for sub-task decomposition.

A job is decomposed into atomic sub-tasks, at most 2 levels deep (prompt §1).
Pure, deterministic, dependency-free → held at 100% test coverage.
"""

from __future__ import annotations

from collections import deque

MAX_DEPTH = 2

DepGraph = dict[str, list[str]]


class DagError(ValueError):
    """Raised when a sub-task graph is not a valid, shallow-enough DAG."""


def _check_references(graph: DepGraph) -> None:
    for node, deps in graph.items():
        for dep in deps:
            if dep not in graph:
                raise DagError(f"sub-task {node!r} depends on unknown {dep!r}")
            if dep == node:
                raise DagError(f"sub-task {node!r} depends on itself")


def topological_order(graph: DepGraph) -> list[str]:
    """Kahn's algorithm; deterministic (preserves input insertion order on ties).

    Raises DagError on missing references or cycles.
    """
    _check_references(graph)
    indegree: dict[str, int] = {n: 0 for n in graph}
    for deps in graph.values():
        for dep in deps:
            indegree[dep] += 1

    # A node is ready once everything it depends on is emitted: process nodes
    # whose dependencies are all already placed. We invert: roots first.
    dependents: dict[str, list[str]] = {n: [] for n in graph}
    remaining: dict[str, int] = {n: len(deps) for n, deps in graph.items()}
    for node, deps in graph.items():
        for dep in deps:
            dependents[dep].append(node)

    ready = deque(n for n in graph if remaining[n] == 0)
    order: list[str] = []
    while ready:
        node = ready.popleft()
        order.append(node)
        for child in dependents[node]:
            remaining[child] -= 1
            if remaining[child] == 0:
                ready.append(child)

    if len(order) != len(graph):
        cyclic = sorted(n for n, r in remaining.items() if r > 0)
        raise DagError(f"cycle detected among sub-tasks: {cyclic}")
    return order


def depth(graph: DepGraph) -> int:
    """Longest dependency chain measured in nodes (a single node is depth 1)."""
    order = topological_order(graph)
    longest: dict[str, int] = {}
    for node in order:
        deps = graph[node]
        longest[node] = 1 + max((longest[d] for d in deps), default=0)
    return max(longest.values(), default=0)


def validate_dag(graph: DepGraph) -> list[str]:
    """Validate references, acyclicity and depth ≤ MAX_DEPTH; return topo order."""
    if not graph:
        raise DagError("sub-task graph is empty")
    order = topological_order(graph)
    d = depth(graph)
    if d > MAX_DEPTH:
        raise DagError(f"sub-task graph is {d} levels deep (max {MAX_DEPTH})")
    return order
