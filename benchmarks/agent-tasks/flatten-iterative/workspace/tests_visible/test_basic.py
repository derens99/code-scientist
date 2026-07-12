from flatten import flatten_nested


def test_flat_list():
    assert flatten_nested([1, 2, 3]) == [1, 2, 3]


def test_nested_list():
    assert flatten_nested([1, [2, [3, 4], 5], 6]) == [1, 2, 3, 4, 5, 6]


def test_empty_list():
    assert flatten_nested([]) == []


def test_non_list_items_preserved():
    assert flatten_nested(["a", [1, None], (2, 3)]) == ["a", 1, None, (2, 3)]
