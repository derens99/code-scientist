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
    index = 0
    while index < len(pattern):
        character = pattern[index]
        if character == "\\":
            if index + 1 == len(pattern):
                raise ValueError("trailing backslash")
            tokens.append(("literal", pattern[index + 1]))
            index += 2
        elif character == "*":
            if not tokens or tokens[-1][0] != "star":
                tokens.append(("star",))
            index += 1
        elif character == "?":
            tokens.append(("any",))
            index += 1
        elif character == "[":
            end = pattern.find("]", index + 1)
            if end == -1:
                raise ValueError("unterminated character class")
            body = pattern[index + 1:end]
            negated = bool(body) and body[0] in ("!", "^")
            if negated:
                body = body[1:]

            literals = set()
            ranges = []
            body_index = 0
            while body_index < len(body):
                if body_index + 2 < len(body) and body[body_index + 1] == "-":
                    start = body[body_index]
                    stop = body[body_index + 2]
                    if start <= stop:
                        ranges.append((start, stop))
                        body_index += 3
                        continue
                literals.add(body[body_index])
                body_index += 1
            tokens.append(("class", negated, literals, ranges))
            index = end + 1
        else:
            tokens.append(("literal", character))
            index += 1

    previous = [False] * (len(text) + 1)
    previous[0] = True
    for token in tokens:
        current = [False] * (len(text) + 1)
        kind = token[0]
        if kind == "star":
            current[0] = previous[0]
            for text_index in range(1, len(text) + 1):
                current[text_index] = previous[text_index] or current[text_index - 1]
        else:
            for text_index, character in enumerate(text, 1):
                if not previous[text_index - 1]:
                    continue
                if kind == "any":
                    matches = True
                elif kind == "literal":
                    matches = character == token[1]
                else:
                    _, negated, literals, ranges = token
                    member = character in literals or any(
                        start <= character <= stop for start, stop in ranges
                    )
                    matches = not member if negated else member
                if matches:
                    current[text_index] = True
        previous = current

    return previous[len(text)]
