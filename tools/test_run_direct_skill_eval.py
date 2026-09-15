from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from run_direct_skill_eval import command_plan


class DirectSkillEvalRunnerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo = self.root / "repo"
        self.skill_ci = self.root / "skill-ci"
        manifest = self.repo / "evals" / "demo" / "shared-benchmark.json"
        manifest.parent.mkdir(parents=True)
        manifest.write_text("{}", encoding="utf-8")
        runner = self.skill_ci / "tools" / "run_runner.py"
        runner.parent.mkdir(parents=True)
        runner.write_text("", encoding="utf-8")

    def plan(self, **changes: object) -> list[list[str]]:
        values = {
            "repo": self.repo,
            "skill_ci": self.skill_ci,
            "skill": "demo",
            "split": "tune",
            "agent": "codex",
            "model": "candidate",
            "judge_backend": "claude",
            "judge_model": "judge",
            "output": self.root / "out",
            "runs": 3,
            "judge_runs": 3,
            "timeout": 240,
        }
        values.update(changes)
        return command_plan(**values)

    def test_plan_runs_complete_pipeline_on_requested_split(self) -> None:
        commands = self.plan(split="holdback")
        self.assertEqual([command[6] for command in commands], [
            "validate", "audit-manifest", "prepare", "run-agent", "grade", "judge", "benchmark", "report",
        ])
        for command in commands:
            if command[6] in {"prepare", "grade", "judge", "benchmark"}:
                self.assertIn("holdback", command)
        self.assertIn("--strict-holdback", commands[0])
        self.assertIn("--allow-scripts", commands[4])
        self.assertIn("--allow-scripts", commands[6])
        self.assertIn("--judge-results", commands[6])

    def test_codex_answer_uses_claude_judge_adapters(self) -> None:
        commands = self.plan()
        self.assertIn("--codex-cmd", commands[3])
        self.assertIn("--claude-bin", commands[5])

    def test_claude_answer_uses_codex_judge_adapters(self) -> None:
        commands = self.plan(agent="claude", judge_backend="codex")
        self.assertIn("--claude-bin", commands[3])
        self.assertIn("--codex-cmd", commands[5])

    def test_rejects_same_family_answer_and_judge(self) -> None:
        with self.assertRaisesRegex(ValueError, "different model families"):
            self.plan(agent="codex", judge_backend="codex")


if __name__ == "__main__":
    unittest.main()
