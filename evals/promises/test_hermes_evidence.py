import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from harnesses import hermes, hermes_evidence
from test_hermes import HermesDatabase, bind_legacy, owned_directory


class HarvestCustodyRegression(unittest.TestCase):
    def setUp(self):
        self.base = owned_directory(self, "hermes-custody-")
        self.root = self.base / "run"
        self.project = self.root / "w" / "p"
        self.project.mkdir(parents=True)
        self.run = SimpleNamespace(root=self.root, project=self.project, case={"turns": ["go"]},
                                   turns=[{"session_id": "root", "exit_code": 0, "duration_s": 1}])
        hermes.profile(self.run).mkdir(parents=True)
        hermes.transcripts(self.run).mkdir()
        (self.root / "hermes.json").write_text(json.dumps({"image": "img", "cli_version": "1", "entry": None,
                                                         "preload": {}, "todo_eager": True, "todo_tools": "on"}))
        bind_legacy(self.run, self.addCleanup)

    def database(self):
        path = hermes.profile(self.run) / "state.db"
        db = HermesDatabase(path)
        db.session("root")
        db.message("root", "user", "go")
        db.message("root", "assistant", "owned native reply")
        db.done()
        return path

    def test_source_alias_is_incomplete_without_copying_outside_bytes(self):
        outside = self.base / "outside-read"
        outside.write_bytes(b"owned-outside-read-canary\n")
        (hermes.profile(self.run) / "state.db").symlink_to(outside)
        trace = hermes.harvest(self.run)
        copies = list(self.root.rglob("state.db"))
        self.assertTrue(trace.get("x_harvest_error"), trace)
        self.assertEqual([p.read_bytes() for p in copies if not p.is_symlink()], [])
        self.assertEqual(outside.read_bytes(), b"owned-outside-read-canary\n")

    def test_legacy_destination_alias_cannot_overwrite_outside_bytes(self):
        self.database()
        outside = self.base / "outside-write"
        outside.write_bytes(b"owned-outside-write-canary\n")
        (hermes.transcripts(self.run) / "state.db").symlink_to(outside)
        trace = hermes.harvest(self.run)
        self.assertEqual(outside.read_bytes(), b"owned-outside-write-canary\n")
        self.assertEqual(trace["final_reply"], "owned native reply")

    def harvest_with_arguments(self, arguments):
        path = hermes.profile(self.run) / "state.db"
        path.unlink(missing_ok=True)
        db = HermesDatabase(path)
        db.session("root")
        db.message("root", "user", "go")
        db.message("root", "assistant", "owned native reply",
                   calls=[{"id": "c1", "function": {"name": "read_file", "arguments": arguments}}])
        db.done()
        return hermes.harvest(self.run)

    def test_non_string_tool_arguments_are_retained_incomplete(self):
        for arguments in ({"path": "x"}, {}, [], 0, 1.5, False):
            with self.subTest(arguments=arguments):
                trace = self.harvest_with_arguments(arguments)
                self.assertEqual(trace.get("x_harvest_error"),
                                 "decode-failed: EvidenceRefused: invalid native tool arguments")
                self.assertEqual(trace["events"], [])
                result = self.run._hermes_evidence.private_root / "acquisitions" / trace["x_acquisition"] / "result.json"
                self.assertEqual(json.loads(result.read_text())["reason"], "decode-failed")

    def test_unrelated_type_error_during_acquisition_propagates(self):
        self.database()
        with mock.patch.object(hermes_evidence.HermesEvidence, "_read_fd", side_effect=TypeError("owned acquisition bug")):
            with self.assertRaisesRegex(TypeError, "^owned acquisition bug$"):
                hermes.harvest(self.run)

    def test_null_or_empty_tool_arguments_read_as_none(self):
        for arguments in (None, ""):
            with self.subTest(arguments=arguments):
                trace = self.harvest_with_arguments(arguments)
                self.assertEqual((trace.get("x_harvest_error"), trace["final_reply"]), (None, "owned native reply"))

    def test_missing_main_cannot_reuse_previous_acquisition(self):
        path = self.database()
        self.assertEqual(hermes.harvest(self.run)["final_reply"], "owned native reply")
        path.unlink()
        trace = hermes.harvest(self.run)
        self.assertTrue(trace.get("x_harvest_error"), trace)
        self.assertEqual(trace["events"], [])


