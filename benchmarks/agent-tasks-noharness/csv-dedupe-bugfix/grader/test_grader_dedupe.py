from dedupe import dedupe_rows


def test_last_wins_values():
    rows = [
        {"id": 1, "name": "a", "score": 10},
        {"id": 2, "name": "b", "score": 20},
        {"id": 1, "name": "a-updated", "score": 99},
    ]
    result = dedupe_rows(rows, "id")
    assert result == [
        {"id": 1, "name": "a-updated", "score": 99},
        {"id": 2, "name": "b", "score": 20},
    ]


def test_order_follows_first_occurrence():
    rows = [
        {"id": 3, "v": "x"},
        {"id": 1, "v": "y"},
        {"id": 3, "v": "z"},
    ]
    result = dedupe_rows(rows, "id")
    assert [r["id"] for r in result] == [3, 1]
    assert result[0]["v"] == "z"


def test_many_duplicates_keeps_final():
    rows = [{"id": 1, "v": i} for i in range(5)]
    result = dedupe_rows(rows, "id")
    assert result == [{"id": 1, "v": 4}]


def test_does_not_mutate_input_with_duplicates():
    rows = [{"id": 1, "v": "a"}, {"id": 1, "v": "b"}]
    original = [dict(r) for r in rows]
    dedupe_rows(rows, "id")
    assert rows == original


def test_output_dicts_are_copies():
    rows = [{"id": 1, "v": "a"}]
    result = dedupe_rows(rows, "id")
    result[0]["v"] = "changed"
    assert rows[0]["v"] == "a"
