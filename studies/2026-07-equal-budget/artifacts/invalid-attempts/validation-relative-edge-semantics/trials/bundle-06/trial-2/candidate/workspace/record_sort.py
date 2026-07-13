"""Stable multi-key sorter for lists of dict records."""

from functools import cmp_to_key


def sort_records(records, keys):
    """Sort `records` (a list of dicts) by one or more keys.

    `keys` is a non-empty list of `(field_name, direction)` pairs, where
    `direction` is the string `"asc"` or `"desc"`. The first pair is the
    primary sort key, the second pair breaks ties on the first, and so
    on.

    Rules:

    1. `records` must be a list; otherwise raise `TypeError`.
    2. `keys` must be a non-empty list; otherwise raise `ValueError`.
    3. Each element of `keys` must be a tuple or list of exactly two
       elements `(field_name, direction)`; otherwise raise `ValueError`.
    4. `direction` must be exactly `"asc"` or `"desc"`; any other value
       raises `ValueError`.
    5. For a given key's `field_name`, a record missing that field (the
       key is absent from the dict) is treated as having the value
       `None` for that field.
    6. Records with a `None` value for a key always sort AFTER all
       records with a non-`None` value for that key, regardless of
       whether that key's direction is `"asc"` or `"desc"`.
    7. Among records that are all `None` for a given key, their relative
       order is preserved from the input (this follows from the general
       stability rule below).
    8. Non-`None` values for a key are compared using `<` in the usual
       Python sense (so, for example, `bool` and `int` values are
       mutually comparable since `bool` is a subtype of `int`). If two
       non-`None` values for the same key are of incomparable types
       (e.g. `int` and `str`), raise `TypeError`.
    9. Sorting is a full multi-key stable sort: when two records compare
       equal on every key, their relative order from the input list is
       preserved in the output.
    10. The same `field_name` may appear more than once in `keys`
        (e.g. to combine with a different direction is unusual but not
        an error); this must simply be honored as any other key.
    11. The returned list is a new list object (not the same list as
        `records`) containing the exact same dict objects as `records`,
        reordered; its length always equals `len(records)`.
    12. String field values are compared using ordinary Python string
        (ordinal) comparison; no locale-specific or case-insensitive
        handling is performed.

    Returns the sorted list.
    """
    if not isinstance(records, list):
        raise TypeError("records must be a list")
    if any(not isinstance(record, dict) for record in records):
        raise TypeError("each record must be a dict")
    if not isinstance(keys, list) or not keys:
        raise ValueError("keys must be a non-empty list")

    normalized = []
    for key in keys:
        if not isinstance(key, (tuple, list)) or len(key) != 2:
            raise ValueError("each key must be a pair")
        field, direction = key
        if direction not in ("asc", "desc"):
            raise ValueError("direction must be 'asc' or 'desc'")
        normalized.append((field, direction))

    def compare(left, right):
        for field, direction in normalized:
            left_value = left.get(field)
            right_value = right.get(field)
            if left_value is None:
                if right_value is not None:
                    return 1
                continue
            if right_value is None:
                return -1
            try:
                left_less = left_value < right_value
                right_less = right_value < left_value
            except TypeError:
                raise TypeError(
                    f"values for field {field!r} are not comparable"
                ) from None
            if left_less:
                return -1 if direction == "asc" else 1
            if right_less:
                return 1 if direction == "asc" else -1
        return 0

    return sorted(records, key=cmp_to_key(compare))
