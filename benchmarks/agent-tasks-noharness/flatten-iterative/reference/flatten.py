"""Flatten arbitrarily nested lists.

flatten_nested(lst) takes a list that may contain other lists nested to
any depth, and returns a single flat list containing all non-list items
in left-to-right order. Non-list items (strings, numbers, None, tuples,
etc.) are kept as-is and never iterated into.
"""


def flatten_nested(lst):
    result = []
    # Explicit stack of iterators, one per active nesting level, so no
    # Python function recursion is used regardless of nesting depth.
    stack = [iter(lst)]
    while stack:
        it = stack[-1]
        try:
            item = next(it)
        except StopIteration:
            stack.pop()
            continue
        if isinstance(item, list):
            stack.append(iter(item))
        else:
            result.append(item)
    return result
