"""Single-line, quoted-field record splitter (a minimal CSV-record parser)."""


def split_record(line, sep=","):
    """Split one record `line` into a list of field strings.

    `sep` is the field separator character (default ","). Rules:

    1. `sep` must be a string of length exactly 1; otherwise raise
       `ValueError`. `sep` must not be the double-quote character `"`;
       otherwise raise `ValueError`.
    2. If `line` is the empty string, return `[""]` (one empty field).
    3. A field is "quoted" if and only if its very first character is a
       double quote `"`. Any other field (including one that merely
       contains a `"` somewhere in the middle) is "unquoted".
    4. An unquoted field is taken literally, character for character,
       up to (but not including) the next unescaped `sep` character or
       the end of the line. Unquoted fields support no escaping at all:
       whatever characters appear are kept exactly as written, including
       leading/trailing whitespace.
    5. A quoted field starts at the opening `"` and its content runs
       until the next `"` that is NOT immediately followed by another
       `"`. That closing `"` is consumed and is not part of the field's
       value.
    6. Inside a quoted field, a doubled quote `""` represents one
       literal `"` character in the field's value (and is consumed as a
       single unit, advancing past both characters).
    7. Inside a quoted field, occurrences of `sep` are literal characters
       that are part of the field's value, not delimiters.
    8. If a quoted field's closing `"` is never found (the quote never
       terminates), raise `ValueError`.
    9. Immediately after a quoted field's closing `"`, the very next
       character must be either `sep` or the end of the line. If any
       other character appears there, raise `ValueError` (trailing data
       after a closing quote is not allowed).
    10. Fields are separated by single `sep` characters; two consecutive
        `sep` characters (with nothing quoted between them) produce an
        empty field `""` between them.
    11. A `sep` character at the very end of `line` produces one final
        empty field `""` after it (e.g. `"a,b,"` with `sep=","` yields
        `["a", "b", ""]`).
    12. The function works identically for any valid single-character
        `sep`, not just `","`.

    Returns a list of field strings, in order.
    """
    if not isinstance(sep, str) or len(sep) != 1:
        raise ValueError("sep must be a single character")
    if sep == '"':
        raise ValueError("sep cannot be the quote character")
    if line == "":
        return [""]

    fields = []
    i, n = 0, len(line)
    while True:
        if i < n and line[i] == '"':
            i += 1
            chars = []
            closed = False
            while i < n:
                c = line[i]
                if c == '"':
                    if i + 1 < n and line[i + 1] == '"':
                        chars.append('"')
                        i += 2
                        continue
                    closed = True
                    i += 1
                    break
                chars.append(c)
                i += 1
            if not closed:
                raise ValueError("unterminated quoted field")
            if i < n and line[i] != sep:
                raise ValueError("trailing data after closing quote")
            field = "".join(chars)
        else:
            start = i
            while i < n and line[i] != sep:
                i += 1
            field = line[start:i]

        fields.append(field)

        if i < n and line[i] == sep:
            i += 1
            if i == n:
                fields.append("")
                break
            continue
        break

    return fields
