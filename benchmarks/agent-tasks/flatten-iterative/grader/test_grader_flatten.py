import sys

from flatten import flatten_nested


def test_deeply_nested_does_not_raise_recursion_error():
    depth = 5000
    nested = []
    current = nested
    for _ in range(depth - 1):
        inner = []
        current.append(inner)
        current = inner
    current.append("leaf")

    result = flatten_nested(nested)
    assert result == ["leaf"]


def test_deeply_nested_exceeds_default_recursion_limit():
    # Build nesting deeper than the default recursion limit to prove a
    # genuinely iterative implementation is used.
    depth = sys.getrecursionlimit() + 2000
    nested = []
    current = nested
    for _ in range(depth - 1):
        inner = []
        current.append(inner)
        current = inner
    current.append(42)

    result = flatten_nested(nested)
    assert result == [42]


def test_wide_and_deep_mixed():
    nested = [1, [2, 3, [4, [5, 6], 7]], 8, [[9]]]
    assert flatten_nested(nested) == [1, 2, 3, 4, 5, 6, 7, 8, 9]


def test_still_preserves_non_list_types():
    assert flatten_nested([{"a": 1}, [(1, 2), "x"]]) == [{"a": 1}, (1, 2), "x"]


def test_empty_nested_lists():
    assert flatten_nested([[], [[]], [[[]]]]) == []
