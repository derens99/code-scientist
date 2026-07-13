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
    if not isinstance(headers, list) or not headers:
        raise ValueError("headers must be a non-empty list")
    if any(not isinstance(header, str) for header in headers):
        raise TypeError("headers must be strings")

    for row in rows:
        if not isinstance(row, list) or len(row) != len(headers):
            raise ValueError("each row must match the number of columns")
        if any(not isinstance(cell, str) for cell in row):
            raise TypeError("cells must be strings")

    if alignments is None:
        alignments = ["left"] * len(headers)
    else:
        if len(alignments) != len(headers):
            raise ValueError("alignments must match the number of columns")
        if any(value not in ("left", "right", "center") for value in alignments):
            raise ValueError("invalid alignment")

    if max_col_width is not None:
        if type(max_col_width) is not int or max_col_width < 4:
            raise ValueError("max_col_width must be an integer >= 4")

        def truncate(value):
            if len(value) > max_col_width:
                return value[: max_col_width - 3] + "..."
            return value
    else:
        def truncate(value):
            return value

    rendered_headers = [truncate(header) for header in headers]
    rendered_rows = [[truncate(cell) for cell in row] for row in rows]
    widths = []
    for column, header in enumerate(rendered_headers):
        widths.append(max([len(header)] + [len(row[column]) for row in rendered_rows]))

    def render_row(row):
        cells = []
        for value, width, alignment in zip(row, widths, alignments):
            if alignment == "left":
                aligned = value.ljust(width)
            elif alignment == "right":
                aligned = value.rjust(width)
            else:
                aligned = value.center(width)
            cells.append(" " + aligned + " ")
        return "|" + "|".join(cells) + "|"

    border = "+" + "+".join("-" * (width + 2) for width in widths) + "+"
    return [
        border,
        render_row(rendered_headers),
        border,
        *(render_row(row) for row in rendered_rows),
        border,
    ]
