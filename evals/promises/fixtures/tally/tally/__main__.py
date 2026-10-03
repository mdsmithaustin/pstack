import argparse
import sys
from collections import Counter


def tally(lines):
    words = Counter()
    for line in lines:
        words.update(line.lower().split())
    return words


def main(argv=None):
    parser = argparse.ArgumentParser(prog="tally", description="Count words in a file.")
    parser.add_argument("path")
    parser.add_argument("--top", type=int, default=5)
    args = parser.parse_args(argv)
    with open(args.path, encoding="utf-8") as f:
        counts = tally(f)
    for word, n in counts.most_common(args.top):
        print(f"{n:>5}  {word}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
