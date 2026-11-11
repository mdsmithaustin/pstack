#!/usr/bin/env python3
"""Report the Test exception a no-mistakes run records, from saved gate output. It never calls the gate.

  no-mistakes axi rounds --run <run-id> --step test --json > <rounds-file>
  no-mistakes axi status --run <run-id> | python3 "${PSTACK_SKILLS_ROOT:?}/poteto-mode/scripts/gate-exception.py" --rounds <rounds-file>

It reads `axi status --run` text from a file or from stdin. The status carries `test_override_reason` only until
a later Test round of the same run, which drops it. With --rounds it also reads the Test round history
(schema_version 1), which keeps each round's findings and summary but not the reason.

Exit 0: the status read now records no Test exception. With --rounds, no Test round left a finding unfixed either.
  This never proves that Test drove every scenario. A round can end with no finding while scenarios stay undriven,
  so read the round summaries it prints. Without --rounds, an exception in an earlier round is not ruled out.
Exit 1: a Test exception is recorded with no operator reason. Never report that run as passed or merge-ready.
Exit 3: a Test exception is recorded with a reason, or a Test round left a finding unfixed and the status no longer
  shows how it was answered. Any caller can write a reason, so match it to the operator's own approval of that gap.
Exit 2: no verdict. The input is unreadable, a gate error, `axi status --branch` output, or an unparsed Test
  exception, or the run ended cancelled or failed with no exception on record.

When the text holds several runs, the worst record decides the exit code.
"""
import argparse
import json
import re
import sys
from pathlib import Path

RECORD = re.compile(r"^[ \t]*test_override_reason:[ \t]*(\S[^\r\n]*)$", re.M)
TEST_EXCEPTION = re.compile(r"^[ \t]*[\"']?[\w -]*\btest[ _-]+(?:override|exception)[\w -]*[\"']?:", re.I | re.M)
RUN_FIELDS = {name: re.compile(rf"^[ \t]*{name}:[ \t]*\"?([^\"\s]+)", re.M) for name in ("id", "status", "head_sha")}
GATE_ERROR = re.compile(r"^error:[ \t]*(.*)$", re.M)
BRANCH_FORM = re.compile(r"^schema:[ \t]*branch-publication", re.M)
APPROVED = "Test exception approved:"
NO_REASON = "no operator reason supplied"
ENDED = {"cancelled", "failed"}
NOT_PROVEN = "Not proven: that Test drove every scenario."


def reason(record):
    value = record.strip().strip("\"'").rpartition(APPROVED)[2]
    return value.replace("\\n", " ").strip()


def unfixed(rounds):
    return [
        f"Test round {entry['round']} left finding {finding['id']} ({finding['action']}) unfixed: {finding['description']}"
        for entry in rounds
        for finding in entry["findings"] or []
        if finding["action"] != "no-op" and finding["id"] not in (entry["selected_finding_ids"] or [])
    ]


def classify(text, history=None):
    if BRANCH_FORM.search(text):
        return 2, ["UNREAD: this is `axi status --branch` output, which never carries a Test exception record. "
                   "Pass `no-mistakes axi status --run <run-id>` output. Nothing was checked."]
    fields = {name: list(dict.fromkeys(pattern.findall(text))) for name, pattern in RUN_FIELDS.items()}
    error = GATE_ERROR.search(text)
    if not all(fields.values()):
        cause = f"the gate returned an error: {error.group(1)}" if error else "the status names no run"
        return 2, [f"UNREAD: {cause}. Nothing was checked."]
    ended = sorted(ENDED.intersection(fields["status"]))
    if error and not ended:
        return 2, ["UNREAD: the status reports an error beside a run that has not ended. Nothing was checked."]
    records = RECORD.findall(text)
    if TEST_EXCEPTION.search(RECORD.sub("", text)):
        return 2, ["UNREAD: the status contains an unparsed Test exception. Nothing was checked."]
    run = f"run {', '.join(fields['id'])} ({', '.join(fields['status'])})"
    summaries, dropped = [], []
    if history is not None:
        try:
            if (history["schema_version"], history["step"]) != (1, "test") or history["run_id"] not in fields["id"]:
                raise ValueError
            rounds = history["rounds"] or []
            summaries = [f"Test round {entry['round']} summary: {entry['summary']}" for entry in rounds]
            dropped = unfixed(rounds)
        except (KeyError, TypeError, ValueError):
            return 2, ["UNREAD: the round history is not schema_version 1 Test rounds of the run the status names. Nothing was checked."]
    unapproved = [record for record in records if not reason(record) or NO_REASON in reason(record).casefold()]
    if unapproved:
        return 1, [f"BLOCKED: {run} records a Test exception with no operator reason: {record}" for record in unapproved] + summaries
    if records:
        return 3, [f"MATCH: {run} records a Test exception with this reason: {reason(record)}" for record in records] + [
            "Match each reason to the operator's own approval of that gap. A reason with no such approval is BLOCKED."] + summaries
    if dropped:
        return 3, [f"MATCH: {run}: the status read now carries no Test exception record, but {line}" for line in dropped] + [
            "The round history keeps no reason. Match each finding to the operator's own approval of that gap. "
            "A finding with no such approval is BLOCKED."] + summaries
    if ended:
        return 2, [f"NO VERDICT: {run} ended {' and '.join(ended)} with no Test exception on record. "
                   "An ended run is no verdict on Test. Check the run that replaced it."] + summaries
    if history is None:
        return 0, [f"NO RECORD: {run}: the status read now records no Test exception. Not read: the Test round history, "
                   f"so an exception in an earlier Test round of this run is not ruled out. Pass --rounds. {NOT_PROVEN}"]
    return 0, [f"NO RECORD: {run}: the status read now records no Test exception, and none of its {len(summaries)} "
               f"Test round(s) left a finding unfixed. {NOT_PROVEN} Read each summary."] + summaries


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("status", nargs="?", help="saved `no-mistakes axi status --run <run-id>` text (default: stdin)")
    parser.add_argument("--rounds", help="saved `no-mistakes axi rounds --run <run-id> --step test --json` output")
    args = parser.parse_args(argv[1:])
    try:
        text = Path(args.status).read_text(encoding="utf-8") if args.status else sys.stdin.read()
        history = json.loads(Path(args.rounds).read_text(encoding="utf-8")) if args.rounds else None
    except (OSError, ValueError) as error:
        print(f"UNREAD: {error}. Nothing was checked.")
        return 2
    code, lines = classify(text, history)
    print("\n".join(lines))
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv))
