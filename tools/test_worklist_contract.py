import re
import unittest
from pathlib import Path


SKILLS = Path(__file__).resolve().parents[1] / "skills"


class WorklistContract(unittest.TestCase):
    def test_callers_use_declared_states(self):
        harness = (SKILLS / "pstack-harness/SKILL.md").read_text(encoding="utf-8")
        contract = next(
            line for line in harness.splitlines()
            if line.startswith("**Track a worklist.**")
        )
        states = {
            token.partition(":")[0]
            for token in re.findall(r"`([^`]+)`", contract)
        }
        self.assertEqual(states, {"pending", "in progress", "completed", "skipped"})

        cases = [(state, True) for state in states]
        cases.extend((f"deploy {state}", True) for state in states)
        cases.extend((label, False) for label in (
            "skip", "n/a", "progress", "deploy skip", "notskipped", "deploy n/a",
        ))
        for caller in ("poteto-mode/SKILL.md", "poteto-mode/playbooks/feature.md"):
            with self.subTest(caller=caller):
                content = (SKILLS / caller).read_text(encoding="utf-8")
                labels = re.findall(r"`([^`]+): <reason>`", content)
                self.assertTrue(labels, "caller must retain an explicit reason state")
                cases.extend((label, True) for label in labels)

        for label, expected in cases:
            with self.subTest(label=label):
                valid = any(
                    label == state or label.endswith(f" {state}")
                    for state in states
                )
                self.assertEqual(valid, expected)


if __name__ == "__main__":
    unittest.main()
