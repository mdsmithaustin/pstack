"""Precheck for judged document cases: the deliverable is present and non-empty.

The judge decides the verdict. This oracle only refuses a run that delivered
nothing to judge. A file case must return the named file inside a
<file path="..."> block of the final message. A reply case must say something.
The project is ignored; regrade passes None for a pasted case.
"""
from shared import parse_files

DOCUMENT = "ops/premortem.md"


def document_present(answer, project):
    if not parse_files(answer).get(DOCUMENT, "").strip():
        return [f"the final message holds no {DOCUMENT}"]
    return []


def reply_present(answer, project):
    if not answer.strip():
        return ["the final message is empty"]
    return []


CHECKS = {
    "tally-push-hook-rollout": document_present,
    "ledgerd-changelog-gate": document_present,
    "tally-retry-bump": reply_present,
}
