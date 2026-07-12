"""A simple key-value cache (currently unbounded)."""


class SimpleCache:
    def __init__(self):
        self._store = {}

    def get(self, key):
        return self._store.get(key)

    def put(self, key, value):
        self._store[key] = value
