# Boundary contract

## `format_number(value, *, decimals=2, thousands_sep=False, percent=False, width=None)`
- Valid edges: numeric finite `int`/`float` (excluding `bool`); `decimals` non-negative `int`; `width` `None` or non-negative `int`; flags may be truthy as documented. Percent conversion precedes banker's rounding; negative zero suppressed; grouping/sign/suffix then left-padding.
- Invalid: non-numeric/bool `value` -> `TypeError`; non-finite value -> `ValueError`; invalid `decimals` or `width` -> `ValueError`.

## `split_record(line, sep=",")`
- Valid edges: any line string (empty gives `[""]`); `sep` is exactly one non-quote character. Quoted fields begin with `"`, support doubled quotes, separators inside quotes, and require immediate separator/end after closing quote; unquoted fields are literal.
- Invalid: `sep` not a one-character string or is `"` -> `ValueError`; unterminated quoted field or trailing data after a closing quote -> `ValueError`.

## `merge_intervals(intervals, *, lo=None, hi=None)`
- Valid edges: iterable of 2-item tuple/list integer pairs; `lo`/`hi` are `None` or ints with `lo <= hi`. Zero-length and clamped-empty intervals are dropped; remaining half-open intervals are sorted and overlap/touch merged.
- Invalid: malformed interval shape or `start > end` -> `ValueError`; non-int endpoints or bounds -> `TypeError`; `lo > hi` -> `ValueError`.
