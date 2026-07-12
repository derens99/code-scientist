from intervals import merge_intervals


def test_empty():
    assert merge_intervals([]) == []


def test_single():
    assert merge_intervals([(1, 5)]) == [(1, 5)]


def test_overlapping():
    assert merge_intervals([(1, 5), (3, 7)]) == [(1, 7)]


def test_unsorted_input():
    assert merge_intervals([(8, 10), (1, 3)]) == [(1, 3), (8, 10)]
