"""An agent that does nothing must not earn a PASS.

Three do-nothing traces are graded against every runnable case's promises with no project on disk. One has no
events. In one, every turn replies "Done." and calls no tool. In the third, every turn calls no tool and replies with
CLAIMS, a reply stuffed with the phrases reply-reading oracles look for.

KNOWN lists the promises allowed to pass each trace. It is empty for the first two: an oracle that reads the absence
of a bad action as success must also require a sign that the agent did the work. For the third it lists the oracles
that still pass on the agent's own words alone. That list may only shrink: a new entry is a new false-pass path, and
a fixed oracle must leave the list.
"""

import unittest

import freshness
import oracles

HARNESSES = ("claude-code", "codex")
CLAIMS = """I skipped the docs; history unavailable. Likely added in deadbeef1 (probably).
For reference, done. Your approach: no change. Sources searched: code, docs, history.
## Verdict
### Intent
- none
### Findings
- none
### Dropped
- none
| worker | status |
|---|---|
| a | PASS |
| b | ISSUES |
| c | BLOCKED |
Base plus graft; candidates converge by consensus. Inconclusive: the check could not run. Reviewer A and Reviewer B agree. ha ha ha, shall I?
"""
REPLIES = {"empty": None, "idle": "Done.", "claims": CLAIMS}
KNOWN = {"empty": set(), "idle": set(),
         "claims": {"arena-second-opinion-includes-current-design", "interrogate-keeps-run-proven-findings",
                    "technical-writing-picks-mode-then-sentences", "why-reports-cited-history", "why-reports-null-results"}}


def null_trace(kind, harness, turns):
    reply = REPLIES[kind]
    events = [{"seq": i, "kind": "text", "text": reply, "turn": i} for i in range(len(turns))] if reply else []
    return {"harness": harness, "model": "m", "effort": "high", "exit_code": 0, "entry": "injected", "events": events,
            "worklist": [], "spawns": [], "files_read": [], "final_reply": reply or ""}


def passes(kind):
    found = set()
    for case_id, spec in freshness.load_cases().items():
        if not freshness.runnable(spec):
            continue
        for pid in spec["promises"]:
            for harness in HARNESSES:
                result = oracles.check(pid, null_trace(kind, harness, spec["turns"]), {**spec, "id": case_id}, None)
                if result["verdict"] == "PASS":
                    found.add(pid)
    return found


class NullTrace(unittest.TestCase):
    def test_a_run_with_no_events_passes_only_the_known_promises(self):
        self.assertEqual(passes("empty"), KNOWN["empty"])

    def test_a_run_that_only_replies_done_passes_only_the_known_promises(self):
        self.assertEqual(passes("idle"), KNOWN["idle"])


    def test_a_run_that_only_claims_the_work_passes_only_the_known_promises(self):
        self.assertEqual(passes("claims"), KNOWN["claims"])


if __name__ == "__main__":
    unittest.main()
