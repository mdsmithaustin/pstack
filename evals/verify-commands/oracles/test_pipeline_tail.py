import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent


class PipelineTailTests(unittest.TestCase):
    def run_script(self, script, selector="pipeline-tail"):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory).resolve()
            (output / "output.md").write_text("```sh\n" + script + "\n```\n")
            result = subprocess.run(
                [sys.executable, str(ROOT / "check_plan.py"), selector, str(output)],
                capture_output=True, text=True, timeout=60,
            )
            self.assertNotEqual(result.returncode, 2, result.stderr + result.stdout)
            return result.returncode, json.loads(result.stdout)

    def test_public_cli_accepts_multiple_correct_repairs(self):
        for name in ("valid-pipeline-bash", "valid-pipeline-log", "valid-pipeline-normalized"):
            with self.subTest(name=name):
                answer = (ROOT / "samples" / (name + ".md")).read_text()
                code, result = self.run_script(answer.split("```sh\n")[1].split("\n```")[0])
                self.assertEqual((code, result["status"]), (0, "pass"), result)
                evidence = result["output_evidence"]
                self.assertEqual([item["state"] for item in evidence], ["healthy", "broken", "forced-operation-failure"])
                self.assertTrue(all(item["output_matches"] for item in evidence), result)
                self.assertEqual(evidence[0]["stdout"].splitlines()[0], "check 11")
                self.assertEqual(evidence[1]["stdout"].splitlines()[-1], "ERROR release blocked")
                self.assertEqual(evidence[2]["stdout"], "")

    def test_public_cli_rejects_output_and_verdict_violations(self):
        for name in ("silent", "unfiltered", "unprotected", "ignored", "nineteen", "twentyone", "wrong-suffix", "no-operation", "print-only"):
            with self.subTest(name=name):
                answer = (ROOT / "samples" / (name + "-pipeline.md")).read_text()
                code, result = self.run_script(answer.split("```sh\n")[1].split("\n```")[0])
                self.assertEqual((code, result["status"]), (1, "candidate_failure"), result)

    def test_scratch_resets_and_prepared_project_is_immutable(self):
        script = """test ! -e "$TMPDIR/seen" || exit 90
touch "$TMPDIR/seen" || exit 91
if (printf tampered >release-state.json) 2>/dev/null; then exit 92; fi
if (printf tampered >tools/verify-release.py) 2>/dev/null; then exit 93; fi
bash -o pipefail -c 'python3 tools/verify-release.py 2>&1 | tail -n 20'"""
        code, result = self.run_script(script)
        self.assertEqual((code, result["status"]), (0, "pass"), result)

    def test_old_selector_has_no_scratch_or_file_write_allowance(self):
        script = """test -z "${TMPDIR+x}" || exit 90
if (printf tampered >/work/run/project/scratch) 2>/dev/null; then exit 91; fi
if (printf tampered >/dev/shm/scratch) 2>/dev/null; then exit 92; fi
python3 tools/verify-release.py"""
        code, result = self.run_script(script, "healthy-control")
        self.assertEqual((code, result["status"]), (0, "pass"), result)


if __name__ == "__main__":
    unittest.main()
