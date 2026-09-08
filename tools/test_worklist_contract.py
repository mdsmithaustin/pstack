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

        for caller in ("poteto-mode/SKILL.md", "poteto-mode/playbooks/feature.md"):
            with self.subTest(caller=caller):
                content = (SKILLS / caller).read_text(encoding="utf-8")
                labels = re.findall(r"`([^`]+): <reason>`", content)
                self.assertTrue(labels, "caller must retain an explicit reason state")
                used_states = {label.split()[-1] for label in labels}
                self.assertEqual(used_states - states, set(), "undeclared worklist states")


if __name__ == "__main__":
    unittest.main()
