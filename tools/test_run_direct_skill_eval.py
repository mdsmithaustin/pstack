from __future__ import annotations

import json
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
            "lane": "isolated",
            "helper": Path(__file__).resolve().parent / "direct_skill_lanes.py",
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

    def test_integrated_plan_runs_only_the_old_and_new_pair(self) -> None:
        manifest = self.repo / "evals" / "demo" / "shared-benchmark.json"
        manifest.write_text(json.dumps({
            "old_skill_paths": ["arms/control/skills/base/SKILL.md"],
            "skill_paths": [
                "arms/treatment/skills/base/SKILL.md",
                "arms/treatment/skills/demo/SKILL.md",
            ],
            "optional_variants": ["old_skill"],
        }), encoding="utf-8")
        commands = self.plan(lane="integrated")
        harness_commands = [command[6] for command in commands if len(command) > 6 and command[0] == "uv"]
        self.assertEqual(harness_commands, [
            "validate", "audit-manifest", "prepare", "run-agent", "grade", "compare-tasks",
        ])
        self.assertIn("--include-old-skill", commands[2])
        self.assertEqual(commands[3][-4:], [
            "--input", str(self.root / "out" / "tasks.all.jsonl"),
            "--out", str(self.root / "out" / "tasks.jsonl"),
        ])
        self.assertIn(str(self.root / "out" / "tasks.jsonl"), commands[4])
        self.assertIn("--allow-scripts", commands[5])
        self.assertIn("--variant", commands[5])
        self.assertIn("check-exposure", commands[6])
        self.assertIn("--primary", commands[7])
        self.assertIn("with_skill", commands[7])
        self.assertIn("--baseline", commands[7])
        self.assertIn("old_skill", commands[7])
        self.assertNotIn("benchmark", harness_commands)
        self.assertNotIn("judge", harness_commands)

    def test_integrated_plan_rejects_manifest_without_pair_arms(self) -> None:
        with self.assertRaisesRegex(ValueError, "integrated manifest"):
            self.plan(lane="integrated")

    def test_integrated_plan_does_not_require_an_inline_judge(self) -> None:
        manifest = self.repo / "evals" / "demo" / "shared-benchmark.json"
        manifest.write_text(json.dumps({
            "old_skill_paths": ["arms/control/skills/base/SKILL.md"],
            "skill_paths": ["arms/treatment/skills/demo/SKILL.md"],
            "optional_variants": ["old_skill"],
        }), encoding="utf-8")
        commands = self.plan(lane="integrated", judge_backend=None, judge_model=None)
        self.assertTrue(any("compare-tasks" in command for command in commands))


if __name__ == "__main__":
    unittest.main()
