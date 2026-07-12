from config_merge import deep_merge


def test_flat_override():
    assert deep_merge({"a": 1, "b": 2}, {"b": 3}) == {"a": 1, "b": 3}


def test_nested_merge():
    base = {"db": {"host": "localhost", "port": 5432}}
    override = {"db": {"port": 5433}}
    assert deep_merge(base, override) == {"db": {"host": "localhost", "port": 5433}}


def test_new_key_added():
    assert deep_merge({"a": 1}, {"b": 2}) == {"a": 1, "b": 2}


def test_empty_override():
    base = {"a": 1, "b": {"c": 2}}
    assert deep_merge(base, {}) == base
