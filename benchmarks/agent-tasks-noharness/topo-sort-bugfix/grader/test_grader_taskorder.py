import pytest

from taskorder import topological_order


def test_two_node_cycle_raises():
    deps = {"a": ["b"], "b": ["a"]}
    with pytest.raises(ValueError):
        topological_order(deps)


def test_self_cycle_raises():
    deps = {"a": ["a"]}
    with pytest.raises(ValueError):
        topological_order(deps)


def test_longer_cycle_raises():
    deps = {"a": ["b"], "b": ["c"], "c": ["a"], "d": []}
    with pytest.raises(ValueError):
        topological_order(deps)


def test_cycle_alongside_acyclic_part_raises():
    deps = {"a": [], "b": ["a"], "x": ["y"], "y": ["x"]}
    with pytest.raises(ValueError):
        topological_order(deps)


def test_alphabetical_tie_break():
    deps = {"z": [], "a": [], "m": []}
    assert topological_order(deps) == ["a", "m", "z"]


def test_dependency_only_in_list_not_key():
    deps = {"b": ["a"]}
    result = topological_order(deps)
    assert result == ["a", "b"]
