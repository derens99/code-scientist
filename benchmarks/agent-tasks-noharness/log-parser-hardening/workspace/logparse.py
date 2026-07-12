"""Log line parsing.

parse_log(lines) parses a list of log line strings of the form
"TIMESTAMP LEVEL MESSAGE" into a list of dicts with keys "timestamp",
"level", and "message".
"""


def parse_log(lines):
    result = []
    for line in lines:
        line = line.rstrip("\n")
        timestamp, level, message = line.split(" ", 2)
        result.append({"timestamp": timestamp, "level": level, "message": message})
    return result
