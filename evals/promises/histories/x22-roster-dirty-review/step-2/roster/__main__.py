import argparse
import sys

from .load import load
from .report import count_by_team, top_teams


def main(argv=None):
    parser = argparse.ArgumentParser(prog="roster", description="Count members per team.")
    parser.add_argument("path")
    parser.add_argument("--top", type=int, help="show only the N largest teams")
    args = parser.parse_args(argv)
    rows = load(args.path)
    teams = top_teams(rows, args.top) if args.top else count_by_team(rows)
    for team, n in teams:
        print(f"{n:>4}  {team}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
