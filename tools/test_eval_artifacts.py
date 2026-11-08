#!/usr/bin/env python3
from __future__ import annotations

import fnmatch
import json
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
    "evals/unslop/shared-benchmark.json",
    "evals/unslop/oracles/check_edited.py",
    "evals/shared-benchmark.json",
    "skills/unslop/SKILL.md",
)

EVAL_DIRECTORY_NAMES = ("evals", "eval-runs")

WHY_EVALS_LIVE_OUTSIDE_SKILLS = (
    "A skill installer copies a skill directory verbatim and offers no exclude "
    "mechanism. Eval material placed there reaches everyone who installs the skill. "
    "Manifests, oracles, and runs belong under the repository-root evals/ tree, which "
    "skill-ci reads through the evals_dir key in .skill-ci.toml."
)

TEST_FILE_PATTERNS = (
    "*.test.ts",
    "*.test.js",
    "*.test.mjs",
    "*.test-helper.ts",
    "*.compile.ts",
    "test_*.py",
    "*_test.py",
)

WHY_TESTS_LIVE_OUTSIDE_SKILLS = (
    "Tests live under tests/, mirroring their path under skills/, because "
    "`npx skills` ships skills/ verbatim to everyone who installs a skill."
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


class SkillsShipNoTests(unittest.TestCase):
    def test_no_tracked_skill_file_is_a_test(self) -> None:
        tracked = subprocess.run(
            ["git", "ls-files", "-z", "--", "skills"],
            cwd=ROOT, capture_output=True, check=True, text=True,
        ).stdout.split("\0")
        found = sorted(
            path for path in tracked
            if path and any(fnmatch.fnmatchcase(Path(path).name, pattern) for pattern in TEST_FILE_PATTERNS)
        )
        listing = "\n".join(f"  {path} -> tests/{path}" for path in found)
        if found:
            self.fail(f"test files under skills/:\n{listing}\n{WHY_TESTS_LIVE_OUTSIDE_SKILLS}")


class MiseTasksReadTheEvalsTree(unittest.TestCase):
    """A task that searches the wrong tree finds no manifest and still exits 0."""

    def setUp(self) -> None:
        self.pin = tomllib.loads((ROOT / ".skill-ci.toml").read_text(encoding="utf-8"))
        self.config = tomllib.loads((ROOT / "mise.toml").read_text(encoding="utf-8"))

    def test_evals_dir_names_the_tree_that_holds_the_manifests(self) -> None:
        self.assertEqual(self.pin["evals_dir"], "evals")
        manifests = sorted(p.relative_to(ROOT).as_posix() for p in EVALS.rglob("shared-benchmark.json"))
        self.assertIn("evals/unslop/shared-benchmark.json", manifests)

    def test_tasks_run_the_pinned_skill_ci_command(self) -> None:
        self.assertNotIn("env", self.config)
        self.assertNotIn("task_config", self.config)
        skill_tasks = {name: task["run"] for name, task in self.config["tasks"].items() if name.startswith("skill-")}
        self.assertEqual(
            skill_tasks,
            {
                "skill-check": "skill-ci check",
                "skill-lint": "skill-ci lint",
                "skill-package": "skill-ci package",
                "skill-coverage": "skill-ci coverage",
                "skill-validate": "skill-ci validate",
                "skill-audit": "skill-ci audit",
                "skill-trigger": "skill-ci trigger",
                "skill-run": "skill-ci run",
            },
        )


class ManifestsNameRealSkillFiles(unittest.TestCase):
    def test_every_skill_path_is_a_file(self) -> None:
        for manifest in sorted(EVALS.rglob("shared-benchmark.json")):
            name = manifest.relative_to(ROOT).as_posix()
            with self.subTest(manifest=name):
                entries = json.loads(manifest.read_text(encoding="utf-8"))["skill_paths"]
                for entry in entries:
                    self.assertTrue((ROOT / entry).is_file(), f"{name} names {entry}, which is not a file")


POLICY_FIELDS = ("decision", "unique_coverage", "rerun_when", "model_required")


def evaluation_policy_errors(manifest: dict, root: Path) -> list[str]:
    policy = manifest.get("evaluation_policy")
    if not isinstance(policy, dict):
        return ["missing evaluation_policy: name the decision and why fresh model output is needed"]
    errors = [f"evaluation_policy.{field} must be non-empty text"
              for field in POLICY_FIELDS
              if not isinstance(policy.get(field), str) or not policy[field].strip()]
    checks = policy.get("deterministic_checks")
    if not isinstance(checks, list) or not checks:
        errors.append("evaluation_policy.deterministic_checks must name existing checks to reuse first")
    else:
        for check in checks:
            if (not isinstance(check, str) or Path(check).is_absolute()
                    or ".." in Path(check).parts or not (root / check).is_file()):
                errors.append(f"deterministic check does not name a repository file: {check!r}")
    return errors


def duplicate_case_key(manifest: Path, case: dict) -> tuple:
    return (
        case.get("kind") == "trigger",
        case.get("prompt", ""),
        tuple(sorted((manifest.parent / path).resolve() for path in case.get("files", []))),
    )


class EvaluationSpendPolicy(unittest.TestCase):
    def test_maintained_manifests_name_the_decision_and_existing_checks(self) -> None:
        manifests = sorted(EVALS.glob("*/shared-benchmark.json"))
        self.assertTrue(manifests, "no maintained manifests were checked")
        for path in manifests:
            with self.subTest(manifest=str(path.relative_to(ROOT))):
                self.assertEqual(evaluation_policy_errors(json.loads(path.read_text()), ROOT), [])

    def test_exact_duplicate_prompts_do_not_add_paid_coverage(self) -> None:
        seen = {}
        for path in sorted(EVALS.glob("*/shared-benchmark.json")):
            for case in json.loads(path.read_text())["cases"]:
                if not case.get("prompt", ""):
                    continue
                key = duplicate_case_key(path, case)
                identity = f"{path.parent.name}/{case['id']}"
                self.assertNotIn(key, seen, f"{identity} duplicates {seen.get(key)}; reuse the existing case")
                seen[key] = identity

    def test_duplicate_key_preserves_whitespace_inside_literals(self) -> None:
        manifest = EVALS / "unslop" / "shared-benchmark.json"
        case = {"prompt": 'Preserve `const title = "Q3 — regional totals";`'}
        self.assertEqual(duplicate_case_key(manifest, case), duplicate_case_key(manifest, dict(case)))
        changed = {"prompt": 'Preserve `const title = "Q3  — regional totals";`'}
        self.assertNotEqual(duplicate_case_key(manifest, case), duplicate_case_key(manifest, changed))

    def test_duplicate_key_distinguishes_manifest_relative_fixtures(self) -> None:
        first = EVALS / "spec-probes" / "shared-benchmark.json"
        second = EVALS / "runtime-probes" / "shared-benchmark.json"
        case = {"prompt": "Review this input", "files": ["fixtures/input.md"]}
        self.assertNotEqual(duplicate_case_key(first, case), duplicate_case_key(second, case))
        equivalent = {**case, "files": ["fixtures/./input.md"]}
        self.assertEqual(duplicate_case_key(first, case), duplicate_case_key(first, equivalent))

    def test_reordering_the_same_attachments_adds_no_coverage(self) -> None:
        manifest = EVALS / "runtime-probes" / "shared-benchmark.json"
        case = {"prompt": "Review these inputs", "files": ["fixtures/first.md", "fixtures/second.md"]}
        reordered = {**case, "files": list(reversed(case["files"]))}
        self.assertEqual(duplicate_case_key(manifest, case), duplicate_case_key(manifest, reordered))

    def test_policy_controls_reject_missing_coverage_and_missing_checks(self) -> None:
        valid = {"evaluation_policy": {
            **dict.fromkeys(POLICY_FIELDS, "A concrete study decision"),
            "deterministic_checks": ["tools/test_eval_artifacts.py"],
        }}
        self.assertEqual(evaluation_policy_errors(valid, ROOT), [])
        self.assertTrue(evaluation_policy_errors({}, ROOT))
        valid["evaluation_policy"]["unique_coverage"] = " "
        self.assertIn("evaluation_policy.unique_coverage must be non-empty text",
                      evaluation_policy_errors(valid, ROOT))
        valid["evaluation_policy"]["deterministic_checks"] = ["missing-check.py"]
        self.assertTrue(any("missing-check.py" in error for error in evaluation_policy_errors(valid, ROOT)))


if __name__ == "__main__":
    unittest.main()
