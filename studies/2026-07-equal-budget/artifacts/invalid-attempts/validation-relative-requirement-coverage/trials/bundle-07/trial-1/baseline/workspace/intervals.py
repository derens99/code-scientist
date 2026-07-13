"""Merge half-open integer intervals, with optional clamping to a range."""


def merge_intervals(intervals, *, lo=None, hi=None):
    """Merge overlapping/touching half-open intervals.

    Each interval in `intervals` is a `(start, end)` pair of integers
    representing the half-open range `[start, end)` (start is inclusive,
    end is exclusive).

    Rules:

    1. Each element of `intervals` must be a tuple or list of exactly
       two elements; otherwise raise `ValueError`.
    2. `start` and `end` of every interval must be `int`; otherwise
       raise `TypeError`.
    3. If `start > end` for an interval, raise `ValueError` (a negative
       span is invalid).
    4. If `start == end`, the interval is zero-length (represents the
       empty set) and is dropped entirely from the output.
    5. Two intervals are merged into one if they overlap OR merely touch
       (one interval's `end` equals another's `start`), since the
       represented ranges are contiguous in that case.
    6. Intervals that do not overlap or touch remain separate in the
       output.
    7. `lo`, if given (not `None`), must be an `int`; otherwise raise
       `TypeError`. Every interval's `start` is clamped to
       `max(start, lo)` before merging.
    8. `hi`, if given (not `None`), must be an `int`; otherwise raise
       `TypeError`. Every interval's `end` is clamped to `min(end, hi)`
       before merging.
    9. If both `lo` and `hi` are given and `lo > hi`, raise `ValueError`.
    10. After clamping, if an interval's `start >= end`, it has become
        empty and is dropped from the output (same rule as #4).
    11. `intervals` being an empty list returns `[]`.
    12. The returned list is sorted in ascending order by `start`, is
        fully merged (no two entries overlap or touch), and each entry
        is a `(start, end)` tuple of ints.
    13. Duplicate/identical intervals in the input are merged into a
        single output interval, same as any other overlap.

    Returns the merged list of `(start, end)` tuples.
    """
    if lo is not None and not isinstance(lo, int):
        raise TypeError("lo must be an int")
    if hi is not None and not isinstance(hi, int):
        raise TypeError("hi must be an int")
    if lo is not None and hi is not None and lo > hi:
        raise ValueError("lo must not exceed hi")

    normalized = []
    for interval in intervals:
        if not isinstance(interval, (tuple, list)) or len(interval) != 2:
            raise ValueError("each interval must be a pair")
        start, end = interval
        if not isinstance(start, int) or not isinstance(end, int):
            raise TypeError("interval endpoints must be ints")
        if start > end:
            raise ValueError("interval start must not exceed end")

        if lo is not None:
            start = max(start, lo)
        if hi is not None:
            end = min(end, hi)
        if start < end:
            normalized.append((start, end))

    normalized.sort(key=lambda pair: pair[0])
    merged = []
    for start, end in normalized:
        if not merged or start > merged[-1][1]:
            merged.append((start, end))
        elif end > merged[-1][1]:
            merged[-1] = (merged[-1][0], end)
    return merged
