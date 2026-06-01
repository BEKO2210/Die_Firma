import pytest

from die_firma.dag import DagError, depth, topological_order, validate_dag


def test_topo_order_chain_and_parallel():
    chain = {"a": [], "b": ["a"], "c": ["b"]}
    assert topological_order(chain) == ["a", "b", "c"]
    diamond = {"a": [], "b": ["a"], "c": ["a"], "d": ["b", "c"]}
    order = topological_order(diamond)
    assert order.index("a") == 0
    assert order.index("d") == 3
    assert order.index("b") < order.index("d")


def test_topo_deterministic_on_ties():
    graph = {"x": [], "y": [], "z": []}
    assert topological_order(graph) == ["x", "y", "z"]


def test_unknown_and_self_dependency():
    with pytest.raises(DagError, match="unknown"):
        topological_order({"a": ["missing"]})
    with pytest.raises(DagError, match="itself"):
        topological_order({"a": ["a"]})


def test_cycle_detected():
    with pytest.raises(DagError, match="cycle"):
        topological_order({"a": ["b"], "b": ["a"]})


def test_depth():
    assert depth({"a": []}) == 1
    assert depth({"a": [], "b": ["a"]}) == 2
    assert depth({"a": [], "b": ["a"], "c": ["b"]}) == 3
    assert depth({}) == 0


def test_validate_dag():
    assert validate_dag({"a": [], "b": ["a"]}) == ["a", "b"]
    with pytest.raises(DagError, match="empty"):
        validate_dag({})
    with pytest.raises(DagError, match="levels deep"):
        validate_dag({"a": [], "b": ["a"], "c": ["b"]})
