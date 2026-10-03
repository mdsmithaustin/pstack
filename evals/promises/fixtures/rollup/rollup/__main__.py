import csv
import os
import sys

from .export import export
from .sink import Sink


def main(argv):
    if len(argv) != 2:
        print("usage: python3 -m rollup <orders.csv> <out.csv>", file=sys.stderr)
        return 2
    source, target = argv
    busy_after = os.environ.get("ROLLUP_BUSY_AFTER")
    with open(source, newline="") as handle:
        rows = list(csv.DictReader(handle))
    with Sink(target, int(busy_after) if busy_after else None) as sink:
        count = export(rows, sink)
    print(f"wrote {count} rows to {target}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
