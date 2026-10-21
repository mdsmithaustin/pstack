import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "evals/skill-recovery/evaluate.py"
FIXTURES = CLI.parent / "fixtures"
ENTRY = b"Recover the entry on its own before the next reviewed action.\n"
STEP = b"Read the current step requirements before its action.\n"


def digest(data):
    return hashlib.sha256(data).hexdigest()


def boundary():
    return {"type": "compacted", "payload": {"replacement_history": []}}


def call(name):
    return {"type": "response_item", "payload": {"type": "custom_tool_call", "name": "exec", "call_id": name, "input": "reviewed input"}}


def returned(name, bodies, **flags):
    blocks = [{"type": "input_text", "text": "Script completed\nWall time 0.1 seconds\nOutput:\n"}]
    for body in bodies:
        blocks.append({"type": "input_text", "text": json.dumps({"exit_code": 0, "output": body.decode("utf-8")})})
    return {"type": "response_item", "payload": {"type": "custom_tool_call_output", "call_id": name, "output": blocks}, **flags}


def read(name, file="entry", block=1, source=None, output=None):
    return {"call_id": name, "file": file, "block": block, "source": source, "output": output}


class SkillRecoveryCliTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="skill-recovery-test-")
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.files = {"entry": ENTRY, "step": STEP}

    def prepare(self, rows, reads=(), governed=("action",), requirements=None, scope="MODE_ENTRY_CHECKPOINT", supplied=()):
        self.rows = copy.deepcopy(rows)
        self.raw = self.directory / "raw.jsonl"
        self.manifest_path = self.directory / "review.json"
        self.write_raw()
        lines = self.raw.read_bytes().splitlines(keepends=True)
        calls = {r["payload"]["call_id"]: n for n, r in enumerate(rows, 1)
                 if r["type"] == "response_item" and r["payload"].get("type") == "custom_tool_call"}
        returns = {r["payload"]["call_id"]: n for n, r in enumerate(rows, 1)
                   if r["type"] == "response_item" and r["payload"].get("type") == "custom_tool_call_output"}
        boundaries = [(n, "native_compacted") for n, r in enumerate(rows, 1) if r["type"] == "compacted"]
        boundaries += [(n, "supplied_context_summary") for n in supplied]
        required = requirements or [{"file": "entry", "policy": "whole_standalone"}]
        manifest = {"schema_version": 1, "raw_sha256": digest(self.raw.read_bytes()), "assessment_scope": scope,
                    "review": {"reviewer": "public CLI test contract", "complete": True}, "files": [],
                    "boundaries": [{"row": n, "row_sha256": digest(lines[n - 1]), "kind": kind,
                                    "requirements": copy.deepcopy(required)} for n, kind in sorted(boundaries)],
                    "calls": [], "reads": []}
        for file_id, data in self.files.items():
            (self.directory / (file_id + ".md")).write_bytes(data)
            manifest["files"].append({"id": file_id, "path": file_id + ".md", "sha256": digest(data),
                                      "role": "mode_entry" if file_id == "entry" else "guidance"})
        first = min((n for n, _ in boundaries), default=0)
        for call_id, n in calls.items():
            if n > first:
                manifest["calls"].append({"row": n, "row_sha256": digest(lines[n - 1]), "call_id": call_id,
                                          "disposition": "governed" if call_id in governed else "incidental",
                                          "reason": "task action" if call_id in governed else "guidance read"})
        for spec in reads:
            n = returns[spec["call_id"]]
            source = spec["source"] or [0, len(self.files[spec["file"]])]
            output = spec["output"] or [0, source[1] - source[0]]
            manifest["reads"].append({"call_id": spec["call_id"], "return_row": n,
                                      "return_sha256": digest(lines[n - 1]), "file": spec["file"],
                                      "block": spec["block"], "source_range": source, "output_range": output})
        self.manifest = manifest
        self.write_manifest()
        return self

    def write_raw(self):
        self.raw.write_bytes(b"".join(json.dumps(row, ensure_ascii=True).encode() + b"\n" for row in self.rows))

    def write_manifest(self):
        self.manifest_path.write_text(json.dumps(self.manifest))

    def rebind(self):
        self.write_raw()
        lines = self.raw.read_bytes().splitlines(keepends=True)
        self.manifest["raw_sha256"] = digest(self.raw.read_bytes())
        for item in self.manifest["boundaries"] + self.manifest["calls"]:
            item["row_sha256"] = digest(lines[item["row"] - 1])
        for item in self.manifest["reads"]:
            item["return_sha256"] = digest(lines[item["return_row"] - 1])
        self.write_manifest()

    def run_cli(self, expected):
        result = subprocess.run([sys.executable, str(CLI), "--raw", str(self.raw), "--manifest", str(self.manifest_path)],
                                capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, expected, (result.stdout, result.stderr))
        self.assertEqual(result.stderr, "")
        report = json.loads(result.stdout)
        self.assertEqual(report["raw_sha256"], digest(self.raw.read_bytes()))
        return report

    def basic(self):
        return self.prepare([boundary(), call("read"), returned("read", [ENTRY]), call("action"), returned("action", [b"Done."])], [read("read")])

    def test_standalone_full_entry(self):
        report = self.basic().run_cli(0)
        self.assertEqual(report["status"], "SATISFIED")
        self.assertEqual(report["applicable_windows"], 1)
        attempt = report["windows"][0]["attempts"][0]
        self.assertEqual((attempt["content"], attempt["packaging"], attempt["ordering"]), ("COMPLETE", "STANDALONE", "BEFORE_ACTION"))

    def test_committed_controls(self):
        cases = [("mixed-full", 1, "FAIL"), ("pickup-late-entry", 1, "FAIL"), ("repaired-entry", 0, "SATISFIED_WITH_REPAIRS")]
        for name, code, status in cases:
            with self.subTest(name=name):
                result = subprocess.run([sys.executable, str(CLI), "--raw", str(FIXTURES / (name + ".jsonl")),
                                         "--manifest", str(FIXTURES / (name + ".manifest.json"))], capture_output=True, text=True, timeout=15)
                self.assertEqual(result.returncode, code, result.stdout + result.stderr)
                report = json.loads(result.stdout)
                self.assertEqual(report["status"], status)
                if name == "repaired-entry":
                    self.assertTrue(report["windows"][0]["attempts"][0]["repaired_before_action"])
                if name == "pickup-late-entry":
                    self.assertEqual(report["windows"][0]["first_action_row"], 2)
                    self.assertEqual(report["windows"][0]["attempts"][-1]["packaging"], "STANDALONE")
                    self.assertEqual(report["windows"][0]["attempts"][-1]["ordering"], "LATE")

    def test_separate_full_blocks_are_one_mixed_outer_response(self):
        self.prepare([boundary(), call("read"), returned("read", [ENTRY, STEP]), call("action"), returned("action", [b"Done."])],
                     [read("read"), read("read", "step", 2)])
        report = self.run_cli(1)
        self.assertEqual(len(report["windows"][0]["attempts"]), 2)
        self.assertTrue(all(a["content"] == "COMPLETE" and a["packaging"] == "MIXED_FILES" for a in report["windows"][0]["attempts"]))
        self.assertEqual(len(report["outer_responses"][0]["blocks"]), 3)

    def test_one_command_multi_file_output_is_mixed(self):
        self.prepare([boundary(), call("read"), returned("read", [ENTRY + STEP]), call("action"), returned("action", [b"Done."])],
                     [read("read"), read("read", "step", 1, output=[len(ENTRY), len(ENTRY) + len(STEP)])])
        report = self.run_cli(1)
        self.assertTrue(all(a["packaging"] == "MIXED_FILES" for a in report["windows"][0]["attempts"]))

    def test_extra_output_block_prevents_standalone(self):
        self.prepare([boundary(), call("read"), returned("read", [ENTRY, b"unrelated output"]), call("action"), returned("action", [b"Done."])], [read("read")])
        report = self.run_cli(1)
        self.assertEqual(report["windows"][0]["attempts"][0]["packaging"], "EXTRA_CONTENT")
        self.assertEqual(report["windows"][0]["attempts"][0]["content"], "COMPLETE")

    def test_extra_output_in_same_body_prevents_standalone(self):
        self.prepare([boundary(), call("read"), returned("read", [ENTRY + b"extra"]), call("action"), returned("action", [b"Done."])], [read("read")])
        self.assertEqual(self.run_cli(1)["windows"][0]["attempts"][0]["packaging"], "EXTRA_CONTENT")

    def test_same_call_read_and_action_is_late(self):
        self.prepare([boundary(), call("read-action"), returned("read-action", [ENTRY])], [read("read-action")], governed=("read-action",))
        report = self.run_cli(1)
        self.assertEqual(report["windows"][0]["first_action_row"], 2)
        attempt = report["windows"][0]["attempts"][0]
        self.assertEqual((attempt["content"], attempt["packaging"], attempt["ordering"]), ("COMPLETE", "STANDALONE", "LATE"))

    def test_later_standalone_does_not_repair_first_action(self):
        self.prepare([boundary(), call("first"), returned("first", [ENTRY, STEP]), call("action"), returned("action", [b"Done."]), call("late"), returned("late", [ENTRY])],
                     [read("first"), read("first", "step", 2), read("late")])
        attempts = self.run_cli(1)["windows"][0]["attempts"]
        self.assertEqual(attempts[-1]["ordering"], "LATE")
        self.assertFalse(any(a["repaired_before_action"] for a in attempts))

    def test_invalid_attempt_after_valid_read_is_not_clean(self):
        self.prepare([boundary(), call("first"), returned("first", [ENTRY]), call("mixed"), returned("mixed", [ENTRY, STEP]),
                      call("action"), returned("action", [b"Done."])],
                     [read("first"), read("mixed"), read("mixed", "step", 2)])
        report = self.run_cli(1)
        self.assertEqual(report["windows"][0]["requirements"][0]["unrepaired_violation_attempts"], [1])

    def test_unverified_attempt_after_valid_read_is_inconclusive(self):
        for observation in ("wrong_bytes", "truncated", "unsupported_carrier"):
            with self.subTest(observation=observation):
                later = returned("later", [ENTRY])
                if observation == "wrong_bytes":
                    later = returned("later", [b"x" * len(ENTRY)])
                elif observation == "truncated":
                    later["truncated"] = True
                else:
                    later["payload"]["output"][1]["text"] = json.dumps({"status": "fulfilled", "value": {"exit_code": 0, "output": ENTRY.decode()}})
                self.prepare([boundary(), call("valid"), returned("valid", [ENTRY]), call("later"), later,
                              call("action"), returned("action", [b"Done."])], [read("valid"), read("later")])
                self.assertEqual(self.run_cli(2)["status"], "INCONCLUSIVE")

    def test_flagged_attempt_can_be_repaired_before_action(self):
        self.prepare([boundary(), call("flagged"), returned("flagged", [ENTRY], truncated=True), call("repair"), returned("repair", [ENTRY]),
                      call("action"), returned("action", [b"Done."])], [read("flagged"), read("repair")])
        report = self.run_cli(0)
        self.assertEqual(report["status"], "SATISFIED_WITH_REPAIRS")
        self.assertTrue(report["windows"][0]["attempts"][0]["repaired_before_action"])

    def test_source_notice_words_are_exact_content(self):
        self.files["entry"] = b"Read after compaction, truncation, or an output truncated example.\n"
        self.prepare([boundary(), call("read"), returned("read", [self.files["entry"]]), call("action"), returned("action", [b"Done."])], [read("read")])
        self.assertEqual(self.run_cli(0)["windows"][0]["attempts"][0]["transport"], "CLEAR")

    def test_literal_notice_source_is_not_transport(self):
        self.files["entry"] = b"output truncated\n"
        self.prepare([boundary(), call("read"), returned("read", [self.files["entry"]]), call("action"), returned("action", [b"Done."])], [read("read")])
        self.run_cli(0)

    def test_structured_truncation_with_exact_bytes_is_inconclusive(self):
        self.basic()
        self.rows[2]["truncated"] = True
        self.rebind()
        attempt = self.run_cli(2)["windows"][0]["attempts"][0]
        self.assertEqual(attempt["content"], "COMPLETE")
        self.assertIn("structured_truncation", attempt["reasons"])

    def test_notice_outside_source_stays_visible(self):
        self.prepare([boundary(), call("read"), returned("read", [ENTRY + b"Warning: truncated output\n"]), call("action"), returned("action", [b"Done."])], [read("read")])
        self.assertIn("transport_notice", self.run_cli(2)["windows"][0]["attempts"][0]["reasons"])

    def test_native_unicode_truncation_marker_is_transport(self):
        for marker in ("…5 tokens truncated…", "…40 chars truncated…"):
            with self.subTest(marker=marker):
                head, tail, notice = ENTRY[:20], ENTRY[20:], marker.encode()
                self.prepare([boundary(), call("read"), returned("read", [head + notice + tail]), call("action"), returned("action", [b"Done."])],
                             [read("read", source=[0, 20], output=[0, 20]),
                              read("read", source=[20, len(ENTRY)], output=[20 + len(notice), len(ENTRY) + len(notice)])])
                self.assertIn("transport_notice", self.run_cli(2)["windows"][0]["attempts"][0]["reasons"])

    def test_nonzero_command_does_not_prove_delivery(self):
        self.basic()
        body = json.loads(self.rows[2]["payload"]["output"][1]["text"])
        body["exit_code"] = 7
        self.rows[2]["payload"]["output"][1]["text"] = json.dumps(body)
        self.rebind()
        self.assertIn("command_failed", self.run_cli(2)["windows"][0]["attempts"][0]["reasons"])

    def test_prefix_cannot_satisfy_whole_entry(self):
        self.prepare([boundary(), call("read"), returned("read", [ENTRY[:12]]), call("action"), returned("action", [b"Done."])],
                     [read("read", source=[0, 12])])
        self.assertFalse(self.run_cli(1)["windows"][0]["requirements"][0]["satisfied_before_action"])

    def test_wrong_bytes_are_inconclusive(self):
        self.prepare([boundary(), call("read"), returned("read", [b"x" * len(ENTRY)]), call("action"), returned("action", [b"Done."])], [read("read")])
        self.run_cli(2)

    def test_missing_pair_is_inconclusive(self):
        self.basic()
        self.rows.pop()
        self.rebind()
        self.assertEqual(self.run_cli(2)["errors"][0]["code"], "unpaired_outer_call")

    def test_duplicate_call_identity_is_inconclusive(self):
        self.basic()
        self.rows.append(copy.deepcopy(self.rows[1]))
        self.rebind()
        self.assertEqual(self.run_cli(2)["errors"][0]["code"], "duplicate_outer_identity")

    def test_later_duplicate_return_invalidates_earlier_apparent_success(self):
        self.basic()
        self.rows.append(copy.deepcopy(self.rows[2]))
        self.rebind()
        self.assertEqual(self.run_cli(2)["errors"][0]["code"], "duplicate_outer_identity")

    def test_omitted_call_review_cannot_hide_action(self):
        self.basic()
        self.manifest["calls"].pop()
        self.write_manifest()
        self.assertEqual(self.run_cli(2)["errors"][0]["code"], "incomplete_call_review")

    def test_omitted_native_boundary_is_inconclusive(self):
        self.basic()
        self.rows.append(boundary())
        self.rebind()
        self.assertEqual(self.run_cli(2)["errors"][0]["code"], "omitted_native_boundary")

    def test_unclaimed_exact_governing_body_is_inconclusive(self):
        self.basic()
        self.manifest["reads"] = []
        self.write_manifest()
        self.assertEqual(self.run_cli(2)["errors"][0]["code"], "undeclared_governing_body")

    def test_foreign_fragments_cannot_hide_complete_entry(self):
        for embedded in (False, True):
            for fragments in (1, 3):
                for repaired in (False, True):
                    with self.subTest(embedded=embedded, fragments=fragments, repaired=repaired):
                        prefix = b"unrelated prefix\n" if embedded else b""
                        body = prefix + ENTRY + (b"unrelated suffix\n" if embedded else b"")
                        masks = [read("mixed", "step", source=[STEP.index(bytes([byte])), STEP.index(bytes([byte])) + 1],
                                      output=[len(prefix) + offset, len(prefix) + offset + 1])
                                 for offset, byte in enumerate(ENTRY[:fragments])]
                        rows = [boundary()]
                        if not repaired:
                            rows += [call("valid"), returned("valid", [ENTRY])]
                        rows += [call("mixed"), returned("mixed", [body, STEP])]
                        if repaired:
                            rows += [call("valid"), returned("valid", [ENTRY])]
                        rows += [call("action"), returned("action", [b"Done."])]
                        self.prepare(rows, masks + [read("mixed", "step", 2), read("valid")])
                        report = self.run_cli(2)
                        self.assertEqual(report["status"], "INCONCLUSIVE")
                        self.assertEqual(report["errors"][0]["code"], "undeclared_governing_body")

    def test_unsupported_carriers_cannot_hide_complete_entry(self):
        def envelope(body):
            return {"chunk_id": "c", "wall_time_seconds": 0.1, "exit_code": 0, "original_token_count": 1, "output": body.decode()}

        shapes = {
            "status_value": lambda body: {"type": "input_text", "text": json.dumps({"status": "fulfilled", "value": envelope(body)})},
            "i_status_value": lambda body: {"type": "input_text", "text": json.dumps({"i": 0, "status": "fulfilled", "value": envelope(body)})},
            "envelope_extra_key": lambda body: {"type": "input_text", "text": json.dumps(dict(envelope(body), stderr=""))},
            "output_metadata": lambda body: {"type": "input_text", "text": json.dumps({"output": body.decode(), "metadata": {"exit_code": 0}})},
            "block_extra_key": lambda body: {"type": "input_text", "text": json.dumps(envelope(body)), "annotations": []},
        }
        for name, shape in shapes.items():
            for hidden in (True, False):
                with self.subTest(shape=name, hidden=hidden):
                    mixed = returned("mixed", [])
                    mixed["payload"]["output"] += [shape(ENTRY if hidden else b"Done.\n"), shape(STEP if hidden else b"Done.\n")]
                    self.prepare([boundary(), call("valid"), returned("valid", [ENTRY]), call("mixed"), mixed,
                                  call("action"), returned("action", [b"Done."])], [read("valid")])
                    report = self.run_cli(2 if hidden else 0)
                    if hidden:
                        self.assertEqual(report["errors"][0]["code"], "undeclared_governing_body")
                    else:
                        self.assertEqual(report["status"], "SATISFIED")

    def test_every_repeated_or_overlapping_occurrence_needs_own_claim(self):
        for entry, body, source, output in (
            (ENTRY, ENTRY + ENTRY, [0, len(ENTRY)], [0, len(ENTRY)]),
            (b"aaa", b"aaaa", [0, 3], [0, 3]),
            (ENTRY, ENTRY, [0, 12], [0, 12]),
            (ENTRY, ENTRY + ENTRY[:12], [0, 12], [len(ENTRY), len(ENTRY) + 12]),
        ):
            with self.subTest(entry=entry, output=output):
                self.files["entry"] = entry
                self.prepare([boundary(), call("read"), returned("read", [body]),
                              call("valid"), returned("valid", [entry]), call("action"), returned("action", [b"Done."])],
                             [read("read", source=source, output=output), read("valid")])
                self.assertEqual(self.run_cli(2)["errors"][0]["code"], "undeclared_governing_body")

    def test_declared_repeated_occurrences_are_accounted_for(self):
        self.prepare([boundary(), call("read"), returned("read", [ENTRY + ENTRY]),
                      call("action"), returned("action", [b"Done."])],
                     [read("read"), read("read", output=[len(ENTRY), 2 * len(ENTRY)])])
        self.assertEqual(self.run_cli(0)["status"], "SATISFIED")

    def test_split_blocks_cannot_hide_complete_entry(self):
        for split in (1, 17, len(ENTRY) - 1):
            for foreign_mask in (False, True):
                with self.subTest(split=split, foreign_mask=foreign_mask):
                    reads = [read("mixed", "step", 3), read("valid")]
                    if foreign_mask:
                        reads.append(read("mixed", "step", 1, source=[STEP.index(b"R"), STEP.index(b"R") + 1], output=[0, 1]))
                    self.prepare([boundary(), call("mixed"), returned("mixed", [ENTRY[:split], ENTRY[split:], STEP]),
                                  call("valid"), returned("valid", [ENTRY]), call("action"), returned("action", [b"Done."])], reads)
                    self.assertEqual(self.run_cli(2)["errors"][0]["code"], "undeclared_governing_body")

    def test_declared_split_blocks_preserve_whole_entry_policy(self):
        self.prepare([boundary(), call("split"), returned("split", [ENTRY[:17], ENTRY[17:]]),
                      call("valid"), returned("valid", [ENTRY]), call("action"), returned("action", [b"Done."])],
                     [read("split", source=[0, 17]), read("split", block=2, source=[17, len(ENTRY)]), read("valid")])
        report = self.run_cli(0)
        self.assertEqual(report["status"], "SATISFIED_WITH_REPAIRS")
        self.assertFalse(report["windows"][0]["attempts"][0]["whole_body"])

    def test_raw_hash_binding(self):
        self.basic()
        self.raw.write_bytes(self.raw.read_bytes() + b"\n")
        self.assertEqual(self.run_cli(2)["errors"][0]["code"], "raw_hash_mismatch")

    def test_row_hash_binding(self):
        self.basic()
        self.manifest["reads"][0]["return_sha256"] = "0" * 64
        self.write_manifest()
        self.assertEqual(self.run_cli(2)["errors"][0]["code"], "row_hash_mismatch")

    def test_expected_hash_binding(self):
        self.basic()
        (self.directory / "entry.md").write_bytes(b"other")
        self.assertEqual(self.run_cli(2)["errors"][0]["code"], "expected_file_hash_or_bytes_mismatch")

    def test_malformed_and_non_utf8_raw(self):
        for data in (b"{\n", b"\xff\n", b""):
            with self.subTest(data=data):
                self.basic()
                self.raw.write_bytes(data)
                self.manifest["raw_sha256"] = digest(data)
                self.write_manifest()
                self.run_cli(2)

    def test_duplicate_json_keys(self):
        self.basic()
        self.raw.write_bytes(self.raw.read_bytes().replace(b'"type": "compacted"', b'"type": "compacted", "type": "compacted"', 1))
        self.manifest["raw_sha256"] = digest(self.raw.read_bytes())
        self.write_manifest()
        self.assertEqual(self.run_cli(2)["errors"][0]["code"], "duplicate_json_key")

    def test_unknown_record_is_inconclusive(self):
        self.basic()
        self.rows[0]["type"] = "unknown_native_action"
        self.rebind()
        self.assertEqual(self.run_cli(2)["errors"][0]["code"], "unsupported_record")

    def test_non_text_record_tags_are_inconclusive(self):
        for tag in ([], {}, None, 7, True):
            with self.subTest(tag=tag):
                self.basic()
                self.rows[0]["type"] = tag
                self.rebind()
                report = self.run_cli(2)
                self.assertEqual(report["status"], "INCONCLUSIVE")
                self.assertEqual(report["errors"], [{"code": "unsupported_record", "row": 1}])

    def test_post_action_unresolved_calls_preserve_frozen_verdict(self):
        for satisfied in (False, True):
            with self.subTest(satisfied=satisfied):
                rows = [boundary()]
                if satisfied:
                    rows += [call("entry"), returned("entry", [ENTRY])]
                rows += [call("action"), returned("action", [b"Done."]),
                         call("unresolved"), returned("unresolved", [b"Later observation."])]
                self.prepare(rows, [read("entry")] if satisfied else [])
                self.manifest["calls"][-1]["disposition"] = "unresolved"
                self.write_manifest()
                report = self.run_cli(0 if satisfied else 1)
                self.assertEqual(report["status"], "SATISFIED" if satisfied else "FAIL")
                self.assertEqual(report["windows"][0]["unresolved_call_rows"], [len(rows) - 1])

    def test_late_unverified_reads_preserve_frozen_verdict(self):
        for satisfied in (False, True):
            for observation in ("truncated", "command_failed", "unsupported", "wrong_bytes"):
                with self.subTest(satisfied=satisfied, observation=observation):
                    rows = [boundary()]
                    reads = []
                    if satisfied:
                        rows += [call("entry"), returned("entry", [ENTRY])]
                        reads.append(read("entry"))
                    late = returned("late", [ENTRY])
                    if observation == "truncated":
                        late["truncated"] = True
                    elif observation == "command_failed":
                        late["payload"]["output"][1]["text"] = json.dumps({"exit_code": 7, "output": ENTRY.decode()})
                    elif observation == "unsupported":
                        late["payload"]["output"][1] = {"type": "image", "data": "sample"}
                    else:
                        late = returned("late", [b"x" * len(ENTRY)])
                    rows += [call("action"), returned("action", [b"Done."]), call("late"), late]
                    self.prepare(rows, reads + [read("late")])
                    report = self.run_cli(0 if satisfied else 1)
                    self.assertEqual(report["status"], "SATISFIED" if satisfied else "FAIL")
                    attempt = report["windows"][0]["attempts"][-1]
                    self.assertEqual(attempt["ordering"], "LATE")
                    self.assertFalse(attempt["repaired_before_action"])

    def test_flagged_return_crossing_boundary_preserves_failure(self):
        self.prepare([boundary(), call("read"), call("action"), returned("action", [b"Done."]), boundary(),
                      returned("read", [ENTRY], truncated=True), call("next-action"), returned("next-action", [b"Done."])],
                     [read("read")], governed=("action", "next-action"))
        report = self.run_cli(1)
        self.assertEqual([window["status"] for window in report["windows"]], ["FAIL", "FAIL"])
        self.assertEqual(report["windows"][0]["attempts"][0]["ordering"], "CROSSES_BOUNDARY")

    def test_unresolved_call_prevents_pass(self):
        self.basic()
        self.manifest["calls"][0]["disposition"] = "unresolved"
        self.write_manifest()
        self.assertEqual(self.run_cli(2)["windows"][0]["unresolved_call_rows"], [2])

    def test_mode_chunks_are_rejected_by_policy(self):
        self.basic()
        self.manifest["boundaries"][0]["requirements"][0]["policy"] = "explicit_chunks"
        self.write_manifest()
        self.assertEqual(self.run_cli(2)["errors"][0]["code"], "mode_entry_cannot_use_chunks")

    def test_guidance_chunks_cover_exact_bytes(self):
        split = 17
        self.prepare([boundary(), call("entry"), returned("entry", [ENTRY]), call("one"), returned("one", [STEP[:split]]),
                      call("two"), returned("two", [STEP[split:]]), call("action"), returned("action", [b"Done."])],
                     [read("entry"), read("one", "step", source=[0, split]), read("two", "step", source=[split, len(STEP)])],
                     requirements=[{"file": "entry", "policy": "whole_standalone"}, {"file": "step", "policy": "explicit_chunks"}],
                     scope="CURRENT_STEP_RECOVERY")
        self.assertTrue(all(r["satisfied_before_action"] for r in self.run_cli(0)["windows"][0]["requirements"]))

    def test_chunk_repair_requires_complete_post_violation_coverage(self):
        split = 17
        for repair in ("prefix", "suffix", "complete"):
            with self.subTest(repair=repair):
                rows = [boundary(), call("one"), returned("one", [STEP[:split]]),
                        call("two"), returned("two", [STEP[split:]]),
                        call("mixed"), returned("mixed", [ENTRY, STEP])]
                reads = [read("one", "step", source=[0, split]),
                         read("two", "step", source=[split, len(STEP)]),
                         read("mixed"), read("mixed", "step", 2)]
                if repair in ("prefix", "complete"):
                    rows += [call("prefix"), returned("prefix", [STEP[:split]])]
                    reads.append(read("prefix", "step", source=[0, split]))
                if repair in ("suffix", "complete"):
                    rows += [call("suffix"), returned("suffix", [STEP[split:]])]
                    reads.append(read("suffix", "step", source=[split, len(STEP)]))
                rows += [call("entry"), returned("entry", [ENTRY]), call("action"), returned("action", [b"Done."])]
                reads.append(read("entry"))
                self.prepare(rows, reads,
                             requirements=[{"file": "entry", "policy": "whole_standalone"},
                                           {"file": "step", "policy": "explicit_chunks"}], scope="CURRENT_STEP_RECOVERY")
                complete = repair == "complete"
                report = self.run_cli(0 if complete else 1)
                self.assertEqual(report["status"], "SATISFIED_WITH_REPAIRS" if complete else "FAIL")
                window = report["windows"][0]
                step = window["requirements"][1]
                self.assertTrue(step["satisfied_before_action"])
                self.assertEqual(step["unrepaired_violation_attempts"], [] if complete else [3])
                self.assertEqual(window["attempts"][2]["packaging"], "MIXED_FILES")
                self.assertTrue(window["attempts"][2]["repaired_before_action"])
                self.assertEqual(window["attempts"][3]["packaging"], "MIXED_FILES")
                self.assertEqual(window["attempts"][3]["repaired_before_action"], complete)

    def test_chunks_do_not_cross_windows(self):
        split = 17
        self.prepare([boundary(), call("entry"), returned("entry", [ENTRY]), call("one"), returned("one", [STEP[:split]]),
                      boundary(), call("two"), returned("two", [STEP[split:]]), call("action"), returned("action", [b"Done."])],
                     [read("entry"), read("one", "step", source=[0, split]), read("two", "step", source=[split, len(STEP)])],
                     requirements=[{"file": "entry", "policy": "whole_standalone"}, {"file": "step", "policy": "explicit_chunks"}], scope="CURRENT_STEP_RECOVERY")
        report = self.run_cli(1)
        self.assertEqual([w["status"] for w in report["windows"]], ["NO_LATER_GOVERNED_ACTION", "FAIL"])
        self.assertEqual((report["applicable_windows"], report["non_applicable_windows"]), (1, 1))

    def test_multiple_applicable_windows(self):
        self.prepare([boundary(), call("one"), returned("one", [ENTRY]), call("action"), returned("action", [b"Done."]),
                      boundary(), call("action-two"), returned("action-two", [b"Done."])], [read("one")], governed=("action", "action-two"))
        report = self.run_cli(1)
        self.assertEqual([w["status"] for w in report["windows"]], ["SATISFIED", "FAIL"])
        self.assertEqual(report["applicable_windows"], 2)

    def test_no_later_action_is_not_green(self):
        self.prepare([boundary(), call("read"), returned("read", [ENTRY])], [read("read")])
        report = self.run_cli(3)
        self.assertEqual(report["status"], "NO_LATER_GOVERNED_ACTION")
        self.assertEqual(report["applicable_windows"], 0)
        self.assertEqual(report["non_applicable_windows"], 1)

    def test_empty_boundary_list_is_not_green(self):
        self.basic()
        self.manifest["boundaries"] = []
        self.write_manifest()
        self.assertEqual(self.run_cli(2)["errors"][0]["code"], "missing_boundary")

    def test_initial_injection_does_not_satisfy_recovery(self):
        message = {"type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": ENTRY.decode()}]}}
        self.prepare([message, boundary(), call("action"), returned("action", [b"Done."])])
        self.manifest["initial_injections"] = [{"row": 1, "row_sha256": digest(self.raw.read_bytes().splitlines(keepends=True)[0]),
                                               "file": "entry", "block": 0, "output_range": [0, len(ENTRY)]}]
        self.write_manifest()
        report = self.run_cli(1)
        self.assertEqual(report["initial_deliveries"], [{"row": 1, "file": "entry", "exact_content": True, "recovery_credit": False}])

    def test_replacement_history_does_not_create_read(self):
        marker = boundary()
        marker["payload"]["replacement_history"] = [call("nested"), returned("nested", [ENTRY])]
        self.prepare([marker, call("action"), returned("action", [b"Done."])])
        self.assertEqual(self.run_cli(1)["windows"][0]["attempts"], [])

    def test_preboundary_read_does_not_satisfy_recovery(self):
        self.prepare([call("before"), returned("before", [ENTRY]), boundary(), call("action"), returned("action", [b"Done."])], [read("before")])
        report = self.run_cli(1)
        self.assertEqual(len(report["outside_window_attempts"]), 1)
        self.assertEqual(report["windows"][0]["attempts"], [])

    def test_call_spanning_boundary_cannot_satisfy_new_window(self):
        self.prepare([boundary(), call("read"), boundary(), returned("read", [ENTRY]), call("action"), returned("action", [b"Done."])], [read("read")])
        report = self.run_cli(1)
        self.assertEqual(report["windows"][0]["attempts"][0]["ordering"], "CROSSES_BOUNDARY")
        self.assertFalse(report["windows"][1]["requirements"][0]["satisfied_before_action"])

    def test_utf8_byte_ranges_and_unchanged_inputs(self):
        self.files["entry"] = "Recover café 🥔.\n".encode()
        self.prepare([boundary(), call("read"), returned("read", [self.files["entry"]]), call("action"), returned("action", [b"Done."])], [read("read")])
        before = {p.name: p.read_bytes() for p in self.directory.iterdir()}
        first = self.run_cli(0)
        second = self.run_cli(0)
        self.assertEqual(first, second)
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.directory.iterdir()})

    def test_unsupported_output_cannot_pass(self):
        self.basic()
        self.rows[2]["payload"]["output"][1] = {"type": "image", "data": "sample"}
        self.rebind()
        self.assertEqual(self.run_cli(2)["windows"][0]["attempts"][0]["transport"], "UNVERIFIED")

    def test_malformed_inner_envelope_is_retained_as_unverified(self):
        self.basic()
        self.rows[2]["payload"]["output"][1]["text"] = '{"exit_code":0,"output":'
        self.rebind()
        self.run_cli(2)

    def test_supplied_boundary_cannot_hide_call_start(self):
        self.basic()
        self.manifest["boundaries"][0].update(row=2, row_sha256=self.manifest["calls"][0]["row_sha256"], kind="supplied_context_summary")
        self.rows[0]["type"] = "event_msg"
        self.rebind()
        self.assertEqual(self.run_cli(2)["errors"][0]["code"], "summary_boundary_not_user_message")


if __name__ == "__main__":
    unittest.main()
