"""Semantic version comparison."""


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
    raise NotImplementedError
