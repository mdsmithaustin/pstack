import argparse
import json
import sys
from collections import Counter


def tally(lines):
    words = Counter()
    for line in lines:
        words.update(line.lower().split())
    return words


def to_json(counts, top):
    return json.dumps([{"word": word, "count": n} for word, n in counts.most_common(top)])


def main(argv=None):
    parser = argparse.ArgumentParser(prog="tally", description="Count words in a file.")
    parser.add_argument("path")
    parser.add_argument("--top", type=int, default=5)
    parser.add_argument("--json", action="store_true", help="print the counts as JSON")
    args = parser.parse_args(argv)
    with open(args.path, encoding="utf-8") as f:
        counts = tally(f)
    if args.json:
        print(to_json(counts, args.limit))
        return 0
    for word, n in counts.most_common(args.top):
        print(f"{n:>5}  {word}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
