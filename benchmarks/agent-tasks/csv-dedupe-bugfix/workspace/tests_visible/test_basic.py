from dedupe import dedupe_rows


def test_no_duplicates():
    rows = [{"id": 1, "name": "a"}, {"id": 2, "name": "b"}]
    assert dedupe_rows(rows, "id") == rows


def test_empty():
    assert dedupe_rows([], "id") == []


def test_does_not_mutate_input():
    rows = [{"id": 1, "name": "a"}]
    original = [dict(r) for r in rows]
    dedupe_rows(rows, "id")
    assert rows == original
