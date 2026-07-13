"""POSIX-style forward-slash path normalizer."""


def normalize_path(path):
    """Normalize a forward-slash path string.

    Rules:

    1. `path` must be a `str`; otherwise raise `TypeError`.
    2. `path` must not be the empty string `""`; otherwise raise
       `ValueError`.
    3. If `path` contains any backslash `\\` character anywhere,
       raise `ValueError` (Windows-style paths are rejected; only
       forward slashes are accepted as separators).
    4. Any run of two or more consecutive `/` characters, anywhere in
       the path (including at the very start), collapses to a single
       `/`.
    5. A segment equal to `.` is removed (it never appears, and never
       contributes, to the output).
    6. A segment equal to `..` cancels the nearest preceding real
       (non-`.`, non-`..`) segment that has already been kept, removing
       both of them.
    7. For an ABSOLUTE path (one starting with `/`), a `..` segment that
       has no preceding real segment to cancel (i.e. it would go above
       the root) is simply dropped — it contributes nothing to the
       output.
    8. For a RELATIVE path (one that does not start with `/`), a `..`
       segment that has no preceding real segment to cancel is kept
       literally in the output, in its original position relative to
       other kept `..` segments (so e.g. `"../../a"` stays
       `"../../a"`).
    9. A trailing `/` in the input (other than when the whole path is
       just `/`) is removed from the output; it never produces a
       trailing `/` or an extra empty segment.
    10. The root path `/` (and any input that collapses to just the
        root under rule 4, such as `"//"`) normalizes to `/`.
    11. If, after resolving `.`/`..` segments, a RELATIVE path has no
        segments left, the result is `"."` (not an empty string).
    12. An ABSOLUTE path in the output always begins with exactly one
        `/` character.
    13. Segments that are neither empty, `.`, nor `..` (including
        segments made up entirely of whitespace, such as `" "`) are
        kept literally and are never trimmed or otherwise modified.

    Returns the normalized path string.
    """
    if not isinstance(path, str):
        raise TypeError("path must be a string")
    if path == "":
        raise ValueError("path must not be empty")
    if "\\" in path:
        raise ValueError("backslashes are not allowed")

    absolute = path.startswith("/")
    kept = []
    for segment in path.split("/"):
        if segment == "" or segment == ".":
            continue
        if segment == "..":
            if kept and kept[-1] != "..":
                kept.pop()
            elif not absolute:
                kept.append(segment)
        else:
            kept.append(segment)

    if absolute:
        return "/" + "/".join(kept)
    return "/".join(kept) or "."
