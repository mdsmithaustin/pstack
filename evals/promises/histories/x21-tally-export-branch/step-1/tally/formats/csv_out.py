"""CSV output: a header row, then one row per word.

The csv module handles quoting, so a word that holds a comma, a quote, or a
newline survives a round trip through any CSV reader. Rows end in \r\n, which
is what the csv module writes by default and what spreadsheet imports expect.
"""

import csv
import io

HEADER = ("rank", "word", "count")


def render(rows):
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(HEADER)
    for rank, (word, count) in enumerate(rows, start=1):
        writer.writerow((rank, word, count))
    return buffer.getvalue()


def parse(text):
    """Read rendered CSV back into (word, count) pairs. The tests use it for round trips."""
    reader = csv.reader(io.StringIO(text))
    header = next(reader)
    if tuple(header) != HEADER:
        raise ValueError(f"unexpected header: {header!r}")
    return [(word, int(count)) for _, word, count in reader]
