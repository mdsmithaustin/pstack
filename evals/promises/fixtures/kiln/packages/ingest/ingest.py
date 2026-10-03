import re
from typing import NamedTuple

LINE = re.compile(r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2})\s+\[([a-z0-9-]+)\]\s+(.+)$")


class Entry(NamedTuple):
    timestamp: str
    tag: str
    text: str


def parse_line(line):
    match = LINE.match(line.strip())
    if match is None:
        return None
    timestamp, tag, text = match.groups()
    return Entry(timestamp, tag, text.strip())


def read_entries(lines):
    entries = []
    for line in lines:
        entry = parse_line(line)
        if entry is not None:
            entries.append(entry)
    return entries


def read_file(path):
    with open(path, encoding="utf-8") as handle:
        return read_entries(handle)


def count_skipped(lines):
    return sum(1 for line in lines if line.strip() and parse_line(line) is None)


def tags(entries):
    seen = []
    for entry in entries:
        if entry.tag not in seen:
            seen.append(entry.tag)
    return seen


def newest(entries):
    return max(entries, key=lambda entry: entry.timestamp, default=None)
