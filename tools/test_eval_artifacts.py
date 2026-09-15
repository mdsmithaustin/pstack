#!/usr/bin/env python3
from __future__ import annotations

import json
import shlex
import subprocess
import tomllib
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILLS = ROOT / "skills"
EVALS = ROOT / "evals"

IGNORED = (
    "evals/runs/transcript.jsonl",
    "evals/unslop/runs/transcript.jsonl",
    "skills/unslop/evals/runs/transcript.jsonl",
    "skills/unslop/evals/runs/nested/judge-transcripts/run-1/prompt.md",
    "eval-runs/transcript.jsonl",
    "skills/unslop/evals/eval-runs/transcript.jsonl",
    "review-inbox/harvest.md",
    "skills/unslop/evals/review-inbox/harvest.md",
)

TRACKABLE = (
    "evals/README.md",
    "evals/direct-skills-experiment.json",
    "evals/private-holdback.template.json",
    "tools/run_direct_skill_eval.py",
    "evals/unslop/shared-benchmark.json",
    "evals/unslop/oracles/check_edited.py",
    "evals/shared-benchmark.json",
    "skills/unslop/SKILL.md",
)

EVAL_DIRECTORY_NAMES = ("evals", "eval-runs")
DIRECT_EVAL_SKILLS = ("runtime-probes", "spec-probes", "verify-commands")
GENERATED_NAMES = {
    "answer-design.json",
    "benchmark.json",
    "benchmark-objective.json",
    "events.json",
    "grade.json",
    "judge.jsonl",
    "metrics.json",
    "output.md",
    "report.md",
    "trace.jsonl",
    "trigger-matrix.json",
}

WHY_EVALS_LIVE_OUTSIDE_SKILLS = (
    "A skill installer copies a skill directory verbatim and offers no exclude "
    "mechanism. Eval material placed there reaches everyone who installs the skill. "
    "Manifests, oracles, and runs belong under the repository-root evals/ tree, which "
    "skill-checks reads through its evals-dir input."
)


def ignored(path: str) -> bool:
    return subprocess.run(
        ["git", "check-ignore", "-q", "--no-index", path],
        cwd=ROOT, capture_output=True,
    ).returncode == 0


class EvalArtifactsStayOutOfGit(unittest.TestCase):
    def test_run_transcripts_are_ignored_at_every_depth(self) -> None:
        for path in IGNORED:
            with self.subTest(path=path):
                self.assertTrue(ignored(path), f"{path} would be committable")

    def test_manifests_and_oracles_stay_trackable(self) -> None:
        for path in TRACKABLE:
            with self.subTest(path=path):
                self.assertFalse(ignored(path), f"{path} cannot be committed")

    def test_no_skill_ships_eval_material(self) -> None:
        found = sorted(
            str(path.relative_to(ROOT))
            for name in EVAL_DIRECTORY_NAMES
            for path in SKILLS.rglob(name)
            if path.is_dir()
        )
        self.assertEqual(found, [], f"{found} must move out of skills/. {WHY_EVALS_LIVE_OUTSIDE_SKILLS}")

    def test_direct_eval_sources_are_trackable_and_generated_results_are_not_tracked(self) -> None:
        tracked = subprocess.run(
            ["git", "ls-files", "--cached", *[f"evals/{name}" for name in DIRECT_EVAL_SKILLS]],
            cwd=ROOT, capture_output=True, text=True, check=True,
        ).stdout.splitlines()
        for skill_name in DIRECT_EVAL_SKILLS:
            suite = EVALS / skill_name
            with self.subTest(skill=skill_name):
                self.assertTrue((suite / "shared-benchmark.json").is_file())
                self.assertTrue(any((suite / "oracles").glob("*.py")))
                self.assertFalse(ignored(f"evals/{skill_name}/shared-benchmark.json"))
        generated = [path for path in tracked if "runs" in Path(path).parts or Path(path).name in GENERATED_NAMES]
        self.assertEqual(generated, [], f"generated eval results are tracked: {generated}")


class MiseTasksReadTheEvalsTree(unittest.TestCase):
    """A task that searches the wrong tree finds no manifest and still exits 0."""

    def setUp(self) -> None:
        self.config = tomllib.loads((ROOT / "mise.toml").read_text(encoding="utf-8"))

    def test_evals_dir_names_the_tree_that_holds_the_manifests(self) -> None:
        self.assertEqual(self.config["env"]["EVALS_DIR"], "evals")
        manifests = sorted(p.relative_to(ROOT).as_posix() for p in EVALS.rglob("shared-benchmark.json"))
        self.assertIn("evals/unslop/shared-benchmark.json", manifests)

    def test_tasks_come_from_the_skill_ci_checkout(self) -> None:
        self.assertEqual(self.config["env"]["SKILL_CI"], "{{ config_root }}/../skill-ci")
        self.assertEqual(self.config["task_config"]["includes"], ["../skill-ci/skill-tasks.toml"])

    def test_ci_fails_when_manifest_discovery_is_empty(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "skill-checks.yml").read_text(encoding="utf-8")
        self.assertIn("require-manifests: true", workflow)


