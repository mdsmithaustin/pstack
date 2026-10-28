#!/usr/bin/env python3
"""Replace TLC's 13- to 19-digit state fingerprints and seeds in the statechart corpus with short IDs.

skill-ci's PII scan reads a Luhn-valid run of 13 to 19 digits as a payment card number.
Within one corpus case, each long integer maps to the same short ID in every file, so state
references stay consistent. The tests compare only chart.mmd and report.md with TLC's output,
and cli.test.ts checks that state IDs do not change either. Rerun after a sync that changes
the corpus. A second run changes nothing.
"""

import re
import sys
from pathlib import Path

CORPUS = Path(__file__).resolve().parent.parent / "tests/skills/statechart/scripts/test/corpus"
LONG = re.compile(r"(?<![0-9A-Za-z])-?\d{13,19}(?![0-9A-Za-z])")


def renumber(case: Path) -> int:
    ids: dict[str, str] = {}
    changed = 0
    for file in sorted(case.iterdir()):
        if file.suffix not in {".dot", ".out"}:
            continue
        text = file.read_text(encoding="utf-8")
        new = LONG.sub(lambda m: ids.setdefault(m.group(), str(100001 + len(ids))), text)
        if new != text:
            file.write_text(new, encoding="utf-8")
            changed += 1
    return changed


def main() -> int:
    changed = sum(renumber(case) for case in sorted(CORPUS.iterdir()) if case.is_dir())
    print(f"renumbered {changed} file(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
