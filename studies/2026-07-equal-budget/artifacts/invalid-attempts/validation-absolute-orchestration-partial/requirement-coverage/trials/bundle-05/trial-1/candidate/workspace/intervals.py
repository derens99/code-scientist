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
    # Validate optional bounds before processing the input so malformed
    # bounds are reported consistently even when ``intervals`` is empty.
    if lo is not None and type(lo) is not int:
        raise TypeError("lo must be an int")
    if hi is not None and type(hi) is not int:
        raise TypeError("hi must be an int")
    if lo is not None and hi is not None and lo > hi:
        raise ValueError("lo must not exceed hi")

    kept = []
    for interval in intervals:
        if not isinstance(interval, (tuple, list)) or len(interval) != 2:
            raise ValueError("each interval must be a tuple or list of length 2")
        start, end = interval
        if type(start) is not int or type(end) is not int:
            raise TypeError("interval endpoints must be ints")
        if start > end:
            raise ValueError("interval start must not exceed end")

        if lo is not None:
            start = max(start, lo)
        if hi is not None:
            end = min(end, hi)
        if start >= end:
            continue
        kept.append((start, end))

    if not kept:
        return []

    kept.sort(key=lambda pair: pair[0])
    merged = [kept[0]]
    for start, end in kept[1:]:
        prev_start, prev_end = merged[-1]
        if start <= prev_end:  # overlap or merely touch
            if end > prev_end:
                merged[-1] = (prev_start, end)
        else:
            merged.append((start, end))
    return merged
