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
    tokens = _parse_pattern(pattern)
    m, n = len(tokens), len(text)
    dp = [[False] * (n + 1) for _ in range(m + 1)]
    dp[0][0] = True
    for i in range(1, m + 1):
        if tokens[i - 1][0] == "star":
            dp[i][0] = dp[i - 1][0]

    for i in range(1, m + 1):
        kind, val = tokens[i - 1]
        for j in range(1, n + 1):
            if kind == "star":
                dp[i][j] = dp[i - 1][j] or dp[i][j - 1]
            elif kind == "any":
                dp[i][j] = dp[i - 1][j - 1]
            elif kind == "lit":
                dp[i][j] = dp[i - 1][j - 1] and text[j - 1] == val
            elif kind == "class":
                negate, chars = val
                inside = text[j - 1] in chars
                if negate:
                    inside = not inside
                dp[i][j] = dp[i - 1][j - 1] and inside

    return dp[m][n]


def _parse_class(body):
    negate = body[:1] in ("!", "^")
    if negate:
        body = body[1:]
    chars = set()
    i, n = 0, len(body)
    while i < n:
        if i + 2 < n and body[i + 1] == "-":
            lo_c, hi_c = body[i], body[i + 2]
            if lo_c <= hi_c:
                for code in range(ord(lo_c), ord(hi_c) + 1):
                    chars.add(chr(code))
                i += 3
                continue
        chars.add(body[i])
        i += 1
    return negate, chars


def _parse_pattern(pattern):
    tokens = []
    i, n = 0, len(pattern)
    while i < n:
        c = pattern[i]
        if c == "\\":
            if i + 1 >= n:
                raise ValueError("trailing backslash with nothing to escape")
            tokens.append(("lit", pattern[i + 1]))
            i += 2
        elif c == "*":
            tokens.append(("star", None))
            i += 1
        elif c == "?":
            tokens.append(("any", None))
            i += 1
        elif c == "[":
            end = pattern.find("]", i + 1)
            if end == -1:
                raise ValueError("unterminated character class")
            body = pattern[i + 1 : end]
            negate, chars = _parse_class(body)
            tokens.append(("class", (negate, chars)))
            i = end + 1
        else:
            tokens.append(("lit", c))
            i += 1
    return tokens
