import csv

from ..retry import Transient


def load(path):
    with open(path, newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise Transient(f"{path} has no rows")
    lines = []
    for row in rows:
        lines.append(";".join(f"{key}={value}" for key, value in row.items()))
    return "\n".join(lines) + "\n"