class ManifestsNameRealSkillFiles(unittest.TestCase):
    """Every skill_paths entry resolves, which no runner command checks."""

    def test_every_skill_path_is_a_file(self) -> None:
        for manifest in sorted(EVALS.rglob("shared-benchmark.json")):
            name = manifest.relative_to(ROOT).as_posix()
            with self.subTest(manifest=name):
                entries = json.loads(manifest.read_text(encoding="utf-8"))["skill_paths"]
                for entry in entries:
                    self.assertTrue((ROOT / entry).is_file(), f"{name} names {entry}, which is not a file")

    def test_every_manifest_reference_is_a_file(self) -> None:
        for manifest_path in sorted(EVALS.rglob("shared-benchmark.json")):
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            for case in manifest.get("cases", []):
                references = [*case.get("files", [])]
                if case.get("prompt_ref"):
                    references.append(case["prompt_ref"])
                for assertion in case.get("assertions", []):
                    if assertion.get("type") != "script":
                        continue
                    command = assertion.get("command", [])
                    parts = command if isinstance(command, list) else [command]
                    for part in parts:
                        for token in shlex.split(part):
                            if "/" in token and not token.startswith("{"):
                                references.append(token)
                for reference in references:
                    with self.subTest(manifest=manifest_path.name, case=case.get("id"), reference=reference):
                        self.assertTrue((manifest_path.parent / reference).is_file())


class DirectSkillExperimentContract(unittest.TestCase):
    def setUp(self) -> None:
        self.contract = json.loads((EVALS / "direct-skills-experiment.json").read_text(encoding="utf-8"))

    def test_baseline_matches_last_synced_upstream_change(self) -> None:
        recorded = (ROOT / ".github" / "upstream-sha").read_text(encoding="utf-8").strip()
        self.assertEqual(self.contract["baseline"]["commit"], recorded)
        self.assertEqual(self.contract["baseline"]["behavioral_arm"], "without_skill")
        self.assertEqual(sorted(self.contract["targets"]), sorted(DIRECT_EVAL_SKILLS))
        self.assertEqual(sorted(self.contract["baseline"]["target_skills_absent"]), sorted(DIRECT_EVAL_SKILLS))
        self.assertTrue(self.contract["judging"]["answer_and_judge_families_must_differ"])
        self.assertEqual(self.contract["judging"]["repetitions"], 3)

    def test_agreed_experiment_policy_is_frozen(self) -> None:
        self.assertEqual(
            [(row["agent"], row["model"]) for row in self.contract["answer_models"]],
            [
                ("codex", "gpt-5.6-luna"),
                ("codex", "gpt-5.6-sol"),
                ("codex", "gpt-5.6-terra"),
                ("claude", "opus"),
            ],
        )
        self.assertEqual(self.contract["priority"], ["quality", "tokens", "elapsed_time"])
        self.assertEqual(self.contract["judging"], {
            "repetitions": 3,
            "answer_and_judge_families_must_differ": True,
            "codex_answers": {"agent": "claude", "model": "opus"},
            "claude_answers": {"agent": "codex", "model": "gpt-6-astra"},
        })
        self.assertEqual(self.contract["promotion"], {
            "finalist_repetitions": 3,
            "hard_gates_require_full_pass": True,
            "no_model_regression": True,
            "aggregate": "median",
            "numeric_threshold_source": "repeated-incumbent-variance",
            "private_behavior_cases_per_skill": 4,
            "private_positive_trigger_cases_per_skill": 4,
            "private_negative_trigger_cases_per_skill": 4,
            "user_approval_required": True,
        })
        self.assertEqual(self.contract["climb"], {
            "separate_trigger_and_behavior": True,
            "maximum_cycles_per_metric": 5,
            "stop_after_consecutive_no_gain_cycles": 2,
            "maximum_live_branches": 2,
            "combined_candidate_must_beat_each_parent": True,
            "compression_is_separate": True,
        })

    def test_public_corpus_reserves_holdback_for_external_cases(self) -> None:
        for skill_name in DIRECT_EVAL_SKILLS:
            manifest = json.loads((EVALS / skill_name / "shared-benchmark.json").read_text(encoding="utf-8"))
            cases = manifest["cases"]
            trigger_cases = [case for case in cases if case.get("kind") == "trigger"]
            positive = [case for case in trigger_cases if case.get("should_trigger") is True]
            negative = [case for case in trigger_cases if case.get("should_trigger") is False]
            behavior = [case for case in cases if case.get("kind") != "trigger"]
            with self.subTest(skill=skill_name):
                self.assertGreaterEqual(len(behavior), 4)
                self.assertGreaterEqual(len(positive), 4)
                self.assertGreaterEqual(len(negative), 4)
                self.assertEqual({case.get("split") for case in cases}, {"tune"})


if __name__ == "__main__":
    unittest.main()
