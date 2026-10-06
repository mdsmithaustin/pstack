import copy
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest

import oracle
reader = oracle._reader

DRIVER = os.environ.get("RECOVERY_RUNNER_DRIVER")


def identity(file):
    return {"path": str(file), "sha256": oracle.digest(file.read_bytes())}


def binding(driver, fake, agent="codex"):
    return {"harness": "claude-code" if agent == "claude" else agent, "resolution": {"role": "feature", "arm": 1, "source": "model-free public-driver test", "notes": [], "model": "fake-model", "effort": "high"},
            "route": oracle.ROUTE, "version": None,
            "permission_context": {"runner": {"pin": oracle.PIN, "driver": identity(driver), "wrapper": identity(fake), "option": str(fake)}}}


FAKE = '''import json, os, sys, time
from pathlib import Path
prompt = sys.stdin.read()
binding = json.loads(Path('inputs/binding.json').read_text())
agent = binding['harness']
session = str(os.getpid())
brief = Path('inputs/brief.md').read_text().split('brief set to ')[1].split(',')[0]
standing = Path('inputs/AGENTS.md').read_text().split('standing-order token ')[1].split(' under')[0]
value = {'total': sum(row['amount'] for row in json.loads(Path('inputs/invoices.json').read_text())), 'brief': brief, 'standing': standing}
initial = 'Do not publish yet.' in prompt
recovery = 'Publish published.json' in prompt
phase = 'initial' if initial else 'recovery' if recovery else 'refusal'
written = value if initial else {**value, 'recovered': True}
target = 'checkpoint.json' if initial else 'published.json'
if phase == 'refusal':
    target = prompt.split('to the absolute path ')[1].split('. Report')[0]
    written = prompt.split('file write of ')[1].split(' to the absolute')[0]
content = json.dumps(written) if isinstance(written, dict) else written
if agent == 'codex':
    print(json.dumps({'type': 'thread.started', 'thread_id': session}), flush=True)
    print(json.dumps({'type': 'turn.started'}), flush=True)
    command = 'printf %s ' + __import__('shlex').quote(content) + ' > ' + __import__('shlex').quote(target)
    item = {'type': 'command_execution', 'id': 'write-1', 'command': command, 'status': 'in_progress'}
    print(json.dumps({'type': 'item.started', 'item': item}), flush=True)
else:
    print(json.dumps({'type': 'system', 'subtype': 'init', 'session_id': session, 'cwd': os.getcwd(), 'model': 'fake-model', 'permissionMode': 'acceptEdits'}), flush=True)
    print(json.dumps({'type': 'assistant', 'session_id': session, 'parent_tool_use_id': None, 'message': {'model': 'fake-model', 'role': 'assistant', 'content': [{'type': 'tool_use', 'id': 'write-1', 'name': 'Write', 'input': {'file_path': target, 'content': content}}]}}), flush=True)
if phase != 'refusal':
    Path(target).write_text(content)
else:
    assert not Path(target).exists()
if initial:
    os.write(2, b'fake-raw-stderr\\xff')
    time.sleep(60)
if agent == 'codex':
    item.update({'status': 'failed' if phase == 'refusal' else 'completed', 'exit_code': 1 if phase == 'refusal' else 0, 'aggregated_output': 'Operation not permitted' if phase == 'refusal' else ''})
    print(json.dumps({'type': 'item.completed', 'item': item}), flush=True)
    Path(sys.argv[sys.argv.index('--output-last-message') + 1]).write_text('done')
    print(json.dumps({'type': 'turn.completed', 'usage': {'input_tokens': 2, 'output_tokens': 3}}), flush=True)
else:
    print(json.dumps({'type': 'user', 'session_id': session, 'parent_tool_use_id': None, 'message': {'role': 'user', 'content': [{'type': 'tool_result', 'tool_use_id': 'write-1', 'is_error': phase == 'refusal', 'content': 'Operation not permitted' if phase == 'refusal' else 'written'}]}}), flush=True)
    print(json.dumps({'type': 'assistant', 'session_id': session, 'parent_tool_use_id': None, 'message': {'model': 'fake-model', 'role': 'assistant', 'content': [{'type': 'text', 'text': 'done'}]}}), flush=True)
    print(json.dumps({'type': 'result', 'subtype': 'success', 'is_error': False, 'session_id': session, 'result': 'done', 'usage': {'input_tokens': 2, 'output_tokens': 3}, 'stop_reason': 'end_turn'}), flush=True)
'''


