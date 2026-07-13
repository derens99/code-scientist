import pytest

from path_normalize import normalize_path


def test_req_01_non_str_raises_typeerror():
    with pytest.raises(TypeError):
        normalize_path(123)


def test_req_02_empty_string_raises():
    with pytest.raises(ValueError):
        normalize_path("")


def test_req_03_backslash_raises():
    with pytest.raises(ValueError):
        normalize_path("a\\b")


def test_req_04_collapse_duplicate_slashes():
    assert normalize_path("a//b///c") == "a/b/c"
    assert normalize_path("//a/b") == "/a/b"


def test_req_05_dot_segments_removed():
    assert normalize_path("a/./b/./c") == "a/b/c"


def test_req_06_dotdot_cancels_preceding_segment():
    assert normalize_path("a/b/../c") == "a/c"


def test_req_07_absolute_leading_dotdot_dropped():
    assert normalize_path("/../a") == "/a"
    assert normalize_path("/../../a/b") == "/a/b"


def test_req_08_relative_leading_dotdot_kept_in_order():
    assert normalize_path("../../a") == "../../a"
    assert normalize_path("../a/../../b") == "../../b"


def test_req_09_trailing_slash_removed():
    assert normalize_path("a/b/") == "a/b"
    assert normalize_path("a/b//") == "a/b"


def test_req_10_root_normalizes_to_root():
    assert normalize_path("/") == "/"
    assert normalize_path("//") == "/"


def test_req_11_relative_empty_result_is_dot():
    assert normalize_path("a/..") == "."
    assert normalize_path("./") == "."
    assert normalize_path("././.") == "."


def test_req_12_absolute_starts_with_single_slash():
    result = normalize_path("/a/b/c")
    assert result.startswith("/") and not result.startswith("//")


def test_req_13_whitespace_segment_kept_literally():
    assert normalize_path("a/ /b") == "a/ /b"


def test_multi_dotdot_cancel_multiple_segments():
    assert normalize_path("a/b/c/../../d") == "a/d"
