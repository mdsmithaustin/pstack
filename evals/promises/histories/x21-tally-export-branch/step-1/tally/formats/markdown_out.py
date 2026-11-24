"""Markdown output: an optional heading, then a table with a rank, word, and count column.

The count column is right-aligned with the `---:` delimiter so the numbers line
up in renderers that honour column alignment.
"""

HEADER = "| Rank | Word | Count |"
DELIMITER = "| ---: | --- | ---: |"


def cell(text):
    """Make text safe inside a table cell.

    Backslashes are doubled so a word cannot start an escape sequence. A newline
    would end the row early, so it becomes a space.
    """
    return str(text).replace("\\", "\\\\").replace("\n", " ")


def render(rows, *, title=None):
    lines = []
    if title:
        lines.append(f"## {cell(title)}")
        lines.append("")
    lines.append(HEADER)
    lines.append(DELIMITER)
    for rank, (word, count) in enumerate(rows, start=1):
        lines.append(f"| {rank} | {cell(word)} | {count} |")
    if not rows:
        lines.append("| | (no words) | |")
    return "\n".join(lines) + "\n"
