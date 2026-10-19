import importlib.util
import io
import json
import os
import shutil
import struct
import subprocess
import sys
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

    def evaluate_bytecode_script(self, script):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            (root / "output.md").write_text(f"```sh\n{script}\n```\n", encoding="utf-8")
            return MODULE.evaluate("bytecode-controls", root)

    def replay_lifecycle(self, script, extra_states=(), timeout=None):
        definition, bootstrap = MODULE.load_case("lifecycle-observation")
        definition = json.loads(json.dumps(definition))
        definition["states"].extend(extra_states)
        if timeout is not None:
            for state in definition["states"]:
                state["timeout_seconds"] = timeout
        return MODULE.replay(MODULE.parse_plan(f"```sh\n{script}\n```\n"), definition, bootstrap)

    def lifecycle_record(self, state):
        return state["lifecycle_checks"][0]["attempts"][0]["record"]

    def assert_lifecycle_teardown(self, record):
        self.assertEqual(record["teardown"]["failure"], None, record)
        self.assertEqual(record["teardown"]["writer"], "closed")
        self.assertEqual(record["teardown"]["child_absent"], True)
        self.assertEqual(record["teardown"]["subreaper_restored"], 0)
        self.assertEqual(record["teardown"]["direct_children_after"], record["baseline_direct_children"])
        self.assertEqual(record["teardown"]["frozen_sha256_after"], record["frozen_sha256"])

    def test_lifecycle_public_cli_retains_clean_and_dirty_facts_and_actual_exits(self):
        code, result = self.evaluate_sample("lifecycle-observation", "valid-lifecycle-observation.md")
        self.assertEqual((code, result["status"]), (0, "pass"), result)
        self.assertEqual(result["states"], ["cleanup-present", "cleanup-omitted", "forced-operation-failure"])
        self.assertEqual(len(result["control_evidence"]), 2)
        for state, expected in zip(result["control_evidence"], [("reaped", "closed", 0), ("zombie", "open", 1)]):
            record = self.lifecycle_record(state)
            for name in ("application", "observation"):
                self.assertEqual((record["facts"][name]["child"], record["facts"][name]["writer"]), expected[:2])
            self.assertEqual((state["exit"], record["execution"]["exit"]), (expected[2], expected[2]))
            self.assertEqual(record["facts"]["actions"], [{"action": "application_snapshot", "sequence": 1}, {"action": "candidate_observation", "sequence": 2}])
            worker, child = record["worker_identity"], record["registered_child_identity"]
            self.assertEqual((worker["uid"], child["uid"], child["parent"]), (65533, 65533, worker["pid"]))
            self.assertEqual((worker["parent"], worker["session"], worker["group"]), (record["broker_pid"], worker["pid"], worker["pid"]))
            self.assertNotEqual(record["broker_pid"], 1)
            self.assertEqual((record["pipe"]["writer_owner"], record["pipe"]["reader_owner"], record["pipe"]["sole_writer"]), (worker["pid"], record["broker_pid"], True))
            self.assertEqual(record["pipe"]["role"], "application_cleanup_writer")
            self.assert_lifecycle_teardown(record)

    def test_lifecycle_repair_first_is_authenticated_and_rejected_with_an_outer_zero_control(self):
        state = {"name": "omitted-outer-zero", "bootstrap_state": "cleanup-omitted", "exit": "zero", "required_operations": [{"program": "python", "args": ["tools/check-lifecycle.py"], "expected_lifecycle": {"child": "zombie", "writer": "open"}}]}
        code, result = self.replay_lifecycle("set -eu\npython3 tools/check-lifecycle.py --repair-first", [state])
        self.assertEqual((code, result["status"]), (1, "candidate_failure"), result)
        control = next(item for item in result["control_evidence"] if item["state"] == "omitted-outer-zero")
        self.assertEqual((control["exit"], control["exit_matches"], control["missing_operations"]), (0, True, []))
        attempt = control["lifecycle_checks"][0]["attempts"][0]
        self.assertEqual((attempt["application_matches"], attempt["execution_matches"], attempt["protocol_matches"], attempt["order_matches"]), (True, True, True, False))
        self.assertIn("observer_repair_preceded_observation", attempt["failure_causes"])
        record = attempt["record"]
        self.assertEqual((record["facts"]["application"]["child"], record["facts"]["application"]["writer"]), ("zombie", "open"))
        self.assertEqual((record["facts"]["observation"]["child"], record["facts"]["observation"]["writer"]), ("reaped", "closed"))
        self.assertEqual(record["execution"]["exit"], 0)
        self.assertEqual(record["owner_diagnostics"]["repair"]["waitpid"], [record["registered_child_identity"]["pid"], 0])
        self.assert_lifecycle_teardown(record)

    def test_lifecycle_invalid_attempt_stays_invalid_in_either_order(self):
        for commands in [("--repair-first", ""), ("", "--repair-first")]:
            with self.subTest(commands=commands):
                script = "\n".join(f"python3 tools/check-lifecycle.py {argument} || true" for argument in commands) + "\nexit 1"
                code, result = self.replay_lifecycle(script)
                self.assertEqual((code, result["status"]), (1, "candidate_failure"), result)
                for state in result["control_evidence"]:
                    check = state["lifecycle_checks"][0]
                    self.assertEqual(len(check["attempts"]), 2)
                    self.assertEqual([item["order_matches"] for item in check["attempts"]], [argument == "" for argument in commands])
                    self.assertEqual(check["matches"], False)
                    for attempt in check["attempts"]:
                        self.assert_lifecycle_teardown(attempt["record"])

    def test_eight_lifecycle_attempts_run_and_ninth_latches_failure_without_a_worker(self):
        for count in (8, 9):
            with self.subTest(count=count):
                script = "\n".join("python3 tools/check-lifecycle.py || result=$?" for _ in range(count)) + "\nexit ${result:-0}"
                code, result = self.replay_lifecycle(script)
                self.assertEqual((code, result["status"]), (0, "pass") if count == 8 else (1, "candidate_failure"), result)
                for state in result["control_evidence"]:
                    check = state["lifecycle_checks"][0]
                    self.assertEqual(len(check["attempts"]), 8)
                    self.assertEqual(check["attempt_limit_exceeded"], count == 9)
                    workers = [attempt["record"]["worker_identity"]["pid"] for attempt in check["attempts"]]
                    self.assertEqual(len(set(workers)), 8)
                    for attempt in check["attempts"]:
                        self.assertLessEqual(len(json.dumps(attempt["record"]).encode()), 32768)
                        self.assert_lifecycle_teardown(attempt["record"])

    def test_candidate_failure_and_timeout_preserve_completed_lifecycle_observation(self):
        for suffix, timeout, wanted_timeout in [("exit 7", None, False), ("sleep 10", 1, True)]:
            with self.subTest(suffix=suffix):
                code, result = self.replay_lifecycle("python3 tools/check-lifecycle.py\n" + suffix, timeout=timeout)
                self.assertEqual((code, result["status"]), (1, "candidate_failure"), result)
                for state in result["control_evidence"]:
                    self.assertEqual(state["timed_out"], wanted_timeout)
                    self.assertEqual(state["lifecycle_checks"][0]["matches"], True)
                    self.assert_lifecycle_teardown(self.lifecycle_record(state))

    def test_real_lifecycle_worker_failures_recover_only_owned_children(self):
        faults = [("worker-timeout", "worker_timeout", 1), ("missing-registration", "protocol", 1), ("identity-failure", "identity", 1), ("missing-observation", "missing_observation", 1), ("death-before-registration", "missing_registration", 1), ("before-fork-failure", "missing_registration", 0)]
        for fault, cause, recovered_count in faults:
            with self.subTest(fault=fault):
                state = {"name": fault, "exit": "nonzero", "required_operations": [{"program": "python", "args": ["tools/check-lifecycle.py"], "expected_lifecycle": {"child": "zombie", "writer": "open"}}]}
                code, result = self.replay_lifecycle("set -eu\npython3 tools/check-lifecycle.py", [state])
                self.assertEqual((code, result["status"]), (1, "candidate_failure"), result)
                control = next(item for item in result["control_evidence"] if item["state"] == fault)
                self.assertEqual((control["exit_matches"], control["missing_operations"]), (True, []))
                record = self.lifecycle_record(control)
                self.assertEqual(record["facts"]["failure"]["cause"], cause)
                self.assertEqual(record["facts"]["observation"], None)
                self.assert_lifecycle_teardown(record)
                recovered = record["teardown"]["recovered_child"]
                self.assertEqual(int(recovered is not None), recovered_count)
                if recovered:
                    self.assertEqual((recovered["parent"], recovered["uid"], recovered["session"], recovered["group"]), (record["broker_pid"], 65533, record["worker_identity"]["session"], record["worker_identity"]["group"]))
                    self.assertEqual(record["teardown"]["recovered_identity_use"], "teardown_only")
                if fault == "death-before-registration":
                    self.assertEqual(record["registered_child_identity"], None)
                    self.assertEqual(record["facts"]["application"], None)
                    self.assertEqual(record["execution"]["exit"], 23)

    def test_lifecycle_crash_and_wrong_status_fail_despite_expected_outer_nonzero(self):
        for fault, actual in [("signaled-worker", -9), ("wrong-status", 97)]:
            with self.subTest(fault=fault):
                state = {"name": fault, "exit": "nonzero", "required_operations": [{"program": "python", "args": ["tools/check-lifecycle.py"], "expected_lifecycle": {"child": "zombie", "writer": "open"}}]}
                code, result = self.replay_lifecycle("set -eu\npython3 tools/check-lifecycle.py", [state])
                self.assertEqual((code, result["status"]), (1, "candidate_failure"), result)
                control = next(item for item in result["control_evidence"] if item["state"] == fault)
                attempt = control["lifecycle_checks"][0]["attempts"][0]
                self.assertEqual((control["exit_matches"], attempt["application_matches"], attempt["order_matches"], attempt["execution_matches"]), (True, True, True, False))
                self.assertEqual(attempt["record"]["execution"]["exit"], actual)
                self.assert_lifecycle_teardown(attempt["record"])

    def test_lifecycle_broker_preserves_an_unrelated_baseline_child(self):
        runtime = MODULE.CONTAINER_PROGRAM.split('\nroot = Path("/work")', 1)[0]
        program = r'''
broker = os.fork()
if broker == 0:
    project = Path("/work/baseline-control")
    project.mkdir()
    unrelated = os.fork()
    if unrelated == 0:
        os._exit(31)
    unrelated_pidfd = os.pidfd_open(unrelated)
    lifecycle_ready(unrelated_pidfd, time.monotonic() + 2)
    original = lifecycle_identity(unrelated)
    original_descriptors = sorted(os.listdir("/proc/self/fd"))
    records = []
    for configuration in [{"cleanup": True, "fault": None}, {"cleanup": False, "fault": None}, {"cleanup": False, "fault": "death-before-registration"}]:
        (project / "lifecycle-state.json").write_text(json.dumps(configuration))
        outcome = execute_lifecycle_operation({"arguments": [sys.executable, "tools/check-lifecycle.py"], "script_index": 1}, project)
        records.append(outcome["lifecycle"])
        lifecycle_same_identity(lifecycle_identity(unrelated), original)
        assert lifecycle_identity(unrelated).state == "Z"
        assert lifecycle_children() == {unrelated}
        assert sorted(os.listdir("/proc/self/fd")) == original_descriptors
    separate_wait = lifecycle_wait(unrelated, unrelated_pidfd, time.monotonic() + 2)
    os.close(unrelated_pidfd)
    print(json.dumps({"records": records, "unrelated": dataclasses.asdict(original), "separate_wait": separate_wait, "remaining": sorted(lifecycle_children())}), flush=True)
    os._exit(0)
_, status = os.waitpid(broker, 0)
raise SystemExit(os.waitstatus_to_exitcode(status))
'''
        command = MODULE.docker_command()
        command[-1] = runtime + program
        completed = subprocess.run(command, input=b"", capture_output=True, timeout=15)
        self.assertEqual(completed.returncode, 0, completed.stderr.decode())
        result = json.loads(completed.stdout)
        self.assertEqual((result["separate_wait"]["exit"], result["remaining"]), (31, []))
        self.assertEqual(len(result["records"]), 3)
        for record in result["records"]:
            self.assertNotEqual(record["broker_pid"], 1)
            self.assertEqual(record["baseline_direct_children"], [result["unrelated"]["pid"]])
            self.assert_lifecycle_teardown(record)

    def test_lifecycle_worker_output_bound_fails_without_erasing_facts(self):
        state = {"name": "output-limit", "exit": "nonzero", "required_operations": [{"program": "python", "args": ["tools/check-lifecycle.py"], "expected_lifecycle": {"child": "zombie", "writer": "open"}}]}
        code, result = self.replay_lifecycle("set -eu\npython3 tools/check-lifecycle.py", [state])
        self.assertEqual((code, result["status"]), (1, "candidate_failure"), result)
        record = self.lifecycle_record(next(item for item in result["control_evidence"] if item["state"] == "output-limit"))
        self.assertEqual(record["receipt_failure"], "lifecycle evidence exceeded its byte bound")
        self.assertEqual((record["facts"]["application"]["child"], record["facts"]["observation"]["child"]), ("zombie", "zombie"))
        self.assertEqual(record["execution"]["exit"], 1)
        self.assert_lifecycle_teardown(record)

    def test_lifecycle_measured_pipe_has_eof_while_worker_and_child_are_alive(self):
        state = {"name": "writer-ownership", "exit": "nonzero", "required_operations": [{"program": "python", "args": ["tools/check-lifecycle.py"], "expected_lifecycle": {"child": "zombie", "writer": "open"}}]}
        code, result = self.replay_lifecycle("set -eu\npython3 tools/check-lifecycle.py", [state])
        self.assertEqual((code, result["status"]), (1, "candidate_failure"), result)
        record = self.lifecycle_record(next(item for item in result["control_evidence"] if item["state"] == "writer-ownership"))
        self.assertEqual(record["teardown"]["sole_writer_control"], {"worker_alive": True, "child_alive": True, "pipe_eof": True})
        self.assertEqual(record["facts"]["application"], None)
        self.assertEqual(record["facts"]["observation"], None)
        self.assert_lifecycle_teardown(record)

    def test_bytecode_controls_observe_literal_imported_values_with_fresh_namespaces(self):
        code, result = self.evaluate_sample("bytecode-controls", "valid-bytecode-controls.md")
        self.assertEqual((code, result["status"]), (0, "pass"), result)
        self.assertEqual(result["states"], ["baseline", "mutated", "restored", "expected-mismatch", "forced-operation-failure"])
        controls = result["control_evidence"]
        self.assertEqual(
            [(control["state"], control["behavior_checks"][0]["observation"]["behavior"]) for control in controls],
            [("baseline", "baseline"), ("mutated", "mutation"), ("restored", "baseline"), ("expected-mismatch", "baseline")],
        )
        self.assertEqual(
            [control["behavior_checks"][0]["observation"]["cache_prefix"] for control in controls],
            ["/fresh-baseline", "/fresh-mutated", "/fresh-restored", "/fresh-expected-mismatch"],
        )
        self.assertEqual(
            [control["behavior_checks"][0]["observation"]["execution"] for control in controls],
            [
                {"exit": 0, "stdout_hex": "626173656c696e650a", "stderr_hex": ""},
                {"exit": 0, "stdout_hex": "6d75746174696f6e0a", "stderr_hex": ""},
                {"exit": 0, "stdout_hex": "626173656c696e650a", "stderr_hex": ""},
                {"exit": 0, "stdout_hex": "626173656c696e650a", "stderr_hex": ""},
            ],
        )
        for control in controls:
            observation = control["behavior_checks"][0]["observation"]
            self.assertEqual(observation["observer_uid"], 65533)
            self.assertEqual(
                (control["stdout"], control["stderr"], control["exit"]),
                ("", "", 1 if control["state"] == "expected-mismatch" else 0),
            )
            receipt = control["fixture_receipt"]
            self.assertEqual((receipt["source_size"], receipt["source_mtime_ns"]), (35, 1700000000000000000))
            self.assertEqual(struct.unpack("<III", bytes.fromhex(receipt["cache_header_hex"])[4:]), (0, 1700000000, 35))

    def test_prepopulated_timestamp_cache_is_read_despite_no_write_setting_and_rejected(self):
        code, result = self.evaluate_sample("bytecode-controls", "no-write-bytecode.md")
        self.assertEqual((code, result["status"]), (1, "candidate_failure"), result)
        self.assertEqual([control["state"] for control in result["failed_states"]], ["mutated", "restored", "expected-mismatch"])
        self.assertEqual(
            [control["behavior_checks"][0]["observation"]["behavior"] for control in result["control_evidence"]],
            ["baseline", "baseline", "mutation", "baseline"],
        )
        for control in result["failed_states"]:
            mismatch = control["state"] == "expected-mismatch"
            self.assertEqual((control["exit"], control["exit_matches"], control["missing_operations"]), (0, not mismatch, []))
            self.assertEqual(control["behavior_checks"][0]["observation"]["dont_write_bytecode"], True)
            self.assertEqual(control["behavior_checks"][0]["matches"], mismatch)

    def test_native_cache_prefix_options_and_equivalent_script_paths_pass(self):
        for command in (
            "python3 -B -X pycache_prefix=/native-prefix ./tools/observe.py",
            "python3 -Xpycache_prefix=/attached-prefix tools/../tools/observe.py",
        ):
            with self.subTest(command=command):
                code, result = self.evaluate_bytecode_script(
                    "set -eu\nobserved=$(" + command + ")\n[ \"$observed\" = \"$(cat expected.txt)\" ]"
                )
                self.assertEqual((code, result["status"]), (0, "pass"), result)
                self.assertEqual(
                    [control["behavior_checks"][0]["observation"]["behavior"] for control in result["control_evidence"]],
                    ["baseline", "mutation", "baseline", "baseline"],
                )

    def test_fresh_cache_print_only_gate_rejects_expected_mismatch(self):
        code, result = self.evaluate_bytecode_script(
            "set -eu\nPYTHONPYCACHEPREFIX=/fresh python3 tools/observe.py"
        )
        self.assertEqual((code, result["status"]), (1, "candidate_failure"), result)
        self.assertEqual([state["state"] for state in result["failed_states"]], ["expected-mismatch"])
        mismatch = result["failed_states"][0]
        self.assertEqual((mismatch["exit"], mismatch["exit_matches"], mismatch["missing_operations"]), (0, False, []))
        check = mismatch["behavior_checks"][0]
        self.assertTrue(check["matches"])
        self.assertEqual(check["observation"]["behavior"], "baseline")
        self.assertEqual(check["observation"]["execution"],
                         {"exit": 0, "stdout_hex": "626173656c696e650a", "stderr_hex": ""})
        self.assertEqual(mismatch["fixture_receipt"]["expected_value"], "mutation")

    def test_native_no_write_flag_alone_still_reads_stale_cache(self):
        code, result = self.evaluate_bytecode_script("set -eu\npython3 -B tools/observe.py")
        self.assertEqual((code, result["status"]), (1, "candidate_failure"))
        self.assertEqual([control["state"] for control in result["failed_states"]], ["mutated", "restored", "expected-mismatch"])
        self.assertEqual(
            [control["behavior_checks"][0]["observation"]["behavior"] for control in result["control_evidence"]],
            ["baseline", "baseline", "mutation", "baseline"],
        )

    def test_stdin_runpy_wrapper_is_outside_the_script_entrypoint_contract(self):
        code, result = self.evaluate_bytecode_script(
            "set -eu\npython3 -B - <<'PY'\nimport runpy\nrunpy.run_path('tools/observe.py', run_name='__main__')\nPY"
        )
        self.assertEqual((code, result["status"]), (1, "candidate_failure"))
        self.assertEqual(
            [control["behavior_checks"][0]["observation"] for control in result["control_evidence"]],
            [None, None, None, None],
        )
        self.assertIn("REJECT", result["control_evidence"][0]["stderr"])

    def test_source_hash_receipts_do_not_establish_executed_bytecode_behavior(self):
        code, result = self.evaluate_sample("bytecode-controls", "hash-only-bytecode.md")
        self.assertEqual((code, result["status"]), (1, "candidate_failure"))
        self.assertEqual(
            [control["behavior_checks"][0]["observation"] for control in result["control_evidence"]],
            [None, None, None, None],
        )
        self.assertIn("tools/subject.py", result["control_evidence"][0]["stdout"])

    def test_expected_stdout_cannot_replace_wrong_authenticated_imports(self):
        code, result = self.evaluate_sample("bytecode-controls", "forged-bytecode-output.md")
        self.assertEqual((code, result["status"]), (1, "candidate_failure"))
        mutated = result["failed_states"][0]
        self.assertEqual((mutated["stdout"], mutated["behavior_checks"][0]["observation"]["behavior"]), ("mutation\n", "baseline"))

    def test_wrong_then_correct_and_correct_then_wrong_imports_both_fail(self):
        default = "python3 tools/observe.py"
        fresh = "PYTHONPYCACHEPREFIX=/fresh python3 tools/observe.py"
        for commands in ((default, fresh), (fresh, default)):
            with self.subTest(commands=commands):
                code, result = self.evaluate_bytecode_script("set -eu\n" + "\n".join(commands))
                self.assertEqual((code, result["status"]), (1, "candidate_failure"))
                self.assertEqual([control["state"] for control in result["failed_states"]], ["mutated", "restored", "expected-mismatch"])
                observed = result["failed_states"][0]["behavior_checks"][0]["observation"]
                self.assertEqual(
                    (observed["behavior"], observed["conflicting_behavior"]),
                    ("baseline", "mutation") if commands[0] == default else ("mutation", "baseline"),
                )

    def test_repeated_correct_imports_with_different_cache_paths_pass(self):
        code, result = self.evaluate_bytecode_script(
            "set -eu\nPYTHONPYCACHEPREFIX=/first python3 tools/observe.py\n"
            'observed=$(PYTHONPYCACHEPREFIX=/second python3 tools/observe.py)\n'
            '[ "$observed" = "$(cat expected.txt)" ]'
        )
        self.assertEqual((code, result["status"]), (0, "pass"), result)
        self.assertEqual(
            [control["behavior_checks"][0]["observation"]["behavior"] for control in result["control_evidence"]],
            ["baseline", "mutation", "baseline", "baseline"],
        )

    def test_unrelated_socket_sender_cannot_forge_imported_behavior(self):
        code, result = self.evaluate_bytecode_script(
            "set -eu\npython3 tools/observe.py\npython3 - <<'PY'\n"
            "import json, os, socket\n"
            "with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:\n"
            "    client.connect(os.environ['PSTACK_EVIDENCE_SOCKET'])\n"
            "    client.sendall((json.dumps({'kind': 'observation', 'behavior': 'mutation', 'cache': '/fake', "
            "'cache_prefix': '/fake', 'dont_write_bytecode': True}) + '\\n').encode())\n"
            "    print(client.recv(1024).decode().strip())\nPY"
        )
        self.assertEqual((code, result["status"]), (1, "candidate_failure"))
        mutated = result["failed_states"][0]
        self.assertEqual(mutated["stdout"], "baseline\nREJECT\n")
        self.assertEqual(mutated["behavior_checks"][0]["observation"]["behavior"], "baseline")

    def test_import_observation_survives_a_later_checker_output_failure(self):
        code, result = self.evaluate_bytecode_script("set -eu\nPYTHONPYCACHEPREFIX=/fresh python3 tools/observe.py >/dev/full")
        self.assertEqual((code, result["status"]), (1, "candidate_failure"))
        self.assertEqual(
            [control["behavior_checks"][0]["observation"]["behavior"] for control in result["control_evidence"]],
            ["baseline", "mutation", "baseline", "baseline"],
        )
        self.assertEqual([control["exit_matches"] for control in result["control_evidence"]], [False, False, False, True])

    def test_ignored_forced_status_fails_even_with_correct_imported_values(self):
        code, result = self.evaluate_bytecode_script(
            'if observed=$(PYTHONPYCACHEPREFIX=/fresh python3 tools/observe.py); then\n'
            '  [ "$observed" = "$(cat expected.txt)" ]\nelse\n  true\nfi'
        )
        self.assertEqual((code, result["status"]), (1, "candidate_failure"))
        self.assertEqual([control["state"] for control in result["failed_states"]], ["forced-operation-failure"])
        self.assertEqual(result["failed_states"][0]["exit_matches"], False)

    def test_unsupported_startup_settings_do_not_enter_the_observer_worker(self):
        for setting in ("PYTHONINSPECT=1", "PYTHONSAFEPATH=1", "PYTHONWARNINGS=ignore", "LD_LIBRARY_PATH=/usr/local/lib"):
            with self.subTest(setting=setting):
                code, result = self.evaluate_bytecode_script(
                    f"set -eu\n{setting} PYTHONPYCACHEPREFIX=/fresh python3 tools/observe.py"
                )
                self.assertEqual((code, result["status"]), (1, "candidate_failure"), result)
                self.assertEqual([state["state"] for state in result["failed_states"]], ["baseline", "mutated", "restored", "expected-mismatch"])
                for control in result["control_evidence"]:
                    self.assertEqual((control["exit"], control["stdout"], control["behavior_checks"][0]["observation"]), (125, "", None))
                    self.assertIn("unsupported observer startup environment", control["stderr"])

    def test_unused_closed_stderr_preserves_valid_observer_execution(self):
        code, result = self.evaluate_bytecode_script(
            'set -eu\nobserved=$(PYTHONPYCACHEPREFIX=/fresh python3 tools/observe.py 2>&-)\n'
            'printf "%s\\n" "$observed"\n[ "$observed" = "$(cat expected.txt)" ]'
        )
        self.assertEqual((code, result["status"]), (0, "pass"), result)
        self.assertEqual([control["stdout"] for control in result["control_evidence"]], ["baseline\n", "mutation\n", "baseline\n", "baseline\n"])
        self.assertEqual([control["exit"] for control in result["control_evidence"]], [0, 0, 0, 1])

    def test_controller_receives_observer_output_and_propagates_its_exit(self):
        code, result = self.evaluate_bytecode_script(
            "python3 - <<'PY'\n"
            "import os, subprocess, sys\n"
            "from pathlib import Path\n"
            "result = subprocess.run(['python3', 'tools/observe.py'], "
            "env=dict(os.environ, PYTHONPYCACHEPREFIX='/controller'), capture_output=True, text=True)\n"
            "sys.stdout.write(result.stdout)\n"
            "sys.stderr.write(result.stderr)\n"
            "raise SystemExit(result.returncode or (0 if result.stdout == Path('expected.txt').read_text() else 1))\n"
            "PY"
        )
        self.assertEqual((code, result["status"]), (0, "pass"), result)
        self.assertEqual([control["stdout"] for control in result["control_evidence"]], ["baseline\n", "mutation\n", "baseline\n", "baseline\n"])
        self.assertEqual([control["exit"] for control in result["control_evidence"]], [0, 0, 0, 1])

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
