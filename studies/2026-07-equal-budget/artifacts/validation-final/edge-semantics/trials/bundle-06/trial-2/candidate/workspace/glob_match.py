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
    if not isinstance(pattern, str):
        raise TypeError("pattern must be a string")
    if not isinstance(text, str):
        raise TypeError("text must be a string")

    tokens = []
    index = 0
    while index < len(pattern):
        character = pattern[index]
        if character == "\\":
            if index + 1 == len(pattern):
                raise ValueError("trailing escape")
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
            close = pattern.find("]", index + 1)
            if close == -1:
                raise ValueError("unterminated character class")
            body = pattern[index + 1 : close]
            negated = bool(body) and body[0] in "!^"
            if negated:
                body = body[1:]
            members = set()
            body_index = 0
            while body_index < len(body):
                if body_index + 2 < len(body) and body[body_index + 1] == "-":
                    start_character = body[body_index]
                    end_character = body[body_index + 2]
                    if start_character <= end_character:
                        members.update(
                            chr(codepoint)
                            for codepoint in range(
                                ord(start_character), ord(end_character) + 1
                            )
                        )
                    else:
                        members.update((start_character, "-", end_character))
                    body_index += 3
                else:
                    members.add(body[body_index])
                    body_index += 1
            tokens.append(("class", members, negated))
            index = close + 1
        else:
            tokens.append(("literal", character))
            index += 1

    reachable = {0}
    for token in tokens:
        kind = token[0]
        if kind == "star":
            start = min(reachable) if reachable else len(text) + 1
            reachable = set(range(start, len(text) + 1))
            continue
        next_reachable = set()
        for position in reachable:
            if position == len(text):
                continue
            character = text[position]
            if kind == "any":
                matches = True
            elif kind == "literal":
                matches = character == token[1]
            else:
                contained = character in token[1]
                matches = not contained if token[2] else contained
            if matches:
                next_reachable.add(position + 1)
        reachable = next_reachable
    return len(text) in reachable
