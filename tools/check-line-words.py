#!/usr/bin/env python3
"""Fail when a line of skill Markdown runs past the word limit.

A long line packs several cases into one block, and a reader that skims it keeps the start and the end.
PORTING.md records the reference suites used to choose the limit. Lines inside a code fence,
table rows, block quotes, and headings are not instructions and are not counted.
"""
import argparse
import re
import subprocess
import sys
from pathlib import Path

LIMIT = 150
SKIPPED_LEADS = ("|", ">")
FENCES = ("```", "~~~")
HEADING = re.compile(r"#{1,6}( |$)")


def long_lines(text, limit=LIMIT):
    """(line number, word count) for each counted line over the limit."""
    found, fence = [], None
    for number, line in enumerate(text.split("\n"), 1):
        lead = line.lstrip()
        if fence is None and lead.startswith(FENCES):
            fence = lead[:3]
            continue
        if fence is not None:
            if lead.startswith(fence):
                fence = None
            continue
        if lead.startswith(SKIPPED_LEADS) or HEADING.match(lead):
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
