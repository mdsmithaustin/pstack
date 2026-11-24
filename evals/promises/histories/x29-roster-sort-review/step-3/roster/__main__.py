import argparse
import sys

from .load import load
from .report import count_by_team, drop_small, sort_counts


def main(argv=None):
    parser = argparse.ArgumentParser(prog="roster", description="Count members per team.")
    parser.add_argument("path")
    parser.add_argument("--sort", choices=("team", "count"), default="team")
    parser.add_argument("--min", type=int, default=1, dest="minimum")
    args = parser.parse_args(argv)
    pairs = count_by_team(load(args.path))
    # hide the teams below --min before sorting
    pairs = drop_small(pairs, args.minimum)
    for team, n in sort_counts(pairs, args.sort):
        print(f"{n:>4}  {team}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
