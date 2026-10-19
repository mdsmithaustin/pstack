import importlib.util
import fcntl
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest

SPEC = importlib.util.spec_from_file_location("port_value_study", Path(__file__).with_name("study.py"))
study = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(study)


def program(level):
    return f"import json\nprint(json.dumps({{'level': {level}}}))\n"


ORACLE = '''import argparse
import json
from pathlib import Path
import subprocess
import sys

parser = argparse.ArgumentParser()
parser.add_argument("--project", type=Path, required=True)
parser.add_argument("--stage", required=True)
args = parser.parse_args()
observed = subprocess.run([sys.executable, str(args.project / "app.py")], capture_output=True, text=True)
expected = 1 if args.stage == "initial" else 2
try:
    passed = observed.returncode == 0 and json.loads(observed.stdout)["level"] >= expected
except (ValueError, KeyError):
    passed = False
print(json.dumps({"passed": passed, "assertions": 1, "failures": [] if passed else ["required level absent"]}))
sys.exit(0 if passed else 1)
'''


def recording_grader(oracle, snapshot, stage, receipt):
    receipt.mkdir(parents=True)
    with tempfile.TemporaryDirectory(prefix="local-oracle-") as temporary:
        project = study.replay(snapshot, Path(temporary) / "app")
        result = subprocess.run([sys.executable, "-I", "-B", str(oracle), "--project", str(project), "--stage", stage], capture_output=True)
    (receipt / "oracle.stdout").write_bytes(result.stdout)
    (receipt / "oracle.stderr").write_bytes(result.stderr)
    grade = {"state": "graded", **study.parse_grade(result.stdout, result.returncode)}
    study.write_json(receipt / "receipt.json", grade)
    return grade


def recording_templates():
    return {"local-recording:1": {"id": "recording-identity"}}


class RecordingApplication:
    def __init__(self, *, fail_initial=False, omit_capture=False):
        self.fail_initial = fail_initial
        self.omit_capture = omit_capture
        self.calls = []

    def __call__(self, request, slot):
        slot.mkdir(parents=True)
        project = study.replay(request.project, slot / "workspace")
        maintenance = "history" in request.prompt
        inherited = (project / "record.json").read_text() if (project / "record.json").exists() else None
        self.calls.append({"prompt": request.prompt, "parent": request.project.sha256,
                           "inherited": inherited, "skills": request.skills is not None,
                           "files": sorted(path.name for path in project.iterdir())})
        if maintenance and inherited != '{"created":true}\n':
            raise ValueError("maintenance did not receive captured parent data")
        (project / "app.py").write_text(program(2 if maintenance else 1))
        (project / "record.json").write_text('{"created":true}\n')
        native_valid = not (self.fail_initial and not maintenance)
        capture = None if self.omit_capture else study.Snapshot.freeze(project, slot / "capture")
        receipt = slot / "receipt.json"
        study.write_json(receipt, {"native_valid": native_valid, "capture_sha256": capture.sha256 if capture else None})
        return SimpleNamespace(state="completed" if native_valid else "native_failed", native_valid=native_valid,
                               capture=capture, receipt=receipt, elapsed_s=0.25,
                               usage=None if maintenance else {"input_tokens": 7, "output_tokens": 3})


