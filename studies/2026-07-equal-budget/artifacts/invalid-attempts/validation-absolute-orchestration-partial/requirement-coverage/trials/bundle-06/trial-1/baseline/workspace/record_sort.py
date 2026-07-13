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
    if not isinstance(keys, list) or not keys:
        raise ValueError("keys must be a non-empty list")

    normalized = []
    for item in keys:
        if not isinstance(item, (tuple, list)) or len(item) != 2:
            raise ValueError("each key must be a (field_name, direction) pair")
        field, direction = item
        if direction not in ("asc", "desc"):
            raise ValueError("direction must be 'asc' or 'desc'")
        normalized.append((field, direction))

    def compare(left, right):
        for field, direction in normalized:
            # Missing fields are deliberately indistinguishable from None.
            lv = left.get(field, None)
            rv = right.get(field, None)
            if lv is None or rv is None:
                if lv is None and rv is None:
                    continue
                # None always goes last, including for descending sorts.
                return 1 if lv is None else -1

            # Use only Python's ordinary ordering operation.  In particular,
            # this preserves the normal bool/int relationship and propagates
            # TypeError for incomparable values (such as int and str).
            try:
                if direction == "asc":
                    if lv < rv:
                        return -1
                    if rv < lv:
                        return 1
                else:
                    if rv < lv:
                        return -1
                    if lv < rv:
                        return 1
            except TypeError:
                raise TypeError("values for a sort key are not comparable")
        return 0

    # sorted() is stable and returns a new list while retaining the original
    # dictionary objects.
    return sorted(records, key=cmp_to_key(compare))
