import importlib.util
import io
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
            output = Path(directory) / "output.md"
            shutil.copyfile(ROOT / "samples" / sample_name, output)
            return MODULE.evaluate(case_id, Path(directory))

    def test_two_different_valid_commands_pass_real_replays(self):
        for sample in ("valid-stale-npm.md", "valid-stale-direct.md"):
            with self.subTest(sample=sample):
                code, result = self.evaluate_sample("stale-summary", sample)
                self.assertEqual((code, result["status"]), (0, "pass"))
                self.assertEqual(result["states"], ["current", "count-changed", "broken"])

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
        for sample in ("parrot-only.md", "no-op.md", "always-fail.md", "forged-print.md"):
            with self.subTest(sample=sample):
                code, result = self.evaluate_sample("stale-summary", sample)
                self.assertEqual(code, 1)
                self.assertEqual(result["status"], "candidate_failure")

    def test_malicious_command_cannot_write_outside_tmpfs(self):
        code, result = self.evaluate_sample("stale-summary", "malicious-command.md")
        self.assertEqual(code, 1)
        self.assertEqual(result["status"], "candidate_failure")

    def test_quoted_shell_vocabulary_is_data(self):
        code, result = self.evaluate_sample("stale-summary", "quoted-malicious-vocabulary.md")
        self.assertEqual((code, result["status"]), (0, "pass"))

    def test_unavailable_docker_is_unmeasured(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "output.md"
            shutil.copyfile(ROOT / "samples" / "valid-stale-npm.md", output)
            with mock.patch.object(MODULE.shutil, "which", return_value=None):
                code, result = MODULE.evaluate("stale-summary", Path(directory))
        self.assertEqual(code, 2)
        self.assertEqual(result, {"status": "infrastructure", "reason": "docker is unavailable"})

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
        self.assertIn("65534:65534", arguments)
        self.assertIn(MODULE.IMAGE, arguments)

    def test_record_shape_is_exact(self):
        with self.assertRaisesRegex(ValueError, "only one verification-plan"):
            MODULE.parse_plan("prose <verification-plan>{}</verification-plan>")
        with self.assertRaisesRegex(ValueError, "exactly script"):
            MODULE.parse_plan(
                '<verification-plan>{"script":":","workdir":".","failure_signals":["non-zero exit"],"note":"extra"}</verification-plan>'
            )


if __name__ == "__main__":
    unittest.main()
