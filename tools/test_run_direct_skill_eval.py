from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from direct_skill_lanes import LaneError
from run_direct_skill_eval import command_plan, execute_plan, main


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
        (runner.parent / "claude-project-only").write_text("", encoding="utf-8")
        adapter = self.repo / "tools" / "claude-pstack-eval"
        adapter.parent.mkdir(parents=True)
        adapter.write_text("", encoding="utf-8")

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
        self.assertIn(str(self.skill_ci / "tools" / "claude-project-only"), commands[5])

    def test_claude_answer_uses_codex_judge_adapters(self) -> None:
        commands = self.plan(agent="claude", judge_backend="codex")
        self.assertIn("--claude-bin", commands[3])
        self.assertIn(str(self.repo / "tools" / "claude-pstack-eval"), commands[3])
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
        self.assertIn("--split", commands[6])
        self.assertIn("tune", commands[6])
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

    def test_main_rejects_a_symlinked_output_before_resolving_it(self) -> None:
        target = self.root / "target"
        target.mkdir()
        output = self.root / "linked-output"
        output.symlink_to(target, target_is_directory=True)
        argv = [
            "run_direct_skill_eval.py",
            "--skill",
            "demo",
            "--agent",
            "codex",
            "--model",
            "candidate",
            "--out",
            str(output),
        ]
        with (
            mock.patch.object(sys, "argv", argv),
            contextlib.redirect_stderr(io.StringIO()),
            self.assertRaises(SystemExit) as raised,
        ):
            main()
        self.assertEqual(raised.exception.code, 2)

    def test_integrated_execution_reverifies_before_each_post_model_stage(self) -> None:
        commands = [["runner", "run-agent"], ["runner", "grade"], ["helper", "check-exposure"]]
        events: list[str] = []

        def run(command: list[str], **_: object) -> None:
            events.append(command[-1])

        with (
            mock.patch("run_direct_skill_eval.subprocess.run", side_effect=run),
            mock.patch(
                "run_direct_skill_eval.verify_materialized_lane",
                side_effect=lambda *_: events.append("verify"),
            ),
        ):
            execute_plan(
                commands,
                cwd=self.repo,
                integrated_repo=self.repo,
                source_repo=self.root,
                skill="demo",
            )
        self.assertEqual(events, ["run-agent", "verify", "grade", "verify", "check-exposure"])

    def test_integrated_execution_stops_before_grading_a_changed_shadow(self) -> None:
        commands = [["runner", "run-agent"], ["runner", "grade"]]
        with (
            mock.patch("run_direct_skill_eval.subprocess.run") as run,
            mock.patch(
                "run_direct_skill_eval.verify_materialized_lane",
                side_effect=LaneError("changed shadow"),
            ),
            self.assertRaisesRegex(LaneError, "changed shadow"),
        ):
            execute_plan(
                commands,
                cwd=self.repo,
                integrated_repo=self.repo,
                source_repo=self.root,
                skill="demo",
            )
        run.assert_called_once_with(commands[0], cwd=self.repo, check=True)

    def test_integrated_execution_keeps_the_external_suite_bound(self) -> None:
        commands = [["runner", "run-agent"], ["runner", "grade"]]
        suite = self.root / "external-suite"
        with (
            mock.patch("run_direct_skill_eval.subprocess.run"),
            mock.patch("run_direct_skill_eval.verify_materialized_lane") as verify,
        ):
            execute_plan(
                commands,
                cwd=self.repo,
                integrated_repo=self.repo,
                source_repo=self.root,
                skill="demo",
                suite_root=suite,
            )
        verify.assert_called_once_with(self.root, self.repo, "demo", suite)

    def test_isolated_execution_continues_after_the_model_stage(self) -> None:
        commands = [["runner", "run-agent"], ["runner", "grade"], ["runner", "report"]]
        with (
            mock.patch("run_direct_skill_eval.subprocess.run") as run,
            mock.patch("run_direct_skill_eval.verify_materialized_lane") as verify,
        ):
            execute_plan(commands, cwd=self.repo)
        self.assertEqual(
            [call.args[0] for call in run.call_args_list],
            commands,
        )
        verify.assert_not_called()


if __name__ == "__main__":
    unittest.main()
