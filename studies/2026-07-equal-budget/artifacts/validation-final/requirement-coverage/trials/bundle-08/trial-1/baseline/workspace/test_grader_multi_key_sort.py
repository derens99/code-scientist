import pytest

from record_sort import sort_records


def test_req_01_records_must_be_list():
    with pytest.raises(TypeError):
        sort_records("not a list", [("a", "asc")])


def test_req_02_keys_must_be_nonempty():
    with pytest.raises(ValueError):
        sort_records([{"a": 1}], [])


def test_req_03_key_pair_shape():
    with pytest.raises(ValueError):
        sort_records([{"a": 1}], [("a", "asc", "extra")])


def test_req_04_invalid_direction():
    with pytest.raises(ValueError):
        sort_records([{"a": 1}], [("a", "up")])


def test_req_05_missing_field_treated_as_none():
    recs = [{"a": 1}, {}, {"a": 2}]
    out = sort_records(recs, [("a", "asc")])
    assert out[0]["a"] == 1 and out[1]["a"] == 2
    assert "a" not in out[2]


def test_req_06_none_sorts_last_regardless_of_direction():
    recs = [{"a": None}, {"a": 3}, {"a": 1}]
    asc = sort_records(recs, [("a", "asc")])
    assert [r["a"] for r in asc] == [1, 3, None]
    desc = sort_records(recs, [("a", "desc")])
    assert [r["a"] for r in desc] == [3, 1, None]


def test_req_07_none_group_preserves_relative_order():
    recs = [{"id": 1, "a": None}, {"id": 2, "a": None}, {"id": 3, "a": 1}]
    out = sort_records(recs, [("a", "asc")])
    none_ids = [r["id"] for r in out if r["a"] is None]
    assert none_ids == [1, 2]


def test_req_08_incomparable_types_raise_typeerror():
    with pytest.raises(TypeError):
        sort_records([{"a": 1}, {"a": "x"}], [("a", "asc")])


def test_req_08b_bool_int_comparable():
    recs = [{"a": True}, {"a": 0}, {"a": 2}]
    out = sort_records(recs, [("a", "asc")])
    assert [r["a"] for r in out] == [0, True, 2]


def test_req_09_stability_on_full_tie():
    recs = [{"id": 1, "a": 1}, {"id": 2, "a": 1}, {"id": 3, "a": 1}]
    out = sort_records(recs, [("a", "asc")])
    assert [r["id"] for r in out] == [1, 2, 3]


def test_req_10_duplicate_field_key():
    recs = [{"a": 2}, {"a": 1}]
    out = sort_records(recs, [("a", "asc"), ("a", "desc")])
    assert [r["a"] for r in out] == [1, 2]


def test_req_11_new_list_same_length_and_objects():
    recs = [{"a": 2}, {"a": 1}]
    out = sort_records(recs, [("a", "asc")])
    assert out is not recs
    assert len(out) == len(recs)
    assert all(r in recs for r in out)


def test_req_12_string_ordinal_comparison():
    recs = [{"a": "banana"}, {"a": "Apple"}, {"a": "apple"}]
    out = sort_records(recs, [("a", "asc")])
    assert [r["a"] for r in out] == ["Apple", "apple", "banana"]


def test_multi_key_secondary_breaks_tie():
    recs = [
        {"grp": 1, "n": "b"},
        {"grp": 2, "n": "a"},
        {"grp": 1, "n": "a"},
    ]
    out = sort_records(recs, [("grp", "asc"), ("n", "asc")])
    assert [(r["grp"], r["n"]) for r in out] == [(1, "a"), (1, "b"), (2, "a")]
