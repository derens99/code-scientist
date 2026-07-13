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
    if not isinstance(pattern, str) or not isinstance(text, str):
        # The docstring specifies string inputs implicitly; normal Python
        # operations below would otherwise produce obscure errors.
        raise TypeError("pattern and text must be strings")

    tokens = []
    i = 0
    plen = len(pattern)
    while i < plen:
        ch = pattern[i]
        if ch == "\\":
            if i + 1 >= plen:
                raise ValueError("trailing escape")
            tokens.append(("lit", pattern[i + 1]))
            i += 2
        elif ch == "*":
            # Consecutive stars are equivalent to one star.
            if not tokens or tokens[-1][0] != "star":
                tokens.append(("star",))
            i += 1
            while i < plen and pattern[i] == "*":
                i += 1
        elif ch == "?":
            tokens.append(("any",))
            i += 1
        elif ch == "[":
            close = pattern.find("]", i + 1)
            if close < 0:
                raise ValueError("unterminated character class")
            body = pattern[i + 1 : close]
            negate = bool(body) and body[0] in "!^"
            if negate:
                body = body[1:]

            # Build a set of members.  A range is recognized only when the
            # hyphen is interior and endpoints are in ascending code-point
            # order; otherwise all three characters remain literals.
            members = set()
            j = 0
            while j < len(body):
                if j + 2 < len(body) and body[j + 1] == "-" and body[j] <= body[j + 2]:
                    members.update(chr(cp) for cp in range(ord(body[j]), ord(body[j + 2]) + 1))
                    j += 3
                else:
                    members.add(body[j])
                    j += 1
            tokens.append(("class", frozenset(members), negate))
            i = close + 1
        else:
            tokens.append(("lit", ch))
            i += 1

    # Dynamic programming over pattern-token and text positions.  The table
    # uses full-match semantics and avoids any regular-expression machinery.
    current = {0}
    for token in tokens:
        kind = token[0]
        nxt = set()
        if kind == "star":
            # A star can consume any number of remaining characters.  Every
            # position reachable from an existing state is therefore reachable.
            for pos in current:
                nxt.update(range(pos, len(text) + 1))
        else:
            for pos in current:
                if pos >= len(text):
                    continue
                c = text[pos]
                matches = (
                    (kind == "lit" and c == token[1])
                    or (kind == "any")
                    or (kind == "class" and ((c in token[1]) != token[2]))
                )
                if matches:
                    nxt.add(pos + 1)
        current = nxt
        if not current:
            return False
    return len(text) in current
