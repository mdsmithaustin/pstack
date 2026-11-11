#!/usr/bin/env python3
"""Fail when a line of skill Markdown runs past the word limit.

A long line packs several cases into one block, and a reader that skims it keeps the start and the end.
The limit is the longest line the two reference suites in PORTING.md carry. Lines inside a code fence,
table rows, block quotes, and headings are not instructions and are not counted.
"""
import argparse
import subprocess
import sys
from pathlib import Path

LIMIT = 150
SKIPPED_LEADS = ("|", "#", ">")


def long_lines(text, limit=LIMIT):
    """(line number, word count) for each counted line over the limit."""
    found, fenced = [], False
    for number, line in enumerate(text.split("\n"), 1):
        lead = line.lstrip()
        if lead.startswith("```"):
            fenced = not fenced
            continue
        if fenced or lead.startswith(SKIPPED_LEADS):
            continue
        words = len(line.split())
        if words > limit:
            found.append((number, words))
    return found


def skill_files(root):
    listed = subprocess.run(["git", "-C", str(root), "ls-files", "-z", "--", "skills"], check=True, capture_output=True).stdout
    return sorted(Path(name) for name in listed.decode().split("\0")
                  if name.endswith(".md") and "node_modules" not in Path(name).parts)


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent.parent)
    parser.add_argument("--limit", type=int, default=LIMIT)
    args = parser.parse_args()
    failures = [(path, number, words) for path in skill_files(args.root)
                for number, words in long_lines((args.root / path).read_text(encoding="utf-8"), args.limit)]
    for path, number, words in failures:
        print(f"FAIL line words: {path}:{number} has {words} words, above the limit of {args.limit}. Give each case its own line.")
    if failures:
        return 1
    print(f"PASS line words: no skill line runs past {args.limit} words.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
