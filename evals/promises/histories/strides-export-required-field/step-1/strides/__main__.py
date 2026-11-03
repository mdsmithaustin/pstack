import argparse
import sys

from strides.config import ConfigError, read_config
from strides.log import read_runs
from strides.totals import totals


def main(argv=None):
    parser = argparse.ArgumentParser(prog="strides")
    commands = parser.add_subparsers(dest="command", required=True)
    totals_command = commands.add_parser("totals", help="total kilometres per member")
    totals_command.add_argument("log", nargs="?")
    totals_command.add_argument("--config")
    args = parser.parse_args(argv)
    try:
        settings = read_config(args.config) if args.config else {}
    except ConfigError as error:
        print(f"strides: {error}", file=sys.stderr)
        return 2
    log = args.log or settings.get("log")
    if log is None:
        parser.error("give LOG, or a --config file with a log key")
    for name, km in totals(read_runs(log)):
        print(f"{name}: {km:.1f} km")
    return 0


if __name__ == "__main__":
    sys.exit(main())
