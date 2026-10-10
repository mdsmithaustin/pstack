import csv
import os
import sys

from .export import export
from .sink import Sink


def main(argv):
    # pull --header out of the arguments
    header = "--header" in argv
    argv = [arg for arg in argv if arg != "--header"]
    if len(argv) != 2:
        print("usage: python3 -m rollup [--header] <orders.csv> <out.csv>", file=sys.stderr)
        return 2
    source, target = argv
    busy_after = os.environ.get("ROLLUP_BUSY_AFTER")
    with open(source, newline="") as handle:
        rows = list(csv.DictReader(handle))
    with Sink(target, int(busy_after) if busy_after else None) as sink:
        # hand the flag to export
        count = export(rows, sink, header=header)
    print(f"wrote {count} rows to {target}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
