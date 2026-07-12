from logparse import parse_log


def test_blank_and_whitespace_lines_skipped():
    lines = [
        "2024-01-01T10:00:00 INFO ok",
        "",
        "   ",
        "2024-01-01T10:00:01 INFO also ok",
    ]
    result = parse_log(lines)
    assert len(result) == 2
    assert result[0]["message"] == "ok"
    assert result[1]["message"] == "also ok"


def test_malformed_line_skipped_not_raised():
    lines = ["not a real log line", "2024-01-01T10:00:00 INFO fine"]
    result = parse_log(lines)
    assert result == [{"timestamp": "2024-01-01T10:00:00", "level": "INFO", "message": "fine"}]


def test_two_field_line_skipped():
    lines = ["2024-01-01T10:00:00 INFO"]
    assert parse_log(lines) == []


def test_level_normalized_to_uppercase():
    lines = ["2024-01-01T10:00:00 info lowercase level"]
    result = parse_log(lines)
    assert result[0]["level"] == "INFO"


def test_mixed_case_level_normalized():
    lines = ["2024-01-01T10:00:00 WaRnInG mixed case"]
    result = parse_log(lines)
    assert result[0]["level"] == "WARNING"


def test_unknown_level_skipped():
    lines = [
        "2024-01-01T10:00:00 TRACE not a real level",
        "2024-01-01T10:00:01 INFO real level",
    ]
    result = parse_log(lines)
    assert result == [{"timestamp": "2024-01-01T10:00:01", "level": "INFO", "message": "real level"}]


def test_message_internal_spacing_preserved():
    lines = ["2024-01-01T10:00:00 INFO message  with   extra    spaces"]
    result = parse_log(lines)
    assert result[0]["message"] == "message  with   extra    spaces"


def test_never_raises_on_garbage():
    lines = ["", "   ", "one", "a b"]
    result = parse_log(lines)
    assert result == []
