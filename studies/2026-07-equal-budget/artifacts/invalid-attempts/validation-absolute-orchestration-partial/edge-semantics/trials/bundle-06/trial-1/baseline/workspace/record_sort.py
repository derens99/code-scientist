"""Stable multi-key sorter for lists of dict records."""


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
    if not isinstance(keys, list) or not keys:
        raise ValueError("keys must be a non-empty list")

    parsed = []
    for item in keys:
        if not isinstance(item, (tuple, list)) or len(item) != 2:
            raise ValueError("each key must be a pair")
        field, direction = item
        if direction not in ("asc", "desc"):
            raise ValueError("direction must be 'asc' or 'desc'")
        parsed.append((field, direction))

    from functools import cmp_to_key

    def compare(left, right):
        for field, direction in parsed:
            # Records are documented as dictionaries; using [] preserves the
            # normal mapping error behavior for malformed records.
            a = left.get(field, None)
            b = right.get(field, None)
            if a is None:
                if b is None:
                    continue
                return 1
            if b is None:
                return -1
            if a == b:
                continue
            try:
                a_before_b = a < b
                b_before_a = b < a
            except TypeError as exc:
                raise TypeError("values for a sort key are not comparable") from exc
            if a_before_b:
                result = -1
            elif b_before_a:
                result = 1
            else:
                # Objects such as NaN can be unequal while having no ordering;
                # treat them as equal so Python's stable sort preserves order.
                continue
            return result if direction == "asc" else -result
        return 0

    return sorted(records, key=cmp_to_key(compare))