class _OwnerFixture(unittest.TestCase):
    def setUp(self):
        import sys
        import subprocess
        from unittest import mock
        import live
        from harnesses import hermes_evidence as custody
        self.custody = custody
        self.base = owned_directory(self, "hermes-owner-")
        self.root = self.base / "run"
        self.project = self.root / "w" / "p"
        self.project.mkdir(parents=True)
        self.auth = self.base / "auth"
        self.auth.mkdir()
        (self.auth / "auth.json").write_text("{}")
        (self.auth / "config.yaml").write_text("model:\n  provider: fixture\n  default: fixture-model\n")
        case = {"id": "owned", "fixture": "p", **getattr(self, "case", {"turns": ["go", "again"]})}
        self.run = live.Run(self.root, "hermes", case, "pin", 10)
        self.script = self.base / "docker_fixture.py"
        self.script.write_text('''import json, pathlib, sys
args = json.loads(sys.argv[1])
base = pathlib.Path(__file__).parent
if args[1:3] == ["container", "ls"]:
    sys.exit(1 if (base / "unknown").exists() else 0)
if args[1] == "rm":
    sys.exit(1 if (base / "unknown").exists() else 0)
if args[1] in ("inspect", "image"):
    print("sha256:" + "a" * 64)
elif "--version" in args:
    print("Hermes fixture 1")
elif "-c" in args:
    print(json.dumps({"loaded": [args[-1]], "missing": [], "chars": 4}))
else:
    print(json.dumps({"type": "system", "session_id": "root"}))
    print("owned captured turn")
''')
        self.calls = []
        real_popen = subprocess.Popen
        def process(argv, **kwargs):
            if argv[0] != "docker":
                return real_popen(argv, **kwargs)
            self.calls.append((list(argv), kwargs["cwd"], kwargs["stdout"].name, kwargs["stderr"].name))
            return real_popen([sys.executable, str(self.script), json.dumps(argv)], **kwargs)
        for target, attr, value in ((hermes, "USER_HERMES", self.auth), (custody, "USER_HERMES", self.auth),
                                    (custody.subprocess, "Popen", process)):
            patcher = mock.patch.object(target, attr, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        hermes.prepare(self.run)
        self.owner = self.run._hermes_evidence
        self.addCleanup(self.owner.close)
        self.run.turns.append(hermes.turn(self.run, self.run.case["turns"][0], 0))

    def database(self):
        path = hermes.profile(self.run) / "state.db"
        db = HermesDatabase(path)
        db.session("root")
        db.con.execute("update sessions set cwd=?", (str(self.project),))
        db.message("root", "user", "go")
        db.message("root", "assistant", "native owned reply")
        db.done()
        return path


class NativeOwnerControls(_OwnerFixture):
    def test_native_lsp_link_survives_export_relocation_replay_and_reexport(self):
        import os
        import shutil
        self.database()
        trace = hermes.harvest(self.run)
        link = hermes.profile(self.run) / "lsp/bin/pyright-langserver"
        link.parent.mkdir(parents=True)
        target = b"../lib/node_modules/pyright/langserver.js"
        os.symlink(target, os.fsencode(link))
        pair = self.owner.retain_pair(self.custody.OwnedExport(self.base / "link-pair"))
        member = "run/" + str(link.relative_to(self.root))
        self.assertEqual(os.readlink(os.fsencode(pair.root / member)), target)
        moved = self.base / "moved-link-pair"
        shutil.copytree(pair.root, moved, symlinks=True)
        self.assertEqual(os.readlink(os.fsencode(moved / member)), target)
        self.root.rename(self.base / "preserved-link-run")
        self.owner.private_root.rename(self.base / "preserved-link-evidence")
        replay = self.custody.HermesEvidence.replay(
            self.custody.ReplayBinding(moved, pair.run_id, trace["x_acquisition"]), self.base)
        self.addCleanup(replay.close)
        self.assertEqual(hermes.build_trace(replay.read())["final_reply"], "native owned reply")
        reexport = replay.retain_pair(self.custody.OwnedExport(self.base / "reexported-link-pair"))
        self.assertEqual(os.readlink(os.fsencode(reexport.root / member)), target)
        original = json.loads((pair.root / "pair.json").read_text())
        copied = json.loads((reexport.root / "pair.json").read_text())
        self.assertEqual(original["symlinks"], {member: {"target_hex": target.hex()}})
        self.assertEqual(original["symlinks"], copied["symlinks"])
        self.assertEqual(copied["acquisitions"][:len(original["acquisitions"])], original["acquisitions"])
        for name in original["members"]:
            if name == "hermes-evidence/binding.json":
                continue
            self.assertEqual((pair.root / name).read_bytes(), (reexport.root / name).read_bytes(), name)

    def test_run_link_targets_remain_opaque_bytes(self):
        import os
        import shutil
        self.database()
        trace = hermes.harvest(self.run)
        outside = self.base / "link-targets"
        outside.mkdir()
        (outside / "sentinel.txt").write_bytes(b"target contents stay outside the pair\n")
        links = hermes.profile(self.run) / "lsp/bin"
        links.mkdir(parents=True)
        targets = {
            "absolute-file": os.fsencode(outside / "sentinel.txt"),
            "absolute-dangling": os.fsencode(self.base / "missing/pyright-langserver"),
            "directory": os.fsencode(outside),
            "dangling": b"../missing/langserver.js",
            "non-utf8": b"../lib/\xff-langserver.js",
        }
        for name, target in targets.items():
            os.symlink(target, os.fsencode(links / name))
        pair = self.owner.retain_pair(self.custody.OwnedExport(self.base / "opaque-link-pair"))
        manifest = json.loads((pair.root / "pair.json").read_text())
        expected = {"run/" + str((links / name).relative_to(self.root)): target for name, target in targets.items()}
        self.assertEqual(manifest["symlinks"], {member: {"target_hex": target.hex()} for member, target in expected.items()})
        self.assertFalse(any(member.startswith(link + "/") for member in manifest["members"] for link in expected))
        self.assertTrue(all(set(receipt) == {"size", "sha256"} for receipt in manifest["members"].values()))
        moved = self.base / "moved-opaque-link-pair"
        shutil.copytree(pair.root, moved, symlinks=True)
        self.root.rename(self.base / "preserved-opaque-run")
        self.owner.private_root.rename(self.base / "preserved-opaque-evidence")
        replay = self.custody.HermesEvidence.replay(
            self.custody.ReplayBinding(moved, pair.run_id, trace["x_acquisition"]), self.base)
        self.addCleanup(replay.close)
        self.assertEqual(hermes.build_trace(replay.read())["final_reply"], "native owned reply")
        reexport = replay.retain_pair(self.custody.OwnedExport(self.base / "reexported-opaque-link-pair"))
        for root in (pair.root, moved, reexport.root):
            for member, target in expected.items():
                self.assertEqual(os.readlink(os.fsencode(root / member)), target)
        self.assertEqual((outside / "sentinel.txt").read_bytes(), b"target contents stay outside the pair\n")

    def test_changed_run_link_target_refuses_replay(self):
        import os
        self.database()
        trace = hermes.harvest(self.run)
        link = hermes.profile(self.run) / "lsp/bin/pyright-langserver"
        link.parent.mkdir(parents=True)
        link.symlink_to("../lib/pyright.js")
        pair = self.owner.retain_pair(self.custody.OwnedExport(self.base / "changed-link-pair"))
        saved = pair.root / "run" / link.relative_to(self.root)
        saved.rename(self.base / "preserved-link")
        os.symlink(b"../lib/changed.js", os.fsencode(saved))
        replay = self.custody.HermesEvidence.replay(
            self.custody.ReplayBinding(pair.root, pair.run_id, trace["x_acquisition"]), self.base)
        self.addCleanup(replay.close)
        self.assertIn("pair symlink catalog mismatch", hermes.build_trace(replay.read())["x_harvest_error"])

    def test_literal_regex_end_anchors_do_not_make_harvest_unavailable(self):
        from test_hermes import tool_call
        (self.project / "note.txt").write_text("note")
        (self.project / "src").mkdir()
        (self.project / "src" / "a.py").write_text("def example():\n    pass\n")
        db = HermesDatabase(hermes.profile(self.run) / "state.db")
        db.session("root")
        db.con.execute("update sessions set cwd=?", (str(self.project),))
        db.message("root", "user", "inspect source")
        for index, command in enumerate((r'grep -n "\.py$" note.txt', r'ls src | grep "\.py$"',
                                         'grep -E "^def .*:$" src/a.py')):
            call_id = f"read-{index}"
            db.message("root", "assistant", calls=[tool_call(call_id, "terminal", command=command)])
            db.message("root", "tool", '{"exit_code":0}', call_id=call_id, tool_name="terminal")
        db.message("root", "assistant", "inspected source")
        db.done()
        trace = hermes.harvest(self.run)
        self.assertNotIn("x_harvest_error", trace, trace.get("x_harvest_error"))
        self.assertEqual(trace["files_read"], [str(self.project / "note.txt"), str(self.project / "src" / "a.py")])
        self.assertEqual(len(trace["events"]), 8)
        self.assertEqual(trace["final_reply"], "inspected source")

    def test_attempt_setup_and_export_publication_errors_release_handles(self):
        import os
        from unittest import mock
        self.database()
        baseline = len(os.listdir("/dev/fd"))
        mkdir = self.owner._mkdir
        def fail_work(parent, name):
            directory = mkdir(parent, name)
            if name == "work":
                raise OSError("owned attempt setup failure")
            return directory
        with mock.patch.object(self.owner, "_mkdir", fail_work), self.assertRaisesRegex(OSError, "owned attempt setup failure"):
            self.owner.read()
        self.assertEqual(len(os.listdir("/dev/fd")), baseline)
        self.assertEqual(hermes.harvest(self.run)["final_reply"], "native owned reply")
        write = self.owner._write
        def fail_manifest(directory, name, data):
            if name == "pair.json":
                raise OSError("owned manifest publication failure")
            return write(directory, name, data)
        destination = self.base / "failed-pair"
        with mock.patch.object(self.owner, "_write", fail_manifest), self.assertRaisesRegex(self.custody.RetentionUnavailable, "owned manifest publication failure"):
            self.owner.retain_pair(self.custody.OwnedExport(destination))
        self.assertFalse((destination / "pair.json").exists())
        self.assertEqual(len(os.listdir("/dev/fd")), baseline)
        self.assertEqual(hermes.harvest(self.run)["final_reply"], "native owned reply")

    def test_replaced_descendant_between_scan_and_copy_refuses_export(self):
        import os
        from unittest import mock
        self.database()
        directory = self.project / "bucket"
        directory.mkdir()
        (directory / "note.txt").write_text("owned descendant marker")
        hermes.harvest(self.run)
        baseline = len(os.listdir("/dev/fd"))
        read = self.owner._member_bytes
        changed = False
        def replace(root, parts, *args):
            nonlocal changed
            if root is self.owner._root and parts == ("w", "p", "bucket", "note.txt") and not changed:
                changed = True
                directory.rename(self.base / "preserved-bucket")
                directory.mkdir()
                (directory / "note.txt").write_text("owned descendant marker")
            return read(root, parts, *args)
        destination = self.base / "replaced-pair"
        with mock.patch.object(self.owner, "_member_bytes", replace), self.assertRaisesRegex(self.custody.RetentionUnavailable, "observed directory replaced"):
            self.owner.retain_pair(self.custody.OwnedExport(destination))
        self.assertFalse((destination / "pair.json").exists())
        self.assertEqual(len(os.listdir("/dev/fd")), baseline)
        self.assertEqual((self.base / "preserved-bucket/note.txt").read_text(), "owned descendant marker")
        self.assertEqual(hermes.harvest(self.run)["final_reply"], "native owned reply")

    def test_wide_fixture_reads_exports_and_replays_at_256_descriptors(self):
        import os
        import resource
        self.database()
        for index in range(300):
            directory = self.project / f"part-{index:03d}"
            directory.mkdir()
            (directory / "note.txt").write_text("owned width marker")
        baseline = len(os.listdir("/dev/fd"))
        soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
        resource.setrlimit(resource.RLIMIT_NOFILE, (256, hard))
        try:
            for index in range(2):
                trace = hermes.harvest(self.run)
                self.assertEqual(trace["final_reply"], "native owned reply")
                self.assertNotIn("x_harvest_error", trace)
                self.assertEqual(len(os.listdir("/dev/fd")), baseline)
                pair = self.owner.retain_pair(self.custody.OwnedExport(self.base / f"wide-pair-{index}"))
                self.assertEqual((pair.root / "run/w/p/part-299/note.txt").read_text(), "owned width marker")
                self.assertEqual(len(os.listdir("/dev/fd")), baseline)
                replay = self.custody.HermesEvidence.replay(
                    self.custody.ReplayBinding(pair.root, pair.run_id, trace["x_acquisition"]), self.base)
                try:
                    self.assertEqual(hermes.build_trace(replay.read())["final_reply"], "native owned reply")
                finally:
                    replay.close()
                self.assertEqual(len(os.listdir("/dev/fd")), baseline)
        finally:
            resource.setrlimit(resource.RLIMIT_NOFILE, (soft, hard))

    def test_descendant_handles_close_after_depth_refusal_and_decode_error(self):
        import os
        from unittest import mock
        self.database()
        directory = self.project
        for _ in range(64):
            directory /= "d"
            directory.mkdir()
        (directory / "note.txt").write_text("owned depth marker")
        baseline = len(os.listdir("/dev/fd"))
        self.assertEqual(hermes.harvest(self.run)["final_reply"], "native owned reply")
        self.assertEqual(len(os.listdir("/dev/fd")), baseline)
        (directory / "too-deep").mkdir()
        trace = hermes.harvest(self.run)
        self.assertIn("resource-limit", trace["x_harvest_error"])
        self.assertEqual(len(os.listdir("/dev/fd")), baseline)
        with mock.patch.object(self.owner, "_decode", side_effect=ValueError("owned decode failure")):
            self.assertIn("owned decode failure", hermes.harvest(self.run)["x_harvest_error"])
        self.assertEqual(len(os.listdir("/dev/fd")), baseline)
        self.owner.close()
        self.owner.close()

    def test_restarted_wal_keeps_stale_tail_and_committed_reply(self):
        import sqlite3
        from test_hermes import SESSION_COLUMNS, MESSAGE_COLUMNS
        path = hermes.profile(self.run) / "state.db"
        con = sqlite3.connect(path)
        self.addCleanup(con.close)
        con.execute("pragma page_size=512")
        self.assertEqual(con.execute("pragma journal_mode=wal").fetchone(), ("wal",))
        con.execute("pragma wal_autocheckpoint=0")
        con.execute(f"create table sessions ({SESSION_COLUMNS})")
        con.execute(f"create table messages ({MESSAGE_COLUMNS})")
        con.execute("insert into sessions values ('root',null,'{}',1,'fixture',?,0,0,0,0)", (str(self.project),))
        con.executemany("insert into messages(session_id,role,content) values ('root','assistant',?)", [("x" * 400,)] * 40)
        con.commit()
        wal_path = path.with_name("state.db-wal")
        old = wal_path.read_bytes()
        self.assertEqual(con.execute("pragma wal_checkpoint(restart)").fetchone()[0], 0)
        con.execute("update messages set content='fresh' where id=40")
        con.commit()
        main, wal = path.read_bytes(), wal_path.read_bytes()
        self.assertEqual(len(wal), len(old))
        self.assertNotEqual(wal[16:24], old[16:24])
        control = self.base / "sqlite-control.db"
        control.write_bytes(main)
        control.with_name("sqlite-control.db-wal").write_bytes(wal)
        with sqlite3.connect(control) as reader:
            self.assertEqual(reader.execute("select count(*), (select content from messages where id=40) from messages").fetchone(), (40, "fresh"))
            self.assertEqual(reader.execute("pragma quick_check").fetchall(), [("ok",)])
        reader.close()
        trace = hermes.harvest(self.run)
        self.assertEqual(trace["final_reply"], "fresh")
        self.assertNotIn("x_harvest_error", trace)
        raw = self.owner.private_root / "acquisitions" / trace["x_acquisition"] / "raw"
        self.assertEqual((raw / "state.db").read_bytes(), main)
        self.assertEqual((raw / "state.db-wal").read_bytes(), wal)
        pair = self.owner.retain_pair(self.custody.OwnedExport(self.base / "tail-pair"))
        self.assertEqual((pair.root / "hermes-evidence/acquisitions" / trace["x_acquisition"] / "raw/state.db-wal").read_bytes(), wal)
        corrupted = bytearray(wal)
        corrupted[56] ^= 1
        with self.assertRaisesRegex(self.custody.EvidenceRefused, "frame checksum"):
            self.owner._validate_wal(main, bytes(corrupted))
        with self.assertRaisesRegex(self.custody.EvidenceRefused, "frame length"):
            self.owner._validate_wal(main, wal[:-1])
        foreign_first = bytearray(wal)
        foreign_first[40:48] = old[16:24]
        with self.assertRaisesRegex(self.custody.EvidenceRefused, "no committed prefix"):
            self.owner._validate_wal(main, bytes(foreign_first))
        mixed_tail = bytearray(wal)
        mixed_tail[-512 - 16:-512 - 8] = wal[16:24]
        with self.assertRaisesRegex(self.custody.EvidenceRefused, "mixes generations"):
            self.owner._validate_wal(main, bytes(mixed_tail))

    def test_private_captures_and_first_resume_survive_mutable_legacy_records(self):
        outside = self.base / "outside"
        outside.write_text("owned canary")
        (self.root / "transcripts").mkdir()
        (self.root / "transcripts" / "turn-1.stream.jsonl").symlink_to(outside)
        (self.root / "hermes.json").symlink_to(outside)
        self.run.turns[0]["session_id"] = "poison"
        self.run.turns[0]["hermes_argv"].append("poison")
        second = hermes.turn(self.run, "again", 1)
        self.assertEqual(second["hermes_argv"][-2:], ["--resume", "root"])
        self.run.turns.append(second)
        self.database()
        trace = hermes.harvest(self.run)
        self.assertEqual(trace["final_reply"], "native owned reply")
        self.assertEqual(trace["x_session_ids"], ["root"])
        self.assertNotIn("poison", trace["argv"])
        self.assertEqual(outside.read_text(), "owned canary")
        self.assertEqual([str(call[1]) for call in self.calls], [str(self.owner.private_root)] * len(self.calls))
        self.assertTrue(all(isinstance(call[2], int) and isinstance(call[3], int) for call in self.calls))
        self.assertEqual([w.disposition for w in self.owner._writers], ["removed"] * 3)
        self.assertEqual(Path(second["stream"]).read_text(), '{"type": "system", "session_id": "root"}\nowned captured turn\n')

    def test_unknown_writer_blocks_read_and_later_turn(self):
        from unittest import mock
        self.database()
        (self.base / "unknown").touch()
        with self.assertRaisesRegex(self.custody.EvidenceRefused, "unknown termination"):
            hermes.turn(self.run, "again", 1)
        with mock.patch.object(self.owner, "_open", side_effect=AssertionError("native evidence opened")):
            trace = hermes.harvest(self.run)
        self.assertIn("termination-unknown", trace["x_harvest_error"])
        with self.assertRaisesRegex(self.custody.EvidenceRefused, "unknown termination"):
            hermes.turn(self.run, "again", 1)
        self.assertEqual(self.owner._writers[-1].disposition, "unknown")

    def test_replaced_prepared_config_blocks_resume(self):
        config = hermes.profile(self.run) / "config.yaml"
        config.rename(config.with_name("old-config"))
        config.write_text("replaced")
        with self.assertRaisesRegex(self.custody.EvidenceRefused, "prepared entry replaced"):
            hermes.turn(self.run, "again", 1)
        self.assertIn("identity-changed", hermes.harvest(self.run)["x_harvest_error"])

    def test_special_alias_and_parent_replacement_refuse_before_content_open(self):
        import os
        import socket
        from unittest import mock
        path = hermes.profile(self.run) / "state.db"
        outside = self.base / "outside"
        outside.write_bytes(b"outside native canary")
        for kind in ("symlink", "hardlink", "fifo", "socket"):
            with self.subTest(kind=kind):
                sock = None
                if kind == "symlink":
                    path.symlink_to(outside)
                elif kind == "hardlink":
                    os.link(outside, path)
                elif kind == "fifo":
                    os.mkfifo(path)
                else:
                    sock = socket.socket(socket.AF_UNIX)
                    previous = os.open(".", os.O_RDONLY | os.O_DIRECTORY)
                    try:
                        os.chdir(path.parent)
                        sock.bind(path.name)
                    finally:
                        os.fchdir(previous)
                        os.close(previous)
                opened = []
                real_open = os.open
                def record_open(name, flags, *args, **kwargs):
                    opened.append(name)
                    return real_open(name, flags, *args, **kwargs)
                with mock.patch.object(self.custody.os, "open", record_open):
                    trace = hermes.harvest(self.run)
                self.assertIn("path-refused", trace["x_harvest_error"])
                self.assertNotIn("state.db", opened)
                self.assertEqual(outside.read_bytes(), b"outside native canary")
                if sock:
                    sock.close()
                path.unlink()
        home = hermes.profile(self.run)
        home.rename(home.with_name("preserved-profile"))
        home.symlink_to(home.with_name("preserved-profile"), target_is_directory=True)
        self.assertIn("identity-changed", hermes.harvest(self.run)["x_harvest_error"])

    def test_wal_only_commit_survives_fresh_raw_and_work_copies(self):
        import hashlib
        import sqlite3
        import subprocess
        import sys
        from test_hermes import SESSION_COLUMNS, MESSAGE_COLUMNS
        path = hermes.profile(self.run) / "state.db"
        script = '''import os, sqlite3, sys
con=sqlite3.connect(sys.argv[1])
con.execute("pragma journal_mode=wal")
con.execute("pragma wal_autocheckpoint=0")
con.execute("create table sessions ("+sys.argv[2]+")")
con.execute("create table messages ("+sys.argv[3]+")")
con.execute("insert into sessions values ('root',null,'{}',1,'fixture',?,0,0,0,0)",(sys.argv[4],))
con.execute("insert into messages values (1,'root','user','go',null,null,null)")
con.commit()
con.execute("pragma wal_checkpoint(truncate)")
con.execute("insert into messages values (2,'root','assistant','committed only in WAL',null,null,null)")
con.commit()
os._exit(0)
'''
        # The fixture process exits without SQLite close so the committed row remains in WAL.
        subprocess.run([sys.executable, "-c", script, str(path), SESSION_COLUMNS, MESSAGE_COLUMNS, str(self.project)],
                              check=True, capture_output=True)
        before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in path.parent.glob("state.db*")}
        main_only = self.base / "main-only.db"
        main_only.write_bytes(path.read_bytes())
        with sqlite3.connect(main_only) as con:
            self.assertEqual(con.execute("select content from messages order by id").fetchall(), [("go",)])
        con.close()
        trace = hermes.harvest(self.run)
        self.assertEqual(trace["final_reply"], "committed only in WAL")
        after = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in path.parent.glob("state.db*")}
        self.assertEqual(before, after)
        raw = self.owner.private_root / "acquisitions" / trace["x_acquisition"] / "raw"
        self.assertEqual({p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in raw.iterdir()}, before)
        for member in ("state.db-wal", "state.db-shm"):
            (path.parent / member).rename(self.base / (member + ".preserved"))
        second = hermes.harvest(self.run)
        self.assertEqual(second["final_reply"], "")
        receipt = json.loads((self.owner.private_root / "acquisitions" / second["x_acquisition"] / "database.json").read_text())
        self.assertEqual(receipt["wal"], {"member": "state.db-wal"})
        self.assertEqual(receipt["shm"], {"member": "state.db-shm"})
        self.assertNotEqual(second["x_acquisition"], trace["x_acquisition"])
        self.assertEqual({p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in raw.iterdir()}, before)

    def test_all_attempts_relocate_and_missing_old_member_refuses(self):
        import shutil
        self.database()
        first = hermes.harvest(self.run)
        second = hermes.harvest(self.run)
        path = hermes.profile(self.run) / "state.db"
        path.rename(path.with_name("preserved-state.db"))
        third = hermes.harvest(self.run)
        self.assertIn("missing-state", third["x_harvest_error"])
        (self.root / "verdict.json").write_bytes(b'{"original":"unchanged"}\n')
        pair = self.owner.retain_pair(self.custody.OwnedExport(self.base / "pair"))
        manifest = json.loads((pair.root / "pair.json").read_text())
        self.assertNotIn("symlinks", manifest)
        self.assertEqual(manifest["acquisitions"], [first["x_acquisition"], second["x_acquisition"], third["x_acquisition"]])
        self.assertIn("run/verdict.json", manifest["members"])
        self.assertTrue(any(k.startswith("hermes-evidence/captures/") for k in manifest["members"]))
        moved = self.base / "moved"
        shutil.copytree(pair.root, moved)
        self.root.rename(self.base / "preserved-original-run")
        self.owner.private_root.rename(self.base / "preserved-original-evidence")
        replay = self.custody.HermesEvidence.replay(self.custody.ReplayBinding(moved, pair.run_id, second["x_acquisition"]), self.base)
        self.addCleanup(replay.close)
        actual = hermes.build_trace(replay.read())
        self.assertEqual(actual["final_reply"], "native owned reply")
        self.assertEqual(actual["x_provenance"], "pair-offline")
        reexport = replay.retain_pair(self.custody.OwnedExport(self.base / "reexport"))
        reexported = self.custody.HermesEvidence.replay(
            self.custody.ReplayBinding(reexport.root, pair.run_id, second["x_acquisition"]), self.base)
        self.addCleanup(reexported.close)
        self.assertEqual(hermes.build_trace(reexported.read())["final_reply"], "native owned reply")
        self.assertEqual((moved / "run/verdict.json").read_bytes(), b'{"original":"unchanged"}\n')
        old = moved / "hermes-evidence/acquisitions" / first["x_acquisition"] / "raw/state.db"
        old.rename(self.base / "preserved-catalog-member")
        incomplete = self.custody.HermesEvidence.replay(self.custody.ReplayBinding(moved, pair.run_id, second["x_acquisition"]), self.base)
        self.addCleanup(incomplete.close)
        self.assertIn("pair-incomplete", hermes.build_trace(incomplete.read())["x_harvest_error"])


