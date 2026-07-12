"""Log line parsing.

parse_log(lines) parses a list of log line strings of the form
"TIMESTAMP LEVEL MESSAGE" into a list of dicts with keys "timestamp",
"level", and "message".
"""

_VALID_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR"}


def parse_log(lines):
    result = []
    for line in lines:
        stripped_line = line.rstrip("\n")
        if not stripped_line.strip():
            continue

        parts = stripped_line.split(" ", 2)
        if len(parts) < 3:
            continue

        timestamp, level, message = parts
        level = level.upper()
        if level not in _VALID_LEVELS:
            continue

        result.append({"timestamp": timestamp, "level": level, "message": message})
    return result
