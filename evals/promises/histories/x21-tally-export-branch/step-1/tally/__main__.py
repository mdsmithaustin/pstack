import argparse
import sys
from collections import Counter

from . import formats


def tally(lines):
    words = Counter()
    for line in lines:
        words.update(line.lower().split())
    return words


def ranked(counts, top):
    """The top words, most common first. Ties keep the order the words first appeared in."""
    return counts.most_common(top)


def main(argv=None):
    parser = argparse.ArgumentParser(prog="tally", description="Count words in a file.")
    parser.add_argument("path")
    parser.add_argument("--top", type=int, default=5)
    parser.add_argument("--format", choices=formats.names(), default="text",
                        help="output shape (default: text)")
    parser.add_argument("--title", help="heading for markdown and html output")
    args = parser.parse_args(argv)
    if args.top < 1:
        parser.error("--top must be at least 1")
    with open(args.path, encoding="utf-8") as f:
        counts = tally(f)
    rows = ranked(counts, args.top)
    sys.stdout.write(formats.render(args.format, rows, title=args.title))
    return 0


if __name__ == "__main__":
    sys.exit(main())
