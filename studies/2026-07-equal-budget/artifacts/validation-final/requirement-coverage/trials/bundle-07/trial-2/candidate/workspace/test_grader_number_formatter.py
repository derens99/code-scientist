import pytest

from num_format import format_number


def test_req_01_bool_rejected():
    with pytest.raises(TypeError):
        format_number(True)
    with pytest.raises(TypeError):
        format_number("5")


def test_req_02_nan_and_inf_raise():
    with pytest.raises(ValueError):
        format_number(float("nan"))
    with pytest.raises(ValueError):
        format_number(float("inf"))


def test_req_03_decimals_validation():
    with pytest.raises(ValueError):
        format_number(1.0, decimals=-1)
    with pytest.raises(ValueError):
        format_number(1.0, decimals=1.5)


def test_req_04_percent_multiplies_before_round_and_appends_suffix():
    assert format_number(0.4567, decimals=1, percent=True) == "45.7%"


def test_req_05_round_half_to_even():
    assert format_number(2.5, decimals=0) == "2"
    assert format_number(3.5, decimals=0) == "4"
    assert format_number(0.125, decimals=2) == "0.12"


def test_req_06_negative_sign_and_negative_zero_suppressed():
    assert format_number(-5.2, decimals=1) == "-5.2"
    assert format_number(-0.001, decimals=2) == "0.00"
    assert format_number(-0.00001, decimals=2, percent=True) == "0.00%"


def test_req_07_decimals_zero_no_dot():
    assert format_number(7.0, decimals=0) == "7"
    assert "." not in format_number(7.4, decimals=0)


def test_req_08_thousands_separator_integer_only():
    assert format_number(1234567.891, decimals=2, thousands_sep=True) == "1,234,567.89"
    assert format_number(1234567, decimals=0, thousands_sep=True) == "1,234,567"


def test_req_09_width_padding():
    s = format_number(5.0, decimals=1, width=8)
    assert s == "     5.0"
    assert len(s) == 8
    # already longer than width: unchanged
    s2 = format_number(12345.6, decimals=1, width=3)
    assert s2 == "12345.6"


def test_negative_thousands_and_percent_combo():
    assert format_number(-1234.5, decimals=1, thousands_sep=True) == "-1,234.5"
