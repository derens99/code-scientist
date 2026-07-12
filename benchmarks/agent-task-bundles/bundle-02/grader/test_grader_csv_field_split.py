import pytest

from record_split import split_record


def test_req_01_sep_must_be_single_char():
    with pytest.raises(ValueError):
        split_record("a,b", sep=",,")
    with pytest.raises(ValueError):
        split_record("a,b", sep="")


def test_req_01b_sep_cannot_be_quote():
    with pytest.raises(ValueError):
        split_record("a,b", sep='"')


def test_req_02_empty_line():
    assert split_record("") == [""]


def test_req_03_quoted_detection_requires_leading_quote():
    # a quote not at position 0 of the field does not make it quoted
    assert split_record('a"b,c') == ['a"b', "c"]


def test_req_04_unquoted_preserves_whitespace_literally():
    assert split_record("  a  , b ") == ["  a  ", " b "]


def test_req_05_and_06_quoted_field_and_doubled_quote_escape():
    assert split_record('"ab""cd",x') == ['ab"cd', "x"]


def test_req_07_sep_inside_quotes_is_literal():
    assert split_record('"a,b",c') == ["a,b", "c"]


def test_req_08_unterminated_quote_raises():
    with pytest.raises(ValueError):
        split_record('"abc')


def test_req_09_trailing_data_after_closing_quote_raises():
    with pytest.raises(ValueError):
        split_record('"abc"x,y')


def test_req_10_consecutive_sep_makes_empty_field():
    assert split_record("a,,b") == ["a", "", "b"]


def test_req_11_trailing_sep_makes_final_empty_field():
    assert split_record("a,b,") == ["a", "b", ""]


def test_req_12_custom_separator():
    assert split_record("a|b|c", sep="|") == ["a", "b", "c"]
    assert split_record('"a|b"|c', sep="|") == ["a|b", "c"]


def test_quoted_field_at_end_of_line_no_trailing_sep():
    assert split_record('a,"bc"') == ["a", "bc"]


def test_all_quoted_fields_record():
    assert split_record('"a","b","c"') == ["a", "b", "c"]
