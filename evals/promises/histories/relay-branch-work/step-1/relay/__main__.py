import argparse
import sys

from .ingest import import_feed
from .summarize import summarize


def main(argv):
    parser = argparse.ArgumentParser(prog="relay")
    commands = parser.add_subparsers(dest="command", required=True)
    importing = commands.add_parser("import", help="write one file per record")
    importing.add_argument("feed")
    importing.add_argument("--store", required=True)
    importing.add_argument("--dedupe", action="store_true", help="drop records with a repeated id")
    summing = commands.add_parser("summarize", help="count records by kind")
    summing.add_argument("feed")
    summing.add_argument("--store", required=True)
    args = parser.parse_args(argv)

    if args.command == "import":
        count = import_feed(args.feed, args.store, args.dedupe)
        print(f"imported {count} records into {args.store}")
    else:
        for key, value in summarize(args.feed, args.store).items():
            print(f"{key}: {value}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
