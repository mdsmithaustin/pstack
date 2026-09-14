#!/usr/bin/env python3
"""Grade only the edited text a case produced, never the surrounding reply.

A skill that works explains what it changed, and the explanation quotes the
very phrasing the skill removed. Scanning the whole reply therefore fails the
good run and passes the silent one. Each case asks for its final text inside a
<edited> block; everything outside those tags is commentary and is
ignored. Those tags are the artifact boundary, which is why an agent-written file
is not used: run-agent discards its temporary workspace.
"""
import pathlib
import re
import sys

FENCE = re.compile(r"<edited>\n?(.*?)\n?</edited>", re.S)

RULES = {
    "readme-paragraph-tells": {
        "need": ["41", "9", "Ledger", "0.4"],
        "ban": ["delve", "tapestry", "testament", "serves as",
                "it is important to note", "I hope this helps", "fast-paced", "—"],
        "ban_re": [r"not (just|only|merely|simply) .{1,80}?\bbut\b"],
    },
    "docs-section-protected-constructs": {
        "need": ["Supported inputs: CSV, TSV, and Parquet.",
                 "**Schema in TypeScript.**",
                 'const title = "Q3 — regional totals";',
                 "Landscape Analyzer"],
        "ban": ["Additionally", "crucial", "underscore that",
                "intricate", "interplay", "pivotal"],
        "ban_re": [],
    },
}


def main() -> int:
    case, check, output_dir = sys.argv[1], sys.argv[2], sys.argv[3]
    rules = RULES[case]
    reply = pathlib.Path(output_dir) / "output.md"
    if not reply.exists():
        print("no output.md in the run directory")
        return 1
    found = FENCE.search(reply.read_text(encoding="utf-8", errors="replace"))
    if not found:
        print("the reply contains no <edited> block, so there is no final text to grade")
        return 1
    text = found.group(1)
    if check == "fence":
        print(f"edited block present, {len(text.split())} words")
        return 0
    if check == "preserved":
        missing = [s for s in rules["need"] if s not in text]
        print("dropped from the edit: " + ", ".join(missing) if missing
              else "every required string survived the edit")
        return 1 if missing else 0
    hits = [s for s in rules["ban"] if s.lower() in text.lower()]
    hits += [r for r in rules["ban_re"] if re.search(r, text, re.I)]
    print("still present in the edit: " + ", ".join(hits) if hits
          else "no banned phrasing in the edit")
    return 1 if hits else 0


if __name__ == "__main__":
    sys.exit(main())
