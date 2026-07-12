"""Simple greedy word-wrapping utility."""


def wrap_text(text, width):
    """Greedily wrap `text` into lines of at most `width` characters.

    Rules:
    - `width` must be an integer >= 1; otherwise raise ValueError.
    - Words are maximal runs of non-whitespace characters. Any run of one
      or more whitespace characters (spaces, tabs, newlines) between
      words is treated as a single separator and collapsed to exactly one
      space when words are placed on the same output line. Leading and
      trailing whitespace in `text` is ignored entirely (not turned into
      empty words or blank lines).
    - If `text` is empty or contains only whitespace, return `[]`.
    - Build lines greedily: add words to the current line, one at a
      time, as long as `len(current_line + " " + next_word) <= width`
      (where `current_line` is empty before the first word is added, so
      the first word never needs the extra space). When the next word
      would not fit, start a new line with it.
    - A single word that is itself longer than `width` is placed alone on
      its own line, unmodified (never split or truncated). It does not
      cause a ValueError.
    - Return a list of strings, one per output line, with no leading or
      trailing whitespace on any line, and no empty lines.
    """
    if not isinstance(width, int) or width < 1:
        raise ValueError("width must be an integer >= 1")

    words = text.split()
    if not words:
        return []

    lines = []
    current = words[0]
    for word in words[1:]:
        candidate = current + " " + word
        if len(candidate) <= width:
            current = candidate
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines
