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
        char = pattern[index]
        if char == "\\":
            if index + 1 == len(pattern):
                raise ValueError("trailing escape")
            tokens.append(("literal", pattern[index + 1]))
            index += 2
        elif char == "*":
            if not tokens or tokens[-1][0] != "star":
                tokens.append(("star", None))
            index += 1
        elif char == "?":
            tokens.append(("any", None))
            index += 1
        elif char == "[":
            closing = pattern.find("]", index + 1)
            if closing == -1:
                raise ValueError("unterminated character class")
            body = pattern[index + 1 : closing]
            negated = bool(body) and body[0] in "!^"
            if negated:
                body = body[1:]

            members = set()
            body_index = 0
            while body_index < len(body):
                if (
                    body_index + 2 < len(body)
                    and body[body_index + 1] == "-"
                    and body[body_index] <= body[body_index + 2]
                ):
                    start = ord(body[body_index])
                    end = ord(body[body_index + 2])
                    members.update(chr(codepoint) for codepoint in range(start, end + 1))
                    body_index += 3
                else:
                    members.add(body[body_index])
                    body_index += 1
            tokens.append(("class", (members, negated)))
            index = closing + 1
        else:
            tokens.append(("literal", char))
            index += 1

    possible = {0}
    for token_type, value in tokens:
        next_possible = set()
        if token_type == "star":
            for position in possible:
                next_possible.update(range(position, len(text) + 1))
        else:
            for position in possible:
                if position == len(text):
                    continue
                char = text[position]
                if token_type == "any":
                    matched = True
                elif token_type == "literal":
                    matched = char == value
                else:
                    members, negated = value
                    matched = (char in members) != negated
                if matched:
                    next_possible.add(position + 1)
        possible = next_possible
        if not possible:
            return False

    return len(text) in possible
