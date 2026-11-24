import argparse
import sys
from collections import Counter


def tally(lines):
    words = Counter()
    for line in lines:
        words.update(line.lower().split())
    return words


def pair_counts(lines):
    pairs = Counter()
    for line in lines:
        words = line.lower().split()
        pairs.update(" ".join(pair) for pair in zip(words, words[1:]))
    return pairs


def main(argv=None):
    parser = argparse.ArgumentParser(prog="tally", description="Count words in a file.")
    parser.add_argument("path")
    parser.add_argument("--top", type=int, default=5)
    parser.add_argument("--min-count", type=int, default=1, help="hide words seen fewer than N times")
    parser.add_argument("--pairs", action="store_true", help="count adjacent word pairs instead of single words")
    args = parser.parse_args(argv)
    with open(args.path, encoding="utf-8") as f:
        counts = pair_counts(f) if args.pairs else tally(f)
    for word, n in counts.most_common(args.top):
        if n >= args.min_count:
            print(f"{n:>5}  {word}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
