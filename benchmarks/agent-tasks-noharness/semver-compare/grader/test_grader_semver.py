import pytest

from semver import compare_versions


def test_release_beats_prerelease():
    assert compare_versions("1.0.0", "1.0.0-alpha") == 1
    assert compare_versions("1.0.0-alpha", "1.0.0") == -1


def test_prerelease_numeric_field_comparison():
    assert compare_versions("1.0.0-alpha.1", "1.0.0-alpha.2") == -1
    assert compare_versions("1.0.0-alpha.9", "1.0.0-alpha.10") == -1


def test_numeric_lower_precedence_than_alphanumeric():
    assert compare_versions("1.0.0-alpha.1", "1.0.0-alpha.beta") == -1


def test_alphanumeric_string_comparison():
    assert compare_versions("1.0.0-alpha", "1.0.0-beta") == -1


def test_shorter_prerelease_lower_precedence():
    assert compare_versions("1.0.0-alpha", "1.0.0-alpha.1") == -1


def test_equal_prereleases():
    assert compare_versions("1.0.0-alpha.1", "1.0.0-alpha.1") == 0


def test_malformed_missing_component_raises():
    with pytest.raises(ValueError):
        compare_versions("1.2", "1.2.0")


def test_malformed_non_integer_raises():
    with pytest.raises(ValueError):
        compare_versions("1.x.0", "1.2.0")


def test_leading_zero_raises():
    with pytest.raises(ValueError):
        compare_versions("1.02.0", "1.2.0")


def test_empty_prerelease_identifier_raises():
    with pytest.raises(ValueError):
        compare_versions("1.0.0-alpha..1", "1.0.0")


def test_numeric_field_not_confused_with_length():
    # "10" > "9" numerically even though "10" is longer as a string
    assert compare_versions("1.0.0-10", "1.0.0-9") == 1
