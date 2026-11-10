import json
import unittest

from harnesses import codex
from test_oracles import FAIL, PASS, feature_case, grade, minimal


class CompactStart(unittest.TestCase):
    def test_normalized_start_wording_through_public_grading(self):
        cases = (
            ("playbooks/feature.md starting at abc1234", PASS),
            ("playbooks/feature.md starting\tat\tabc1234", PASS),
            ("playbooks/feature.md starting at " + "a" * 40, PASS),
            ("playbooks/feature.md start abc1234", PASS),
            ("playbooks/feature.md record start commit", PASS),
            ("playbooks/feature.md start no commits", PASS),
            ("playbooks/feature.md abc1234", FAIL),
            ("playbooks/feature.md starting at", FAIL),
            ("playbooks/feature.md starting at\nabc1234", FAIL),
            ("playbooks/feature.md starting\nat abc1234", FAIL),
            ("playbooks/feature.md starting at; unrelated abc1234", FAIL),
            ("playbooks/feature.md starting at abc123g", FAIL),
            ("playbooks/feature.md starting at abc123", FAIL),
            ("playbooks/feature.md starting at " + "a" * 41, FAIL),
            ("playbooks/feature.md starting at abc1234extra", FAIL),
            ("playbooks/feature.md starting at no commits", FAIL),
            ("starting at abc1234", FAIL),
        )
        for opening, expected in cases:
            with self.subTest(opening=opening):
                rows = [
                    {"type": "session_meta", "payload": {"cwd": "/w", "id": "control"}},
                    {"type": "response_item", "payload": {
                        "type": "function_call", "name": "update_plan", "call_id": "plan",
                        "arguments": json.dumps({"plan": [
                            {"step": opening, "status": "in_progress"},
                            {"step": "Implement and verify abc1234", "status": "pending"},
                        ]}),
                    }},
                ]
                normalized = codex.harvest_rollout(
                    "".join(json.dumps(row) + "\n" for row in rows).encode())
                trace = minimal(events=normalized["events"], worklist=normalized["worklist"], harness="codex")
                result = grade("worklist-opens-with-playbook-steps", trace, feature_case())
                self.assertEqual(result["verdict"], expected, result)


if __name__ == "__main__":
    unittest.main()
