from cache import SimpleCache


def test_evicts_least_recently_used_on_overflow():
    c = SimpleCache(capacity=2)
    c.put("a", 1)
    c.put("b", 2)
    c.put("c", 3)  # should evict "a"
    assert c.get("a") is None
    assert c.get("b") == 2
    assert c.get("c") == 3


def test_get_counts_as_use_and_protects_from_eviction():
    c = SimpleCache(capacity=2)
    c.put("a", 1)
    c.put("b", 2)
    c.get("a")  # "a" is now most recently used
    c.put("c", 3)  # should evict "b", not "a"
    assert c.get("a") == 1
    assert c.get("b") is None
    assert c.get("c") == 3


def test_overwrite_counts_as_use():
    c = SimpleCache(capacity=2)
    c.put("a", 1)
    c.put("b", 2)
    c.put("a", 99)  # "a" is now most recently used
    c.put("c", 3)  # should evict "b"
    assert c.get("a") == 99
    assert c.get("b") is None
    assert c.get("c") == 3


def test_missing_get_does_not_affect_lru_order():
    c = SimpleCache(capacity=2)
    c.put("a", 1)
    c.put("b", 2)
    c.get("missing")
    c.put("c", 3)  # "a" is still the least recently used, should be evicted
    assert c.get("a") is None
    assert c.get("b") == 2


def test_capacity_of_one():
    c = SimpleCache(capacity=1)
    c.put("a", 1)
    c.put("b", 2)
    assert c.get("a") is None
    assert c.get("b") == 2


def test_repeated_eviction_sequence():
    c = SimpleCache(capacity=3)
    for i in range(10):
        c.put(f"k{i}", i)
    # only the last 3 keys should remain
    for i in range(7):
        assert c.get(f"k{i}") is None
    for i in range(7, 10):
        assert c.get(f"k{i}") == i
