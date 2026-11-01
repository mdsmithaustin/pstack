import argparse
import sys

from strides.log import read_runs
from strides.streaks import MUTANT, longest_streaks
from strides.totals import totals


def main(argv=None):
    parser = argparse.ArgumentParser(prog="strides")
    commands = parser.add_subparsers(dest="command", required=True)
    totals_command = commands.add_parser("totals", help="total kilometres per member")
    totals_command.add_argument("log")
    streaks_command = commands.add_parser("streaks", help="longest streak per member")
    streaks_command.add_argument("log")
    streaks_command.add_argument("--min-days", type=int, default=3)
    args = parser.parse_args(argv)
    runs = read_runs(args.log)
    if args.command == "totals":
        for name, km in totals(runs):
            print(f"{name}: {km:.1f} km")
        return 0
    if MUTANT == "empty" and not runs:
        return 0
    listed = longest_streaks(runs, args.min_days)
    if not listed:
        print("no streaks")
    for name, days in listed:
        print(f"{name}: {days}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
