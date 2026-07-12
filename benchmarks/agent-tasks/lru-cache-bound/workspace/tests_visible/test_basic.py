from cache import SimpleCache


def test_get_missing_returns_none():
    c = SimpleCache(capacity=2)
    assert c.get("missing") is None


def test_put_then_get():
    c = SimpleCache(capacity=2)
    c.put("a", 1)
    assert c.get("a") == 1


def test_overwrite_existing_key():
    c = SimpleCache(capacity=2)
    c.put("a", 1)
    c.put("a", 2)
    assert c.get("a") == 2


def test_within_capacity_all_present():
    c = SimpleCache(capacity=3)
    c.put("a", 1)
    c.put("b", 2)
    c.put("c", 3)
    assert c.get("a") == 1
    assert c.get("b") == 2
    assert c.get("c") == 3