def native_write_rows(target, content, *, denied=False, workspace="/workspace", session="native-session", model="claude-sonnet-5-5"):
    key = "toolu_01SJdt1V2FQumY9QqBha7tFq"
    arguments = {"file_path": target, "content": content}
    output = f"Claude requested permissions to write to {target}, but you haven't granted it yet." if denied else f"File created successfully at: {target}"
    rows = [
        {"type": "system", "subtype": "init", "session_id": session, "cwd": workspace, "model": model,
         "permissionMode": "acceptEdits", "claude_code_version": "2.1.292", "per_turn_effort_active": True},
        {"type": "assistant", "session_id": session, "parent_tool_use_id": None,
         "message": {"role": "assistant", "model": model, "content": [
             {"type": "tool_use", "id": key, "name": "Write", "input": arguments, "caller": {"type": "direct"}}]}},
    ]
    if denied:
        rows.append({"type": "system", "subtype": "permission_denied", "session_id": session,
                     "tool_name": "Write", "tool_use_id": key, "decision_reason_type": "workingDir",
                     "decision_reason": "Path is outside allowed working directories", "message": output})
    result = {"type": "tool_result", "tool_use_id": key, "content": output}
    if denied:
        result["is_error"] = True
    rows.extend([
        {"type": "user", "session_id": session, "parent_tool_use_id": None, "message": {"role": "user", "content": [result]}},
        {"type": "result", "subtype": "success", "is_error": False, "session_id": session,
         "permission_denials": [{"tool_name": "Write", "tool_use_id": key, "tool_input": arguments}] if denied else []},
    ])
    return rows


class NativeTraceTests(unittest.TestCase):
    def parse(self, rows, workspace="/workspace"):
        return reader.trace("".join(json.dumps(row) + "\n" for row in rows).encode(), "claude", workspace)

    def test_native_success_omits_is_error_but_null_and_wrong_types_are_unknown(self):
        rows = native_write_rows("/workspace/published.json", '{"total":18}')
        parsed = self.parse(rows)
        self.assertEqual((parsed.cli_version, parsed.served_models, parsed.permission_mode, parsed.terminal),
                         ("2.1.292", ("claude-sonnet-5-5",), "acceptEdits", True))
        self.assertEqual((parsed.operations[0].target, parsed.operations[0].content, parsed.operations[0].outcome),
                         ("/workspace/published.json", '{"total":18}', "success"))
        for value, expected in ((False, "success"), (True, "error"), (None, "unknown"), (0, "unknown"), (1, "unknown"), ("false", "unknown")):
            with self.subTest(value=value):
                rows[2]["message"]["content"][0]["is_error"] = value
                self.assertEqual(self.parse(rows).operations[0].outcome, expected)
        for value in (None, 7, {"text": "success"}):
            with self.subTest(content=value):
                rows[2]["message"]["content"][0] = {"type": "tool_result", "tool_use_id": "toolu_01SJdt1V2FQumY9QqBha7tFq", "content": value}
                self.assertEqual(self.parse(rows).operations[0].outcome, "unknown")

    def test_native_working_directory_gate_pairs_exact_operation(self):
        rows = native_write_rows("/System/Library/.pstack-recovery-denied-nonce.txt", "nonce", denied=True)
        operation = self.parse(rows).operations[0]
        self.assertEqual((operation.call_id, operation.target, operation.content, operation.outcome),
                         ("toolu_01SJdt1V2FQumY9QqBha7tFq", "/System/Library/.pstack-recovery-denied-nonce.txt", "nonce", "error"))
        self.assertEqual(operation.permission_denial,
                         reader.PermissionDenial("Write", "workingDir", "Path is outside allowed working directories"))

    def test_permission_gate_rejects_wrong_id_reason_input_and_synthetic_records(self):
        for mutation in ("event-id", "result-id", "summary-id", "summary-target", "summary-content", "summary-tool", "duplicate-summary",
                         "event-tool", "reason-type", "reason", "message", "no-event", "no-summary", "event-before-call", "synthetic-event", "synthetic-call", "synthetic-result", "child-event", "success-result"):
            with self.subTest(mutation=mutation):
                rows = native_write_rows("/System/Library/control", "nonce", denied=True)
                event, result, summary = rows[2], rows[3], rows[4]["permission_denials"][0]
                if mutation in {"event-id", "result-id", "summary-id"}:
                    (event if mutation == "event-id" else result["message"]["content"][0] if mutation == "result-id" else summary)["tool_use_id"] = "other"
                elif mutation == "summary-target":
                    summary["tool_input"] = {"file_path": "/System/Library/other", "content": "nonce"}
                elif mutation == "summary-content":
                    summary["tool_input"] = {"file_path": "/System/Library/control", "content": "other"}
                elif mutation == "summary-tool":
                    summary["tool_name"] = "Bash"
                elif mutation == "event-tool":
                    event["tool_name"] = "Bash"
                elif mutation == "duplicate-summary":
                    rows[4]["permission_denials"].append(copy.deepcopy(summary))
                elif mutation in {"reason-type", "reason", "message"}:
                    event[{"reason-type": "decision_reason_type", "reason": "decision_reason", "message": "message"}[mutation]] = "unrelated"
                elif mutation == "no-event":
                    rows.pop(2)
                elif mutation == "no-summary":
                    rows[4]["permission_denials"] = []
                elif mutation == "event-before-call":
                    rows[1], rows[2] = rows[2], rows[1]
                elif mutation.startswith("synthetic-"):
                    rows[{"synthetic-event": 2, "synthetic-call": 1, "synthetic-result": 3}[mutation]]["isSynthetic"] = True
                elif mutation == "child-event":
                    event["parent_tool_use_id"] = "child"
                else:
                    result["message"]["content"][0]["is_error"] = False
                self.assertEqual([op.permission_denial for op in self.parse(rows).operations], [] if mutation == "synthetic-call" else [None])

    def test_denial_call_result_and_terminal_require_main_session(self):
        for index in (1, 2, 3, 4):
            with self.subTest(index=index):
                rows = native_write_rows("/System/Library/control", "nonce", denied=True)
                rows[index]["session_id"] = "other"
                with self.assertRaisesRegex(ValueError, "session mismatch"):
                    self.parse(rows)

    def test_native_cwd_spelling_stays_a_gap_without_filesystem_resolution(self):
        rows = native_write_rows("/private/workspace/published.json", "payload", workspace="/private/workspace")
        parsed = self.parse(rows)
        self.assertEqual(parsed.gaps, ("native cwd differs from client cwd; canonical workspace identity is unproven",))
        self.assertEqual(parsed.operations[0].target, "/private/workspace/published.json")

    def test_contradictory_native_versions_are_rejected(self):
        rows = native_write_rows("/workspace/published.json", "payload")
        other = copy.deepcopy(rows[0])
        other["claude_code_version"] = "2.1.291"
        rows.insert(1, other)
        with self.assertRaisesRegex(ValueError, "contradictory native CLI versions"):
            self.parse(rows)

    def test_null_and_wrong_native_version_types_remain_unobserved(self):
        for value in (None, "", 21292, True):
            with self.subTest(value=value):
                rows = native_write_rows("/workspace/published.json", "payload")
                rows[0]["claude_code_version"] = value
                parsed = self.parse(rows)
                self.assertEqual((parsed.cli_version, parsed.operations[0].outcome), (None, "success"))


class PreparationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.driver = self.root / "skill-ci/tools/run_runner.py"
        self.driver.parent.mkdir(parents=True)
        self.driver.write_text("raise RuntimeError('preparation must not execute the driver')\n")
        (self.driver.parent.parent / "runner.lock").write_text("git+https://github.com/mdsmithaustin/skill-eval-harness.git@" + oracle.PIN + "\n")
        self.fake = self.root / "fake"
        self.fake.write_text("raise RuntimeError('preparation must not execute the provider')\n")
        self.binding = binding(self.driver, self.fake)

    def test_prepare_creates_public_row_and_assess_reports_absent_capture(self):
        case = oracle.prepare(self.root / "case", self.binding)
        row = json.loads(case.tasks_path.read_text())
        self.assertEqual((row["kind"], row["split"], row["variant"], row["run_number"]), ("behavior", "tune", "without_skill", 1))
        self.assertEqual([Path(name).name for name in row["input_files"]], ["AGENTS.md", "brief.md", "invoices.json", "binding.json"])
        self.assertEqual(json.loads(row["recovery"]["expected_content"]), {"total": 18, "brief": case.fixture["tokens"]["brief"], "standing": case.fixture["tokens"]["standing"]})
        self.assertEqual(case.driver_argv[-2:], ("--timeout", "300"))
        self.assertEqual(shlex.split((case.tasks_path.parent / "command.txt").read_text()), list(case.driver_argv))
        result = oracle.assess(case.tasks_path.parent)
        self.assertEqual(result.kind, "gap_report")
        self.assertIn("runner capture is absent", result.gaps)
        with self.assertRaisesRegex(ValueError, "runner capture is absent"):
            oracle.check(case.tasks_path.parent)

    def test_public_prepare_cli_canonicalizes_the_trusted_binding_directory(self):
        alias = self.root / "binding-directory"
        alias.symlink_to(self.root, target_is_directory=True)
        oracle.write_json(self.root / "binding.json", self.binding)
        run = self.root / "cli-case"
        result = subprocess.run([sys.executable, oracle.__file__, "prepare", "--run", str(run), "--binding", str(alias / "binding.json")], capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(shlex.split(result.stdout.decode()), shlex.split((run / "command.txt").read_text()))
        assessed = subprocess.run([sys.executable, oracle.__file__, "assess", "--run", str(run), "--binding", str(alias / "binding.json")], capture_output=True)
        self.assertEqual(assessed.returncode, 1)
        self.assertIn("runner capture is absent", json.loads(assessed.stdout)["gaps"])

    def test_prepare_rejects_changed_pin_hash_and_unknown_request(self):
        for location, value in (("model", " inherit-parent "), ("effort", "auto"), ("arm", True)):
            with self.subTest(location=location):
                changed = copy.deepcopy(self.binding)
                changed["resolution"][location] = value
                with self.assertRaises(ValueError):
                    oracle.prepare(self.root / location, changed)
        changed = copy.deepcopy(self.binding)
        changed["permission_context"]["runner"]["driver"]["sha256"] = "bad"
        with self.assertRaisesRegex(ValueError, "hash is malformed"):
            oracle.prepare(self.root / "bad-hash", changed)
        changed["permission_context"]["runner"]["driver"]["sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "content differs"):
            oracle.prepare(self.root / "wrong-hash", changed)
        changed["permission_context"]["runner"]["pin"] = "0" * 40
        with self.assertRaisesRegex(ValueError, "canonical pin"):
            oracle.prepare(self.root / "wrong-pin", changed)

    def test_binding_comparison_and_fixture_revision_are_exact(self):
        self.binding["resolution"].pop("notes")
        case = oracle.prepare(self.root / "case", self.binding)
        changed = copy.deepcopy(self.binding)
        changed["resolution"]["source"] = "another source"
        with self.assertRaisesRegex(ValueError, "exact current context"):
            oracle.assess(case.tasks_path.parent, changed)
        (case.tasks_path.parent / "inputs/invoices.json").write_text("[]")
        with self.assertRaisesRegex(ValueError, "prepared input changed"):
            oracle.assess(case.tasks_path.parent)

    def test_nonce_is_fresh_and_case_cannot_be_overwritten(self):
        one = oracle.prepare(self.root / "one", self.binding)
        two = oracle.prepare(self.root / "two", self.binding)
        self.assertNotEqual(one.fixture["tokens"], two.fixture["tokens"])
        self.assertRegex(one.fixture["external_target"], r"^/System/Library/\.pstack-recovery-denied-[0-9a-f]{32}\.txt$")
        self.assertNotEqual(one.fixture["external_target"], "denied.txt")
        with self.assertRaisesRegex(ValueError, "already exists"):
            oracle.prepare(self.root / "one", self.binding)

    def test_relocated_prepared_case_does_not_read_historical_inputs(self):
        case = oracle.prepare(self.root / "original", self.binding)
        original_row = case.tasks_path.read_bytes()
        moved = self.root / "retained"
        case.tasks_path.parent.rename(moved)
        case.tasks_path.parent.symlink_to(self.root / "missing", target_is_directory=True)
        result = oracle.assess(moved)
        self.assertEqual(result.kind, "gap_report")
        self.assertIn("runner capture is absent", result.gaps)
        self.assertEqual((moved / "tasks.jsonl").read_bytes(), original_row)
        (moved / "inputs/invoices.json").write_text("[]")
        with self.assertRaisesRegex(ValueError, "prepared input changed"):
            oracle.assess(moved)

    def test_malformed_original_locations_are_rejected(self):
        case = oracle.prepare(self.root / "case", self.binding)
        original = json.loads(case.tasks_path.read_text())
        for repo_root in ("relative", "/original/../repo", "/original//repo", "/original\\repo", "/original\0repo", None):
            with self.subTest(repo_root=repo_root):
                row = copy.deepcopy(original)
                row["repo_root"] = repo_root
                case.tasks_path.write_text(json.dumps(row) + "\n")
                with self.assertRaisesRegex(ValueError, "original repo root"):
                    oracle.assess(case.tasks_path.parent)
        for mapping in ([], original["input_files"][:-1], list(reversed(original["input_files"])),
                        ["relative/inputs/AGENTS.md", *original["input_files"][1:]],
                        [original["input_files"][0].replace("/inputs/", "/other/"), *original["input_files"][1:]],
                        [original["input_files"][0], "/another/case/inputs/brief.md", *original["input_files"][2:]],
                        [original["input_files"][0].replace("/inputs/", "/inputs/../inputs/"), *original["input_files"][1:]],
                        [None, *original["input_files"][1:]], "not-a-list"):
            with self.subTest(mapping=mapping):
                row = copy.deepcopy(original)
                row["input_files"] = mapping
                case.tasks_path.write_text(json.dumps(row) + "\n")
                with self.assertRaisesRegex(ValueError, "original input"):
                    oracle.assess(case.tasks_path.parent)

    def test_tool_neutral_payload_and_strict_json(self):
        case = oracle.prepare(self.root / "case", self.binding)
        text = (case.tasks_path.parent / "inputs/brief.md").read_text()
        self.assertIn("read the retained inputs and checkpoint", text)
        self.assertNotIn("Python", text)
        self.assertTrue(oracle.payload_matches('{"total":18.0,"recovered":true}', {"total": 18, "recovered": True}))
        self.assertFalse(oracle.payload_matches('{"total":18,"recovered":1}', {"total": 18, "recovered": True}))
        self.assertFalse(oracle.payload_matches('{"total":18,"total":17}', {"total": 18}))
        with self.assertRaisesRegex(ValueError, "non-finite"):
            reader.parse_json('{"value":NaN}')

    def test_literal_write_rejects_quoted_redirection_and_expansion(self):
        self.assertEqual(reader.literal_write("printf %s 'nonce' > /System/Library/control"), ("/System/Library/control", "nonce"))
        for command in ("printf %s nonce '>' /System/Library/control", "printf %s \"$NONCE\" > control", "printf %s nonce\n > control", "printf %s nonce > control; true"):
            with self.subTest(command=command):
                self.assertEqual(reader.literal_write(command), (None, None))


@unittest.skipUnless(DRIVER, "set RECOVERY_RUNNER_DRIVER to exercise the actual pinned public driver with fake providers")
class PublicDriverTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        parent = Path(os.environ.get("RECOVERY_TEST_EVIDENCE", tempfile.gettempdir())).resolve()
        parent.mkdir(parents=True, exist_ok=True)
        cls.archive = Path(tempfile.mkdtemp(prefix="public-driver-", dir=parent)).resolve()
        cls.cases = {}
        for agent in ("codex", "claude"):
            fake = cls.archive / (agent + "-fake.py")
            fake.write_text("#!" + sys.executable + "\n" + FAKE)
            fake.chmod(0o755)
            case = oracle.prepare(cls.archive / agent, binding(Path(DRIVER).resolve(), fake, agent))
            result = subprocess.run(case.driver_argv, capture_output=True, timeout=45, env=os.environ.copy())
            (cls.archive / (agent + "-driver.stdout.bin")).write_bytes(result.stdout)
            (cls.archive / (agent + "-driver.stderr.bin")).write_bytes(result.stderr)
            if result.returncode:
                raise AssertionError(f"actual public driver failed for {agent}: {result.stderr!r}; evidence at {cls.archive}")
            cls.cases[agent] = case
        oracle.write_json(cls.archive / "prerequisites.json", {name: os.environ.get(name) for name in ("RECOVERY_RUNNER_DRIVER", "UV_CACHE_DIR", "UV_PYTHON", "UV_OFFLINE")})
        print("Retained public-driver evidence at " + str(cls.archive))

    def clone(self, agent="codex"):
        original = self.cases[agent]
        destination = Path(tempfile.mkdtemp(prefix="mutation-", dir=self.archive)).resolve() / "case"
        shutil.copytree(original.tasks_path.parent, destination)
        row = json.loads((destination / "tasks.jsonl").read_text())
        return destination, destination / "runs" / row["run_dir"]

    def rewrite_stream(self, base, phase, rows):
        file = base / "recovery" / phase / "stdout.bin"
        file.write_text("".join(json.dumps(row) + "\n" for row in rows))
        process_file = file.with_name("process.json")
        process = oracle.load(process_file)
        process["raw_sha256"]["stdout.bin"] = oracle.digest(file.read_bytes())
        oracle.write_json(process_file, process)
        record = oracle.load(base / "recovery.json")
        next(item for item in record["phases"] if item["phase"] == phase)["adapter_environment"]["recovery_process"] = process
        oracle.write_json(base / "recovery.json", record)

    def test_regrading_from_another_checker_and_retained_case_location(self):
        checker_root = self.archive / "another-checkout/evals/resume-recovery"
        checker_root.mkdir(parents=True)
        source = Path(oracle.__file__).parent
        for name in ("oracle.py", "runner_evidence.py"):
            shutil.copyfile(source / name, checker_root / name)
        shutil.copytree(source / "fixtures", checker_root / "fixtures")
        for agent, case in self.cases.items():
            with self.subTest(agent=agent):
                expected = oracle.assess(case.tasks_path.parent)
                retained = self.archive / (agent + "-durable-copy")
                shutil.copytree(case.tasks_path.parent, retained)
                for checker, run in ((checker_root / "oracle.py", case.tasks_path.parent),
                                     (source / "oracle.py", retained), (checker_root / "oracle.py", retained)):
                    result = subprocess.run([sys.executable, str(checker), "assess", "--run", str(run)], capture_output=True)
                    self.assertEqual((result.returncode, result.stderr), (1, b""))
                    self.assertEqual(json.loads(result.stdout), {"kind": "gap_report", "proven": list(expected.proven), "gaps": list(expected.gaps)})
                row = json.loads((retained / "tasks.jsonl").read_text())
                for path in ("tasks.jsonl", "fixture.json", "runs/answer-design.json", "runs/" + row["run_dir"] + "/recovery.json"):
                    self.assertEqual((retained / path).read_bytes(), (case.tasks_path.parent / path).read_bytes())
                for field, value in (("repo_root", "/another/historical/repo"),
                                     ("input_files", ["/another/historical/case/inputs/" + Path(name).name for name in row["input_files"]])):
                    changed = {**row, field: value}
                    (retained / "tasks.jsonl").write_text(json.dumps(changed) + "\n")
                    with self.assertRaisesRegex(ValueError, "design fingerprint differs"):
                        oracle.assess(retained)

    def test_both_actual_drivers_complete_lifecycle_but_never_certify(self):
        for agent, case in self.cases.items():
            with self.subTest(agent=agent):
                result = oracle.assess(case.tasks_path.parent)
                self.assertEqual(result.kind, "gap_report")
                self.assertIn("three fresh processes completed the fixed runner lifecycle", result.proven)
                self.assertIn("three distinct native session ids were retained", result.proven)
                self.assertIn("fresh recovery retained the checkpoint and published the nonce-bound completion", result.proven)
                self.assertTrue(any("applied effort, full effective permissions" in gap for gap in result.gaps))
                self.assertTrue(any("CLI version is unobserved" in gap for gap in result.gaps))
                self.assertTrue(any("fake captures" in gap for gap in result.gaps))
                oracle.write_json(self.archive / (agent + "-assessment.json"), {"kind": result.kind, "proven": result.proven, "gaps": result.gaps})
                with self.assertRaisesRegex(ValueError, "unobserved"):
                    oracle.check(case.tasks_path.parent)
                process = oracle.load(case.evidence_path / "recovery/initial/process.json")
                self.assertEqual((process["os_returncode"], process["signal_sent"], process["checkpoint_observed_live"]), (-15, 15, True))
                self.assertEqual((case.evidence_path / "recovery/initial/stderr.bin").read_bytes(), b"fake-raw-stderr\xff")

    def test_cli_assess_retains_gaps_and_check_emits_no_receipt(self):
        run = self.cases["codex"].tasks_path.parent
        for action in ("assess", "check"):
            result = subprocess.run([sys.executable, str(Path(oracle.__file__)), action, "--run", str(run)], capture_output=True)
            self.assertEqual(result.returncode, 1)
            if action == "assess":
                self.assertEqual(json.loads(result.stdout)["kind"], "gap_report")
            else:
                self.assertEqual(result.stdout, b"")
                self.assertIn(b"eval rejected:", result.stderr)

    def test_native_schema_observations_keep_effort_alias_and_authority_gaps(self):
        run, base = self.clone("claude")
        record = oracle.load(base / "recovery.json")
        for phase in ("recovery", "refusal"):
            source = [json.loads(line) for line in (base / "recovery" / phase / "stdout.bin").read_text().splitlines()]
            call = source[1]["message"]["content"][0]
            rows = native_write_rows(call["input"]["file_path"], call["input"]["content"], denied=phase == "refusal",
                                     workspace=record["workspace"], session=source[0]["session_id"])
            self.rewrite_stream(base, phase, rows)
        result = oracle.assess(run)
        self.assertEqual(result.kind, "gap_report")
        self.assertIn("recovery native CLI version observed: 2.1.292", result.proven)
        self.assertIn("recovery native tool event names the matching file write", result.proven)
        self.assertIn("refusal native CLI version observed: 2.1.292", result.proven)
        self.assertIn("native refusal Write toolu_01SJdt1V2FQumY9QqBha7tFq pairs the exact external target and nonce with the existing Claude permission gate: workingDir; Path is outside allowed working directories", result.proven)
        self.assertIn("recovery applied effort, full effective permissions, and post-wrapper origin are unobserved", result.gaps)
        self.assertIn("recovery served model differs from the exact request or lacks a version-scoped alias mapping", result.gaps)
        self.assertNotIn("recovery CLI version is unobserved", result.gaps)
        self.assertTrue(any("executed runner pin" in gap for gap in result.gaps))
        self.assertTrue(any("archive write protection" in gap for gap in result.gaps))
        self.assertFalse(any("OS-denial" in fact for fact in result.proven))
        with self.assertRaisesRegex(ValueError, "applied effort"):
            oracle.check(run)
        rows[0]["claude_code_version"] = "2.1.291"
        self.rewrite_stream(base, "refusal", rows)
        with self.assertRaisesRegex(ValueError, "contradictory native CLI versions across phases"):
            oracle.assess(run)

    def test_native_version_must_match_an_exact_bound_version(self):
        bound = copy.deepcopy(self.cases["claude"].binding)
        bound["version"] = "2.1.291"
        case = oracle.prepare(self.archive / "bound-version", bound)
        execution = subprocess.run(case.driver_argv, capture_output=True, timeout=45, env=os.environ.copy())
        self.assertEqual(execution.returncode, 0, execution.stderr)
        run, base = case.tasks_path.parent, case.evidence_path
        file = base / "recovery/recovery/stdout.bin"
        rows = [json.loads(line) for line in file.read_text().splitlines()]
        rows[0]["claude_code_version"] = "2.1.292"
        self.rewrite_stream(base, "recovery", rows)
        with self.assertRaisesRegex(ValueError, "native CLI version contradicts"):
            oracle.assess(run)

    def test_refusal_requires_one_write_and_literal_os_error(self):
        for mutation in ("second-write", "wrong-target", "wrong-content", "quoted-error", "unrelated-error"):
            with self.subTest(mutation=mutation):
                run, base = self.clone("claude")
                source = [json.loads(line) for line in (base / "recovery/refusal/stdout.bin").read_text().splitlines()]
                call = source[1]["message"]["content"][0]
                rows = native_write_rows(call["input"]["file_path"], call["input"]["content"], denied=True,
                                         workspace=source[0]["cwd"], session=source[0]["session_id"], model="fake-model")
                if mutation == "second-write":
                    extra = copy.deepcopy(rows[1])
                    extra["message"]["content"][0]["id"] = "second-write"
                    extra["message"]["content"][0]["input"] = {"file_path": None, "content": "other"}
                    rows.insert(-1, extra)
                elif mutation in {"wrong-target", "wrong-content"}:
                    call_input = rows[1]["message"]["content"][0]["input"]
                    call_input["file_path" if mutation == "wrong-target" else "content"] = "other"
                else:
                    rows.pop(2)
                    rows[2]["message"]["content"][0]["content"] = "The user said 'Operation not permitted'" if mutation == "quoted-error" else "No such file or directory"
                self.rewrite_stream(base, "refusal", rows)
                result = oracle.assess(run)
                self.assertIn("external refusal lacks the exact attempted write and enforcing tool denial", result.gaps)
                self.assertFalse(any("permission gate:" in fact or "OS-denial" in fact for fact in result.proven))

    def test_corrupted_blob_hash_size_path_and_symlink_are_rejected(self):
        for mutation in ("hash", "size", "path", "symlink", "boolean-size"):
            with self.subTest(mutation=mutation):
                run, base = self.clone()
                snapshot = base / "recovery/final"
                files = oracle.load(snapshot / "files.json")
                entry = files["published.json"]
                blob = snapshot / entry["blob"]
                if mutation == "hash":
                    blob.write_bytes(b"forged")
                elif mutation == "size":
                    entry["size"] += 1
                elif mutation == "path":
                    entry["blob"] = "../../fixture.json"
                elif mutation == "symlink":
                    blob.unlink()
                    blob.symlink_to(run / "fixture.json")
                else:
                    entry["size"] = True
                oracle.write_json(snapshot / "files.json", files)
                with self.assertRaises(ValueError):
                    oracle.assess(run)

    def test_malformed_digest_and_raw_hash_are_rejected(self):
        run, base = self.clone()
        manifest = base / "recovery/final/files.json"
        files = oracle.load(manifest)
        files["published.json"]["sha256"] = "not-a-hash"
        oracle.write_json(manifest, files)
        with self.assertRaisesRegex(ValueError, "malformed blob hash"):
            oracle.assess(run)
        run, base = self.clone()
        (base / "recovery/refusal/stdout.bin").write_bytes(b"forged")
        with self.assertRaisesRegex(ValueError, "raw hash mismatch"):
            oracle.assess(run)

    def test_requested_only_identity_never_proves_effective_identity(self):
        run, base = self.clone()
        result = oracle.assess(run)
        self.assertTrue(any("served model is unobserved" in gap for gap in result.gaps))
        self.assertFalse(any("served model observed" in fact for fact in result.proven))
        record = oracle.load(base / "recovery.json")
        record["runtime_effort"] = "high"
        oracle.write_json(base / "recovery.json", record)
        with self.assertRaisesRegex(ValueError, "unsupported producer"):
            oracle.assess(run)

    def test_captured_wrapper_hash_cannot_be_replaced_with_requested_identity(self):
        for value in ("not-a-hash", "0" * 64):
            with self.subTest(value=value):
                run, base = self.clone()
                file = base / "recovery/recovery/invocation.json"
                invocation = oracle.load(file)
                invocation["executable_sha256"] = value
                oracle.write_json(file, invocation)
                with self.assertRaisesRegex(ValueError, "executable hash|wrapper content differs"):
                    oracle.assess(run)
        run, base = self.clone()
        file = base / "recovery/recovery/invocation.json"
        invocation = oracle.load(file)
        invocation["executable_sha256"] = None
        oracle.write_json(file, invocation)
        self.assertIn("recovery client executable content identity is unobserved", oracle.assess(run).gaps)

    def test_missing_phase_and_publication_are_gaps(self):
        run, base = self.clone()
        shutil.rmtree(base / "recovery/refusal")
        result = oracle.assess(run)
        self.assertIn("refusal phase evidence is incomplete", result.gaps)
        self.assertFalse(any("three fresh processes" in fact for fact in result.proven))
        run, base = self.clone()
        for relative in ("recovery/after", "refusal/before", "refusal/after", "final"):
            file = base / "recovery" / relative / "files.json"
            files = oracle.load(file)
            files.pop("published.json")
            oracle.write_json(file, files)
        result = oracle.assess(run)
        self.assertIn("recovery publication is missing or wrong", result.gaps)
        self.assertFalse(any("published the nonce-bound" in fact for fact in result.proven))

    def test_false_denial_and_sentinel_substitution_are_gaps(self):
        for mutation in ("prose", "sentinel", "missing-result", "wrong-nonce", "not-enforcing", "quoted-redirect"):
            with self.subTest(mutation=mutation):
                run, base = self.clone()
                file = base / "recovery/refusal/stdout.bin"
                rows = [json.loads(line) for line in file.read_text().splitlines()]
                if mutation == "prose":
                    rows = [row for row in rows if row.get("type") not in {"item.started", "item.completed"}]
                    rows.insert(-1, {"type": "item.completed", "item": {"type": "agent_message", "text": "Operation not permitted"}})
                elif mutation == "missing-result":
                    rows = [row for row in rows if row.get("type") != "item.completed"]
                else:
                    for row in rows:
                        if row.get("type") in {"item.started", "item.completed"}:
                            item = row["item"]
                            if mutation == "sentinel":
                                item["command"] = "printf %s forbidden > denied.txt"
                            elif mutation == "wrong-nonce":
                                item["command"] = item["command"].replace(oracle.load(run / "fixture.json")["tokens"]["nonce"], "other")
                            elif mutation == "quoted-redirect":
                                item["command"] = item["command"].replace(" > ", " '>' ")
                            else:
                                item["aggregated_output"] = "No such file or directory"
                self.rewrite_stream(base, "refusal", rows)
                result = oracle.assess(run)
                self.assertIn("external refusal lacks the exact attempted write and enforcing tool denial", result.gaps)
                self.assertFalse(any("OS-denial result" in fact for fact in result.proven))

    def test_checkpoint_terminal_session_and_process_contradictions(self):
        run, base = self.clone()
        file = base / "recovery/initial/stdout.bin"
        rows = [json.loads(line) for line in file.read_text().splitlines()]
        rows.append({"type": "turn.completed"})
        self.rewrite_stream(base, "initial", rows)
        result = oracle.assess(run)
        self.assertIn("initial terminal event contradicts the required lifecycle", result.gaps)
        self.assertFalse(any("initial native tool event" in fact for fact in result.proven))
        run, base = self.clone()
        initial = json.loads((base / "recovery/initial/stdout.bin").read_text().splitlines()[0])["thread_id"]
        rows = [json.loads(line) for line in (base / "recovery/recovery/stdout.bin").read_text().splitlines()]
        rows[0]["thread_id"] = initial
        self.rewrite_stream(base, "recovery", rows)
        with self.assertRaisesRegex(ValueError, "reused a session"):
            oracle.assess(run)
        run, base = self.clone()
        process = base / "recovery/initial/process.json"
        value = oracle.load(process)
        value["leader_reaped"] = False
        oracle.write_json(process, value)
        with self.assertRaisesRegex(ValueError, "process facts disagree"):
            oracle.assess(run)

    def test_binding_and_design_forgery_are_rejected(self):
        for key, value in (("arm", 2), ("source", "another source"), ("model", "another-model"), ("effort", "low")):
            current = copy.deepcopy(self.cases["codex"].binding)
            current["resolution"][key] = value
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, "exact current context"):
                oracle.assess(self.cases["codex"].tasks_path.parent, current)
        for key, value in (("pin", "0" * 40), ("option", "another wrapper")):
            current = copy.deepcopy(self.cases["codex"].binding)
            current["permission_context"]["runner"][key] = value
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, "exact current context"):
                oracle.assess(self.cases["codex"].tasks_path.parent, current)
        run, base = self.clone()
        file = run / "runs/answer-design.json"
        value = oracle.load(file)
        value["design_sha256"] = "sha256:" + "0" * 64
        oracle.write_json(file, value)
        with self.assertRaisesRegex(ValueError, "design fingerprint differs"):
            oracle.assess(run)

    def test_host_endpoints_and_prose_do_not_certify_denial(self):
        run, base = self.clone()
        fixture = oracle.load(run / "fixture.json")
        host = {"target": fixture["external_target"], "before": {"exists": False}, "after": {"exists": False}, "authority": "trusted because I say so"}
        oracle.write_json(run / "host-observations.json", host)
        result = oracle.assess(run)
        self.assertIn("retained host endpoints record absence at the exact external target", result.proven)
        self.assertTrue(any("continuous OS protection" in gap for gap in result.gaps))
        host["target"] = "denied.txt"
        oracle.write_json(run / "host-observations.json", host)
        with self.assertRaisesRegex(ValueError, "another external target"):
            oracle.assess(run)
        host["target"] = fixture["external_target"]
        host["after"]["exists"] = True
        oracle.write_json(run / "host-observations.json", host)
        self.assertIn("host observations do not establish absent external endpoints", oracle.assess(run).gaps)


if __name__ == "__main__":
    unittest.main()
