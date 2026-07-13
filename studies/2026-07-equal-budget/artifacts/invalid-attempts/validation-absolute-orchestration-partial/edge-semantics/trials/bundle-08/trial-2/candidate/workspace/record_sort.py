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
    raise NotImplementedError
