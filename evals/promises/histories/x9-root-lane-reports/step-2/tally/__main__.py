import argparse
import sys
from collections import Counter


def tally(lines, min_length=0):
    words = Counter()
    for line in lines:
        words.update(w for w in line.lower().split() if len(w) > min_length)
    return words


def main(argv=None):
    parser = argparse.ArgumentParser(prog="tally", description="Count words in a file.")
    parser.add_argument("path")
    parser.add_argument("--top", type=int, default=5)
    parser.add_argument("--min-length", type=int, default=0, help="drop words shorter than this many characters")
    args = parser.parse_args(argv)
    with open(args.path, encoding="utf-8") as f:
        counts = tally(f, args.min_length)
    for word, n in counts.most_common(args.top):
        print(f"{n:>5}  {word}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