class Study(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="port-instrument-")
        self.addCleanup(self.clean)
        self.root = Path(self.temporary.name)
        self.cases = self.root / "cases"
        for name in ("parcel", "meter", "retention"):
            directory = self.cases / name
            for label, level in (("project", 0), ("initial", 1), ("maintenance", 2), ("noop", 0), ("targeted", 1)):
                (directory / label).mkdir(parents=True)
                (directory / label / "app.py").write_text(program(level))
            (directory / "initial.txt").write_text(f"Add a count command to the {name} tool.\n")
            (directory / "maintenance.txt").write_text(f"Add history support to the {name} tool. Retain its existing data.\n")
            (directory / "oracle.py").write_text(ORACLE)
            study.write_json(directory / "case.json", {"id": name, "project": "project", "initial_request": "initial.txt",
                            "maintenance_request": "maintenance.txt", "oracle": "oracle.py",
                            "controls": {label: label for label in ("initial", "maintenance", "noop", "targeted")}})
        self.runtime = self.root / "runtime.json"
        study.write_json(self.runtime, {"template": "local-recording:1", "observed_template_id": "recording-identity",
                                       "cli_version": "recording executable", "capabilities": {"skills": True, "multi_agent": True}})
        self.directory = self.root / "run"

    def clean(self):
        for root, directories, files in os.walk(self.root):
            Path(root).chmod(0o755)
            for name in directories:
                (Path(root) / name).chmod(0o755)
            for name in files:
                (Path(root) / name).chmod(0o644)
        self.temporary.cleanup()

    def prepare(self, **kwargs):
        return study.prepare(self.directory, self.cases, self.runtime, model="recording", effort="high", grader=recording_grader, template_catalog=recording_templates, **kwargs)

    def test_preparation_calibrates_real_program_results_and_keeps_all_denominators(self):
        plan = self.prepare()
        self.assertEqual(len(plan["cells"]), 18)
        self.assertEqual([cell["id"] for cell in plan["cells"]], [f"p{index:02d}" for index in range(1, 19)])
        self.assertEqual(len({(cell["case"], cell["arm"], cell["repetition"]) for cell in plan["cells"]}), 18)
        for offset in range(0, 18, 3):
            block = plan["cells"][offset:offset + 3]
            self.assertEqual({cell["arm"] for cell in block}, set(study.ARMS))
            self.assertEqual(len({(cell["case"], cell["repetition"]) for cell in block}), 1)
        observed = study.read_json(self.directory / "calibration.json")
        self.assertTrue(observed["passed"])
        self.assertEqual(len(observed["checks"]), 15)
        self.assertEqual(sum(row["observed"]["passed"] for row in observed["checks"]), 6)
        report = study.report(self.directory)
        self.assertEqual(report["planned_opportunities"], 36)
        self.assertEqual(len(report["rows"]), 18)
        for arm in study.ARMS:
            self.assertEqual(report["totals"][arm]["states"], {"never_started": 12})
            self.assertEqual(report["totals"][arm]["unknown_usage_opportunities"], 12)
            self.assertEqual(report["totals"][arm]["accepted_both"], 0)

    def test_schedule_is_seeded_and_arm_order_is_blocked(self):
        first = self.prepare(seed=872)
        self.directory = self.root / "second"
        second = self.prepare(seed=872)
        self.assertEqual(first["cells"], second["cells"])
        self.directory = self.root / "third"
        third = self.prepare(seed=873)
        self.assertNotEqual(first["cells"], third["cells"])

    def test_failed_native_initial_still_binds_exact_capture_and_passes_no_feedback(self):
        plan = self.prepare()
        cell = plan["cells"][0]
        executor = RecordingApplication(fail_initial=True)
        study.run(self.directory, cell_id=cell["id"], execute=executor, grader=recording_grader, template_catalog=recording_templates)
        self.assertEqual(len(executor.calls), 2)
        initial = study.read_json(self.directory / "lineages" / cell["id"] / "initial/outcome.json")
        self.assertEqual(executor.calls[1]["parent"], initial["capture"]["sha256"])
        self.assertEqual(executor.calls[1]["inherited"], '{"created":true}\n')
        self.assertEqual(executor.calls[0]["files"], ["app.py"])
        case = next(case for case in plan["cases"] if case["id"] == cell["case"])
        private = self.directory / "inputs" / case["directory"]
        for call, stage in zip(executor.calls, study.STAGES):
            self.assertEqual(call["prompt"], (private / case[f"{stage}_request"]).read_text())
        row = next(row for row in study.report(self.directory)["rows"] if row["id"] == cell["id"])
        self.assertFalse(row["initial"]["accepted"])
        self.assertTrue(row["initial"]["grade"]["passed"])
        self.assertTrue(row["maintenance"]["accepted"])
        self.assertFalse(row["both_accepted"])

    def test_missing_capture_blocks_maintenance_and_existing_slots_never_retry(self):
        cell = self.prepare()["cells"][0]
        executor = RecordingApplication(omit_capture=True)
        study.run(self.directory, cell_id=cell["id"], execute=executor, grader=recording_grader, template_catalog=recording_templates)
        study.run(self.directory, cell_id=cell["id"], execute=executor, grader=recording_grader, template_catalog=recording_templates)
        self.assertEqual(len(executor.calls), 1)
        row = next(row for row in study.report(self.directory)["rows"] if row["id"] == cell["id"])
        self.assertEqual(row["maintenance"]["state"], "blocked")
        self.assertFalse(row["maintenance"]["accepted"])

    def test_limited_run_continues_only_unspent_stage_and_keeps_unknown_usage(self):
        cell = self.prepare()["cells"][0]
        executor = RecordingApplication()
        relative_directory = Path(os.path.relpath(self.directory, Path.cwd()))
        study.run(relative_directory, cell_id=cell["id"], limit=1, execute=executor, grader=recording_grader, template_catalog=recording_templates)
        self.assertEqual(len(executor.calls), 1)
        study.run(self.directory, cell_id=cell["id"], limit=1, execute=executor, grader=recording_grader, template_catalog=recording_templates)
        self.assertEqual(len(executor.calls), 2)
        report = study.report(self.directory)
        total = report["totals"][cell["arm"]]
        self.assertEqual(total["known_usage_opportunities"], 1)
        self.assertEqual(total["unknown_usage_opportunities"], 11)
        self.assertEqual(total["accepted_both"], 1)
        self.assertEqual(report["planned_opportunities"], 36)

    def test_frozen_input_tamper_prevents_every_call(self):
        cell = self.prepare()["cells"][0]
        prompt = next((self.directory / "inputs/cases").glob("*/initial.txt"))
        prompt.chmod(0o644)
        prompt.write_text("A different request.\n")
        executor = RecordingApplication()
        with self.assertRaisesRegex(ValueError, "frozen study input changed"):
            study.run(self.directory, execute=executor, grader=recording_grader, template_catalog=recording_templates)
        self.assertEqual(executor.calls, [])
        report = study.report(self.directory)
        self.assertIn("frozen study input changed", report["input_integrity_error"])
        self.assertEqual(report["planned_opportunities"], 36)
        self.assertEqual(sum(row["both_accepted"] for row in report["rows"]), 0)
        plan_path = self.directory / "inputs/plan.json"
        changed = study.read_json(plan_path)
        changed["cells"].pop()
        plan_path.chmod(0o644)
        study.write_json(plan_path, changed)
        self.assertEqual(study.report(self.directory)["planned_opportunities"], 36)

    def test_failed_calibration_never_produces_sealed_callable_plan(self):
        for path in self.cases.glob("*/maintenance/app.py"):
            path.write_text(program(0))
        with self.assertRaisesRegex(ValueError, "oracle calibration failed"):
            self.prepare()
        self.assertFalse((self.directory / "seal.json").exists())
        self.assertFalse(study.read_json(self.directory / "calibration.json")["passed"])

    def test_changed_template_identity_consumes_claim_without_starting_a_native_call(self):
        cell = self.prepare()["cells"][0]
        executor = RecordingApplication()
        study.run(self.directory, cell_id=cell["id"], execute=executor, grader=recording_grader,
                  template_catalog=lambda: {"local-recording:1": {"id": "changed"}})
        self.assertEqual(executor.calls, [])
        row = next(row for row in study.report(self.directory)["rows"] if row["id"] == cell["id"])
        self.assertEqual(row["initial"]["state"], "incomplete")
        self.assertIn("template identity changed", row["initial"]["reason"])
        self.assertEqual(row["maintenance"]["state"], "blocked")

    def test_strict_oracle_protocol_rejects_empty_and_false_green_outputs(self):
        for stdout, code in ((b"", 0), (b"{}", 0),
                             (b'{"passed":true,"assertions":0,"failures":[]}', 0),
                             (b'{"passed":true,"assertions":true,"failures":[]}', 0),
                             (b'{"passed":true,"assertions":1,"failures":["bad"]}', 0),
                             (b'{"passed":false,"assertions":1,"failures":["bad"]}', 0),
                             (b'{"passed":true,"passed":false,"assertions":1,"failures":[]}', 0),
                             (b'{"passed":true,"assertions":1,"failures":[]}\nnoise', 0)):
            with self.subTest(stdout=stdout, code=code), self.assertRaises(ValueError):
                study.parse_grade(stdout, code)
        self.assertEqual(study.parse_grade(b'{"passed":true,"assertions":1,"failures":[]}', 0),
                         {"passed": True, "assertions": 1, "failures": []})

    def test_crashed_claim_is_spent_and_retains_planned_row(self):
        cell = self.prepare()["cells"][0]
        initial = self.directory / "lineages" / cell["id"] / "initial"
        initial.mkdir(parents=True)
        executor = RecordingApplication()
        study.run(self.directory, cell_id=cell["id"], execute=executor, grader=recording_grader, template_catalog=recording_templates)
        self.assertEqual(executor.calls, [])
        row = next(row for row in study.report(self.directory)["rows"] if row["id"] == cell["id"])
        self.assertEqual(row["initial"]["state"], "incomplete")
        self.assertEqual(row["maintenance"]["state"], "blocked")

    def test_two_concurrent_lineages_preserve_their_own_captures(self):
        self.prepare()
        barrier = threading.Barrier(2)
        lock = threading.Lock()

        class ConcurrentApplication(RecordingApplication):
            active = 0
            peak = 0

            def __call__(self, request, slot):
                with lock:
                    self.active += 1
                    self.peak = max(self.peak, self.active)
                try:
                    barrier.wait(timeout=5)
                    return super().__call__(request, slot)
                finally:
                    with lock:
                        self.active -= 1

        executor = ConcurrentApplication()
        study.run(self.directory, limit=4, concurrency=2, execute=executor, grader=recording_grader, template_catalog=recording_templates)
        self.assertEqual(executor.peak, 2)
        self.assertEqual(len(executor.calls), 4)
        self.assertEqual(sum(row["both_accepted"] for row in study.report(self.directory)["rows"]), 2)

    def test_a_second_dispatch_cannot_exceed_the_study_concurrency_limit(self):
        self.prepare()
        executor = RecordingApplication()
        with (self.directory / "dispatch.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self.assertRaises(BlockingIOError):
                study.run(self.directory, execute=executor, grader=recording_grader,
                          template_catalog=recording_templates)
        self.assertEqual(executor.calls, [])

    def test_upstream_invocation_translation_preserves_explicit_policy_and_all_other_bytes(self):
        directory = self.root / "guidance"
        entry = directory / "manual/SKILL.md"
        entry.parent.mkdir(parents=True)
        original = b'---\nname: manual\ndisable-model-invocation: true\n---\n\nUse the live tool.\n'
        entry.write_bytes(original)
        ledger = study.adapt_upstream(directory)
        self.assertEqual(entry.read_bytes(), b'---\nname: manual\n---\n\nUse the live tool.\n')
        self.assertEqual((entry.parent / "agents/openai.yaml").read_text(), "policy:\n  allow_implicit_invocation: false\n")
        self.assertEqual(len(ledger["edits"]), 2)
        self.assertEqual(ledger["edits"][0]["before_sha256"], study.digest(original))


if __name__ == "__main__":
    unittest.main()
