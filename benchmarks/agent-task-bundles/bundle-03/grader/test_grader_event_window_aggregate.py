import pytest

from event_windows import aggregate_windows


def test_req_01_window_size_must_be_positive_int():
    with pytest.raises(ValueError):
        aggregate_windows([(0, 1)], 0)
    with pytest.raises(ValueError):
        aggregate_windows([(0, 1)], -5)


def test_req_02_invalid_agg_raises():
    with pytest.raises(ValueError):
        aggregate_windows([(0, 1)], 10, agg="median")


def test_req_03_events_and_pair_validation():
    with pytest.raises(ValueError):
        aggregate_windows("not a list", 10)
    with pytest.raises(ValueError):
        aggregate_windows([(0, 1, 2)], 10)


def test_req_04_timestamp_must_be_int():
    with pytest.raises(TypeError):
        aggregate_windows([(1.5, 1)], 10)


def test_req_05_window_boundary_assignment():
    result = aggregate_windows([(9, 1), (10, 2)], 10)
    starts = {w[0]: w for w in result}
    assert starts[0] == (0, 10, 1)
    assert starts[10] == (10, 20, 2)


def test_req_06_no_gap_filling():
    result = aggregate_windows([(0, 1), (100, 2)], 10)
    assert len(result) == 2
    assert result[0][0] == 0
    assert result[1][0] == 100


def test_req_07_out_of_order_input_same_result():
    a = aggregate_windows([(5, 1), (1, 2), (3, 3)], 10)
    b = aggregate_windows([(1, 2), (3, 3), (5, 1)], 10)
    assert a == b


def test_req_08_duplicate_timestamps_all_counted():
    result = aggregate_windows([(1, 1), (1, 1), (1, 1)], 10, agg="count")
    assert result == [(0, 10, 3)]


def test_req_09_sum_aggregation():
    result = aggregate_windows([(1, 2), (2, 3)], 10, agg="sum")
    assert result == [(0, 10, 5)]


def test_req_10_avg_always_float():
    result = aggregate_windows([(1, 2), (2, 2)], 10, agg="avg")
    assert result == [(0, 10, 2.0)]
    assert isinstance(result[0][2], float)


def test_req_11_min_max_aggregation():
    assert aggregate_windows([(1, 5), (2, 1), (3, 9)], 10, agg="min") == [(0, 10, 1)]
    assert aggregate_windows([(1, 5), (2, 1), (3, 9)], 10, agg="max") == [(0, 10, 9)]


def test_req_12_count_ignores_value():
    result = aggregate_windows([(1, 100), (2, -5)], 10, agg="count")
    assert result == [(0, 10, 2)]


def test_req_13_empty_events():
    assert aggregate_windows([], 10) == []


def test_req_14_sorted_by_window_start_and_end():
    result = aggregate_windows([(25, 1), (5, 1), (15, 1)], 10)
    assert [w[0] for w in result] == [0, 10, 20]
    assert all(w[1] == w[0] + 10 for w in result)
