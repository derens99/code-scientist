import pytest

from intervals import merge_intervals


def test_req_01_malformed_pair_raises():
    with pytest.raises(ValueError):
        merge_intervals([(1, 2, 3)])


def test_req_02_non_int_raises_typeerror():
    with pytest.raises(TypeError):
        merge_intervals([(1.0, 2)])


def test_req_03_negative_span_raises():
    with pytest.raises(ValueError):
        merge_intervals([(5, 2)])


def test_req_04_zero_length_dropped():
    assert merge_intervals([(3, 3), (1, 2)]) == [(1, 2)]


def test_req_05_touching_intervals_merge():
    assert merge_intervals([(1, 3), (3, 5)]) == [(1, 5)]


def test_req_05b_overlapping_intervals_merge():
    assert merge_intervals([(1, 4), (3, 6)]) == [(1, 6)]


def test_req_06_non_touching_stay_separate():
    assert merge_intervals([(1, 2), (5, 6)]) == [(1, 2), (5, 6)]


def test_req_07_lo_clamps_start():
    assert merge_intervals([(1, 5)], lo=3) == [(3, 5)]
    with pytest.raises(TypeError):
        merge_intervals([(1, 5)], lo="x")


def test_req_08_hi_clamps_end():
    assert merge_intervals([(1, 5)], hi=3) == [(1, 3)]
    with pytest.raises(TypeError):
        merge_intervals([(1, 5)], hi="x")


def test_req_09_lo_greater_than_hi_raises():
    with pytest.raises(ValueError):
        merge_intervals([(1, 5)], lo=10, hi=1)


def test_req_10_clamped_to_empty_dropped():
    assert merge_intervals([(1, 2), (10, 20)], lo=5, hi=8) == []


def test_req_11_empty_input():
    assert merge_intervals([]) == []


def test_req_12_sorted_and_merged_output():
    result = merge_intervals([(10, 12), (0, 2), (1, 5)])
    assert result == [(0, 5), (10, 12)]
    assert all(isinstance(s, int) and isinstance(e, int) for s, e in result)


def test_req_13_duplicate_intervals_merge():
    assert merge_intervals([(2, 4), (2, 4)]) == [(2, 4)]
