from intervals import merge_intervals


def test_touching_intervals_merge():
    assert merge_intervals([(1, 3), (3, 5)]) == [(1, 5)]


def test_multiple_touching_chain():
    assert merge_intervals([(1, 2), (2, 3), (3, 4)]) == [(1, 4)]


def test_contained_interval():
    assert merge_intervals([(1, 10), (3, 5)]) == [(1, 10)]


def test_non_overlapping_gap_of_one():
    # (1,3) and (4,6) do not touch (gap of one integer, 3 != 4)
    assert merge_intervals([(1, 3), (4, 6)]) == [(1, 3), (4, 6)]


def test_negative_numbers():
    assert merge_intervals([(-5, -2), (-2, 0)]) == [(-5, 0)]


def test_unsorted_with_touching():
    result = merge_intervals([(10, 12), (1, 3), (3, 8)])
    assert result == [(1, 8), (10, 12)]


def test_single_point_intervals():
    assert merge_intervals([(1, 1), (1, 1), (2, 2)]) == [(1, 1), (2, 2)]


def test_single_point_touching_range():
    assert merge_intervals([(1, 2), (2, 2)]) == [(1, 2)]
