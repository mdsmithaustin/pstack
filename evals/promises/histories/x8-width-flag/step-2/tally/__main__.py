import argparse
import sys

from tally.core import tally
from tally.fmt import format_line


def main(argv=None):
    parser = argparse.ArgumentParser(prog="tally", description="Count words in a file.")
    parser.add_argument("path")
    parser.add_argument("--top", type=int, default=5)
    parser.add_argument("--width", type=int, default=5, help="columns for the count")
    args = parser.parse_args(argv)
    with open(args.path, encoding="utf-8") as f:
        counts = tally(f)
    for word, n in counts.most_common(args.top):
        print(format_line(word, n, args.width))
    return 0


if __name__ == "__main__":
    sys.exit(main())