class AcquisitionReplayControls(_OwnerFixture):
    case = {"entry": "how", "turns": ["first", "/how prepared second"]}

    def setUp(self):
        import itertools
        from unittest import mock
        from harnesses import hermes_evidence as custody
        clock = mock.patch.object(custody, "time", SimpleNamespace(monotonic=lambda: next(self.ticks)))
        self.ticks = itertools.count(0, 2)
        clock.start()
        self.addCleanup(clock.stop)
        super().setUp()

    def temporal_pair(self):
        import itertools
        import shutil
        from test_hermes import tool_call
        self.note = str(self.project / "note.txt")
        (self.project / "note.txt").write_text("first note")
        db = HermesDatabase(hermes.profile(self.run) / "state.db")
        db.con.execute("pragma journal_mode=wal")
        db.con.execute("pragma wal_autocheckpoint=0")
        db.session("root")
        db.session("kid", parent="root", started=1, model="child-model")
        db.con.execute("update sessions set cwd=?", (str(self.project),))
        db.message("root", "user", "first")
        db.message("root", "assistant", calls=[tool_call("read-1", "terminal", command="cat note.txt")])
        db.message("root", "tool", '{"exit_code":0}', call_id="read-1", tool_name="terminal")
        db.message("root", "assistant", calls=[tool_call("todo-1", "todo_list", todos=[{"content": "inspect", "status": "completed"}])])
        db.message("root", "tool", '{"todos":[{"content":"inspect","status":"completed"}]}', call_id="todo-1", tool_name="todo_list")
        db.message("root", "assistant", calls=[tool_call("delegate-1", "delegate_task", goal="inspect child", context="poteto-agent")])
        db.message("root", "tool", '{"results":[]}', call_id="delegate-1", tool_name="delegate_task")
        db.message("kid", "user", "inspect child")
        db.message("kid", "assistant", "persona: poteto-agent\nchild reply")
        db.message("root", "assistant", "first reply")
        db.con.commit()
        self.first = hermes.harvest(self.run)
        (self.project / "note.txt").rename(self.base / "preserved-note.txt")
        (self.project / "note.txt").mkdir()
        self.ticks = itertools.count(100, 3)
        self.script.write_text(self.script.read_text() + '\nif "--resume" in args: sys.exit(7)\n')
        self.run.turns.append(hermes.turn(self.run, "/why actual second", 1))
        db.message("root", "user", "actual second")
        db.message("root", "assistant", "second reply")
        db.done()
        self.second = hermes.harvest(self.run)
        state = hermes.profile(self.run) / "state.db"
        state.rename(state.with_name("preserved-state.db"))
        self.third = hermes.harvest(self.run)
        (self.root / "verdict.json").write_bytes(b'{"original":"unchanged temporal grade"}\n')
        pair = self.owner.retain_pair(self.custody.OwnedExport(self.base / "pair"))
        self.moved = self.base / "moved"
        shutil.copytree(pair.root, self.moved)
        self.root.rename(self.base / "preserved-original-run")
        self.owner.private_root.rename(self.base / "preserved-original-evidence")
        self.run_id = pair.run_id
        return pair

    def replay(self, acquisition, pair=None):
        owner = self.custody.HermesEvidence.replay(
            self.custody.ReplayBinding(pair or self.moved, self.run_id, acquisition), self.base)
        self.addCleanup(owner.close)
        return owner

    def assert_first(self, trace):
        self.assertNotIn("x_harvest_error", trace, trace.get("x_harvest_error"))
        self.assertEqual((trace["duration_s"], trace["exit_code"]), (2.0, 0))
        self.assertEqual(trace["x_turn_argvs"], [["hermes", "chat", "-Q", "--query=first", "--format", "stream-json",
            "--reasoning", "high", "-t", "delegation,file,skills,terminal,todo", "--yolo", "--run-budget", "30", "-s", "how"]])
        self.assertEqual(trace["x_turn_entries"], [{"turn": 0, "skill": "how", "entry": "injected"}])
        self.assertEqual(trace["files_read"], [self.note])
        self.assertEqual(trace["x_path_evidence"], [{"requested": "note.txt", "cwd": str(self.project),
            "spelling": self.note, "disposition": "fixture-request", "reason": None, "kind": "regular"}])
        self.assertEqual(trace["events"], [
            {"seq": 0, "turn": 0, "kind": "user", "text": "first"},
            {"seq": 1, "turn": 0, "kind": "tool_call", "name": "terminal", "input": {"command": "cat note.txt"}, "id": "read-1"},
            {"seq": 2, "turn": 0, "kind": "tool_result", "name": "terminal", "ok": True, "output_head": '{"exit_code":0}', "id": "read-1"},
            {"seq": 3, "turn": 0, "kind": "tool_call", "name": "todo_list", "input": {"todos": [{"content": "inspect", "status": "completed"}]}, "id": "todo-1"},
            {"seq": 4, "turn": 0, "kind": "tool_result", "name": "todo_list", "ok": True, "output_head": '{"todos":[{"content":"inspect","status":"completed"}]}', "id": "todo-1"},
            {"seq": 5, "turn": 0, "kind": "tool_call", "name": "delegate_task", "input": {"goal": "inspect child", "context": "poteto-agent"}, "id": "delegate-1"},
            {"seq": 6, "turn": 0, "kind": "tool_result", "name": "delegate_task", "ok": True, "output_head": '{"results":[]}', "id": "delegate-1"},
            {"seq": 7, "turn": 0, "kind": "text", "text": "first reply"}])
        self.assertEqual(trace["worklist"], [{"seq": 4, "turn": 0, "carrier": "todo_list", "items": [{"text": "inspect", "state": "completed"}]}])
        self.assertEqual(trace["spawns"], [{"seq": 5, "turn": 0, "tool": "delegate_task", "persona": "poteto-agent",
            "model": "child-model", "effort": "high", "prompt_head": "inspect child\npoteto-agent",
            "x_child_first_reply": "persona: poteto-agent\nchild reply", "x_persona_line": "poteto-agent",
            "x_child_session": "kid", "x_child_match": "goal"}])
        self.assertEqual(trace["final_reply"], "first reply")

    def test_earlier_acquisition_keeps_its_turn_prefix_and_fixture_inventory(self):
        self.temporal_pair()
        self.assert_first(self.first)
        actual = hermes.build_trace(self.replay(self.first["x_acquisition"]).read())
        self.assert_first(actual)
        changed = {"x_acquisition", "x_provenance", "transcript_paths"}
        self.assertEqual({k: v for k, v in actual.items() if k not in changed},
                         {k: v for k, v in self.first.items() if k not in changed})

    def test_actual_entry_skill_survives_prepared_case_and_public_record_mutation(self):
        self.database()
        captured = self.owner.read()
        metadata = self.custody.thaw(captured.meta)
        metadata["cli_version"] = "poison"
        metadata["preloads"]["how"]["loaded"].clear()
        self.run.case["entry"] = "why"
        self.run.case["turns"] = ["/why poisoned", "/why wrong plan"]
        self.run.turns[0]["hermes_argv"].append("poison")
        self.assertEqual(hermes.harvest(self.run)["x_turn_entries"], [{"turn": 0, "skill": "how", "entry": "injected"}])
        self.assertEqual(hermes.build_trace(captured)["x_turn_entries"], [{"turn": 0, "skill": "how", "entry": "injected"}])
        self.assertEqual(hermes.build_trace(captured)["cli_version"], "Hermes fixture 1")

    def test_later_acquisition_uses_actual_second_skill_and_second_user_boundary(self):
        self.temporal_pair()
        actual = hermes.build_trace(self.replay(self.second["x_acquisition"]).read())
        self.assertEqual((actual["duration_s"], actual["exit_code"]), (5.0, 7))
        self.assertEqual(actual["x_turn_entries"], [{"turn": 0, "skill": "how", "entry": "injected"},
            {"turn": 1, "skill": "why", "entry": "not-observed"}])
        self.assertEqual(actual["events"][-2:], [{"seq": 8, "turn": 1, "kind": "user", "text": "actual second"},
            {"seq": 9, "turn": 1, "kind": "text", "text": "second reply"}])
        self.assertEqual(actual["x_turn_argvs"][1], ["hermes", "chat", "-Q", "--query=actual second", "--format", "stream-json",
            "--reasoning", "high", "-t", "delegation,file,skills,terminal,todo", "--yolo", "--run-budget", "30", "-s", "how", "-s", "why", "--resume", "root"])
        self.assertEqual(actual["files_read"], [])
        self.assertEqual(actual["x_path_evidence"][0]["kind"], "directory")
        self.assertEqual(actual["final_reply"], "second reply")

    def test_reexport_preserves_all_attempts_turns_and_bytes_including_wal_and_grade(self):
        import shutil
        self.temporal_pair()
        before = {str(p.relative_to(self.moved)): p.read_bytes() for p in self.moved.rglob("*") if p.is_file()}
        self.assertIn(f'hermes-evidence/acquisitions/{self.first["x_acquisition"]}/raw/state.db-wal', before)
        self.assertIn(f'hermes-evidence/acquisitions/{self.first["x_acquisition"]}/raw/state.db-shm', before)
        replay = self.replay(self.first["x_acquisition"])
        first_offline = hermes.build_trace(replay.read())
        self.assert_first(first_offline)
        pair = replay.retain_pair(self.custody.OwnedExport(self.base / "reexport"))
        after = {str(p.relative_to(pair.root)): p.read_bytes() for p in pair.root.rglob("*") if p.is_file()}
        for member, data in before.items():
            if member in ("pair.json", "hermes-evidence/binding.json"):
                prefix = "hermes-evidence/imported-pair-" if member == "pair.json" else "hermes-evidence/imported-binding-"
                self.assertIn(data, [value for name, value in after.items() if name.startswith(prefix)])
            else:
                self.assertEqual(after[member], data, member)
        self.assertEqual({str(p.relative_to(self.moved)): p.read_bytes() for p in self.moved.rglob("*") if p.is_file()}, before)
        manifest = json.loads(after["pair.json"])
        self.assertEqual(manifest["acquisitions"], [self.first["x_acquisition"], self.second["x_acquisition"],
            self.third["x_acquisition"], first_offline["x_acquisition"]])
        self.assertEqual(manifest["turn_members"], ["turn-0000.json", "turn-0001.json"])
        relocated = self.base / "reexport-moved"
        shutil.copytree(pair.root, relocated)
        self.moved.rename(self.base / "preserved-moved")
        pair.root.rename(self.base / "preserved-reexport")
        for acquisition in (self.first["x_acquisition"], first_offline["x_acquisition"]):
            self.assert_first(hermes.build_trace(self.replay(acquisition, relocated).read()))
        failed = hermes.build_trace(self.replay(self.third["x_acquisition"], relocated).read())
        self.assertIn("pair-incomplete", failed["x_harvest_error"])
        self.assertIn("missing-state", failed["x_harvest_error"])

    def test_none_positions_duplicate_skills_and_conflicting_override(self):
        self.database()
        self.run.turns.append(hermes.turn(self.run, "ordinary second", 1))
        self.run.turns.append(hermes.turn(self.run, "/how repeated", 2))
        evidence = self.owner.read()
        self.assertEqual(evidence.entry_skills, ("how", None, "how"))
        expected = [{"turn": 0, "skill": "how", "entry": "injected"}, {"turn": 2, "skill": "how", "entry": "injected"}]
        self.assertEqual(hermes.build_trace(evidence)["x_turn_entries"], expected)
        with self.assertRaisesRegex(ValueError, "entry skills disagree"):
            hermes.build_trace(evidence, ("why",))
        self.assertEqual(hermes.build_trace(evidence, ("how", None, "how"))["x_turn_entries"], expected)

    def recatalog(self, pair):
        import hashlib
        manifest = json.loads((pair / "pair.json").read_text())
        for member in manifest["members"]:
            data = (pair / member).read_bytes()
            manifest["members"][member] = {"size": len(data), "sha256": hashlib.sha256(data).hexdigest()}
        (pair / "pair.json").write_text(json.dumps(manifest))

    def test_semantic_corruption_of_selected_and_unselected_contexts_refuses(self):
        import hashlib
        import shutil
        self.temporal_pair()
        mutations = {
            "run": lambda c: c.update(run_id="other-run"),
            "acquisition": lambda c: c.update(acquisition_id="other-attempt"),
            "future-prefix": lambda c: c["turns"].append(second_context["turns"][1]),
            "reordered-prefix": lambda c: c["turns"].reverse(),
            "duplicate-index": lambda c: c["turns"][1].update(index=0),
            "entry": lambda c: c["turns"][0]["record"].update(entry_skill="why"),
            "inventory-kind": lambda c: c["inventory"]["entries"][0].update(kind="invented"),
            "inventory-duplicate": lambda c: c["inventory"]["entries"].append(c["inventory"]["entries"][0]),
            "inventory-ancestor": lambda c: c["inventory"]["entries"].append({"components": ["missing", "child"], "kind": "regular"}),
            "absent-inventory": lambda c: c.update(inventory={"kind": "not-observed"}),
            "metadata": lambda c: c["meta"].update(cli_version="invented"),
            "writer": lambda c: c["writers"][0].update(name="invented"),
            "context-version": lambda c: c.update(schema_version=9),
            "source": lambda c: c.update(observation={"kind": "replay-of", "acquisition_id": self.third["x_acquisition"]}),
        }
        first_id, second_id = self.first["x_acquisition"], self.second["x_acquisition"]
        second_context = json.loads((self.moved / f"hermes-evidence/acquisitions/{second_id}/context.json").read_text())
        for name, mutate in mutations.items():
            with self.subTest(mutation=name):
                pair = self.base / ("corrupt-" + name)
                shutil.copytree(self.moved, pair)
                target = second_id if name in ("reordered-prefix", "duplicate-index") else first_id
                context_path = pair / f"hermes-evidence/acquisitions/{target}/context.json"
                context = json.loads(context_path.read_text())
                mutate(context)
                context_path.write_text(json.dumps(context))
                result_path = context_path.with_name("result.json")
                result = json.loads(result_path.read_text())
                result["context"]["sha256"] = hashlib.sha256(context_path.read_bytes()).hexdigest()
                result_path.write_text(json.dumps(result))
                self.recatalog(pair)
                for selected in (first_id, second_id):
                    owner = self.replay(selected, pair)
                    trace = hermes.build_trace(owner.read())
                    self.assertIn("pair-incomplete", trace["x_harvest_error"])
                    self.assertEqual(trace["events"], [])
                    with self.assertRaises(self.custody.RetentionUnavailable):
                        owner.retain_pair(self.custody.OwnedExport(self.base / (name + "-blocked-" + selected)))

    def test_recataloged_result_database_and_preparation_mismatches_refuse(self):
        import shutil
        self.temporal_pair()
        aid = self.first["x_acquisition"]
        changes = [
            ("context-digest", f"acquisitions/{aid}/result.json", lambda r: r["context"].update(sha256="0" * 64)),
            ("result-id", f"acquisitions/{aid}/result.json", lambda r: r.update(id="other")),
            ("result-run", f"acquisitions/{aid}/result.json", lambda r: r.update(run_id="other")),
            ("raw-digest", f"acquisitions/{aid}/database.json", lambda r: r["main"].update(sha256="0" * 64)),
            ("duplicate-source", f"acquisitions/{aid}/result.json", lambda r: r["members"].append(r["members"][0])),
            ("preparation", "meta.json", lambda r: r.update(cli_version="invented")),
            ("writer-shape", "writer-0000.json", lambda r: 42),
        ]
        for name, member, mutate in changes:
            with self.subTest(mutation=name):
                pair = self.base / name
                shutil.copytree(self.moved, pair)
                path = pair / "hermes-evidence" / member
                value = json.loads(path.read_text())
                replacement = mutate(value)
                if replacement is not None:
                    value = replacement
                path.write_text(json.dumps(value))
                self.recatalog(pair)
                trace = hermes.build_trace(self.replay(self.second["x_acquisition"], pair).read())
                self.assertIn("pair-incomplete", trace["x_harvest_error"])

    def test_unfinished_publication_is_explicit_and_partial_corruption_blocks_export(self):
        from unittest import mock
        self.database()
        save = self.owner._save
        def fail_result(member, value):
            if member.endswith("/result.json"):
                raise OSError("controlled terminal publication failure")
            save(member, value)
        with mock.patch.object(self.owner, "_save", fail_result):
            with self.assertRaises(self.custody.RetentionUnavailable):
                self.owner.read()
        aid = self.owner._attempts[-1]
        pair = self.owner.retain_pair(self.custody.OwnedExport(self.base / "unfinished"))
        self.run_id = pair.run_id
        trace = hermes.build_trace(self.replay(aid, pair.root).read())
        self.assertIn("terminal-state-absent", trace["x_harvest_error"])
        context = self.owner.private_root / f"acquisitions/{aid}/context.json"
        before = context.read_bytes()
        context.write_bytes(b'{"partial":')
        with self.assertRaises(self.custody.RetentionUnavailable):
            self.owner.retain_pair(self.custody.OwnedExport(self.base / "corrupt-private"))
        self.assertEqual(context.read_bytes(), b'{"partial":')
        self.assertEqual((pair.root / f"hermes-evidence/acquisitions/{aid}/context.json").read_bytes(), before)

    def test_historical_decode_failure_and_unbound_v1_success_remain_incomplete_on_reexport(self):
        import hashlib
        import oracles
        import shutil
        from unittest import mock
        self.database()
        success = hermes.harvest(self.run)
        with mock.patch.object(self.owner, "_decode", side_effect=self.custody.EvidenceRefused("decode-failed", "historical decoder restriction")):
            failed = hermes.harvest(self.run)
        self.assertIn("historical decoder restriction", failed["x_harvest_error"])
        pair = self.owner.retain_pair(self.custody.OwnedExport(self.base / "historical"))
        self.run_id = pair.run_id
        legacy = self.base / "v1"
        shutil.copytree(pair.root, legacy)
        manifest = json.loads((legacy / "pair.json").read_text())
        manifest["schema_version"] = 1
        del manifest["contexts"]
        for aid in manifest["acquisitions"]:
            member = f"hermes-evidence/acquisitions/{aid}/context.json"
            (legacy / member).rename(self.base / (aid + "-preserved-context.json"))
            del manifest["members"][member]
            result_path = legacy / f"hermes-evidence/acquisitions/{aid}/result.json"
            result = json.loads(result_path.read_text())
            del result["run_id"], result["context"]
            result_path.write_text(json.dumps(result))
        (legacy / "pair.json").write_text(json.dumps(manifest))
        self.recatalog(legacy)
        before = {str(p.relative_to(legacy)): hashlib.sha256(p.read_bytes()).hexdigest() for p in legacy.rglob("*") if p.is_file()}
        for selected, expected in ((success["x_acquisition"], "context-unavailable"), (failed["x_acquisition"], "decode-failed")):
            for source in (legacy, pair.root) if selected == failed["x_acquisition"] else (legacy,):
                with self.subTest(selected=selected, source=source.name):
                    owner = self.replay(selected, source)
                    trace = hermes.build_trace(owner.read())
                    self.assertIn("pair-incomplete", trace["x_harvest_error"])
                    self.assertIn(expected, trace["x_harvest_error"])
                    self.assertEqual(trace["events"], [])
                    for promise in oracles.ORACLES:
                        self.assertEqual(oracles.check(promise, trace, {}, self.project)["verdict"], "INCONCLUSIVE")
                    if expected == "decode-failed":
                        self.assertIn("historical decoder restriction", trace["x_harvest_error"])
                    exported = owner.retain_pair(self.custody.OwnedExport(self.base / ("reexport-" + source.name + selected)))
                    again = hermes.build_trace(self.replay(selected, exported.root).read())
                    self.assertIn(expected, again["x_harvest_error"])
                    if source == legacy:
                        rewritten = json.loads((exported.root / "pair.json").read_text())
                        self.assertEqual(rewritten["contexts"][selected], {"kind": "unbound-v1"})
                        for member, digest in before.items():
                            if member not in ("pair.json", "hermes-evidence/binding.json"):
                                self.assertEqual(hashlib.sha256((exported.root / member).read_bytes()).hexdigest(), digest)
        self.assertEqual({str(p.relative_to(legacy)): hashlib.sha256(p.read_bytes()).hexdigest() for p in legacy.rglob("*") if p.is_file()}, before)

    def test_missing_unselected_context_or_raw_member_blocks_later_selection(self):
        import shutil
        self.temporal_pair()
        for name in ("context.json", "raw/state.db"):
            pair = self.base / ("missing-" + name.replace("/", "-"))
            shutil.copytree(self.moved, pair)
            member = pair / f'hermes-evidence/acquisitions/{self.first["x_acquisition"]}/{name}'
            member.rename(self.base / ("preserved-" + name.replace("/", "-")))
            trace = hermes.build_trace(self.replay(self.second["x_acquisition"], pair).read())
            self.assertIn("pair-incomplete", trace["x_harvest_error"])
        self.assert_first(hermes.build_trace(self.replay(self.first["x_acquisition"]).read()))

    def test_historical_refused_prefix_survives_a_later_regular_file(self):
        from test_hermes import tool_call
        blocked = self.project / "blocked"
        blocked.write_text("regular prefix")
        db = HermesDatabase(hermes.profile(self.run) / "state.db")
        db.session("root")
        db.con.execute("update sessions set cwd=?", (str(self.project),))
        db.message("root", "user", "first")
        db.message("root", "assistant", calls=[tool_call("refused-1", "terminal", command="cat blocked/../note.txt")])
        db.message("root", "tool", '{"exit_code":0}', call_id="refused-1", tool_name="terminal")
        db.message("root", "assistant", "refused reply")
        db.done()
        first = hermes.harvest(self.run)
        blocked.rename(self.base / "preserved-blocked")
        blocked.mkdir()
        (self.project / "note.txt").write_text("now reachable")
        later = hermes.harvest(self.run)
        self.assertEqual(later["files_read"], [str(self.project / "note.txt")])
        pair = self.owner.retain_pair(self.custody.OwnedExport(self.base / "refused-prefix"))
        self.run_id = pair.run_id
        trace = hermes.build_trace(self.replay(first["x_acquisition"], pair.root).read())
        self.assertEqual(trace["x_harvest_error"], "path-refused: recorded read crosses an unavailable fixture prefix")
        self.assertEqual(trace["x_path_evidence"], [{"requested": "blocked/../note.txt", "cwd": str(self.project),
            "spelling": None, "disposition": "unavailable", "reason": "unavailable-prefix", "kind": "unavailable-prefix"}])
        self.assertEqual(trace["events"][1]["id"], "refused-1")
        self.assertEqual(trace["final_reply"], "refused reply")

    def test_failed_partial_capture_and_context_absence_retain_available_members(self):
        from unittest import mock
        self.database()
        write = self.owner._write
        def fail_work(directory, name, data):
            if directory.path.name == "work" and name == "state.db":
                raise OSError("controlled work-copy refusal")
            write(directory, name, data)
        with mock.patch.object(self.owner, "_write", fail_work):
            partial = hermes.harvest(self.run)
        self.assertIn("controlled work-copy refusal", partial["x_harvest_error"])
        save = self.owner._save
        def fail_context(member, value):
            if member.endswith("/context.json"):
                raise OSError("controlled context publication failure")
            save(member, value)
        with mock.patch.object(self.owner, "_save", fail_context):
            with self.assertRaises(self.custody.RetentionUnavailable):
                self.owner.read()
        unfinished = self.owner._attempts[-1]
        pair = self.owner.retain_pair(self.custody.OwnedExport(self.base / "partial"))
        self.run_id = pair.run_id
        manifest = json.loads((pair.root / "pair.json").read_text())
        self.assertEqual(manifest["contexts"][unfinished], {"kind": "unfinished"})
        self.assertNotIn(f'hermes-evidence/acquisitions/{partial["x_acquisition"]}/database.json', manifest["members"])
        self.assertIn(f'hermes-evidence/acquisitions/{partial["x_acquisition"]}/raw/state.db', manifest["members"])
        for selected, expected in ((partial["x_acquisition"], "controlled work-copy refusal"), (unfinished, "terminal-state-absent")):
            replay = self.replay(selected, pair.root)
            trace = hermes.build_trace(replay.read())
            self.assertIn(expected, trace["x_harvest_error"])
            exported = replay.retain_pair(self.custody.OwnedExport(self.base / ("partial-reexport-" + selected)))
            again = hermes.build_trace(self.replay(selected, exported.root).read())
            self.assertIn(expected, again["x_harvest_error"])

    def test_derived_inventory_must_equal_selected_context_even_when_recataloged(self):
        import hashlib
        self.temporal_pair()
        owner = self.replay(self.first["x_acquisition"])
        actual = hermes.build_trace(owner.read())
        exported = owner.retain_pair(self.custody.OwnedExport(self.base / "derived"))
        context_path = exported.root / f'hermes-evidence/acquisitions/{actual["x_acquisition"]}/context.json'
        context = json.loads(context_path.read_text())
        context["inventory"]["entries"][0]["kind"] = "directory"
        context_path.write_text(json.dumps(context))
        result_path = context_path.with_name("result.json")
        result = json.loads(result_path.read_text())
        result["context"]["sha256"] = hashlib.sha256(context_path.read_bytes()).hexdigest()
        result_path.write_text(json.dumps(result))
        self.recatalog(exported.root)
        trace = hermes.build_trace(self.replay(self.first["x_acquisition"], exported.root).read())
        self.assertIn("derived context differs from selected source", trace["x_harvest_error"])

    def test_duplicate_json_keys_and_noncontiguous_turn_catalog_refuse(self):
        import shutil
        self.temporal_pair()
        duplicate = self.base / "duplicate-json"
        shutil.copytree(self.moved, duplicate)
        member = duplicate / f'hermes-evidence/acquisitions/{self.first["x_acquisition"]}/result.json'
        member.write_text(member.read_text().replace('"reason": null', '"reason": null, "reason": null'))
        self.recatalog(duplicate)
        trace = hermes.build_trace(self.replay(self.second["x_acquisition"], duplicate).read())
        self.assertIn("duplicate JSON key", trace["x_harvest_error"])
        reordered = self.base / "reordered-turns"
        shutil.copytree(self.moved, reordered)
        path = reordered / "pair.json"
        manifest = json.loads(path.read_text())
        manifest["turn_members"].reverse()
        path.write_text(json.dumps(manifest))
        trace = hermes.build_trace(self.replay(self.second["x_acquisition"], reordered).read())
        self.assertIn("not contiguous", trace["x_harvest_error"])


