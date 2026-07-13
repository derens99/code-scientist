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
        char = pattern[i]
        if char == "\\":
            if i + 1 >= n:
                raise ValueError("trailing escape")
            tokens.append(("lit", pattern[i + 1]))
            i += 2
        elif char == "*":
            if not tokens or tokens[-1][0] != "star":
                tokens.append(("star", None))
            i += 1
        elif char == "?":
            tokens.append(("any", None))
            i += 1
        elif char == "[":
            close = pattern.find("]", i + 1)
            if close < 0:
                raise ValueError("unterminated character class")
            body = pattern[i + 1 : close]
            negate = bool(body) and body[0] in "!^"
            if negate:
                body = body[1:]
            literals = set()
            ranges = []
            j = 0
            while j < len(body):
                # A range is valid only when '-' has characters on both sides
                # and the endpoints are in ascending code-point order.
                if j + 2 < len(body) and body[j + 1] == "-" and body[j] <= body[j + 2]:
                    ranges.append((body[j], body[j + 2]))
                    j += 3
                else:
                    literals.add(body[j])
                    j += 1
            tokens.append(("class", (negate, literals, ranges)))
            i = close + 1
        else:
            tokens.append(("lit", char))
            i += 1

    from functools import lru_cache

    def class_matches(spec, char):
        negate, literals, ranges = spec
        found = char in literals or any(start <= char <= end for start, end in ranges)
        return not found if negate else found

    @lru_cache(maxsize=None)
    def match_at(token_index, text_index):
        if token_index == len(tokens):
            return text_index == len(text)
        kind, value = tokens[token_index]
        if kind == "star":
            return match_at(token_index + 1, text_index) or (
                text_index < len(text) and match_at(token_index, text_index + 1)
            )
        if text_index >= len(text):
            return False
        if kind == "any":
            return match_at(token_index + 1, text_index + 1)
        if kind == "lit":
            return value == text[text_index] and match_at(token_index + 1, text_index + 1)
        return class_matches(value, text[text_index]) and match_at(token_index + 1, text_index + 1)

    return match_at(0, 0)
