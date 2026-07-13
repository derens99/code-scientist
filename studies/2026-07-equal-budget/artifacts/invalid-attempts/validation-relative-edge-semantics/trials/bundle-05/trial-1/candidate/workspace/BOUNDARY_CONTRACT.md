# Boundary contracts

- `merge_intervals(intervals, *, lo=None, hi=None)`: accepts iterable entries that are
  2-item tuples/lists of integers, including zero-length spans; optional bounds are
  integers and may be equal. Empty and clamp-emptied spans are omitted. A malformed
  entry raises `ValueError("each interval must be a pair")`; a non-integer endpoint
  raises `TypeError("interval endpoints must be integers")`; a reversed span raises
  `ValueError("interval start must not exceed end")`; a non-integer `lo`/`hi` raises
  `TypeError("lo must be an integer")` / `TypeError("hi must be an integer")`; and
  `lo > hi` raises `ValueError("lo must not exceed hi")`.
- `normalize_path(path)`: accepts any non-empty string containing no backslash;
  absolute and relative paths may contain duplicate separators, dot segments, and
  unresolved parent segments. Non-string input raises `TypeError("path must be a
  string")`; empty input raises `ValueError("path must not be empty")`; any backslash
  raises `ValueError("backslashes are not allowed")`.
- `aggregate_windows(events, window_size, *, agg="sum")`: accepts a list of 2-item
  tuple/list events, integer timestamps (including negative timestamps), numeric
  values, a positive integer window size, and one supported aggregation name. An
  invalid window size (including a non-integer) raises `ValueError("window_size must
  be a positive integer")`; an unsupported aggregation raises `ValueError("unsupported
  aggregation")`; a non-list events object raises `ValueError("events must be a
  list")`; a malformed event raises `ValueError("each event must be a pair")`; a
  non-integer timestamp raises `TypeError("event timestamps must be integers")`; and
  a non-numeric value raises `TypeError("event values must be numeric")` (except in
  `count` mode, where values are ignored entirely as specified).
