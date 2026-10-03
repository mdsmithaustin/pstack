from typing import NamedTuple

TIME_COL = 17


class Row(NamedTuple):
    timestamp: str
    text: str


class Block(NamedTuple):
    tag: str
    text: str


def header(tag, count):
    return f"== {tag} ({count}) =="


def format_row(row):
    return row.timestamp.ljust(TIME_COL) + row.text


def render_group(tag, rows):
    lines = [header(tag, len(rows))]
    lines.extend(format_row(row) for row in rows)
    return Block(tag, "\n".join(lines) + "\n")


def clip(text, width):
    if len(text) <= width:
        return text
    return text[: width - 3].rstrip() + "..."


def render_all(groups):
    return [render_group(tag, rows) for tag, rows in groups]


def line_count(block):
    return len(block.text.splitlines())
