# Boundary contract

The three public callables use the following validation boundaries and stable
exception messages.

* `sort_records(records, keys)` accepts a list of dicts and a non-empty list of
  two-item tuple/list key specifications. Invalid container/record shapes raise
  `TypeError` with `records must be a list`, `each record must be a dict`, or
  `keys must be a non-empty list`; malformed key specifications raise
  `ValueError` with `each key must be a 2-item tuple or list`; a direction other
  than `asc`/`desc` raises `ValueError` with `direction must be \"asc\" or
  \"desc\"`; incomparable non-null values raise `TypeError` with the formatted
  message `values for field {field_name!r} are not comparable`.
* `render_table(headers, rows, alignments=None, max_col_width=None)` accepts a
  non-empty list of string headers, a list of same-width list rows containing
  strings, optional list alignments, and an integer width of at least four.
  Violations raise `TypeError` with `headers must be a non-empty list`, `rows
  must be a list`, `headers must contain only strings`, `cells must be
  strings`, or `alignments must be a list`; shape/value violations raise
  `ValueError` with `headers must not be empty`, `each row must be a list with
  the same length as headers`,
  `alignments length must match headers`, `alignment must be left, right, or
  center`, or `max_col_width must be an integer >= 4`.
* `match_glob(pattern, text)` accepts strings. Non-strings raise `TypeError`
  (`pattern must be a string` / `text must be a string`); a final unescaped
  backslash raises `ValueError` (`trailing backslash in pattern`), and an
  unclosed class raises `ValueError` (`unterminated character class`).

All valid boundary cases (empty text/pattern, empty rows, repeated stars,
single-column tables, null sort values, and empty classes) are handled without
special exceptions beyond those listed above.