class NativeFtsControls(_OwnerFixture):
    def database(self):
        import sqlite3
        path = super().database()
        with sqlite3.connect(path) as con:
            con.executescript("""
                create view messages_fts_src as select id, content, tool_name, tool_calls from messages;
                create view messages_fts_trigram_src as select id, content, tool_name from messages;
                create virtual table messages_fts using fts5(content, tool_name, tool_calls,
                    content='messages_fts_src', content_rowid='id');
                create virtual table messages_fts_trigram using fts5(content, tool_name,
                    content='messages_fts_trigram_src', content_rowid='id', tokenize='trigram');
                insert into messages_fts(messages_fts) values ('rebuild');
                insert into messages_fts_trigram(messages_fts_trigram) values ('rebuild');
            """)
        con.close()
        return path

    def assert_preserved_harvest(self, path, reply):
        before = {p.name: p.read_bytes() for p in path.parent.glob("state.db*")}
        trace = hermes.harvest(self.run)
        self.assertNotIn("x_harvest_error", trace, trace.get("x_harvest_error"))
        self.assertEqual(trace["final_reply"], reply)
        self.assertEqual(trace["x_session_ids"], ["root"])
        self.assertEqual({p.name: p.read_bytes() for p in path.parent.glob("state.db*")}, before)
        raw = self.owner.private_root / "acquisitions" / trace["x_acquisition"] / "raw"
        self.assertEqual({p.name: p.read_bytes() for p in raw.iterdir()}, before)

    def test_native_fts_tables_harvest_ordinary_messages_without_changing_raw_bytes(self):
        self.assert_preserved_harvest(self.database(), "native owned reply")

    def test_native_display_identity_blob_is_not_a_trace_field(self):
        import sqlite3
        path = self.database()
        with sqlite3.connect(path) as con:
            con.execute("alter table messages add column display_identity blob")
            con.execute("update messages set display_identity=?", (b"\x00\xffnative display identity",))
        con.close()
        self.assert_preserved_harvest(path, "native owned reply")

    def test_blob_in_trace_content_still_refuses_harvest(self):
        import sqlite3
        path = self.database()
        with sqlite3.connect(path) as con:
            con.execute("update messages set content=? where role='assistant'", (b"invalid trace content",))
        con.close()
        trace = hermes.harvest(self.run)
        self.assertIn("invalid native message values", trace["x_harvest_error"])
        self.assertEqual(trace["final_reply"], "")
        self.assertEqual(trace["events"], [])

    def test_native_fts_tables_include_the_reply_committed_only_in_wal(self):
        import sqlite3
        import subprocess
        import sys
        path = self.database()
        script = '''import os, sqlite3, sys
con = sqlite3.connect(sys.argv[1])
con.execute("pragma journal_mode=wal")
con.execute("pragma wal_autocheckpoint=0")
con.execute("pragma wal_checkpoint(truncate)")
con.execute("insert into messages values (3,'root','assistant','native FTS reply only in WAL',null,null,null)")
con.execute("insert into messages_fts(rowid,content) values (3,'native FTS reply only in WAL')")
con.execute("insert into messages_fts_trigram(rowid,content) values (3,'native FTS reply only in WAL')")
con.commit()
os._exit(0)
'''
        subprocess.run([sys.executable, "-c", script, str(path)], check=True, capture_output=True)
        self.assertGreater((path.parent / "state.db-wal").stat().st_size, 32)
        main_only = self.base / "main-only.db"
        main_only.write_bytes(path.read_bytes())
        with sqlite3.connect(main_only) as con:
            self.assertEqual(con.execute("select content from messages where role='assistant'").fetchall(),
                             [("native owned reply",)])
        con.close()
        self.assert_preserved_harvest(path, "native FTS reply only in WAL")

    def test_integrity_and_decode_policies_deny_unrelated_access(self):
        import sqlite3
        path = self.database()
        for policy in (self.owner._authorize_integrity, self.owner._authorize):
            with self.subTest(policy=policy.__name__), sqlite3.connect(path) as con:
                con.execute("create table unrelated(id text)")
                con.commit()
                con.execute("attach ':memory:' as extra")
                con.execute("create table extra.messages(id text)")
                con.commit()
                con.enable_load_extension(False)
                con.set_authorizer(policy)
                for statement in ("select * from unrelated", "select * from extra.messages", "begin",
                                  "attach ':memory:' as outside", "pragma writable_schema=on",
                                  "pragma main.data_version=1", "delete from messages",
                                  "select load_extension('owned')", "select content from messages_fts",
                                  "select content from messages_fts_trigram"):
                    with self.subTest(statement=statement), self.assertRaises(sqlite3.DatabaseError):
                        con.execute(statement)
            con.close()
            with sqlite3.connect(path) as con:
                con.execute("drop table unrelated")
            con.close()

    def test_decode_policy_denies_fts_reads_after_integrity_initialization(self):
        import sqlite3
        path = self.database()
        with sqlite3.connect(path) as con:
            con.set_authorizer(self.owner._authorize_integrity)
            self.assertEqual(con.execute("pragma quick_check").fetchall(), [("ok",)])
            con.set_authorizer(self.owner._authorize)
            self.assertEqual(con.execute("select content from messages where role='assistant'").fetchall(),
                             [("native owned reply",)])
            for statement in ("select k,v from messages_fts_config", "select segid,term,pgno from messages_fts_idx",
                              "select k,v from messages_fts_trigram_config",
                              "select segid,term,pgno from messages_fts_trigram_idx", "pragma main.data_version",
                              "select content from messages_fts", "select content from messages_fts_trigram"):
                with self.subTest(statement=statement), self.assertRaises(sqlite3.DatabaseError):
                    con.execute(statement)
        con.close()

    def test_unknown_virtual_table_refuses_integrated_harvest(self):
        import sqlite3
        path = self.database()
        with sqlite3.connect(path) as con:
            con.execute("create virtual table unrelated_fts using fts5(content)")
        con.close()
        trace = hermes.harvest(self.run)
        self.assertIn("decode-failed", trace["x_harvest_error"])
        self.assertEqual(trace["events"], [])
        self.assertEqual(trace["final_reply"], "")


