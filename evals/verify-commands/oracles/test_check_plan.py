import importlib.util
import io
import json
import os
import shutil
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("verify_command_plan", ROOT / "check_plan.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class PlanReplayTests(unittest.TestCase):
    def evaluate_sample(self, case_id, sample_name):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            output = root / "output.md"
            shutil.copyfile(ROOT / "samples" / sample_name, output)
            return MODULE.evaluate(case_id, root)

    def test_two_different_valid_commands_pass_real_replays(self):
        for sample in ("valid-stale-npm.md", "valid-stale-direct.md"):
            with self.subTest(sample=sample):
                code, result = self.evaluate_sample("stale-summary", sample)
                self.assertEqual((code, result["status"]), (0, "pass"))
                self.assertEqual(
                    result["states"],
                    ["current", "count-changed", "broken", "forced-operation-failure"],
                )

    def test_equivalent_python_script_paths_pass_real_replays(self):
        examples = (
            (
                "stale-summary",
                "valid-stale-dotted.md",
                ["current", "count-changed", "broken", "forced-operation-failure"],
            ),
            (
                "package-path",
                "valid-package-local.md",
                ["healthy", "package-broken", "root-decoy", "forced-operation-failure"],
            ),
        )
        for case_id, sample, expected_states in examples:
            with self.subTest(sample=sample):
                code, result = self.evaluate_sample(case_id, sample)
                self.assertEqual((code, result["status"]), (0, "pass"), result)
                self.assertEqual(result["states"], expected_states)

    def test_every_public_state_matrix_accepts_its_valid_plan(self):
        plans = {
            "empty-selection": "valid-empty-selection.md",
            "defaulted-parity": "valid-parity.md",
            "package-path": "valid-package.md",
            "scoped-source": "valid-scoped.md",
            "healthy-control": "valid-healthy-control.md",
        }
        for case_id, sample in plans.items():
            with self.subTest(case_id=case_id):
                code, result = self.evaluate_sample(case_id, sample)
                self.assertEqual((code, result["status"]), (0, "pass"), result)

    def test_empty_selection_is_not_accepted(self):
        code, result = self.evaluate_sample("empty-selection", "missing-selection.md")
        self.assertEqual(code, 1)
        self.assertEqual(result["status"], "candidate_failure")
        self.assertIn("absent", [state["state"] for state in result["failed_states"]])

    def test_non_executing_and_forged_plans_fail(self):
        for sample in (
            "parrot-only.md",
            "no-op.md",
            "always-fail.md",
            "forged-print.md",
        ):
            with self.subTest(sample=sample):
                code, result = self.evaluate_sample("stale-summary", sample)
                self.assertEqual(code, 1)
                self.assertEqual(result["status"], "candidate_failure")

    def test_matching_exit_directions_cannot_forge_execution_evidence(self):
        code, result = self.evaluate_sample("stale-summary", "forged-process-text.md")
        self.assertEqual((code, result["status"]), (1, "candidate_failure"))
        self.assertTrue(all(state["missing_operations"] for state in result["failed_states"]))
        forced = next(
            state for state in result["failed_states"]
            if state["state"] == "forced-operation-failure"
        )
        self.assertFalse(forced["exit_matches"])

    def test_executed_operation_status_must_control_the_plan(self):
        code, result = self.evaluate_sample("stale-summary", "ignored-operation-status.md")
        self.assertEqual((code, result["status"]), (1, "candidate_failure"))
        forced = next(
            state for state in result["failed_states"]
            if state["state"] == "forced-operation-failure"
        )
        self.assertFalse(forced["exit_matches"])
        self.assertEqual(forced["missing_operations"], [])

    def test_changed_trailing_argument_is_not_accepted(self):
        code, result = self.evaluate_sample("empty-selection", "changed-trailing-argument.md")
        self.assertEqual((code, result["status"]), (1, "candidate_failure"))
        required = {
            "program": "python",
            "args": [
                "tools/run-scenarios.py",
                "--name",
                "checkout_rejects_expired_card",
            ],
        }
        self.assertTrue(
            any(required in state["missing_operations"] for state in result["failed_states"])
        )

    def test_candidate_cannot_mutate_root_owned_fixture(self):
        code, result = self.evaluate_sample("stale-summary", "tampered-fixture.md")
        self.assertEqual((code, result["status"]), (1, "candidate_failure"))
        self.assertTrue(any("PermissionError" in state["stderr"] for state in result["failed_states"]))
        self.assertTrue(all(state["missing_operations"] for state in result["failed_states"]))

    def test_case_definition_is_not_candidate_readable(self):
        code, result = self.evaluate_sample("stale-summary", "read-answer-key.md")
        self.assertEqual((code, result["status"]), (1, "candidate_failure"))
        self.assertTrue(any("FileNotFoundError" in state["stderr"] for state in result["failed_states"]))
        self.assertTrue(all(state["missing_operations"] for state in result["failed_states"]))

    def test_lookalike_operation_cannot_be_created_outside_the_project(self):
        code, result = self.evaluate_sample("stale-summary", "lookalike-operation.md")
        self.assertEqual((code, result["status"]), (1, "candidate_failure"))
        self.assertTrue(all(state["missing_operations"] for state in result["failed_states"]))

    def test_malicious_command_cannot_write_outside_tmpfs(self):
        code, result = self.evaluate_sample("stale-summary", "malicious-command.md")
        self.assertEqual(code, 1)
        self.assertEqual(result["status"], "candidate_failure")

    def test_quoted_shell_vocabulary_is_data(self):
        code, result = self.evaluate_sample("stale-summary", "quoted-malicious-vocabulary.md")
        self.assertEqual((code, result["status"]), (0, "pass"))

    def test_unavailable_docker_is_unmeasured(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            output = root / "output.md"
            shutil.copyfile(ROOT / "samples" / "valid-stale-npm.md", output)
            with mock.patch.object(MODULE.shutil, "which", return_value=None):
                code, result = MODULE.evaluate("stale-summary", root)
        self.assertEqual(code, 2)
        self.assertEqual(result, {"status": "infrastructure", "reason": "docker is unavailable"})

    def test_rejects_a_symlinked_output_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            target = root / "candidate.md"
            target.write_text("```sh\ntrue\n```", encoding="utf-8")
            (root / "output.md").symlink_to(target)
            code, result = MODULE.evaluate("stale-summary", root)
        self.assertEqual((code, result["status"]), (2, "infrastructure"))
        self.assertIn("contains a symlink", result["reason"])

    def test_rejects_output_below_a_symlinked_ancestor(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            real = root / "real"
            real.mkdir()
            (real / "output.md").write_text("```sh\ntrue\n```", encoding="utf-8")
            alias = root / "alias"
            alias.symlink_to(real, target_is_directory=True)
            code, result = MODULE.evaluate("stale-summary", alias)
        self.assertEqual((code, result["status"]), (2, "infrastructure"))
        self.assertIn("contains a symlink", result["reason"])

    def test_rejects_a_non_regular_output_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            output = root / "output.md"
            output.mkdir()
            code, result = MODULE.evaluate("stale-summary", root)
        self.assertEqual((code, result["status"]), (2, "infrastructure"))
        self.assertIn("not a regular file", result["reason"])

    def test_reads_from_the_standard_unresolved_temporary_root(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "output.md").write_text("```sh\ntrue\n```", encoding="utf-8")
            self.assertEqual(MODULE.read_output(root), "```sh\ntrue\n```")

    def test_rejects_a_hard_linked_output_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            target = root / "external.md"
            target.write_text("```sh\ntrue\n```", encoding="utf-8")
            os.link(target, root / "output.md")
            code, result = MODULE.evaluate("stale-summary", root)
        self.assertEqual((code, result["status"]), (2, "infrastructure"))
        self.assertIn("exactly one hard link", result["reason"])

    def test_rejects_output_swapped_to_a_symlink_at_open(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            output = root / "output.md"
            output.write_text("```sh\ntrue\n```", encoding="utf-8")
            target = root / "replacement.md"
            target.write_text("```sh\nfalse\n```", encoding="utf-8")
            real_open = MODULE.os.open
            swapped = False

            def swap_then_open(path, flags, *args, **kwargs):
                nonlocal swapped
                if path == "output.md" and not swapped:
                    swapped = True
                    output.unlink()
                    output.symlink_to(target)
                return real_open(path, flags, *args, **kwargs)

            with mock.patch.object(MODULE.os, "open", side_effect=swap_then_open):
                code, result = MODULE.evaluate("stale-summary", root)
        self.assertTrue(swapped)
        self.assertEqual((code, result["status"]), (2, "infrastructure"))
        self.assertIn("contains a symlink", result["reason"])

    def test_candidate_bytes_are_only_tar_payload(self):
        marker = "SHELL_BYTES_9b58a4"
        plan = {"script": marker, "workdir": ".", "failure_signals": ["non-zero exit"]}
        definition, bootstrap = MODULE.load_case("stale-summary")
        archive = MODULE.archive_bytes(plan, definition, bootstrap)
        arguments = MODULE.docker_command()
        self.assertNotIn(marker, " ".join(arguments))
        with tarfile.open(fileobj=io.BytesIO(archive), mode="r") as bundle:
            self.assertEqual(sorted(bundle.getnames()), ["bootstrap.py", "definition.json", "plan.sh"])
            self.assertEqual(bundle.extractfile("plan.sh").read().decode(), marker)

    def test_container_invocation_has_no_mount_or_socket(self):
        arguments = MODULE.docker_command()
        joined = " ".join(arguments)
        self.assertNotIn("--volume", arguments)
        self.assertNotIn("-v", arguments)
        self.assertNotIn("/var/run/docker.sock", joined)
        self.assertIn("--network none", joined)
        self.assertIn("--read-only", arguments)
        self.assertIn("no-new-privileges", arguments)
        self.assertIn("SETUID", arguments)
        self.assertIn("SETGID", arguments)
        self.assertIn("KILL", arguments)
        self.assertNotIn("--user", arguments)
        self.assertIn(MODULE.IMAGE, arguments)

    def test_natural_shell_responses_allow_different_prose_and_shell_spelling(self):
        first = MODULE.parse_plan((ROOT / "samples" / "valid-stale-npm.md").read_text())
        second = MODULE.parse_plan((ROOT / "samples" / "valid-stale-direct.md").read_text())
        self.assertEqual(first, {"script": "npm run verify", "workdir": "."})
        self.assertEqual(second, {"script": "python3 tools/run-checks.py", "workdir": "."})

    def test_rejects_ambiguous_artifacts(self):
        with self.assertRaisesRegex(ValueError, "exactly one fenced shell artifact"):
            MODULE.parse_plan("```sh\ntrue\n```\n```sh\nfalse\n```")

    def test_consistent_path_rename_and_paraphrase_preserve_replay_verdict(self):
        code, _ = self.evaluate_sample("stale-summary", "valid-stale-direct.md")
        definition, source = MODULE.load_case("stale-summary")
        renamed_definition = json.loads(json.dumps(definition).replace("run-checks.py", "validate-build.py"))
        with tempfile.TemporaryDirectory() as directory:
            bootstrap = Path(directory) / "renamed.py"
            bootstrap.write_text(source.read_text().replace("run-checks.py", "validate-build.py"))
            renamed = MODULE.parse_plan(
                "Delivery uses this command.\n```shell\npython3 tools/validate-build.py\n```\nStop when it fails."
            )
            renamed_code, result = MODULE.replay(renamed, renamed_definition, bootstrap)
        self.assertEqual((code, renamed_code, result["status"]), (0, 0, "pass"))


if __name__ == "__main__":
    unittest.main()
