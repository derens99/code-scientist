"""A minimal glob-style pattern matcher. Do NOT use the `re` module."""


def match_glob(pattern, text):
    """Return True if `text` fully matches glob `pattern`, else False.

    Matching is always a full match of the entire string (as if the
    pattern were implicitly anchored at both ends), never a substring
    search.

    Pattern syntax:

    1. `?` matches exactly one arbitrary character (never zero, never
       two).
    2. `*` matches zero or more arbitrary characters. Two or more
       consecutive `*` characters behave exactly like a single `*`.
    3. `[...]` matches exactly one character that belongs to the
       character class described between the brackets.
       - Inside the brackets, a leading `!` or `^` (as the very first
         character right after `[`) negates the class: the class then
         matches exactly one character that is NOT among the described
         characters.
       - Within the (post-negation) class body, `X-Y` denotes an
         inclusive range from character `X` to character `Y` (by
         Unicode code point), when `X <= Y`. If `X > Y`, or if the `-`
         is the first or last character of the class body, the `-` (and
         the characters around it) are instead treated as individual
         literal characters, not a range.
       - Backslash escaping is NOT recognized inside `[...]`; every
         character in the class body (other than a leading `!`/`^` and
         range-forming `-`) is a literal member of the class.
       - The class must be closed by a `]`; if no `]` appears after the
         `[`, raise `ValueError` (unterminated character class).
    4. A backslash `\\` outside of `[...]` escapes the single character
       that follows it, making that character match itself literally
       (even if it is `*`, `?`, `[`, or `\\`). A `\\` as the very last
       character of `pattern`, with nothing after it to escape, raises
       `ValueError`.
    5. Any other character matches itself literally.
    6. An empty `pattern` matches only an empty `text`.
    7. This function must not import or use the `re` module (or any
       other regular-expression engine); implement the matching logic
       directly (e.g. with dynamic programming or recursion over the
       parsed pattern).

    Returns `True` or `False`.
    """
    raise NotImplementedError
