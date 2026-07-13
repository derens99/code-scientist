"""Tumbling-window aggregation over an integer-timestamped event log."""


def aggregate_windows(events, window_size, *, agg="sum"):
    """Group `events` into fixed-size tumbling windows and aggregate each.

    `events` is a list of `(timestamp, value)` pairs, where `timestamp`
    is an `int` and `value` is an `int` or `float`. `window_size` is a
    positive `int` defining the width of each tumbling window.

    Rules:

    1. `window_size` must be a positive `int` (`> 0`); otherwise raise
       `ValueError`.
    2. `agg` must be one of `"sum"`, `"avg"`, `"min"`, `"max"`, `"count"`;
       any other value raises `ValueError`.
    3. `events` must be a list; otherwise raise `ValueError`. Each
       element must be a tuple or list of exactly two elements
       `(timestamp, value)`; otherwise raise `ValueError`.
    4. `timestamp` must be an `int`; otherwise raise `TypeError`.
    5. Windows are tumbling and half-open: an event with timestamp `t`
       belongs to the window whose index is `t // window_size` (integer
       floor division), covering the half-open range
       `[index * window_size, (index + 1) * window_size)`.
    6. Only windows that contain at least one event appear in the
       output; windows with zero events between populated windows are
       never synthesized or emitted (no gap-filling).
    7. The input `events` list does not need to be sorted by timestamp
       in any way; the result must be identical regardless of the input
       order of `events` (out-of-order input is fully supported).
    8. Events with duplicate/identical timestamps are all included
       individually in their window's aggregation (never deduplicated or
       merged).
    9. `"sum"` aggregates a window's values with `sum()`.
    10. `"avg"` aggregates a window's values as `sum(values) /
        count(values)`, and the result is always a `float`, even if
        every value in the window and the count are such that the true
        mathematical average is a whole number.
    11. `"min"` / `"max"` aggregate a window's values with the plain
        numeric minimum/maximum; when there are ties, the aggregate
        value itself is unambiguous since it is a pure numeric
        reduction.
    12. `"count"` ignores every event's `value` entirely and aggregates
        to the integer number of events in that window.
    13. If `events` is empty, the result is `[]`.
    14. The result is a list of `(window_start, window_end, aggregate)`
        tuples, where `window_end = window_start + window_size`, sorted
        in ascending order by `window_start`.

    Returns the list of `(window_start, window_end, aggregate)` tuples.
    """
    if type(window_size) is not int or window_size <= 0:
        raise ValueError("window_size must be a positive int")
    if agg not in ("sum", "avg", "min", "max", "count"):
        raise ValueError("unsupported aggregation mode")
    if not isinstance(events, list):
        raise ValueError("events must be a list")

    grouped = {}
    for event in events:
        if not isinstance(event, (tuple, list)) or len(event) != 2:
            raise ValueError("each event must be a pair")
        timestamp, value = event
        if type(timestamp) is not int:
            raise TypeError("timestamp must be an int")
        index = timestamp // window_size
        grouped.setdefault(index, []).append(value)

    result = []
    for index in sorted(grouped):
        values = grouped[index]
        if agg == "sum":
            aggregate = sum(values)
        elif agg == "avg":
            aggregate = float(sum(values) / len(values))
        elif agg == "min":
            aggregate = min(values)
        elif agg == "max":
            aggregate = max(values)
        else:  # count
            aggregate = len(values)
        start = index * window_size
        result.append((start, start + window_size, aggregate))
    return result