class InventoryInference(unittest.TestCase):
    def test_trusted_fixture_root_is_literal_but_candidate_suffixes_still_refuse(self):
        from harnesses.hermes_evidence import FixtureEntry, FixtureInventory
        root = "/fixture/root$with~literal*?`chars"
        fixture = FixtureInventory(root, tuple(FixtureEntry(parts, kind) for parts, kind in [
            (("note.txt",), "regular"), (("docs",), "directory"), (("docs", "note.txt"), "regular")]))
        for path, cwd, expected in [("note.txt", root, root + "/note.txt"),
                                    (root + "/note.txt", root, root + "/note.txt"),
                                    ("note.txt", root + "/docs", root + "/docs/note.txt")]:
            with self.subTest(path=path, cwd=cwd):
                self.assertEqual(hermes.classify_path(path, cwd, fixture), {"requested": path, "cwd": cwd,
                    "spelling": expected, "disposition": "fixture-request", "reason": None, "kind": "regular"})
        evidence = []
        self.assertEqual(hermes.tool_reads("terminal", {"command": "cat note.txt"}, {}, root, fixture, evidence), [root + "/note.txt"])
        self.assertEqual(evidence[0]["disposition"], "fixture-request")
        for suffix in ("$HOME/note.txt", "note.txt$", "~/note.txt", "`pwd`/note.txt", "*.txt", "?.txt"):
            with self.subTest(suffix=suffix):
                self.assertEqual(hermes.classify_path(suffix, root, fixture)["disposition"], "unavailable")
                self.assertEqual(hermes.classify_path(root + "/" + suffix, root, fixture)["disposition"], "unavailable")
                self.assertEqual(hermes.classify_path("note.txt", root + "/" + suffix, fixture)["disposition"], "unavailable")
        self.assertEqual(hermes.classify_path(root + "-other/note.txt", root, fixture)["disposition"], "unavailable")
        self.assertEqual(hermes.classify_path("note.txt", root + "-other", fixture)["disposition"], "unavailable")

    def test_literal_regex_end_anchors_keep_only_inventoried_file_reads(self):
        from harnesses.hermes_evidence import FixtureEntry, FixtureInventory
        fixture = FixtureInventory("/fixture", tuple(FixtureEntry(parts, kind) for parts, kind in [
            (("src",), "directory"), (("src", "a.py"), "regular"), (("note.txt",), "regular")]))
        for command, expected in [(r'grep -n "\.py$" note.txt', ["/fixture/note.txt"]),
                                  (r'ls src | grep "\.py$"', []),
                                  ('grep -E "^def .*:$" src/a.py', ["/fixture/src/a.py"])]:
            with self.subTest(command=command):
                evidence = []
                self.assertEqual(hermes.tool_reads("terminal", {"command": command}, {}, "/fixture", fixture, evidence), expected)
                self.assertEqual(evidence, [{"requested": path.removeprefix("/fixture/"), "cwd": "/fixture",
                    "spelling": path, "disposition": "fixture-request", "reason": None, "kind": "regular"} for path in expected])

    def test_ordinary_shell_operands_are_filtered_but_unsafe_prefixes_refuse(self):
        from harnesses.hermes_evidence import FixtureEntry, FixtureInventory
        fixture = FixtureInventory("/fixture", tuple(FixtureEntry(parts, kind) for parts, kind in [
            (("src",), "directory"), (("src", "a.py"), "regular"), (("note.txt",), "regular"),
            (("file",), "regular"), (("link",), "symlink"), (("hard",), "hardlink"),
            (("socket",), "special"), (("gone",), "unavailable")]))
        for command, expected in [( 'grep -rn "foo.*bar" src/', []), ("cat src/*.py", []),
                                  ('sed -i "s/foo/bar/" note.txt', ["/fixture/note.txt"]),
                                  ("grep -n x docs/missing.md", [])]:
            with self.subTest(command=command):
                evidence = []
                self.assertEqual(hermes.tool_reads("terminal", {"command": command}, {}, "/fixture", fixture, evidence), expected)
                self.assertEqual([r for r in evidence if r["disposition"] == "unavailable"], [])
        for path in ("missing/../note.txt", "file/../note.txt", "link/*.py", "hard/*.py", "socket/*.py",
                     "gone/*.py", "missing/../*.py", "/outside/*.py", "~/note.txt", "$(pwd)/note.txt", "../note.txt",
                     "$HOME/note.txt", "${HOME}/note.txt", "$$/note.txt", "$1/note.txt", "$?/note.txt",
                     "`pwd`/note.txt", "foo~.py", "$HOME/*.py$", "note.txt$$", "$foo.py$", "link/.py$",
                     "hard/.py$", "socket/.py$", "gone/.py$", "missing/../.py$", "/outside/.py$"):
            with self.subTest(path=path):
                evidence = []
                hermes.tool_reads("terminal", {"command": "cat " + path}, {}, "/fixture", fixture, evidence)
                self.assertEqual(evidence[0]["disposition"], "unavailable")
        evidence = []
        self.assertEqual(hermes.tool_reads("read_file", {"path": "missing.py"}, {}, "/fixture", fixture, evidence), ["/fixture/missing.py"])
        self.assertEqual(evidence[0]["disposition"], "fixture-missing")

    def test_prefixes_are_checked_before_dot_cancellation_without_host_queries(self):
        import os
        from unittest import mock
        from harnesses.hermes_evidence import FixtureEntry, FixtureInventory
        fixture = FixtureInventory("/fixture", tuple(FixtureEntry(parts, kind) for parts, kind in [
            (("a",), "directory"), (("b.py",), "regular"), (("file",), "regular"),
            (("link",), "symlink"), (("hard",), "hardlink"), (("socket",), "special")]))
        operations = []
        def refuse(*args, **kwargs):
            operations.append((args, kwargs))
            raise AssertionError("candidate-directed host lookup")
        with mock.patch.object(os, "stat", refuse), mock.patch.object(os, "lstat", refuse), \
             mock.patch.object(os.path, "isfile", refuse), mock.patch.object(Path, "resolve", refuse), \
             mock.patch.object(os.path, "expanduser", refuse):
            good = hermes.classify_path("a/../b.py", "/fixture", fixture)
            self.assertEqual((good["disposition"], good["spelling"]), ("fixture-request", "/fixture/b.py"))
            for path in ("link/../b.py", "hard/../b.py", "missing/../b.py", "file/../b.py", "socket/../b.py",
                         "../b.py", "/outside/b.py", "~/b.py", "$(pwd)/b.py"):
                with self.subTest(path=path):
                    self.assertEqual(hermes.classify_path(path, "/fixture", fixture)["disposition"], "unavailable")
            self.assertEqual(hermes.classify_path("b.py", "/outside", fixture)["disposition"], "unavailable")
            records = []
            self.assertEqual(hermes.tool_reads("read_file", {"path": "missing.py"}, {}, "/fixture", fixture, records), ["/fixture/missing.py"])
            self.assertEqual(hermes.tool_reads("terminal", {"command": "cat missing.py b.py --flag README"}, {}, "/fixture", fixture, records), ["/fixture/b.py"])
            self.assertEqual(hermes.tool_reads("terminal", {"command": "cd a && cat ../b.py"}, {}, "/fixture", fixture, records), ["/fixture/b.py"])
            self.assertEqual(hermes.tool_reads("skill_view", {"file_path": "b.py"}, {"skill_dir": "/fixture"}, "/fixture", fixture, records), ["/fixture/b.py"])
            self.assertEqual(operations, [])


