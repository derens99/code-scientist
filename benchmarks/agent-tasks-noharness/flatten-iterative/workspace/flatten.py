"""Flatten arbitrarily nested lists.

flatten_nested(lst) takes a list that may contain other lists nested to
any depth, and returns a single flat list containing all non-list items
in left-to-right order. Non-list items (strings, numbers, None, tuples,
etc.) are kept as-is and never iterated into.
"""


def flatten_nested(lst):
    result = []
    for item in lst:
        if isinstance(item, list):
            result.extend(flatten_nested(item))
        else:
            result.append(item)
    return result
