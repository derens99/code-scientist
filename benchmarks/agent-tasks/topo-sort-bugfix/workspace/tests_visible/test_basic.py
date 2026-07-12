from taskorder import topological_order


def test_linear_chain():
    deps = {"a": [], "b": ["a"], "c": ["b"]}
    assert topological_order(deps) == ["a", "b", "c"]


def test_diamond():
    deps = {"a": [], "b": ["a"], "c": ["a"], "d": ["b", "c"]}
    result = topological_order(deps)
    assert result[0] == "a"
    assert result[-1] == "d"
    assert set(result) == {"a", "b", "c", "d"}


def test_no_dependencies():
    deps = {"a": [], "b": [], "c": []}
    assert topological_order(deps) == ["a", "b", "c"]
