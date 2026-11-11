"""An agent that does nothing must not earn a PASS.

Two do-nothing traces are graded against every runnable case's promises with no project on disk: one with no events,
and one whose every turn replies "Done." and calls no tool. An oracle that reads the absence of a bad action as
success passes both. KNOWN lists the promises allowed to pass, and it is empty: such an oracle must also require a
sign that the agent did the work, and return INCONCLUSIVE without one.
"""

import unittest

import freshness
import oracles

HARNESSES = ("claude-code", "codex")
KNOWN = {"empty": set(), "idle": set()}


def null_trace(kind, harness, turns):
    idle = kind == "idle"
    events = [{"seq": i, "kind": "text", "text": "Done.", "turn": i} for i in range(len(turns))] if idle else []
    return {"harness": harness, "model": "m", "effort": "high", "exit_code": 0, "entry": "injected", "events": events,
            "worklist": [], "spawns": [], "files_read": [], "final_reply": "Done." if idle else ""}


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


if __name__ == "__main__":
    unittest.main()
