import pytest

from textwrap_util import wrap_text


def test_only_whitespace_returns_empty():
    assert wrap_text("   \n\t  ", 10) == []


def test_overlong_word_on_own_line():
    assert wrap_text("a supercalifragilisticexpialidocious word", 10) == [
        "a",
        "supercalifragilisticexpialidocious",
        "word",
    ]


def test_multiple_spaces_collapsed():
    assert wrap_text("hello    world", 20) == ["hello world"]


def test_tabs_and_newlines_as_separators():
    assert wrap_text("a\tb\nc", 10) == ["a b c"]


def test_exact_width_fit():
    assert wrap_text("aa bb", 5) == ["aa bb"]


def test_exact_width_boundary_split():
    assert wrap_text("aa bb", 4) == ["aa", "bb"]


def test_negative_width_raises():
    with pytest.raises(ValueError):
        wrap_text("hello", -5)


def test_non_integer_width_raises():
    with pytest.raises(ValueError):
        wrap_text("hello", 3.5)


def test_no_line_has_leading_or_trailing_whitespace():
    lines = wrap_text("  the   quick brown   fox  ", 9)
    for line in lines:
        assert line == line.strip()
        assert line != ""
