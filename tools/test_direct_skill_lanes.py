from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import direct_skill_lanes as lane_module
from direct_skill_lanes import (
    LaneError,
    _tracked_tree_files,
    exposure_report,
    filter_prepared_tasks,
    materialize_integrated_lane,
    verify_materialized_lane,
)


ROOT = Path(__file__).resolve().parent.parent


def canonical_digest(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


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
        self.assertTrue((self.shadow / "tools" / "direct_skill_lanes.py").is_file())
        self.assertIn("tools/direct_skill_lanes.py", self.receipt["source"]["helpers"])

    def test_receipt_verifies_untampered_materialization(self) -> None:
        verified = verify_materialized_lane(ROOT, self.shadow, "verify-commands")
        self.assertEqual(verified["target_skill"], "verify-commands")

    def test_content_tampering_is_rejected(self) -> None:
        path = self.shadow / "arms" / "control" / "skills" / "architect" / "SKILL.md"
        path.write_text(path.read_text(encoding="utf-8") + "\ntampered\n", encoding="utf-8")
        with self.assertRaisesRegex(LaneError, "inventory"):
            verify_materialized_lane(ROOT, self.shadow, "verify-commands")

    def test_receipt_cannot_authorize_an_added_shadow_file(self) -> None:
        injected = self.shadow / "evals" / "verify-commands" / "injected.json"
        injected.write_text("{}\n", encoding="utf-8")
        receipt_path = self.shadow / "integrated-lane-receipt.json"
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        receipt["files"]["evals/verify-commands/injected.json"] = (
            f"sha256:{hashlib.sha256(injected.read_bytes()).hexdigest()}"
        )
        receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
        with self.assertRaisesRegex(LaneError, "does not match its source"):
            verify_materialized_lane(ROOT, self.shadow, "verify-commands")

    def test_special_file_tampering_is_rejected(self) -> None:
        os.mkfifo(self.shadow / "tamper.pipe")
        with self.assertRaisesRegex(LaneError, "special files are not allowed"):
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
        (fake_repo / "tools").mkdir()
        shutil.copy2(ROOT / ".gitignore", fake_repo / ".gitignore")
        shutil.copy2(ROOT / ".github" / "upstream-sha", fake_repo / ".github" / "upstream-sha")
        shutil.copy2(ROOT / "tools" / "direct_skill_lanes.py", fake_repo / "tools" / "direct_skill_lanes.py")
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
        ignored.parent.mkdir(exist_ok=True)
        ignored.write_bytes(b"ignored")
        ignored_link = (
            fake_repo
            / "skills"
            / "poteto-mode"
            / "scripts"
            / "node_modules"
            / ".bin"
            / "ignored-tool"
        )
        ignored_link.parent.mkdir(parents=True, exist_ok=True)
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

    def test_tracked_file_below_symlinked_ancestor_is_rejected(self) -> None:
        source = Path(self.temp.name) / "symlink-source"
        outside = Path(self.temp.name) / "outside"
        (source / "tree").mkdir(parents=True)
        outside.mkdir()
        (source / "tree" / "file.txt").write_text("tracked", encoding="utf-8")
        subprocess.run(["git", "init", "-q"], cwd=source, check=True)
        subprocess.run(["git", "add", "."], cwd=source, check=True)
        subprocess.run(
            ["git", "-c", "user.name=Lane Test", "-c", "user.email=lane-test", "commit", "-qm", "fixture"],
            cwd=source,
            check=True,
        )
        shutil.move(source / "tree" / "file.txt", outside / "file.txt")
        (source / "tree").rmdir()
        (source / "tree").symlink_to(outside, target_is_directory=True)
        with self.assertRaisesRegex(LaneError, "contains a symlink"):
            _tracked_tree_files(source, Path("tree"))


class PreparedTaskFilterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()

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
        self.root = Path(self.temp.name).resolve()
        self.manifest = self.root / "manifest.json"
        self.manifest.write_text(json.dumps({
            "cases": [
                {"id": "behavior", "kind": "positive", "split": "tune"},
                {"id": "positive-trigger", "kind": "trigger", "split": "tune", "should_trigger": True},
                {"id": "negative-trigger", "kind": "trigger", "split": "tune", "should_trigger": False},
                {
                    "id": "restraint",
                    "kind": "negative",
                    "split": "holdback",
                    "assertions": [{
                        "type": "skill_invoked",
                        "expected": False,
                        "variants": ["with_skill"],
                    }],
                },
            ]
        }), encoding="utf-8")

    def write_design(self, identities: list[dict[str, object]]) -> None:
        identities.sort(key=lambda row: (
            row["case_id"], str(row["model"] or ""), row["variant"], row["run_number"]
        ))
        payload = {
            "schema_version": 2,
            "population": "answer",
            "eval_contract_sha256": f"sha256:{'0' * 64}",
            "identities": identities,
        }
        design = {**payload, "design_sha256": canonical_digest(payload)}
        runs = self.root / "runs"
        runs.mkdir(exist_ok=True)
        (runs / "answer-design.json").write_text(json.dumps(design), encoding="utf-8")

    def plan_run(self, case: str, variant: str, run_number: int = 1) -> str:
        design_path = self.root / "runs" / "answer-design.json"
        identities = []
        if design_path.exists():
            identities = json.loads(design_path.read_text(encoding="utf-8"))["identities"]
        suffix = [] if run_number == 1 else [f"run-{run_number}"]
        run_dir = "/".join([case, variant, *suffix])
        identities.append({
            "case_id": case,
            "model": None,
            "variant": variant,
            "run_number": run_number,
            "run_dir": run_dir,
            "task_sha256": f"sha256:{'1' * 64}",
            "case_input_sha256": f"sha256:{'2' * 64}",
            "instruction_sha256": f"sha256:{'3' * 64}",
            "planned_skill_tree_hash": "4" * 64,
            "fixture_tree_hash": "5" * 64,
        })
        self.write_design(identities)
        return run_dir

    def write_events(
        self,
        case: str,
        variant: str,
        skill: str | None,
        *,
        event: dict[str, object] | None = None,
        run_number: int = 1,
    ) -> None:
        run = self.root / "runs" / self.plan_run(case, variant, run_number)
        run.mkdir(parents=True)
        events = [] if skill is None else [event or {
            "type": "skill_load",
            "name": "Read",
            "input_summary": f"./skills/{skill}/SKILL.md",
            "status": "completed",
        }]
        (run / "events.json").write_text(json.dumps({
            "schema_version": 2,
            "source": "test",
            "events": events,
        }), encoding="utf-8")

    def test_requires_the_target_not_any_skill_event(self) -> None:
        self.write_events("behavior", "with_skill", "architect")
        self.write_events("behavior", "old_skill", "architect")
        report = exposure_report(self.root / "runs", self.manifest, "verify-commands", "tune")
        self.assertFalse(report["eligible"])
        self.assertEqual(report["missing_target_reads"][0]["case_id"], "behavior")

    def test_echo_or_search_text_cannot_satisfy_a_target_read(self) -> None:
        forged = {
            "type": "command",
            "name": "Bash",
            "input_summary": "rg ./skills/verify-commands/SKILL.md",
            "status": "completed",
        }
        self.write_events("behavior", "with_skill", "verify-commands", event=forged)
        self.write_events("behavior", "old_skill", None)
        report = exposure_report(self.root / "runs", self.manifest, "verify-commands", "tune")
        self.assertFalse(report["eligible"])
        self.assertEqual(len(report["missing_target_reads"]), 1)

    def test_completed_reader_command_counts_as_target_read(self) -> None:
        command = {
            "type": "command",
            "name": "Bash",
            "input_summary": "sed -n '1,240p' ./skills/verify-commands/SKILL.md",
            "output_summary": "---\nname: verify-commands\n---",
            "status": "completed",
        }
        self.write_events("behavior", "with_skill", "verify-commands", event=command)
        self.write_events("behavior", "old_skill", None)
        report = exposure_report(self.root / "runs", self.manifest, "verify-commands", "tune")
        self.assertTrue(report["eligible"])

    def test_shell_wrapped_reader_command_counts_as_target_read(self) -> None:
        command = {
            "type": "command",
            "name": "Bash",
            "input_summary": "/bin/zsh -lc \"sed -n '1,240p' ./skills/verify-commands/SKILL.md\"",
            "output_summary": "---\nname: verify-commands\n---",
            "status": "completed",
        }
        self.write_events("behavior", "with_skill", "verify-commands", event=command)
        self.write_events("behavior", "old_skill", None)
        report = exposure_report(self.root / "runs", self.manifest, "verify-commands", "tune")
        self.assertTrue(report["eligible"])

    def test_reader_command_without_returned_content_does_not_count(self) -> None:
        command = {
            "type": "command",
            "name": "Bash",
            "input_summary": "cat ./skills/verify-commands/SKILL.md >/dev/null",
            "output_summary": "",
            "status": "completed",
        }
        self.write_events("behavior", "with_skill", "verify-commands", event=command)
        self.write_events("behavior", "old_skill", None)
        report = exposure_report(self.root / "runs", self.manifest, "verify-commands", "tune")
        self.assertFalse(report["eligible"])

    def test_boolean_false_exit_code_does_not_count(self) -> None:
        command = {
            "type": "command",
            "name": "Bash",
            "input_summary": "cat ./skills/verify-commands/SKILL.md",
            "output_summary": "---\nname: verify-commands\n---",
            "status": "completed",
            "exit_code": False,
        }
        self.write_events("behavior", "with_skill", "verify-commands", event=command)
        self.write_events("behavior", "old_skill", None)
        report = exposure_report(self.root / "runs", self.manifest, "verify-commands", "tune")
        self.assertFalse(report["eligible"])

    def test_target_read_requires_completed_exact_skill_path(self) -> None:
        incomplete = {
            "type": "skill_load",
            "name": "Read",
            "input_summary": "./skills/verify-commands/SKILL.md.backup",
            "status": "in_progress",
        }
        self.write_events("behavior", "with_skill", "verify-commands", event=incomplete)
        self.write_events("behavior", "old_skill", None)
        report = exposure_report(self.root / "runs", self.manifest, "verify-commands", "tune")
        self.assertFalse(report["eligible"])
        self.assertEqual(len(report["missing_target_reads"]), 1)

    def test_native_skill_activation_counts_without_a_file_path(self) -> None:
        native = {
            "type": "skill_load",
            "name": "Skill",
            "input_summary": "verify-commands",
            "status": "completed",
        }
        self.write_events("behavior", "with_skill", "verify-commands", event=native)
        self.write_events("behavior", "old_skill", None)
        report = exposure_report(self.root / "runs", self.manifest, "verify-commands", "tune")
        self.assertTrue(report["eligible"])

    def test_malformed_answer_design_identity_is_rejected(self) -> None:
        self.write_events("behavior", "with_skill", "verify-commands")
        self.write_events("behavior", "old_skill", None)
        design_path = self.root / "runs" / "answer-design.json"
        design = json.loads(design_path.read_text(encoding="utf-8"))
        del design["identities"][0]["fixture_tree_hash"]
        self.write_design(design["identities"])
        with self.assertRaisesRegex(LaneError, "invalid shape"):
            exposure_report(self.root / "runs", self.manifest, "verify-commands", "tune")

    def test_dot_answer_design_run_directory_is_rejected(self) -> None:
        self.write_events("behavior", "with_skill", "verify-commands")
        self.write_events("behavior", "old_skill", None)
        design_path = self.root / "runs" / "answer-design.json"
        design = json.loads(design_path.read_text(encoding="utf-8"))
        design["identities"][0]["run_dir"] = "."
        self.write_design(design["identities"])
        with self.assertRaisesRegex(LaneError, "safe relative path"):
            exposure_report(self.root / "runs", self.manifest, "verify-commands", "tune")

    def test_answer_population_excludes_trigger_cases(self) -> None:
        self.write_events("behavior", "with_skill", "verify-commands")
        self.write_events("behavior", "old_skill", "architect")
        report = exposure_report(self.root / "runs", self.manifest, "verify-commands", "tune")
        self.assertTrue(report["eligible"])
        self.assertEqual(report["missing_target_reads"], [])

    def test_rejects_a_manifest_case_missing_from_both_arms(self) -> None:
        manifest = json.loads(self.manifest.read_text(encoding="utf-8"))
        manifest["cases"].append({"id": "second-behavior", "kind": "positive", "split": "tune"})
        self.manifest.write_text(json.dumps(manifest), encoding="utf-8")
        self.write_events("behavior", "with_skill", "verify-commands")
        self.write_events("behavior", "old_skill", "architect")
        with self.assertRaisesRegex(LaneError, "case population differs.*second-behavior"):
            exposure_report(self.root / "runs", self.manifest, "verify-commands", "tune")

    def test_non_trigger_restraint_uses_explicit_false_expectation(self) -> None:
        self.write_events("restraint", "with_skill", None)
        self.write_events("restraint", "old_skill", "architect")
        report = exposure_report(self.root / "runs", self.manifest, "verify-commands", "holdback")
        restraint = next(row for row in report["runs"] if row["case_id"] == "restraint" and row["variant"] == "with_skill")
        self.assertFalse(restraint["target_read_expected"])
        self.assertTrue(report["eligible"])

    def test_rejects_incomplete_run_pair(self) -> None:
        self.write_events("behavior", "with_skill", "verify-commands")
        self.plan_run("behavior", "old_skill")
        with self.assertRaisesRegex(LaneError, "differs from answer design"):
            exposure_report(self.root / "runs", self.manifest, "verify-commands", "tune")

    def test_rejects_run_missing_from_both_arms(self) -> None:
        self.write_events("behavior", "with_skill", "verify-commands")
        self.write_events("behavior", "old_skill", None)
        self.plan_run("behavior", "with_skill", 2)
        self.plan_run("behavior", "old_skill", 2)
        with self.assertRaisesRegex(
            LaneError,
            "missing=.*behavior/old_skill/run-2.*behavior/with_skill/run-2",
        ):
            exposure_report(self.root / "runs", self.manifest, "verify-commands", "tune")

    def test_rejects_coordinate_absent_from_answer_design(self) -> None:
        self.write_events("behavior", "with_skill", "verify-commands")
        self.write_events("behavior", "old_skill", None)
        extra = self.root / "runs" / "behavior" / "old_skill" / "run-2"
        extra.mkdir(parents=True)
        (extra / "events.json").write_text(json.dumps({"events": []}), encoding="utf-8")
        with self.assertRaisesRegex(LaneError, "extra=.*run-2"):
            exposure_report(self.root / "runs", self.manifest, "verify-commands", "tune")

    def test_rejects_unsupported_event_envelope(self) -> None:
        self.write_events("behavior", "with_skill", "verify-commands")
        self.write_events("behavior", "old_skill", None)
        events_path = self.root / "runs" / "behavior" / "with_skill" / "events.json"
        envelope = json.loads(events_path.read_text(encoding="utf-8"))
        envelope["schema_version"] = 3
        events_path.write_text(json.dumps(envelope), encoding="utf-8")
        with self.assertRaisesRegex(LaneError, "harness event envelope"):
            exposure_report(self.root / "runs", self.manifest, "verify-commands", "tune")

    def test_rejects_non_object_event(self) -> None:
        self.write_events("behavior", "with_skill", "verify-commands")
        self.write_events("behavior", "old_skill", None)
        events_path = self.root / "runs" / "behavior" / "with_skill" / "events.json"
        envelope = json.loads(events_path.read_text(encoding="utf-8"))
        envelope["events"].append("not an event")
        events_path.write_text(json.dumps(envelope), encoding="utf-8")
        with self.assertRaisesRegex(LaneError, "harness event envelope"):
            exposure_report(self.root / "runs", self.manifest, "verify-commands", "tune")

    def test_rejects_a_symlinked_event_file(self) -> None:
        self.write_events("behavior", "with_skill", "verify-commands")
        self.write_events("behavior", "old_skill", None)
        events_path = self.root / "runs" / "behavior" / "with_skill" / "events.json"
        target = self.root / "replacement-events.json"
        events_path.replace(target)
        events_path.symlink_to(target)
        with self.assertRaisesRegex(LaneError, "contains a symlink"):
            exposure_report(self.root / "runs", self.manifest, "verify-commands", "tune")

    def test_rejects_a_symlinked_answer_design(self) -> None:
        self.write_events("behavior", "with_skill", "verify-commands")
        self.write_events("behavior", "old_skill", None)
        design_path = self.root / "runs" / "answer-design.json"
        target = self.root / "replacement-answer-design.json"
        design_path.replace(target)
        design_path.symlink_to(target)
        with self.assertRaisesRegex(LaneError, "contains a symlink"):
            exposure_report(self.root / "runs", self.manifest, "verify-commands", "tune")

    def test_reads_from_the_standard_unresolved_temporary_root(self) -> None:
        self.write_events("behavior", "with_skill", "verify-commands")
        self.write_events("behavior", "old_skill", None)
        report = exposure_report(
            Path(self.temp.name) / "runs",
            Path(self.temp.name) / "manifest.json",
            "verify-commands",
            "tune",
        )
        self.assertTrue(report["eligible"])

    def test_rejects_a_hard_linked_answer_design(self) -> None:
        self.write_events("behavior", "with_skill", "verify-commands")
        self.write_events("behavior", "old_skill", None)
        design_path = self.root / "runs" / "answer-design.json"
        target = self.root / "replacement-answer-design.json"
        design_path.replace(target)
        os.link(target, design_path)
        with self.assertRaisesRegex(LaneError, "exactly one hard link"):
            exposure_report(self.root / "runs", self.manifest, "verify-commands", "tune")

    def test_rejects_a_hard_linked_event_file(self) -> None:
        self.write_events("behavior", "with_skill", "verify-commands")
        self.write_events("behavior", "old_skill", None)
        events_path = self.root / "runs" / "behavior" / "with_skill" / "events.json"
        target = self.root / "replacement-events.json"
        events_path.replace(target)
        os.link(target, events_path)
        with self.assertRaisesRegex(LaneError, "exactly one hard link"):
            exposure_report(self.root / "runs", self.manifest, "verify-commands", "tune")

    def test_rejects_answer_design_swapped_to_a_symlink_at_open(self) -> None:
        self.write_events("behavior", "with_skill", "verify-commands")
        self.write_events("behavior", "old_skill", None)
        design_path = self.root / "runs" / "answer-design.json"
        target = self.root / "replacement-answer-design.json"
        target.write_text(design_path.read_text(encoding="utf-8"), encoding="utf-8")
        real_open = os.open
        swapped = False

        def swap_then_open(path, flags, *args, **kwargs):
            nonlocal swapped
            if path == "answer-design.json" and not swapped:
                swapped = True
                design_path.unlink()
                design_path.symlink_to(target)
            return real_open(path, flags, *args, **kwargs)

        with patch.object(lane_module.os, "open", side_effect=swap_then_open):
            with self.assertRaisesRegex(LaneError, "contains a symlink"):
                exposure_report(self.root / "runs", self.manifest, "verify-commands", "tune")
        self.assertTrue(swapped)

    @unittest.skipUnless(hasattr(os, "mkfifo"), "requires POSIX FIFOs")
    def test_rejects_a_fifo_answer_design_without_blocking(self) -> None:
        self.write_events("behavior", "with_skill", "verify-commands")
        self.write_events("behavior", "old_skill", None)
        design_path = self.root / "runs" / "answer-design.json"
        design_path.unlink()
        os.mkfifo(design_path)
        with self.assertRaisesRegex(LaneError, "not a regular file"):
            exposure_report(self.root / "runs", self.manifest, "verify-commands", "tune")

    @unittest.skipUnless(hasattr(os, "mkfifo"), "requires POSIX FIFOs")
    def test_rejects_a_fifo_event_file_without_blocking(self) -> None:
        self.write_events("behavior", "with_skill", "verify-commands")
        self.write_events("behavior", "old_skill", None)
        events_path = self.root / "runs" / "behavior" / "with_skill" / "events.json"
        events_path.unlink()
        os.mkfifo(events_path)
        with self.assertRaisesRegex(LaneError, "not a regular file"):
            exposure_report(self.root / "runs", self.manifest, "verify-commands", "tune")

    def test_rejects_event_file_swapped_to_a_symlink_at_open(self) -> None:
        self.write_events("behavior", "with_skill", "verify-commands")
        self.write_events("behavior", "old_skill", None)
        events_path = self.root / "runs" / "behavior" / "with_skill" / "events.json"
        target = self.root / "replacement-events.json"
        target.write_text(events_path.read_text(encoding="utf-8"), encoding="utf-8")
        real_open = os.open
        swapped = False

        def swap_then_open(path, flags, *args, **kwargs):
            nonlocal swapped
            if path == "events.json" and not swapped:
                swapped = True
                events_path.unlink()
                events_path.symlink_to(target)
            return real_open(path, flags, *args, **kwargs)

        with patch.object(lane_module.os, "open", side_effect=swap_then_open):
            with self.assertRaisesRegex(LaneError, "contains a symlink"):
                exposure_report(self.root / "runs", self.manifest, "verify-commands", "tune")
        self.assertTrue(swapped)

    def test_rejects_a_symlinked_runs_root(self) -> None:
        self.write_events("behavior", "with_skill", "verify-commands")
        self.write_events("behavior", "old_skill", None)
        linked_runs = self.root / "linked-runs"
        linked_runs.symlink_to(self.root / "runs", target_is_directory=True)
        with self.assertRaisesRegex(LaneError, "contains a symlink"):
            exposure_report(linked_runs, self.manifest, "verify-commands", "tune")

    def test_rejects_a_runs_root_below_a_symlinked_ancestor(self) -> None:
        self.write_events("behavior", "with_skill", "verify-commands")
        self.write_events("behavior", "old_skill", None)
        alias = self.root / "alias"
        alias.symlink_to(self.root, target_is_directory=True)
        with self.assertRaisesRegex(LaneError, "contains a symlink"):
            exposure_report(alias / "runs", self.manifest, "verify-commands", "tune")

    def test_rejects_duplicate_answer_design_coordinate(self) -> None:
        self.write_events("behavior", "with_skill", "verify-commands")
        self.write_events("behavior", "old_skill", None)
        design_path = self.root / "runs" / "answer-design.json"
        design = json.loads(design_path.read_text(encoding="utf-8"))
        identities = design["identities"]
        duplicate = dict(next(row for row in identities if row["variant"] == "with_skill"))
        duplicate["run_dir"] = "behavior/with_skill/run-1"
        identities.append(duplicate)
        self.write_design(identities)
        with self.assertRaisesRegex(LaneError, "duplicate answer design run coordinate"):
            exposure_report(self.root / "runs", self.manifest, "verify-commands", "tune")


if __name__ == "__main__":
    unittest.main()
