"""A configurable numeric-to-string formatter."""

import math


def format_number(value, *, decimals=2, thousands_sep=False, percent=False, width=None):
    """Format `value` as a string according to the given options.

    Rules:

    1. `value` must be an `int` or `float` and must NOT be a `bool`
       (even though `bool` is technically a subtype of `int` in Python);
       otherwise raise `TypeError`.
    2. `value` must be finite: if it is NaN or positive/negative
       infinity, raise `ValueError`.
    3. `decimals` must be a non-negative `int`; otherwise raise
       `ValueError`. It controls how many digits appear after the
       decimal point.
    4. If `percent` is `True`, `value` is first multiplied by 100 (this
       happens BEFORE rounding), and a literal `%` character is
       appended to the final formatted string (after all other
       formatting, including width padding is computed around the
       already-suffixed string — i.e. `%` is part of the string that
       gets width-padded).
    5. Rounding to `decimals` places uses round-half-to-even ("banker's
       rounding"), i.e. Python's built-in `round(x, decimals)` semantics
       exactly.
    6. If the rounded value is negative, the formatted string starts
       with a literal `-` sign; if the rounded value is zero (including
       when rounding a small negative number down to zero, e.g.
       `-0.0001` with 2 decimals), there must be NO leading `-` sign
       (the "negative zero" case is suppressed), even when `percent` is
       also `True`.
    7. If `decimals == 0`, the formatted number has no decimal point at
       all (just the integer digits), not a trailing `.`.
    8. If `thousands_sep` is `True`, a `,` is inserted between every
       group of 3 digits in the INTEGER part of the number (counting
       from the right), e.g. `1234567` becomes `1,234,567`. The
       fractional part (if any) is never grouped. This grouping is
       applied after rounding and before the sign/percent suffix/width
       padding.
    9. `width`, if given, must be a non-negative `int`; otherwise raise
       `ValueError`. If given, the fully-formatted string (including any
       sign, thousands separators, and `%` suffix) is padded on the
       LEFT with plain space characters until its total length is at
       least `width`. If the string is already at least `width`
       characters long, it is returned unchanged (never truncated).

    Returns the formatted string.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError("value must be an int or float")
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("value must be finite")
    if not isinstance(decimals, int) or decimals < 0:
        raise ValueError("decimals must be a non-negative int")
    if width is not None and (not isinstance(width, int) or width < 0):
        raise ValueError("width must be a non-negative int")

    precision = int(decimals)
    converted = value * 100 if percent else value
    rounded = round(converted, precision)
    negative = rounded < 0
    magnitude = abs(rounded)
    grouping = "," if thousands_sep else ""
    result = format(magnitude, f"{grouping}.{precision}f")
    if negative:
        result = "-" + result
    if percent:
        result += "%"
    if width is not None:
        result = result.rjust(width)
    return result
