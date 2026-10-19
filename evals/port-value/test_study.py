import importlib.util
import fcntl
from dataclasses import asdict
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import tomllib
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
    grade = {"state": "graded", **study.parse_grade(result.stdout, result.returncode),
             "returncode": result.returncode, "stage": stage, "capture_sha256": snapshot.sha256,
             "oracle_sha256": study.digest(oracle.read_bytes())}
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
        state = "completed" if native_valid else "native_failed"
        study.write_json(receipt, {"state": state, "native_valid": native_valid,
                                 "capture": {"directory": str(capture.directory), "sha256": capture.sha256} if capture else None,
                                 "spec": {"runtime": asdict(request.runtime), "project": request.project.sha256, "skills": request.skills.sha256 if request.skills else None,
                                          "prompt_sha256": study.digest(request.prompt.encode())}})
        return SimpleNamespace(state=state, native_valid=native_valid,
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

    def test_prepared_guidance_survives_real_git_clone_with_original_modes(self):
        plan = self.prepare()
        for arm in ("upstream", "current"):
            cell = next(cell for cell in plan["cells"] if cell["arm"] == arm)

            def clone_application(request, slot):
                slot.mkdir(parents=True)
                staging = slot / "staging"
                skills = study.replay(request.skills, staging / ".agents/skills")
                subprocess.run(["git", "init", "-q", "--template=", str(staging)], check=True)
                subprocess.run(["git", "-C", str(staging), "add", "--all"], check=True)
                subprocess.run(["git", "-C", str(staging), "-c", "user.name=control", "-c", "user.email=control",
                                "commit", "-qm", "guidance"], check=True)
                clone = slot / "clone"
                subprocess.run(["git", "clone", "-q", "--no-hardlinks", str(staging), str(clone)], check=True)
                after = study.Snapshot.freeze(clone / ".agents/skills", slot / "cloned-guidance")
                self.assertEqual(after.sha256, request.skills.sha256)
                self.assertEqual((skills / "poteto-mode/SKILL.md").stat().st_mode & 0o777, 0o644)
                return RecordingApplication()(request, slot / "result")

            with self.subTest(arm=arm):
                outcome = study.run_stage(self.directory, plan, cell, "initial", execute=clone_application,
                                          grader=recording_grader, template_catalog=recording_templates)
                self.assertEqual(outcome["state"], "attempted", outcome)

    def test_upstream_native_registration_preserves_pinned_persona_bodies_and_ledgers_all_bytes(self):
        self.prepare()
        skills = self.directory / "inputs/guidance/upstream"
        installer = skills / "pstack-harness/scripts/subagents.py"
        self.assertTrue(installer.is_file())
        self.assertFalse((skills / "pstack-harness/SKILL.md").exists())
        project = self.root / "native-project"
        project.mkdir()
        before_install = study.inventory(skills)
        subprocess.run([sys.executable, str(installer), "install", "--harness", "codex", "--project", str(project)],
                       capture_output=True, check=True)
        self.assertEqual(study.inventory(skills), before_install)
        ledger = study.read_json(self.directory / "inputs/compatibility.json")
        self.assertEqual(sum(edit["kind"] == "invocation_policy" for edit in ledger["edits"]), 102)
        original_skills = self.root / "upstream-original"
        study.export_tree(study.REPO, study.UPSTREAM, "pstack/skills", original_skills)
        expected = {path.relative_to(original_skills).as_posix(): path.read_bytes()
                    for path in original_skills.rglob("*") if path.is_file()}
        for edit in ledger["edits"]:
            if edit["kind"] == "native_registration":
                continue
            if edit["kind"] == "invocation_policy":
                self.assertEqual(expected.get(edit["path"]), edit["before"].encode() if edit["before"] is not None else None)
            expected[edit["path"]] = edit["after"].encode()
        self.assertEqual({path.relative_to(skills).as_posix(): path.read_bytes()
                          for path in skills.rglob("*") if path.is_file()}, expected)
        for name in ("poteto-agent", "comment-sicko"):
            original = subprocess.run(["git", "-C", str(study.REPO), "show",
                                       f"{study.UPSTREAM}:pstack/agents/{name}.md"], capture_output=True, check=True).stdout
            self.assertEqual((skills / f"pstack-harness/upstream-agents/{name}.md").read_bytes(), original)
            generated = project / f".codex/agents/{name}.toml"
            native = tomllib.loads(generated.read_text())
            body = original.decode().split("---\n", 2)[2]
            self.assertEqual(native["name"], name)
            self.assertEqual(native["developer_instructions"], ledger["delivery_prefix"] + body)
            entry = next(edit for edit in ledger["edits"] if edit["path"] == f".codex/agents/{name}.toml")
            self.assertEqual(entry["after"].encode(), generated.read_bytes())
            self.assertEqual(entry["after_sha256"], study.digest(generated.read_bytes()))
        self.assertEqual(len(ledger["edits"]), 107)

    def test_report_rejects_tampered_retained_capture_without_repeating_spent_calls(self):
        cell = self.prepare()["cells"][0]
        executor = RecordingApplication()
        study.run(self.directory, cell_id=cell["id"], execute=executor, grader=recording_grader, template_catalog=recording_templates)
        row = next(row for row in study.report(self.directory)["rows"] if row["id"] == cell["id"])
        self.assertTrue(row["both_accepted"])
        capture = self.directory / row["initial"]["capture"]["directory"]
        blob = next((capture / "blobs").iterdir())
        blob.chmod(0o644)
        blob.write_bytes(b"tampered capture")
        blob.chmod(0o444)
        report = study.report(self.directory)
        row = next(row for row in report["rows"] if row["id"] == cell["id"])
        self.assertFalse(row["initial"]["accepted"])
        self.assertIn("snapshot blob digest mismatch", row["initial"]["evidence_error"])
        self.assertFalse(row["both_accepted"])
        self.assertEqual(report["planned_opportunities"], 36)
        study.run(self.directory, cell_id=cell["id"], execute=executor, grader=recording_grader, template_catalog=recording_templates)
        self.assertEqual(len(executor.calls), 2)

    def test_report_rejects_false_green_outcome_and_broken_capture_bindings(self):
        cell = self.prepare()["cells"][0]
        study.run(self.directory, cell_id=cell["id"], execute=RecordingApplication(), grader=recording_grader,
                  template_catalog=recording_templates)
        path = self.directory / "lineages" / cell["id"] / "initial/outcome.json"
        original = study.read_json(path)
        changes = [
            {"capture": None, "grade": {"state": "graded", "passed": True, "assertions": 0, "failures": ["bad"]}},
            {"grade": {**original["grade"], "assertions": 0}},
            {"grade": {**original["grade"], "failures": ["bad"]}},
            {"grade": {**original["grade"], "capture_sha256": "0" * 64}},
            {"grade": {**original["grade"], "stage": "maintenance"}},
            {"grade": {**original["grade"], "oracle_sha256": "0" * 64}},
            {"capture": {**original["capture"], "sha256": "0" * 64}},
            {"application_receipt": "inputs/runtime.json"},
        ]
        for changed in changes:
            with self.subTest(changed=changed):
                study.write_json(path, {**original, **changed})
                report = study.report(self.directory)
                row = next(row for row in report["rows"] if row["id"] == cell["id"])
                self.assertFalse(row["initial"]["accepted"])
                self.assertIsInstance(row["initial"]["evidence_error"], str)
                self.assertFalse(row["both_accepted"])
                self.assertEqual(report["planned_opportunities"], 36)
        study.write_json(path, original)
        self.assertTrue(next(row for row in study.report(self.directory)["rows"] if row["id"] == cell["id"])["both_accepted"])

    def test_report_binds_initial_claim_and_application_to_frozen_inputs(self):
        plan = self.prepare()
        cell = next(cell for cell in plan["cells"] if cell["arm"] == "current")
        study.run(self.directory, cell_id=cell["id"], execute=RecordingApplication(), grader=recording_grader,
                  template_catalog=recording_templates)
        directory = self.directory / "lineages" / cell["id"] / "initial"
        claim_path, receipt_path = directory / "claim.json", directory / "application/receipt.json"
        claim, application = study.read_json(claim_path), study.read_json(receipt_path)
        for claim_key, spec_key, changed in (("prompt_sha256", "prompt_sha256", "incorrect-request"),
                                             ("guidance_sha256", "skills", "incorrect-guidance"),
                                             ("parent_sha256", "project", "incorrect-parent")):
            with self.subTest(binding=claim_key):
                study.write_json(claim_path, {**claim, claim_key: changed})
                study.write_json(receipt_path, {**application, "spec": {**application["spec"], spec_key: changed}})
                report = study.report(self.directory)
                row = next(row for row in report["rows"] if row["id"] == cell["id"])
                self.assertFalse(row["initial"]["accepted"])
                self.assertIn(claim_key, row["initial"]["evidence_error"])
                self.assertFalse(row["both_accepted"])
                self.assertEqual(report["planned_opportunities"], 36)
                study.write_json(claim_path, claim)
                study.write_json(receipt_path, application)
        study.write_json(claim_path, claim)
        study.write_json(receipt_path, {**application, "spec": {**application["spec"], "runtime": {**plan["runtime"], "model": "different-model"}}})
        row = next(row for row in study.report(self.directory)["rows"] if row["id"] == cell["id"])
        self.assertFalse(row["initial"]["accepted"])
        self.assertIn("runtime", row["initial"]["evidence_error"])
        study.write_json(receipt_path, application)
        self.assertTrue(next(row for row in study.report(self.directory)["rows"] if row["id"] == cell["id"])["both_accepted"])

    def test_report_binds_maintenance_to_frozen_request_guidance_and_retained_initial(self):
        plan = self.prepare()
        cell = next(cell for cell in plan["cells"] if cell["arm"] == "current")
        study.run(self.directory, cell_id=cell["id"], execute=RecordingApplication(), grader=recording_grader,
                  template_catalog=recording_templates)
        directory = self.directory / "lineages" / cell["id"] / "maintenance"
        claim_path, receipt_path = directory / "claim.json", directory / "application/receipt.json"
        claim, application = study.read_json(claim_path), study.read_json(receipt_path)
        case = next(case for case in plan["cases"] if case["id"] == cell["case"])
        for claim_key, spec_key, changed in (("prompt_sha256", "prompt_sha256", "incorrect-request"),
                                             ("guidance_sha256", "skills", "incorrect-guidance"),
                                             ("parent_sha256", "project", case["project_snapshot"]["sha256"])):
            with self.subTest(binding=claim_key):
                study.write_json(claim_path, {**claim, claim_key: changed})
                study.write_json(receipt_path, {**application, "spec": {**application["spec"], spec_key: changed}})
                report = study.report(self.directory)
                row = next(row for row in report["rows"] if row["id"] == cell["id"])
                self.assertTrue(row["initial"]["accepted"])
                self.assertFalse(row["maintenance"]["accepted"])
                self.assertIn(claim_key, row["maintenance"]["evidence_error"])
                self.assertEqual(report["planned_opportunities"], 36)
                study.write_json(claim_path, claim)
                study.write_json(receipt_path, application)
        study.write_json(claim_path, claim)
        study.write_json(receipt_path, application)
        initial_claim_path = directory.parent / "initial/claim.json"
        initial_claim = study.read_json(initial_claim_path)
        study.write_json(initial_claim_path, {**initial_claim, "cell": "another-cell"})
        row = next(row for row in study.report(self.directory)["rows"] if row["id"] == cell["id"])
        self.assertFalse(row["maintenance"]["accepted"])
        self.assertIn("planned cell and stage", row["maintenance"]["evidence_error"])
        study.write_json(initial_claim_path, initial_claim)
        self.assertTrue(next(row for row in study.report(self.directory)["rows"] if row["id"] == cell["id"])["both_accepted"])

    def test_report_rejects_another_lineages_initial_capture_even_with_matching_content(self):
        plan = self.prepare()
        cell = plan["cells"][0]
        other = next(other for other in plan["cells"] if other["id"] != cell["id"] and other["case"] == cell["case"])
        executor = RecordingApplication()
        for selected in (cell, other):
            study.run(self.directory, cell_id=selected["id"], execute=executor, grader=recording_grader,
                      template_catalog=recording_templates)
        directory = self.directory / "lineages" / cell["id"] / "initial"
        path = directory / "outcome.json"
        outcome = study.read_json(path)
        other_outcome = study.read_json(self.directory / "lineages" / other["id"] / "initial/outcome.json")
        self.assertEqual(outcome["capture"]["sha256"], other_outcome["capture"]["sha256"])
        study.write_json(path, {**outcome, "capture": other_outcome["capture"]})
        receipt_path = directory / "application/receipt.json"
        application = study.read_json(receipt_path)
        study.write_json(receipt_path, {**application, "capture": {"directory": str(self.directory / other_outcome["capture"]["directory"]),
                                                                 "sha256": other_outcome["capture"]["sha256"]}})
        report = study.report(self.directory)
        row = next(row for row in report["rows"] if row["id"] == cell["id"])
        self.assertFalse(row["initial"]["accepted"])
        self.assertIn("capture is outside the planned stage", row["initial"]["evidence_error"])
        self.assertFalse(row["maintenance"]["accepted"])
        self.assertIn("capture is outside the planned stage", row["maintenance"]["evidence_error"])
        self.assertEqual(report["planned_opportunities"], 36)
        self.assertTrue(next(row for row in report["rows"] if row["id"] == other["id"])["both_accepted"])

    def test_report_retains_all_opportunities_with_malformed_aggregate_fields(self):
        cell = self.prepare()["cells"][0]
        study.run(self.directory, cell_id=cell["id"], execute=RecordingApplication(), grader=recording_grader,
                  template_catalog=recording_templates)
        path = self.directory / "lineages" / cell["id"] / "initial/outcome.json"
        original = study.read_json(path)
        for field, invalid, normalized in (("native_state", [], "unknown"),
                                            ("native_state", None, "unknown"),
                                            ("state", {}, "incomplete"),
                                            ("native_valid", 1, False),
                                            ("usage", [], None),
                                            ("elapsed_s", "unknown", None),
                                            ("elapsed_s", {}, None),
                                            ("elapsed_s", True, None),
                                            ("elapsed_s", -1, None),
                                            ("elapsed_s", float("nan"), None),
                                            ("elapsed_s", float("inf"), None),
                                            ("elapsed_s", 10 ** 400, None)):
            with self.subTest(field=field, invalid=invalid):
                study.write_json(path, {**original, field: invalid})
                report = study.report(self.directory)
                row = next(row for row in report["rows"] if row["id"] == cell["id"])
                self.assertFalse(row["initial"]["accepted"])
                self.assertIn(field, row["initial"]["evidence_error"])
                self.assertEqual(row["initial"][field], normalized)
                self.assertEqual(report["planned_opportunities"], 36)
                self.assertEqual(len(report["rows"]), 18)
                self.assertEqual(sum(sum(total["states"].values()) for total in report["totals"].values()), 36)
        study.write_json(path, original)
        self.assertTrue(next(row for row in study.report(self.directory)["rows"] if row["id"] == cell["id"])["both_accepted"])

    def test_report_reparses_retained_grades_and_checks_application_receipts(self):
        cell = self.prepare()["cells"][0]
        study.run(self.directory, cell_id=cell["id"], execute=RecordingApplication(), grader=recording_grader,
                  template_catalog=recording_templates)
        directory = self.directory / "lineages" / cell["id"] / "initial"
        outcome = study.read_json(directory / "outcome.json")
        for grade in ({**outcome["grade"], "assertions": 0},
                      {**outcome["grade"], "failures": ["bad"]},
                      {**outcome["grade"], "returncode": False}):
            with self.subTest(grade=grade):
                study.write_json(directory / "outcome.json", {**outcome, "grade": grade})
                study.write_json(directory / "acceptance/receipt.json", grade)
                report = study.report(self.directory)
                row = next(row for row in report["rows"] if row["id"] == cell["id"])
                self.assertFalse(row["initial"]["accepted"])
                self.assertIn("oracle", row["initial"]["evidence_error"])
                self.assertEqual(report["planned_opportunities"], 36)
        study.write_json(directory / "outcome.json", outcome)
        study.write_json(directory / "acceptance/receipt.json", outcome["grade"])
        receipt_path = directory / "application/receipt.json"
        application = study.read_json(receipt_path)
        study.write_json(receipt_path, {**application, "native_valid": False})
        row = next(row for row in study.report(self.directory)["rows"] if row["id"] == cell["id"])
        self.assertFalse(row["initial"]["accepted"])
        self.assertIn("native outcome disagrees", row["initial"]["evidence_error"])
        study.write_json(receipt_path, application)
        self.assertTrue(next(row for row in study.report(self.directory)["rows"] if row["id"] == cell["id"])["both_accepted"])


if __name__ == "__main__":
    unittest.main()
