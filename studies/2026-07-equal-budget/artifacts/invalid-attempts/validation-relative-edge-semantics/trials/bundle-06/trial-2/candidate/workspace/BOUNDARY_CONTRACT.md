# Boundary contract

- `sort_records(records, keys)`: `records` is a list of dicts and `keys` is a
  non-empty list of two-item `(field, direction)` sequences. Missing and null
  values sort last; non-null values use Python `<`; ties retain input order.
  Non-list records and non-dict elements raise `TypeError` with `records must be
  a list` and `each record must be a dict`. Empty/non-list keys, malformed key
  entries, and bad directions raise `ValueError` with `keys must be a non-empty
  list`, `each key must be a pair`, and `direction must be 'asc' or 'desc'`.
  Incomparable values raise `TypeError` with `values for field <repr> are not
  comparable`.
- `render_table(headers, rows, alignments=None, max_col_width=None)`: headers
  are a non-empty list of strings; rows is a list of equally-sized string
  lists; alignments are omitted or a same-sized list containing only `left`,
  `right`, and `center`; the optional maximum is an integer at least 4. Invalid
  header/row/alignment shapes raise `ValueError` with respectively `headers
  must be a non-empty list`, `each row must match headers`, `alignments must
  match headers`, and `invalid alignment`; non-string headers/cells raise
  `TypeError` with `headers must contain only strings` and `cells must be
  strings`; a non-list rows value raises `ValueError` with `rows must be a
  list`; a bad maximum raises `ValueError` with `max_col_width must be an
  integer >= 4`.
- `match_glob(pattern, text)`: pattern and text are strings and matching covers
  all of text. Wildcards, classes, ranges, class negation, and outside-class
  escapes follow the callable docstring. Non-string arguments raise `TypeError`
  with `pattern must be a string` or `text must be a string`. An unclosed class
  raises `ValueError` with `unterminated character class`; a final backslash
  raises `ValueError` with `trailing escape`.
