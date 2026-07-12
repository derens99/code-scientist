"""Semantic version comparison."""

import re

_CORE_RE = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-(.+))?$")
_IDENT_RE = re.compile(r"^[0-9A-Za-z-]+$")


def _parse(version):
    match = _CORE_RE.match(version)
    if not match:
        raise ValueError(f"invalid version: {version!r}")
    major, minor, patch, prerelease = match.groups()
    idents = None
    if prerelease is not None:
        idents = prerelease.split(".")
        for ident in idents:
            if not ident or not _IDENT_RE.match(ident):
                raise ValueError(f"invalid prerelease identifier in: {version!r}")
    return int(major), int(minor), int(patch), idents


def _compare_identifier(x, y):
    x_is_num = x.isdigit()
    y_is_num = y.isdigit()
    if x_is_num and y_is_num:
        xi, yi = int(x), int(y)
        return (xi > yi) - (xi < yi)
    if x_is_num and not y_is_num:
        return -1
    if not x_is_num and y_is_num:
        return 1
    return (x > y) - (x < y)


def compare_versions(a, b):
    """Compare two semantic version strings `a` and `b`.

    Each version string has the form "MAJOR.MINOR.PATCH" or
    "MAJOR.MINOR.PATCH-PRERELEASE", where MAJOR, MINOR, and PATCH are
    non-negative integers written without leading zeros (except "0"
    itself), and PRERELEASE (when present) is a dot-separated sequence of
    one or more identifiers, each identifier being a non-empty string of
    ASCII letters, digits, and hyphens.

    If either string does not match this form (e.g. non-integer
    MAJOR/MINOR/PATCH, missing a component, empty prerelease identifier),
    raise ValueError.

    Return -1 if `a` < `b`, 0 if `a` == `b`, and 1 if `a` > `b`, using the
    following precedence rules:

    1. Compare MAJOR, then MINOR, then PATCH numerically (as integers).
       The first of these that differs determines the result.
    2. If MAJOR.MINOR.PATCH are equal: a version WITHOUT a prerelease
       has higher precedence than one WITH a prerelease (e.g. "1.0.0" >
       "1.0.0-alpha").
    3. If both have prereleases and MAJOR.MINOR.PATCH are equal, compare
       the prerelease identifiers left to right, one pair at a time:
       - An identifier consisting only of ASCII digits is compared
         numerically against another all-digit identifier.
       - A numeric identifier always has lower precedence than a
         non-numeric (alphanumeric) identifier.
       - Two non-numeric identifiers are compared as plain strings
         (ASCII lexical order).
       - If all compared identifiers are equal but one prerelease has
         fewer identifiers than the other, the one with fewer identifiers
         has lower precedence (e.g. "1.0.0-alpha" < "1.0.0-alpha.1").
       - If every identifier is equal and both have the same number of
         identifiers, the prereleases (and thus the versions) are equal.
    """
    a_major, a_minor, a_patch, a_pre = _parse(a)
    b_major, b_minor, b_patch, b_pre = _parse(b)

    for x, y in ((a_major, b_major), (a_minor, b_minor), (a_patch, b_patch)):
        if x != y:
            return 1 if x > y else -1

    if a_pre is None and b_pre is None:
        return 0
    if a_pre is None:
        return 1
    if b_pre is None:
        return -1

    for x, y in zip(a_pre, b_pre):
        cmp = _compare_identifier(x, y)
        if cmp != 0:
            return cmp

    if len(a_pre) != len(b_pre):
        return -1 if len(a_pre) < len(b_pre) else 1

    return 0
