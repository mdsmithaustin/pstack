import argparse
import json
import sys
from pathlib import Path

from apply_action import apply
from read_request import read
from write_state import save


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--state", required=True, type=Path)
    path = parser.parse_args().state
    try:
        request = read(sys.stdin.read())
        state = json.loads(path.read_text()) if path.exists() else {"series": {}}
        response = apply(state, request)
        save(path, state)
    except ValueError as error:
        print(json.dumps({"error": str(error)}, sort_keys=True))
        return 2
    print(json.dumps(response, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