class EvidenceRefusalControls(_OwnerFixture):
    def test_wal_page_sizes_validate_before_frame_arithmetic(self):
        import struct
        def headers(db_page, wal_page):
            main = bytearray(100)
            main[:16] = b"SQLite format 3\x00"
            main[16:18] = db_page.to_bytes(2, "big")
            header = struct.pack(">IIIIII", 0x377f0682, 3007000, wal_page, 0, 0, 0)
            a = b = 0
            words = struct.unpack("<6I", header)
            for index in range(0, 6, 2):
                a = (a + words[index] + b) & 0xffffffff
                b = (b + words[index + 1] + a) & 0xffffffff
            return bytes(main), header + struct.pack(">II", a, b)
        for db_page, wal_page in [(512, 512), (1, 65536)]:
            self.owner._validate_wal(*headers(db_page, wal_page))
        for db_page, wal_page in [(0, 512), (3, 3), (511, 511), (513, 513), (65535, 65535),
                                  (512, 0), (512, 3), (512, 65537), (512, 1024)]:
            with self.subTest(db_page=db_page, wal_page=wal_page), self.assertRaises(self.custody.EvidenceRefused) as refused:
                self.owner._validate_wal(*headers(db_page, wal_page))
            self.assertEqual(refused.exception.reason, "decode-failed")

    def test_malformed_page_size_retains_incomplete_attempt(self):
        import struct
        main = bytearray(100)
        main[:16] = b"SQLite format 3\x00"
        main[16:18] = (3).to_bytes(2, "big")
        header = struct.pack(">IIIIII", 0x377f0682, 3007000, 3, 0, 0, 0)
        a = b = 0
        words = struct.unpack("<6I", header)
        for index in range(0, 6, 2):
            a = (a + words[index] + b) & 0xffffffff
            b = (b + words[index + 1] + a) & 0xffffffff
        wal = header + struct.pack(">II", a, b) + bytes(27)
        profile = hermes.profile(self.run)
        (profile / "state.db").write_bytes(main)
        (profile / "state.db-wal").write_bytes(wal)
        trace = hermes.harvest(self.run)
        self.assertIn("decode-failed", trace["x_harvest_error"])
        self.assertEqual(trace["events"], [])
        attempt = self.owner.private_root / "acquisitions" / trace["x_acquisition"]
        self.assertEqual((attempt / "raw/state.db").read_bytes(), bytes(main))
        self.assertEqual((attempt / "raw/state.db-wal").read_bytes(), wal)
        self.assertEqual(json.loads((attempt / "result.json").read_text())["reason"], "decode-failed")
        self.assertEqual(json.loads((attempt / "context.json").read_text())["kind"], "incomplete")

    def test_required_schema_missing_root_and_bad_json_are_incomplete(self):
        import sqlite3
        import oracles
        path = self.database()
        for mutation, expected in (("update sessions set id='missing'", "missing-root"),
                                   ("update sessions set id='root', model_config='[]'", "decode-failed"),
                                   ("drop table messages", "decode-failed")):
            with self.subTest(mutation=mutation):
                with sqlite3.connect(path) as con:
                    con.execute(mutation)
                con.close()
                trace = hermes.harvest(self.run)
                self.assertIn(expected, trace["x_harvest_error"])
                self.assertEqual(trace["events"], [])
                for promise in oracles.ORACLES:
                    self.assertEqual(oracles.check(promise, trace, {}, self.project)["verdict"], "INCONCLUSIVE")

    def test_authorizer_denies_writes_attach_extensions_and_other_tables(self):
        import sqlite3
        with sqlite3.connect(":memory:") as con:
            con.execute("create table sessions(id text)")
            con.execute("insert into sessions values ('owned')")
            con.execute("create table unrelated(id text)")
            con.commit()
            con.set_authorizer(self.owner._authorize)
            self.assertEqual(con.execute("select id from sessions").fetchall(), [("owned",)])
            for statement in ("attach ':memory:' as extra", "pragma writable_schema=on", "delete from sessions",
                              "select load_extension('owned')", "select * from unrelated"):
                with self.subTest(statement=statement), self.assertRaises(sqlite3.DatabaseError):
                    con.execute(statement)
            con.set_authorizer(None)
        con.close()

    def test_inventory_limit_and_private_collision_refuse(self):
        from unittest import mock
        self.database()
        (self.project / "one.py").write_text("owned")
        with mock.patch.object(self.custody, "MAX_ENTRIES", 0):
            self.assertIn("resource-limit", hermes.harvest(self.run)["x_harvest_error"])
        next_capture = self.owner.private_root / "captures" / f"{self.owner._capture_index:04d}.stdout"
        outside = self.base / "outside-capture"
        outside.write_text("unchanged capture marker")
        next_capture.symlink_to(outside)
        with self.assertRaises((FileExistsError, self.custody.EvidenceRefused)):
            hermes.turn(self.run, "again", 1)
        self.assertEqual(outside.read_text(), "unchanged capture marker")
        self.assertEqual(self.owner._writers[-1].disposition, "removed")

    def test_destination_parent_alias_and_replaced_run_refuse(self):
        self.database()
        hermes.harvest(self.run)
        destination = self.base / "dest"
        destination.mkdir()
        alias = self.base / "alias"
        alias.symlink_to(destination, target_is_directory=True)
        with self.assertRaises(self.custody.RetentionUnavailable):
            self.owner.retain_pair(self.custody.OwnedExport(alias / "pair"))
        self.assertEqual(list(destination.iterdir()), [])
        self.root.rename(self.base / "original-root")
        self.root.mkdir()
        self.assertIn("identity-changed", hermes.harvest(self.run)["x_harvest_error"])

    def test_frozen_records_and_refused_paths_make_every_promise_inconclusive(self):
        import dataclasses
        import sqlite3
        import oracles
        from test_hermes import tool_call
        path = self.database()
        with sqlite3.connect(path) as con:
            con.execute("insert into messages(session_id,role,tool_calls) values ('root','assistant',?)",
                        (json.dumps([tool_call("outside", "read_file", path="/outside/canary.py")]),))
            con.execute("insert into messages(session_id,role,content,tool_call_id,tool_name) values ('root','tool','{}','outside','read_file')")
        con.close()
        evidence = self.owner.read()
        with self.assertRaises(dataclasses.FrozenInstanceError):
            evidence.meta.items = ()
        detached = self.custody.thaw(evidence.sessions[0].session)
        detached["model_config"]["reasoning_config"]["effort"] = "poison"
        self.assertEqual(self.custody.thaw(evidence.sessions[0].session)["model_config"]["reasoning_config"]["effort"], "high")
        trace = hermes.build_trace(evidence)
        self.assertEqual(trace["events"][-1]["id"], "outside")
        self.assertIn("path-refused", trace["x_harvest_error"])
        self.assertEqual(trace["files_read"], [])
        for promise in oracles.ORACLES:
            verdict = oracles.check(promise, trace, {}, self.project)
            self.assertEqual(verdict["verdict"], "INCONCLUSIVE")
            self.assertIn("path-refused", json.dumps(verdict))

    def test_bad_wal_and_unavailable_sqlite_restrictions_are_incomplete(self):
        from unittest import mock
        self.database()
        wal = hermes.profile(self.run) / "state.db-wal"
        wal.write_bytes(b"owned invalid WAL")
        first = hermes.harvest(self.run)
        self.assertIn("invalid WAL", first["x_harvest_error"])
        raw = self.owner.private_root / "acquisitions" / first["x_acquisition"] / "raw/state.db-wal"
        self.assertEqual(raw.read_bytes(), b"owned invalid WAL")
        wal.rename(self.base / "preserved-invalid-wal")
        connect = self.custody.sqlite3.connect
        class Unrestricted:
            def __init__(self, *args, **kwargs):
                self.connection = connect(*args, **kwargs)
            def close(self):
                self.connection.close()
        with mock.patch.object(self.custody.sqlite3, "connect", Unrestricted):
            self.assertIn("required SQLite restrictions", hermes.harvest(self.run)["x_harvest_error"])

    def test_device_node_is_refused_before_open_when_host_allows_creation(self):
        import os
        import stat
        path = hermes.profile(self.run) / "state.db"
        try:
            os.mknod(path, stat.S_IFCHR | 0o600, os.makedev(0, 0))
        except (PermissionError, AttributeError):
            self.skipTest("host does not permit an owned device-node fixture")
        self.assertIn("path-refused", hermes.harvest(self.run)["x_harvest_error"])

    def test_unknown_preload_or_version_writer_prevents_preparation_and_harvest(self):
        import live
        (self.base / "unknown").touch()
        for entry in (None, "poteto-mode"):
            with self.subTest(entry=entry):
                root = self.base / ("version-run" if entry is None else "preload-run")
                (root / "w/p").mkdir(parents=True)
                run = live.Run(root, "hermes", {"id": "owned", "fixture": "p", "entry": entry, "turns": ["go"]}, "pin", 10)
                with self.assertRaisesRegex(self.custody.EvidenceRefused, "unknown termination"):
                    hermes.prepare(run)
                self.addCleanup(run._hermes_evidence.close)
                self.assertEqual(len(run._hermes_evidence._writers), 1)
                self.assertEqual(run._hermes_evidence._writers[0].disposition, "unknown")
                self.assertIn("termination-unknown", hermes.harvest(run)["x_harvest_error"])
                with self.assertRaisesRegex(self.custody.EvidenceRefused, "unknown termination"):
                    hermes.turn(run, "go", 0)


if __name__ == "__main__":
    unittest.main()
