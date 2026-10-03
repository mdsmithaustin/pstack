import argparse
import sys

from .load import load
from .report import count_by_team


def main(argv=None):
    parser = argparse.ArgumentParser(prog="roster", description="Count members per team.")
    parser.add_argument("path")
    args = parser.parse_args(argv)
    for team, n in count_by_team(load(args.path)):
        print(f"{n:>4}  {team}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
