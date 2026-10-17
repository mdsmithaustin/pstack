#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import unittest


CLI = Path(__file__).resolve().parents[1] / "skills/show-me-your-work/scripts/evidence.py"


class EvidenceCapture(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="pstack-evidence-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.store = self.root / "persistent" / "evidence"
        self.source = self.root / "disposable-checkout"
        self.source.mkdir()
        self.file = self.source / "report.dat"
        self.file.write_bytes(b"saved\x00\xff\n")

    def cli(self, *args):
        return subprocess.run([sys.executable, str(CLI), *map(str, args)],
                              capture_output=True, cwd=self.root, check=False)

    def capture_file(self, capture_id="saved", *extra):
        result = self.cli("file", "--store", self.store, "--id", capture_id,
                          "--source", self.file, *extra)
        self.assertEqual(result.returncode, 0, result.stderr)
        manifest = self.store / capture_id / "manifest.json"
        self.assertEqual(result.stdout, (str(manifest) + "\n").encode())
        return manifest

    def record(self, manifest):
        return json.loads((manifest.parent / "record.json").read_bytes())

    def verified(self, manifest):
        result = self.cli("verify", manifest)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def refused(self, result):
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, b"")
        self.assertIn(b"evidence:", result.stderr)

    def rewrite_record(self, manifest, record):
        data = (json.dumps(record) + "\n").encode()
        (manifest.parent / "record.json").write_bytes(data)
        envelope = json.loads(manifest.read_bytes())
        envelope["record"]["byte_length"] = len(data)
        envelope["record"]["sha256"] = hashlib.sha256(data).hexdigest()
        manifest.write_text(json.dumps(envelope))

    def identity_request(self, **extra):
        request = {"requested": {"harness": "fixture", "model": "configured-model", "effort": "high"},
                   "resolutionContext": {"workModel": None, "resolvedArm": {
                       "role": "feature", "arm": 1, "model": "configured-model", "effort": "high"}}}
        request.update(extra)
        path = self.root / "identity-request.json"
        path.write_text(json.dumps(request))
        return path, request

    def test_command_preserves_binary_streams_nonzero_argv_and_cwd(self):
        program = "import json, os, sys; open('child-report.json', 'w').write(json.dumps({'cwd': os.getcwd(), 'argument': sys.argv[1]})); sys.stdout.buffer.write(b'out\\x00'); sys.stderr.buffer.write(b'err\\xff'); sys.exit(7)"
        argv = [sys.executable, "-c", program, "literal;$(not-a-shell)"]
        result = self.cli("command", "--store", self.store, "--id", "nonzero", "--cwd", self.source, "--", *argv)
        self.assertEqual(result.returncode, 0, result.stderr)
        manifest = self.store / "nonzero" / "manifest.json"
        self.assertEqual(result.stdout, (str(manifest) + "\n").encode())
        record = self.verified(manifest)
        self.assertEqual(record["captured"]["kind"], "command")
        execution = record["captured"]["execution"]
        self.assertEqual(execution["raw_returncode"], 7)
        self.assertEqual(execution["argv"], argv)
        self.assertEqual(execution["cwd"], str(self.source))
        self.assertEqual(json.loads((self.source / "child-report.json").read_bytes()),
                         {"cwd": str(self.source), "argument": "literal;$(not-a-shell)"})
        self.assertEqual((manifest.parent / "stdout.bin").read_bytes(), b"out\x00")
        self.assertEqual((manifest.parent / "stderr.bin").read_bytes(), b"err\xff")

    def test_command_preserves_signal_returncode(self):
        result = self.cli("command", "--store", self.store, "--id", "signal", "--cwd", self.source,
                          "--", sys.executable, "-c", "import os, signal; os.kill(os.getpid(), signal.SIGTERM)")
        self.assertEqual(result.returncode, 0, result.stderr)
        record = self.verified(self.store / "signal" / "manifest.json")
        self.assertEqual(record["captured"]["execution"]["raw_returncode"], -signal.SIGTERM)

    def test_import_survives_deleted_source_and_has_no_execution(self):
        manifest = self.capture_file()
        shutil.rmtree(self.source)
        record = self.verified(manifest)
        self.assertEqual(record["captured"]["kind"], "imported-file")
        self.assertEqual(set(record["captured"]), {"kind", "source", "saved_file"})
        self.assertEqual(record["captured"]["source"]["original_path"], str(self.file))
        self.assertEqual((manifest.parent / "source.bin").read_bytes(), b"saved\x00\xff\n")

    def test_import_does_not_execute_file(self):
        marker = self.root / "executed"
        self.file.write_text(f"#!/bin/sh\ntouch '{marker}'\n")
        self.file.chmod(0o700)
        manifest = self.capture_file()
        self.assertEqual(self.verified(manifest)["captured"]["kind"], "imported-file")
        self.assertFalse(marker.exists())

    def test_empty_payload_is_valid(self):
        self.file.write_bytes(b"")
        manifest = self.capture_file()
        self.assertEqual((manifest.parent / "source.bin").read_bytes(), b"")
        self.assertEqual(self.verified(manifest)["captured"]["saved_file"], "source.bin")

    def test_duplicate_completed_id_preserves_all_bytes_and_starts_no_child(self):
        manifest = self.capture_file()
        before = {path.name: path.read_bytes() for path in manifest.parent.iterdir()}
        marker = self.root / "child-started"
        result = self.cli("command", "--store", self.store, "--id", "saved", "--cwd", self.source,
                          "--", sys.executable, "-c", f"open({str(marker)!r}, 'w').write('started')")
        self.refused(result)
        self.assertEqual({path.name: path.read_bytes() for path in manifest.parent.iterdir()}, before)
        self.assertFalse(marker.exists())

    def test_incomplete_id_is_preserved_and_starts_no_child(self):
        occupied = self.store / "incomplete"
        occupied.mkdir(parents=True)
        (occupied / "partial").write_bytes(b"prior bytes")
        marker = self.root / "child-started"
        result = self.cli("command", "--store", self.store, "--id", "incomplete", "--cwd", self.source,
                          "--", sys.executable, "-c", f"open({str(marker)!r}, 'w').write('started')")
        self.refused(result)
        self.refused(self.cli("verify", occupied / "manifest.json"))
        self.assertEqual((occupied / "partial").read_bytes(), b"prior bytes")
        self.assertFalse(marker.exists())

    def test_exec_failure_leaves_incomplete_capture(self):
        result = self.cli("command", "--store", self.store, "--id", "missing", "--cwd", self.source,
                          "--", str(self.root / "absent-program"))
        self.refused(result)
        self.assertTrue((self.store / "missing").is_dir())
        self.assertFalse((self.store / "missing" / "manifest.json").exists())

    def test_modified_removed_and_symlink_payloads_fail(self):
        for index, operation in enumerate(("modify", "remove", "symlink")):
            with self.subTest(operation=operation):
                manifest = self.capture_file(f"tamper-{index}")
                payload = manifest.parent / "source.bin"
                if operation == "modify":
                    payload.write_bytes(b"tampered")
                else:
                    payload.unlink()
                    if operation == "symlink":
                        payload.symlink_to(self.file)
                self.refused(self.cli("verify", manifest))

    def test_metadata_tamper_fails_unchanged_envelope(self):
        manifest = self.capture_file()
        path = manifest.parent / "record.json"
        path.write_bytes(path.read_bytes().replace(b"imported-file", b"tampered-file"))
        self.refused(self.cli("verify", manifest))

    def test_manifest_paths_duplicate_payloads_and_versions_are_rejected(self):
        for index, mutation in enumerate(("traversal", "absolute", "duplicate", "version", "length", "digest")):
            with self.subTest(mutation=mutation):
                manifest = self.capture_file(f"schema-{index}")
                data = json.loads(manifest.read_bytes())
                if mutation == "traversal":
                    data["payloads"][0]["path"] = "../report.dat"
                elif mutation == "absolute":
                    data["payloads"][0]["path"] = str(self.file)
                elif mutation == "duplicate":
                    data["payloads"].append(data["payloads"][0])
                elif mutation == "version":
                    data["version"] = 2
                elif mutation == "length":
                    data["payloads"][0]["byte_length"] = True
                else:
                    data["payloads"][0]["sha256"] = "invalid"
                manifest.write_text(json.dumps(data))
                self.refused(self.cli("verify", manifest))

    def test_record_schema_rejects_execution_on_import_and_missing_metadata(self):
        for index, mutation in enumerate(("execution", "missing", "time", "provider")):
            manifest = self.capture_file(f"record-{index}")
            record = self.record(manifest)
            if mutation == "execution":
                record["captured"]["execution"] = {"raw_returncode": 0}
            elif mutation == "missing":
                del record["identity"]
            elif mutation == "time":
                record["captured"]["source"]["captured_at"] = "yesterday"
            else:
                record["identity"]["provider_execution"] = "verified"
            self.rewrite_record(manifest, record)
            self.refused(self.cli("verify", manifest))

    def test_duplicate_json_keys_are_rejected(self):
        manifest = self.capture_file()
        data = manifest.read_bytes()
        manifest.write_bytes(data.replace(b'"version": 1', b'"version": 1, "version": 1', 1))
        self.refused(self.cli("verify", manifest))

    def test_configured_identity_is_retained_without_observation_promotion(self):
        request, data = self.identity_request()
        manifest = self.capture_file("configured", "--identity", request)
        identity = self.verified(manifest)["identity"]
        self.assertEqual(identity["requested"], data["requested"])
        self.assertEqual(identity["resolutionContext"], data["resolutionContext"])
        self.assertEqual(identity["model"], {"kind": "unknown"})
        self.assertEqual(identity["effort"], {"kind": "unknown"})
        self.assertEqual(identity["provider_execution"], "unknown")

    def test_runtime_fixture_identity_uses_saved_basis_after_source_deletion(self):
        basis = self.source / "runtime-fixture.jsonl"
        basis.write_bytes(b'{"ignored": true}\n{"payload":{"model":"fixture-reported","effort":null}}\n')
        request, _ = self.identity_request(runtimeRecords=[{
            "source": str(basis), "line": 2, "modelPointer": "/payload/model", "effortPointer": "/payload/effort"}])
        manifest = self.capture_file("runtime", "--identity", request)
        shutil.rmtree(self.source)
        request.unlink()
        identity = self.verified(manifest)["identity"]
        self.assertEqual(identity["model"], {"kind": "runtime-reported", "value": "fixture-reported",
                         "basis": {"payload": "basis-0000.bin", "line": 2, "pointer": "/payload/model"}})
        self.assertEqual(identity["effort"], {"kind": "unknown"})
        self.assertEqual(identity["provider_execution"], "unknown")
        record = self.record(manifest)
        record["identity"]["model"]["value"] = "invented"
        self.rewrite_record(manifest, record)
        self.refused(self.cli("verify", manifest))

    def test_missing_runtime_field_is_unknown_and_invalid_selectors_refuse(self):
        basis = self.source / "fixture.json"
        basis.write_text('{"model":"fixture-reported","effort":4}')
        for index, selector in enumerate((
                {"modelPointer": "/absent"}, {"modelPointer": "invalid"},
                {"modelPointer": "/model~2"}, {"effortPointer": "/effort"},
                {"line": 0, "modelPointer": "/model"}, {"line": 9, "modelPointer": "/model"})):
            request, _ = self.identity_request(runtimeRecords=[{"source": str(basis), **selector}])
            result = self.cli("file", "--store", self.store, "--id", f"selector-{index}",
                              "--source", self.file, "--identity", request)
            if index == 0:
                self.assertEqual(result.returncode, 0, result.stderr)
                identity = self.verified(self.store / f"selector-{index}" / "manifest.json")["identity"]
                self.assertEqual(identity["model"], {"kind": "unknown"})
            else:
                self.refused(result)
                self.assertFalse((self.store / f"selector-{index}" / "manifest.json").exists())

    def test_multiple_nonnull_claims_for_one_runtime_field_refuse(self):
        basis = self.source / "fixture.json"
        basis.write_text('{"model":"same-fixture-value"}')
        selector = {"source": str(basis), "modelPointer": "/model"}
        request, _ = self.identity_request(runtimeRecords=[selector, selector])
        self.refused(self.cli("file", "--store", self.store, "--id", "ambiguous", "--source", self.file,
                              "--identity", request))
        self.assertFalse((self.store / "ambiguous" / "manifest.json").exists())

    def test_relative_store_invalid_ids_and_symlinks_refuse(self):
        for store, capture_id in (("relative", "id"), (self.store, "../escape"), (self.store, ".")):
            self.refused(self.cli("file", "--store", store, "--id", capture_id, "--source", self.file))
        link = self.root / "linked-source"
        link.symlink_to(self.file)
        self.refused(self.cli("file", "--store", self.store, "--id", "link", "--source", link))
        parent_link = self.root / "linked-directory"
        parent_link.symlink_to(self.source, target_is_directory=True)
        self.refused(self.cli("file", "--store", parent_link / "store", "--id", "id", "--source", self.file))
        manifest = self.capture_file()
        linked_manifest = self.root / "manifest.json"
        linked_manifest.symlink_to(manifest)
        self.refused(self.cli("verify", linked_manifest))
        record = manifest.parent / "record.json"
        saved_record = record.read_bytes()
        record.unlink()
        basis = self.root / "record-copy"
        basis.write_bytes(saved_record)
        record.symlink_to(basis)
        self.refused(self.cli("verify", manifest))

    def test_runtime_model_and_effort_pointers_bind_to_hashed_saved_bytes(self):
        basis = self.source / "fixture.json"
        basis.write_text('{"a/b":{"~key":[{"model":"fixture-model","effort":"fixture-effort"}]}}')
        request, _ = self.identity_request(runtimeRecords=[{
            "source": str(basis), "modelPointer": "/a~1b/~0key/0/model",
            "effortPointer": "/a~1b/~0key/0/effort"}])
        manifest = self.capture_file("pointers", "--identity", request)
        identity = self.verified(manifest)["identity"]
        self.assertEqual(identity["model"]["value"], "fixture-model")
        self.assertEqual(identity["effort"]["value"], "fixture-effort")
        self.assertEqual(identity["provider_execution"], "unknown")
        (manifest.parent / "basis-0000.bin").write_bytes(b'{"changed": true}')
        self.refused(self.cli("verify", manifest))

    def test_symlink_id_and_basis_are_refused_without_touching_the_target(self):
        self.store.mkdir(parents=True)
        (self.store / "occupied").symlink_to(self.source, target_is_directory=True)
        self.refused(self.cli("file", "--store", self.store, "--id", "occupied", "--source", self.file))
        self.assertEqual(self.file.read_bytes(), b"saved\x00\xff\n")
        link = self.source / "basis-link.json"
        link.symlink_to(self.file)
        request, _ = self.identity_request(runtimeRecords=[{"source": str(link), "modelPointer": "/model"}])
        self.refused(self.cli("file", "--store", self.store, "--id", "basis-link", "--source", self.file,
                              "--identity", request))
        self.assertFalse((self.store / "basis-link" / "manifest.json").exists())

    def test_empty_argv_and_relative_cwd_leave_incomplete_captures(self):
        for capture_id, cwd, argv in (("empty", self.source, []), ("relative-cwd", "relative", [sys.executable])):
            result = self.cli("command", "--store", self.store, "--id", capture_id,
                              "--cwd", cwd, "--", *argv)
            self.refused(result)
            self.assertTrue((self.store / capture_id).is_dir())
            self.assertFalse((self.store / capture_id / "manifest.json").exists())

    def test_nonregular_source_refuses_without_blocking(self):
        fifo = self.source / "fifo"
        os.mkfifo(fifo)
        self.refused(self.cli("file", "--store", self.store, "--id", "fifo", "--source", fifo))

    def test_same_id_race_has_one_winner_and_only_one_child_starts(self):
        self.store.mkdir(parents=True)
        marker = self.root / "starts"
        program = f"import os; fd=os.open({str(marker)!r}, os.O_WRONLY|os.O_CREAT|os.O_APPEND, 0o600); os.write(fd,b'started\\n'); os.close(fd); print('winner')"
        args = [sys.executable, str(CLI), "command", "--store", str(self.store), "--id", "race",
                "--cwd", str(self.source), "--", sys.executable, "-c", program]
        children = [subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE) for _ in range(2)]
        outputs = [child.communicate() for child in children]
        self.assertEqual(sorted(child.returncode for child in children), [0, 1], outputs)
        self.assertEqual(marker.read_bytes(), b"started\n")
        manifest = self.store / "race" / "manifest.json"
        self.assertEqual(self.verified(manifest)["captured"]["execution"]["raw_returncode"], 0)
        self.assertEqual((manifest.parent / "stdout.bin").read_bytes(), b"winner\n")

    def test_different_ids_complete_independently(self):
        children = []
        for capture_id in ("first", "second"):
            args = [sys.executable, str(CLI), "command", "--store", str(self.store), "--id", capture_id,
                    "--cwd", str(self.source), "--", sys.executable, "-c", f"print({capture_id!r})"]
            children.append(subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE))
        for child, capture_id in zip(children, ("first", "second")):
            stdout, stderr = child.communicate()
            self.assertEqual(child.returncode, 0, stderr)
            manifest = self.store / capture_id / "manifest.json"
            self.assertEqual(stdout, (str(manifest) + "\n").encode())
            self.assertEqual(self.verified(manifest)["capture_id"], capture_id)
            self.assertEqual((manifest.parent / "stdout.bin").read_bytes(), (capture_id + "\n").encode())


if __name__ == "__main__":
    unittest.main()
