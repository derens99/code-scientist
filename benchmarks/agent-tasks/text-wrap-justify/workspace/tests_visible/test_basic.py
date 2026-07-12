from textwrap_util import wrap_text


def test_simple_wrap():
    assert wrap_text("the quick brown fox", 10) == ["the quick", "brown fox"]


def test_empty_text():
    assert wrap_text("", 10) == []


def test_fits_one_line():
    assert wrap_text("hello world", 80) == ["hello world"]


def test_invalid_width_raises():
    import pytest

    with pytest.raises(ValueError):
        wrap_text("hello", 0)
