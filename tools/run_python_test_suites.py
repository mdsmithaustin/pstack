#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
import unittest
from pathlib import Path
from typing import Sequence


def run_suite(directory: Path, pattern: str = "test_*.py") -> bool:
    if not directory.is_dir():
        print(f"test suite directory is missing: {directory}", file=sys.stderr)
        return False
    suite = unittest.defaultTestLoader.discover(str(directory), pattern=pattern)
    count = suite.countTestCases()
    print(f"{directory}: discovered {count} tests")
    if count == 0:
        print(f"test suite is empty: {directory}", file=sys.stderr)
        return False
    return unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run non-empty Python test suites.")
    parser.add_argument("directories", nargs="+", type=Path)
    parser.add_argument("--pattern", default="test_*.py")
    values = parser.parse_args(argv)
    successful = True
    for directory in values.directories:
        if not run_suite(directory, values.pattern):
            successful = False
    return 0 if successful else 1


if __name__ == "__main__":
    raise SystemExit(main())
