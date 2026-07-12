from logparse import parse_log


def test_well_formed_lines():
    lines = [
        "2024-01-01T10:00:00 INFO Server started",
        "2024-01-01T10:00:01 ERROR Connection refused",
    ]
    result = parse_log(lines)
    assert result == [
        {"timestamp": "2024-01-01T10:00:00", "level": "INFO", "message": "Server started"},
        {"timestamp": "2024-01-01T10:00:01", "level": "ERROR", "message": "Connection refused"},
    ]


def test_empty_input():
    assert parse_log([]) == []


def test_trailing_newline_stripped():
    result = parse_log(["2024-01-01T10:00:00 DEBUG starting up\n"])
    assert result == [{"timestamp": "2024-01-01T10:00:00", "level": "DEBUG", "message": "starting up"}]
