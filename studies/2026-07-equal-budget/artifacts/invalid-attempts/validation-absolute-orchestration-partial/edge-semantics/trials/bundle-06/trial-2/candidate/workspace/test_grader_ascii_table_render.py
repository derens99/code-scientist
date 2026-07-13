import pytest

from table_render import render_table


def test_req_01_empty_headers_and_type_check():
    with pytest.raises(ValueError):
        render_table([], [])
    with pytest.raises(TypeError):
        render_table(["a", 1], [])


def test_req_02_row_length_and_type_checks():
    with pytest.raises(ValueError):
        render_table(["a", "b"], [["x"]])
    with pytest.raises(TypeError):
        render_table(["a"], [[1]])


def test_req_03_alignments_validation():
    with pytest.raises(ValueError):
        render_table(["a", "b"], [], alignments=["left"])
    with pytest.raises(ValueError):
        render_table(["a"], [], alignments=["up"])


def test_req_04_max_col_width_validation():
    with pytest.raises(ValueError):
        render_table(["a"], [], max_col_width=3)


def test_req_05_len_based_width_no_unicode_special_case():
    lines = render_table(["h"], [["\U0001F600"]])
    # emoji has len() == 1, so column width should be 1 (== header width)
    assert lines[1] == "| h |"
    assert lines[3] == "| \U0001F600 |"


def test_req_06_truncation_with_ellipsis():
    lines = render_table(["h"], [["abcdefgh"]], max_col_width=6)
    assert lines[3] == "| abc... |"


def test_req_07_width_computed_after_truncation():
    lines = render_table(["header"], [["abcdefgh"]], max_col_width=6)
    # width should be 6 (max_col_width), not len("header")=6 or 8
    assert lines[0] == "+--------+"


def test_req_08_padding_and_alignment():
    lines = render_table(["a"], [["x"]], alignments=["right"])
    assert lines[3] == "| x |"
    lines2 = render_table(["ab"], [["x"]], alignments=["right"])
    assert lines2[3] == "|  x |"


def test_req_09_border_format():
    lines = render_table(["ab", "c"], [["x", "y"]])
    assert lines[0] == "+----+---+"
    assert lines[0] == lines[2] == lines[-1]


def test_req_10_line_order_and_empty_rows():
    lines = render_table(["a"], [])
    assert len(lines) == 4
    assert lines[0].startswith("+") and lines[2].startswith("+") and lines[3].startswith("+")
    assert lines[1] == "| a |"


def test_req_11_single_column_table():
    lines = render_table(["only"], [["v1"], ["v2"]])
    assert lines == ["+------+", "| only |", "+------+", "| v1   |", "| v2   |", "+------+"]


def test_center_alignment():
    lines = render_table(["ab"], [["x"]], alignments=["center"])
    assert lines[3] == "| x  |"
