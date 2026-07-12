"""Render a list of rows into a bordered, plain-ASCII text table."""


def render_table(headers, rows, alignments=None, max_col_width=None):
    """Render `headers` and `rows` into a bordered text table.

    `headers` is a list of column-name strings. `rows` is a list of
    rows, each row being a list of cell strings with the same length as
    `headers`. `alignments`, if given, is a list (same length as
    `headers`) of `"left"`, `"right"`, or `"center"`, one per column;
    if omitted, every column defaults to `"left"`. `max_col_width`, if
    given, is the maximum rendered width of any single column.

    Rules:

    1. `headers` must be a non-empty list of strings; an empty list
       raises `ValueError`, and any non-string header raises
       `TypeError`.
    2. Every row must be a list whose length equals `len(headers)`;
       otherwise raise `ValueError`. Every cell in every row must be a
       string; otherwise raise `TypeError`.
    3. If `alignments` is given, its length must equal `len(headers)`
       (otherwise raise `ValueError`), and every value in it must be one
       of `"left"`, `"right"`, `"center"` (otherwise raise `ValueError`).
    4. If `max_col_width` is given, it must be an integer `>= 4`
       (otherwise raise `ValueError`).
    5. Cell width is always measured with plain `len()` (character/code
       point count) — no special handling of wide/combining Unicode
       characters.
    6. If `max_col_width` is given and a cell's (or header's) length
       exceeds it, the cell is truncated to exactly `max_col_width`
       characters as `text[: max_col_width - 3] + "..."`. Truncation is
       applied to headers and data cells alike, and happens BEFORE
       column widths are computed.
    7. After any truncation, each column's rendered width is
       `max(len(header_cell), max(len(cell) for cell in that column))`
       (0 if there are no rows).
    8. Every column's cells (including the header) are padded to that
       column's width using the column's alignment (`str.ljust` for
       `"left"`, `str.rjust` for `"right"`, `str.center` for
       `"center"`), with exactly one literal space of padding on each
       side of the aligned content, and `|` characters as the left/right
       border and column separators, e.g. a padded cell renders as
       `"| " + aligned + " |"` joined between columns.
    9. A horizontal border line is `"+"` followed by, for each column,
       `"-" * (width + 2)`, joined by `"+"`, and capped with a final
       `"+"`.
    10. The returned value is a list of text lines in this exact order:
        border, header line, border, one line per data row (in row
        order), border. This holds even when `rows` is empty (there are
        still three border lines and the header line, but zero row
        lines).
    11. A single-column table renders correctly using the same border
        and padding rules (no special-casing needed).

    Returns the list of rendered lines (no trailing newline characters).
    """
    if not isinstance(headers, list) or len(headers) == 0:
        raise ValueError("headers must be a non-empty list")
    for h in headers:
        if not isinstance(h, str):
            raise TypeError("headers must all be strings")
    ncols = len(headers)

    if alignments is None:
        alignments = ["left"] * ncols
    else:
        if len(alignments) != ncols:
            raise ValueError("alignments length must match headers length")
        for a in alignments:
            if a not in ("left", "right", "center"):
                raise ValueError(f"invalid alignment: {a!r}")

    if max_col_width is not None:
        if not isinstance(max_col_width, int) or max_col_width < 4:
            raise ValueError("max_col_width must be an int >= 4")

    for row in rows:
        if not isinstance(row, list) or len(row) != ncols:
            raise ValueError("row length must match headers length")
        for c in row:
            if not isinstance(c, str):
                raise TypeError("row cells must all be strings")

    def truncate(s):
        if max_col_width is not None and len(s) > max_col_width:
            return s[: max_col_width - 3] + "..."
        return s

    t_headers = [truncate(h) for h in headers]
    t_rows = [[truncate(c) for c in row] for row in rows]

    widths = []
    for i in range(ncols):
        w = len(t_headers[i])
        for row in t_rows:
            w = max(w, len(row[i]))
        widths.append(w)

    def align_cell(cell, i):
        width = widths[i]
        mode = alignments[i]
        if mode == "left":
            return cell.ljust(width)
        if mode == "right":
            return cell.rjust(width)
        return cell.center(width)

    def render_row(cells):
        parts = [" " + align_cell(cell, i) + " " for i, cell in enumerate(cells)]
        return "|" + "|".join(parts) + "|"

    border = "+" + "+".join("-" * (w + 2) for w in widths) + "+"

    lines = [border, render_row(t_headers), border]
    for row in t_rows:
        lines.append(render_row(row))
    lines.append(border)
    return lines
