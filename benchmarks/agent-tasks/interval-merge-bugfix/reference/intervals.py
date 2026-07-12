"""Interval merging utilities.

merge_intervals takes a list of (start, end) integer intervals (inclusive
bounds, start <= end) and returns a sorted list of merged intervals where
any two intervals that overlap OR touch (e.g. (1, 3) and (3, 5)) are
combined into a single interval. The result must be sorted by start value
and contain no overlapping or touching intervals.
"""


def merge_intervals(intervals):
    if not intervals:
        return []
    sorted_intervals = sorted(intervals, key=lambda iv: iv[0])
    merged = [sorted_intervals[0]]
    for start, end in sorted_intervals[1:]:
        last_start, last_end = merged[-1]
        if start <= last_end:
            merged[-1] = (last_start, max(last_end, end))
        else:
            merged.append((start, end))
    return merged
