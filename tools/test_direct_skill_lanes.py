from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from direct_skill_lanes import (
    LaneError,
    exposure_report,
    filter_prepared_tasks,
    materialize_integrated_lane,
    verify_materialized_lane,
)


ROOT = Path(__file__).resolve().parent.parent


class IntegratedLaneMaterializationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.shadow = Path(self.temp.name) / "shadow"
        self.receipt = materialize_integrated_lane(ROOT, "verify-commands", self.shadow)

    def test_treatment_adds_only_the_target(self) -> None:
        control = self.receipt["arms"]["control"]["files"]
        treatment = self.receipt["arms"]["treatment"]["files"]
        target_prefix = "skills/verify-commands/"
        self.assertEqual(control, {key: value for key, value in treatment.items() if not key.startswith(target_prefix)})
        self.assertTrue(any(key.startswith(target_prefix) for key in treatment))
        manifest = json.loads((self.shadow / self.receipt["manifest"]).read_text(encoding="utf-8"))
        self.assertEqual(manifest["optional_variants"], ["old_skill"])
        self.assertEqual(len(manifest["skill_paths"]), len(manifest["old_skill_paths"]) + 1)
        self.assertEqual(manifest["skill_paths"][0], "arms/treatment/skills/verify-commands/SKILL.md")

    def test_receipt_verifies_untampered_materialization(self) -> None:
        verified = verify_materialized_lane(ROOT, self.shadow, "verify-commands")
        self.assertEqual(verified["target_skill"], "verify-commands")

    def test_content_tampering_is_rejected(self) -> None:
        path = self.shadow / "arms" / "control" / "skills" / "architect" / "SKILL.md"
        path.write_text(path.read_text(encoding="utf-8") + "\ntampered\n", encoding="utf-8")
        with self.assertRaisesRegex(LaneError, "inventory"):
            verify_materialized_lane(ROOT, self.shadow, "verify-commands")

    def test_nonempty_output_is_rejected(self) -> None:
        occupied = Path(self.temp.name) / "occupied"
        occupied.mkdir()
        (occupied / "keep.txt").write_text("keep", encoding="utf-8")
        with self.assertRaisesRegex(LaneError, "new or empty"):
            materialize_integrated_lane(ROOT, "verify-commands", occupied)

    def test_output_symlink_is_rejected(self) -> None:
        target = Path(self.temp.name) / "empty"
        target.mkdir()
        linked = Path(self.temp.name) / "linked"
        linked.symlink_to(target, target_is_directory=True)
        with self.assertRaisesRegex(LaneError, "symlink"):
            materialize_integrated_lane(ROOT, "verify-commands", linked)

    def test_output_inside_source_repo_is_rejected(self) -> None:
        with self.assertRaisesRegex(LaneError, "outside the source repository"):
            materialize_integrated_lane(ROOT, "verify-commands", ROOT / "never-created-shadow")

    def test_failed_build_leaves_no_partial_output(self) -> None:
        failed = Path(self.temp.name) / "failed-shadow"

        def fail_after_write(repo: Path, destination: Path, name: str) -> None:
            partial = destination / "skills" / name
            partial.mkdir(parents=True)
            (partial / "partial.txt").write_text("partial", encoding="utf-8")
            raise LaneError("injected copy failure")

        with patch("direct_skill_lanes._copy_skill", side_effect=fail_after_write):
            with self.assertRaisesRegex(LaneError, "injected copy failure"):
                materialize_integrated_lane(ROOT, "verify-commands", failed)
        self.assertFalse(failed.exists())
        self.assertEqual(list(Path(self.temp.name).glob(".failed-shadow.*")), [])

    def test_ignored_source_files_do_not_enter_receipt(self) -> None:
        fake_repo = Path(self.temp.name) / "source"
        (fake_repo / ".github").mkdir(parents=True)
        (fake_repo / "evals").mkdir()
        shutil.copy2(ROOT / ".gitignore", fake_repo / ".gitignore")
        shutil.copy2(ROOT / ".github" / "upstream-sha", fake_repo / ".github" / "upstream-sha")
        shutil.copy2(
            ROOT / "evals" / "direct-skills-experiment.json",
            fake_repo / "evals" / "direct-skills-experiment.json",
        )
        shutil.copytree(ROOT / "skills", fake_repo / "skills")
        shutil.copytree(
            ROOT / "evals" / "verify-commands",
            fake_repo / "evals" / "verify-commands",
        )
        subprocess.run(["git", "init", "-q"], cwd=fake_repo, check=True)
        subprocess.run(["git", "add", "."], cwd=fake_repo, check=True)
        subprocess.run(
            [
                "git",
                "-c",
                "user.name=Lane Test",
                "-c",
                "user.email=lane-test",
                "commit",
                "-qm",
                "fixture",
            ],
            cwd=fake_repo,
            check=True,
        )
        ignored = fake_repo / "evals" / "verify-commands" / "oracles" / "__pycache__" / "ignored.pyc"
        ignored.parent.mkdir()
        ignored.write_bytes(b"ignored")
        ignored_link = (
            fake_repo
            / "skills"
            / "poteto-mode"
            / "scripts"
            / "node_modules"
            / ".bin"
            / "tsc"
        )
        ignored_link.parent.mkdir(parents=True)
        ignored_link.symlink_to("../typescript/bin/tsc")
        self.assertEqual(
            subprocess.run(["git", "check-ignore", "-q", str(ignored)], cwd=fake_repo).returncode,
            0,
        )
        self.assertEqual(
            subprocess.run(["git", "check-ignore", "-q", str(ignored_link)], cwd=fake_repo).returncode,
            0,
        )
        shadow = Path(self.temp.name) / "ignored-shadow"
        receipt = materialize_integrated_lane(fake_repo, "verify-commands", shadow)
        self.assertFalse(any("__pycache__" in path for path in receipt["source"]["eval_suite"]))
        self.assertFalse(any(
            "node_modules" in path
            for path in receipt["source"]["skills"]["poteto-mode"]
        ))
        self.assertFalse((shadow / "evals" / "verify-commands" / "oracles" / "__pycache__").exists())
        self.assertFalse((
            shadow
            / "arms"
            / "control"
            / "skills"
            / "poteto-mode"
            / "scripts"
            / "node_modules"
        ).exists())


class PreparedTaskFilterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_filters_to_pair_with_equal_population(self) -> None:
        source = self.root / "prepared.jsonl"
        rows = [
            {"case_id": case, "variant": variant, "run_number": run}
            for case in ("a", "b")
            for run in (1, 2)
            for variant in ("with_skill", "without_skill", "old_skill")
        ]
        source.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
        destination = self.root / "filtered.jsonl"
        result = filter_prepared_tasks(source, destination, ("with_skill", "old_skill"))
        filtered = [json.loads(line) for line in destination.read_text(encoding="utf-8").splitlines()]
        self.assertEqual(result, {"with_skill": 4, "old_skill": 4})
        self.assertEqual({row["variant"] for row in filtered}, {"with_skill", "old_skill"})

    def test_rejects_pair_population_mismatch(self) -> None:
        source = self.root / "prepared.jsonl"
        source.write_text(
            json.dumps({"case_id": "a", "variant": "with_skill", "run_number": 1}) + "\n",
            encoding="utf-8",
        )
        with self.assertRaisesRegex(LaneError, "population mismatch"):
            filter_prepared_tasks(source, self.root / "filtered.jsonl", ("with_skill", "old_skill"))

    def test_rejects_pair_prompt_mismatch(self) -> None:
        source = self.root / "prepared.jsonl"
        rows = [
            {"case_id": "a", "variant": "with_skill", "run_number": 1, "prompt": "one"},
            {"case_id": "a", "variant": "old_skill", "run_number": 1, "prompt": "two"},
        ]
        source.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
        with self.assertRaisesRegex(LaneError, "differs outside its skill arm"):
            filter_prepared_tasks(source, self.root / "filtered.jsonl")


class ExposureEligibilityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.manifest = self.root / "manifest.json"
        self.manifest.write_text(json.dumps({
            "cases": [
                {"id": "behavior", "kind": "positive"},
                {"id": "positive-trigger", "kind": "trigger", "should_trigger": True},
                {"id": "negative-trigger", "kind": "trigger", "should_trigger": False},
                {
                    "id": "restraint",
                    "kind": "negative",
                    "assertions": [{
                        "type": "skill_invoked",
                        "expected": False,
                        "variants": ["with_skill"],
                    }],
                },
            ]
        }), encoding="utf-8")

    def write_events(self, case: str, variant: str, skill: str | None) -> None:
        run = self.root / "runs" / case / variant / "run-1"
        run.mkdir(parents=True)
        events = [] if skill is None else [{
            "type": "skill_load",
            "input_summary": f"./skills/{skill}/SKILL.md",
            "status": "completed",
        }]
        (run / "events.json").write_text(json.dumps({
            "schema_version": 3,
            "source": "test",
            "events": events,
        }), encoding="utf-8")

    def test_requires_the_target_not_any_skill_event(self) -> None:
        self.write_events("behavior", "with_skill", "architect")
        self.write_events("behavior", "old_skill", "architect")
        report = exposure_report(self.root / "runs", self.manifest, "verify-commands")
        self.assertFalse(report["eligible"])
        self.assertEqual(report["missing_target_reads"][0]["case_id"], "behavior")

    def test_negative_trigger_may_omit_target(self) -> None:
        for case in ("behavior", "positive-trigger"):
            self.write_events(case, "with_skill", "verify-commands")
            self.write_events(case, "old_skill", "architect")
        self.write_events("negative-trigger", "with_skill", None)
        self.write_events("negative-trigger", "old_skill", "architect")
        self.write_events("restraint", "with_skill", None)
        self.write_events("restraint", "old_skill", "architect")
        report = exposure_report(self.root / "runs", self.manifest, "verify-commands")
        self.assertTrue(report["eligible"])
        self.assertEqual(report["missing_target_reads"], [])

    def test_non_trigger_restraint_uses_explicit_false_expectation(self) -> None:
        for case in ("behavior", "positive-trigger"):
            self.write_events(case, "with_skill", "verify-commands")
            self.write_events(case, "old_skill", "architect")
        for case in ("negative-trigger", "restraint"):
            self.write_events(case, "with_skill", None)
            self.write_events(case, "old_skill", "architect")
        report = exposure_report(self.root / "runs", self.manifest, "verify-commands")
        restraint = next(row for row in report["runs"] if row["case_id"] == "restraint" and row["variant"] == "with_skill")
        self.assertFalse(restraint["target_read_expected"])
        self.assertTrue(report["eligible"])

    def test_rejects_incomplete_run_pair(self) -> None:
        self.write_events("behavior", "with_skill", "verify-commands")
        with self.assertRaisesRegex(LaneError, "run population mismatch"):
            exposure_report(self.root / "runs", self.manifest, "verify-commands")


if __name__ == "__main__":
    unittest.main()
