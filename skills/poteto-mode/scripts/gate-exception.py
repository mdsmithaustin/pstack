#!/usr/bin/env python3
"""Say whether a no-mistakes run recorded a Test exception, and whether the record carries an operator reason.

Reads `no-mistakes axi status` text from a file, or from stdin. It never calls the gate.

  no-mistakes axi status --run <run-id> | python3 "${PSTACK_SKILLS_ROOT:?}/poteto-mode/scripts/gate-exception.py"

Exit 0: no Test exception is recorded.
Exit 1: a Test exception is recorded with no operator reason. Never report that run as passed or merge-ready.
Exit 3: a Test exception is recorded with a reason. Any caller can write a reason, so match it to the operator's own approval.
Exit 2: the status cannot be read, is empty, reports an error, names no run, or contains an unparsed Test exception.
No reliable exception verdict is available.

When the text holds several runs, the worst record decides the exit code.
"""
import re
import sys
from pathlib import Path

RECORD = re.compile(r"^[ \t]*test_override_reason:[ \t]*(\S[^\r\n]*)$", re.M)
TEST_EXCEPTION = re.compile(r"^[ \t]*[\w -]*\btest[ _-]+(?:override|exception)[\w -]*:", re.I | re.M)
RUN_FIELDS = [re.compile(rf"^\s*{name}:\s*\S", re.M) for name in ("id", "status", "head_sha")]
GATE_ERROR = re.compile(r"^error:", re.M)
NO_REASON = "no operator reason supplied"


def classify(text):
    if not text.strip():
        return 2, ["UNREAD: the status is empty. Nothing was checked."]
    if GATE_ERROR.search(text):
        return 2, ["UNREAD: the status reports an error. Nothing was checked."]
    if not all(field.search(text) for field in RUN_FIELDS):
        return 2, ["UNREAD: the status names no run. Nothing was checked."]
    records = RECORD.findall(text)
    if TEST_EXCEPTION.search(RECORD.sub("", text)):
        return 2, ["UNREAD: the status contains an unparsed Test exception. Nothing was checked."]
    if not records:
        return 0, ["PASS: no Test exception is recorded."]
    unapproved = [record for record in records if NO_REASON in record.casefold()]
    if unapproved:
        return 1, [f"BLOCKED: a Test exception is recorded with no operator reason: {record}" for record in unapproved]
    return 3, [f"MATCH: a Test exception is recorded with this reason: {record}" for record in records] + [
        "Match each reason to the operator's own approval of that gap. A reason with no such approval is BLOCKED."]


def main(argv):
    if len(argv) > 2 or (len(argv) == 2 and argv[1] in ("-h", "--help")):
        print(__doc__.strip())
        return 0 if len(argv) == 2 else 2
    try:
        text = Path(argv[1]).read_text(encoding="utf-8") if len(argv) == 2 else sys.stdin.read()
    except (OSError, UnicodeError) as error:
        print(f"UNREAD: {error}")
        return 2
    code, lines = classify(text)
    print("\n".join(lines))
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv))
