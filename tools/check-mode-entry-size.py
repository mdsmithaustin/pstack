#!/usr/bin/env python3
"""Enforce repository byte budgets for explicitly selected mode entries."""

import argparse
import sys
from pathlib import Path


ENTRY_BUDGETS = {"skills/poteto-mode/SKILL.md": 16_000}

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
args = parser.parse_args()
failed = False
for name, limit in ENTRY_BUDGETS.items():
    try:
        content = (args.root / name).read_bytes()
        content.decode("utf-8")
    except (OSError, UnicodeError) as error:
        print(f"ERROR mode entry: {name}: {error}", file=sys.stderr)
        failed = True
        continue
    size = len(content)
    passed = size <= limit
    print(f"{'PASS' if passed else 'FAIL'} mode entry: {name}: {size}/{limit} UTF-8 bytes")
    failed |= not passed
sys.exit(int(failed))
