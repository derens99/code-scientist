"""Row deduplication utilities.

dedupe_rows(rows, key) takes a list of dicts and a key field name. It
returns a new list of dicts with duplicate key values removed, keeping
only the LAST occurrence's field values for each distinct key value, but
preserving the order in which each distinct key value FIRST appeared in
the input. The input list and its dicts must not be mutated.
"""


def dedupe_rows(rows, key):
    seen = {}
    order = []
    for row in rows:
        k = row[key]
        if k not in seen:
            order.append(k)
        seen[k] = dict(row)
    return [seen[k] for k in order]
