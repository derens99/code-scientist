"""Recursive configuration layer merging."""

import copy


def deep_merge(base, override):
    """Recursively merge two config dicts, `override` taking precedence.

    Rules:
    - The result is a new dict; `base` and `override` (including any
      nested dicts within them) must not be mutated, and the result must
      not share any mutable nested dict object with either input (i.e.
      nested dicts are copied, not aliased).
    - For each key present in `override`:
      - If the key is present in `base` AND both `base[key]` and
        `override[key]` are dicts, the merged value is the recursive
        `deep_merge` of those two dicts.
      - Otherwise (key missing from `base`, or either value is not a
        dict), the merged value is `override[key]` taken as-is (for
        dicts this means a deep copy of that dict; for lists and other
        values, the value itself — lists are never merged element-wise,
        an override list fully replaces a base list).
      - This includes the case `override[key] is None`: an explicit
        `None` in `override` overwrites whatever `base[key]` was, since
        `None` is a value like any other, not "missing".
    - For each key present in `base` but not in `override`, the merged
      value is `base[key]` (deep-copied if it is a dict).
    - Keys not present in either `base` or `override` do not appear in
      the result.
    """
    result = {}
    for key, value in base.items():
        result[key] = copy.deepcopy(value) if isinstance(value, dict) else value

    for key, value in override.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(base[key], value)
        else:
            result[key] = copy.deepcopy(value) if isinstance(value, dict) else value

    return result
