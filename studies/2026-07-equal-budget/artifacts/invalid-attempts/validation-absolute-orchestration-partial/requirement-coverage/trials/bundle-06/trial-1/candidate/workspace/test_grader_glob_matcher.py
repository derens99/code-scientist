import pytest

from glob_match import match_glob


def test_req_01_question_mark_matches_exactly_one():
    assert match_glob("a?c", "abc") is True
    assert match_glob("a?c", "ac") is False
    assert match_glob("a?c", "abbc") is False


def test_req_02_star_matches_zero_or_more_and_consecutive_stars():
    assert match_glob("a*c", "ac") is True
    assert match_glob("a*c", "abbbc") is True
    assert match_glob("a**c", "abbbc") is True


def test_req_03_class_matches_one_char():
    assert match_glob("[abc]", "b") is True
    assert match_glob("[abc]", "d") is False
    assert match_glob("[abc]", "") is False


def test_req_03b_class_range():
    assert match_glob("[a-z]", "m") is True
    assert match_glob("[a-z]", "M") is False


def test_req_03c_class_negation():
    assert match_glob("[!a-z]", "M") is True
    assert match_glob("[!a-z]", "m") is False
    assert match_glob("[^0-9]", "5") is False


def test_req_03d_dash_at_start_or_end_is_literal():
    assert match_glob("[a-]", "-") is True
    assert match_glob("[-a]", "-") is True


def test_req_03e_unterminated_class_raises():
    with pytest.raises(ValueError):
        match_glob("[abc", "a")


def test_req_04_backslash_escapes_metachars():
    assert match_glob(r"a\*c", "a*c") is True
    assert match_glob(r"a\*c", "abc") is False


def test_req_04b_trailing_backslash_raises():
    with pytest.raises(ValueError):
        match_glob("abc\\", "abc")


def test_req_05_literal_characters():
    assert match_glob("hello", "hello") is True
    assert match_glob("hello", "world") is False


def test_req_06_empty_pattern_matches_only_empty_text():
    assert match_glob("", "") is True
    assert match_glob("", "a") is False


def test_req_07_no_regex_module_used():
    import glob_match
    import inspect

    source = inspect.getsource(glob_match)
    assert "import re" not in source
    assert "regex" not in source.lower()


def test_full_match_not_substring():
    assert match_glob("bc", "abcd") is False


def test_combined_pattern():
    assert match_glob("[A-Z]*_[0-9][0-9].log", "REPORT_42.log") is True
    assert match_glob("[A-Z]*_[0-9][0-9].log", "report_42.log") is False
