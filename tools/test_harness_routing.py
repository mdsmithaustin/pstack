#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "evals" / "harness-routing"
sys.path.insert(0, str(MODULE))
import oracle
import study


class ReadProofTests(unittest.TestCase):
    def test_independently_labelled_controls(self):
        results = study.calibrate()
        self.assertEqual([r["id"] for r in results], ["positive", "partial", "failed", "missing-result", "wrong-runtime", "after-decision", "early-decision", "intro-only", "contamination", "chunked", "duplicate", "reordered", "truncated"])
        self.assertEqual(results[0]["observed"], {"reads": "PASS", "routing": "PASS", "exposure": None})
        self.assertEqual(results[2]["observed"]["reads"], "FAIL")
        self.assertEqual(results[4]["observed"]["routing"], "FAIL")
        self.assertEqual(results[8]["observed"]["exposure"], 4)

    def inspect(self, command, output, *, files=None, final=b"Prepared.", prefix=None):
        records = list(prefix or []) + [
            {"type": "item.started", "item": {"id": "one", "type": "command_execution", "command": command}},
            {"type": "item.completed", "item": {"id": "one", "type": "command_execution", "command": command, "aggregated_output": output, "exit_code": 0, "status": "completed"}},
            {"type": "item.completed", "item": {"id": "final", "type": "agent_message", "text": "Prepared."}}
        ]
        raw = "".join(json.dumps(record) + "\n" for record in records).encode()
        return oracle.inspect_trace(raw, final, Path("/grove/maple"), files or {"entry.md": b"first\nsecond\n"}, ["entry.md"], [], [])

    def test_shell_wrapper_and_multiple_explicit_files(self):
        result = self.inspect("/bin/zsh -lc 'cat entry.md another.md'", "first\nsecond\nextra\n", files={"entry.md": b"first\nsecond\n", "another.md": b"extra\n"})
        self.assertEqual(result["reads"]["status"], "PASS")
        self.assertEqual(result["observations"][0], {"path": "entry.md", "start": 0, "end": 13, "call_line": 1, "result_line": 2})

    def test_same_basename_elsewhere_and_search_are_not_read_proof(self):
        for command in ("cat /other/entry.md", "head entry.md", "rg first entry.md", "cat entry.md | head", "cat entry.md; true"):
            with self.subTest(command=command):
                self.assertEqual(self.inspect(command, "first\nsecond\n")["reads"]["status"], "INCONCLUSIVE")

    def test_returned_bytes_and_unique_final_binding_are_required(self):
        self.assertEqual(self.inspect("cat entry.md", "first\nsec")["reads"]["status"], "INCONCLUSIVE")
        self.assertEqual(self.inspect("cat entry.md", "first\nsecond\n", final=b"Other")["reads"]["status"], "INCONCLUSIVE")
        self.assertEqual(self.inspect("cat entry.md", "first\nsecond\n", prefix=[{"type":"item.completed","item":{"id":"old","type":"agent_message","text":"Prepared."}}])["reads"]["status"], "INCONCLUSIVE")

    def test_invalid_utf8_and_unpaired_completed_record(self):
        bad = oracle.inspect_trace(b"\xff", b"Prepared.", Path("/grove/maple"), {"entry.md":b"a"}, ["entry.md"], [], [])
        self.assertEqual(bad["reads"]["status"], "INCONCLUSIVE")
        raw = (MODULE / "calibration" / "positive.jsonl").read_bytes().splitlines(keepends=True)
        result = oracle.inspect_trace(b"".join(raw[1:]), b"Prepared.", Path("/grove/maple"), {"entry.md":b"first\nsecond\n"}, ["entry.md"], [], [])
        self.assertEqual(result["reads"]["status"], "INCONCLUSIVE")

    def test_raw_content_is_authoritative_over_normalized_excerpt(self):
        result = self.inspect("cat entry.md", "first\nsecond\n", prefix=[{"type":"normalization","output_head":"fir","files_read":["entry.md"]}])
        self.assertEqual(result["reads"]["status"], "PASS")

    def test_private_path_mentions_and_failed_attempts_are_not_exposure(self):
        raw = (MODULE / "calibration" / "positive.jsonl").read_bytes()
        raw = raw.replace(b"cat entry.md", b"cat parent-routing-criteria-6f82d1b9")
        result = oracle.inspect_trace(raw, b"Prepared.", Path("/grove/maple"), {"entry.md": b"first\nsecond\n"}, ["entry.md"], [], ["parent-routing-criteria-6f82d1b9"])
        self.assertEqual(result["context"]["exposures"], [])
        self.assertEqual(result["reads"]["status"], "INCONCLUSIVE")

    def test_first_committed_decision_rechecks_ordering(self):
        raw = (MODULE / "calibration" / "early-decision.jsonl").read_bytes()
        args = (raw, b"Prepared.", Path("/grove/maple"), {"entry.md":b"first\nsecond\n"}, ["entry.md"], [], [])
        self.assertEqual(oracle.inspect_trace(*args)["reads"]["status"], "PASS")
        result = oracle.inspect_trace(*args, decision_line=1)
        self.assertEqual(result["reads"]["status"], "FAIL")
        self.assertEqual(result["statements"], [{"line":1,"text":"Use the chat carrier."},{"line":4,"text":"Prepared."}])
        with self.assertRaises(ValueError):
            oracle.inspect_trace(*args, decision_line=2)


class CollectorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="grove-check-")
        self.root = Path(self.temp.name)
        self.fake = self.root / "codex"
        shutil.copy2(MODULE / "calibration" / "fake-cli.py", self.fake)
        self.output = self.root / "private"
        self.frozen = study.freeze(ROOT, self.output, self.fake, "configured-id", "high")
        self.contract = study.verify_study(self.output)

    def tearDown(self):
        for case in self.contract["cases"]:
            workspace = Path(case["workspace"])
            if workspace.exists():
                shutil.rmtree(workspace)
        neutral = Path(self.contract["cases"][0]["workspace"]).parent
        if neutral.exists():
            neutral.rmdir()
        self.temp.cleanup()

    def cli(self, *args):
        return subprocess.run([sys.executable, str(MODULE / "study.py"), *args], capture_output=True, check=False)

    def calls(self):
        path = self.root / "calls.jsonl"
        return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []

    def test_freeze_has_six_exact_inputs_and_normal_sibling_layout_without_exec(self):
        self.assertEqual(self.frozen["labels"], list("ABCDEF"))
        self.assertEqual(self.calls(), [])
        for case in self.contract["cases"]:
            self.assertEqual(study.inventory(Path(case["workspace"])), case["inventory"])
            prompt = (self.output / "inputs" / f"{case['label']}.txt").read_text()
            self.assertTrue(prompt.startswith("Read skills/pstack-harness/SKILL.md in full"))
            self.assertNotIn("references/", prompt)
            self.assertFalse((Path(case["workspace"]) / "rubric.json").exists())
        persona = Path(self.contract["cases"][4]["workspace"])
        emitted = subprocess.run([sys.executable, str(persona / "skills/pstack-harness/scripts/subagents.py"), "brief", "Comment Sicko"], capture_output=True, check=False)
        self.assertEqual(emitted.returncode, 0, emitted.stderr)
        self.assertIn(b"Yes... Ha ha ha... Yes!", emitted.stdout)
        resolved = subprocess.run([sys.executable, str(persona / "skills/setup-pstack/scripts/check-models-config.py"), "--resolve", "--harness", "codex", "--project", str(persona), "trail reviewer"], capture_output=True, check=False)
        self.assertEqual(resolved.returncode, 0, resolved.stderr)
        self.assertEqual(json.loads(resolved.stdout)["model"], "gpt-6-astra")

    def test_actual_cli_runs_exactly_once_per_slot_and_preserves_delivered_input(self):
        result = self.cli("run", "--study", str(self.output), "--approved-contract", self.frozen["contract_sha256"])
        self.assertEqual(result.returncode, 0, result.stderr)
        calls = self.calls()
        self.assertEqual(len(calls), 6)
        for call, case in zip(calls, self.contract["cases"]):
            self.assertEqual(call["stdin"].encode(), (self.output / "inputs" / f"{case['label']}.txt").read_bytes())
            self.assertEqual(call["cwd"], case["workspace"])
            self.assertEqual(call["argv"][call["argv"].index("--sandbox")+1], "read-only")
            self.assertIn("skip_host_skill_discovery", call["argv"])
            self.assertNotIn("OPENAI_API_KEY", call["environment_keys"])
        again = self.cli("run", "--study", str(self.output), "--approved-contract", self.frozen["contract_sha256"])
        self.assertEqual(again.returncode, 0, again.stderr)
        self.assertEqual(len(self.calls()), 6)
        assessed = self.cli("assess", "--study", str(self.output))
        self.assertEqual(assessed.returncode, 0, assessed.stderr)
        report = json.loads(assessed.stdout)
        self.assertEqual(len(report), 6)
        self.assertEqual(report[0]["reads"]["status"], "INCONCLUSIVE")
        self.assertEqual(report[0]["invocation"]["provider_execution"], "unknown")
        self.assertEqual(report[0]["invocation"]["runtime_reported"]["model"], None)
        packet = study.read_json(self.output / "semantic-packet.json")
        self.assertEqual(packet["cases"][0]["statements"], [{"line":1,"text":"I will read the instructions before choosing."},{"line":4,"text":"Prepared."}])
        self.assertNotIn("requested", packet)

    def test_failed_slots_are_consumed_without_retry(self):
        (self.root / "mode").write_text("failure")
        result = self.cli("run", "--study", str(self.output), "--approved-contract", self.frozen["contract_sha256"])
        self.assertEqual(result.returncode, 1)
        self.assertEqual([r["raw_returncode"] for r in json.loads(result.stdout)], [17] * 6)
        self.cli("run", "--study", str(self.output), "--approved-contract", self.frozen["contract_sha256"])
        self.assertEqual(len(self.calls()), 6)

    def test_timeout_retains_stream_and_kills_descendant_process_group(self):
        (self.root / "mode").write_text("timeout")
        result = study.collect_slot(self.contract, self.output, self.contract["cases"][0], deadline_seconds=0.3)
        self.assertEqual(result["state"], "timeout")
        slot = self.output / "slots" / "A"
        self.assertEqual((slot / "stderr.bin").read_bytes(), b"partial stderr\n")
        self.assertEqual((slot / "stream.jsonl").read_bytes(), b'{"type":"turn.started"}\n')
        pid = int((self.root / "descendant.pid").read_text())
        for _ in range(30):
            process = subprocess.run(["ps", "-o", "stat=", "-p", str(pid)], capture_output=True, check=False)
            if process.returncode or process.stdout.strip().startswith(b"Z"):
                break
            time.sleep(0.02)
        else:
            os.kill(pid, signal.SIGKILL)
            self.fail("descendant survived the collector deadline")
        self.assertEqual(study.collect_slot(self.contract, self.output, self.contract["cases"][0])["state"], "consumed")
        self.assertEqual(len(self.calls()), 1)

    def test_exclusive_slot_reservation_under_two_controllers(self):
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: study.collect_slot(self.contract, self.output, self.contract["cases"][0]), range(2)))
        self.assertEqual(sorted(r["state"] for r in results), ["completed", "consumed"])
        self.assertEqual(len(self.calls()), 1)

    def test_changed_frozen_input_and_missing_population_fail_closed(self):
        (self.output / "inputs/A.txt").write_text("changed")
        result = self.cli("run", "--study", str(self.output), "--approved-contract", self.frozen["contract_sha256"])
        self.assertEqual(result.returncode, 2)
        self.assertEqual(self.calls(), [])
        contract = self.output / "frozen.json"
        data = study.read_json(contract)
        data["cases"] = []
        study.write_json(contract, data)
        (self.output / "frozen.sha256").write_text(study.digest(contract.read_bytes()))
        self.assertEqual(self.cli("assess", "--study", str(self.output)).returncode, 2)

    def test_context_disclosure_and_possible_dispatch_stop_remaining_slots(self):
        (self.root / "mode").write_text("contamination")
        result = self.cli("run", "--study", str(self.output), "--approved-contract", self.frozen["contract_sha256"])
        self.assertEqual(result.returncode, 1)
        self.assertEqual(len(self.calls()), 1)
        self.assertEqual([r["state"] for r in json.loads(result.stdout)][1:], ["held-after-invalid-context"] * 5)
        report = study.assess(self.output, None)
        self.assertEqual(report[0]["context"]["first_exposure_line"], 3)
        again = self.cli("run", "--study", str(self.output), "--approved-contract", self.frozen["contract_sha256"])
        self.assertEqual(again.returncode, 1)
        self.assertEqual(len(self.calls()), 1)

    def test_possible_dispatch_in_raw_trace_stops_wave(self):
        (self.root / "mode").write_text("dispatch")
        result = self.cli("run", "--study", str(self.output), "--approved-contract", self.frozen["contract_sha256"])
        self.assertEqual(result.returncode, 1)
        self.assertEqual(len(self.calls()), 1)
        report = study.assess(self.output, None)
        self.assertEqual(report[0]["safeguards"]["status"], "FAIL")
        self.assertEqual(report[0]["prohibited"][0]["line"], 2)

    def test_approval_digest_and_saved_result_integrity(self):
        refused = self.cli("run", "--study", str(self.output), "--approved-contract", "uninspected")
        self.assertEqual(refused.returncode, 2)
        self.assertEqual(self.calls(), [])
        study.collect_slot(self.contract, self.output, self.contract["cases"][0])
        (self.output / "slots/A/stream.jsonl").write_text("changed")
        self.assertEqual(self.cli("assess", "--study", str(self.output)).returncode, 2)

    def test_workspace_mutation_consumes_slot_before_launch(self):
        case = self.contract["cases"][0]
        (Path(case["workspace"]) / "extra.txt").write_text("extra")
        result = study.collect_slot(self.contract, self.output, case)
        self.assertEqual(result, {"label":"A","state":"invalid-input","launched":False})
        self.assertEqual(study.collect_slot(self.contract, self.output, case)["state"], "consumed")
        self.assertEqual(self.calls(), [])


if __name__ == "__main__":
    unittest.main()
