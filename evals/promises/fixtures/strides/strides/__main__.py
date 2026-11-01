import argparse
import sys

from strides.log import read_runs
from strides.totals import totals


def main(argv=None):
    parser = argparse.ArgumentParser(prog="strides")
    commands = parser.add_subparsers(dest="command", required=True)
    totals_command = commands.add_parser("totals", help="total kilometres per member")
    totals_command.add_argument("log")
    args = parser.parse_args(argv)
    for name, km in totals(read_runs(args.log)):
        print(f"{name}: {km:.1f} km")
    return 0


if __name__ == "__main__":
    sys.exit(main())
