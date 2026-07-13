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
    tokens = []
    i = 0
    n = len(pattern)
    while i < n:
        ch = pattern[i]
        if ch == "\\":
            if i + 1 >= n:
                raise ValueError("trailing escape")
            tokens.append(("lit", pattern[i + 1]))
            i += 2
        elif ch == "*":
            if not tokens or tokens[-1][0] != "star":
                tokens.append(("star",))
            i += 1
        elif ch == "?":
            tokens.append(("any",))
            i += 1
        elif ch == "[":
            close = pattern.find("]", i + 1)
            if close < 0:
                raise ValueError("unterminated character class")
            body = pattern[i + 1 : close]
            negate = bool(body) and body[0] in ("!", "^")
            if negate:
                body = body[1:]
            members = set()
            j = 0
            while j < len(body):
                # A hyphen forms a range only when it has characters on both
                # sides and the range is ascending; otherwise it is literal.
                if j + 2 < len(body) and body[j + 1] == "-":
                    start, end = body[j], body[j + 2]
                    if start != "-" and end != "-" and ord(start) <= ord(end):
                        members.update(chr(code) for code in range(ord(start), ord(end) + 1))
                        j += 3
                        continue
                members.add(body[j])
                j += 1
            tokens.append(("class", frozenset(members), negate))
            i = close + 1
        else:
            tokens.append(("lit", ch))
            i += 1

    from functools import lru_cache

    @lru_cache(maxsize=None)
    def match(pi, ti):
        if pi == len(tokens):
            return ti == len(text)
        token = tokens[pi]
        kind = token[0]
        if kind == "star":
            return match(pi + 1, ti) or (ti < len(text) and match(pi, ti + 1))
        if ti >= len(text):
            return False
        if kind == "lit":
            ok = text[ti] == token[1]
        elif kind == "any":
            ok = True
        else:
            present = text[ti] in token[1]
            ok = not present if token[2] else present
        return ok and match(pi + 1, ti + 1)

    return match(0, 0)
