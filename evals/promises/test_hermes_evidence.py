import json
import unittest
from pathlib import Path
from types import SimpleNamespace

from harnesses import hermes
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

    def test_actual_entry_skill_survives_prepared_case_and_public_record_mutation(self):
        self.database()
        captured = self.owner.read()
        self.run.case["entry"] = "why"
        self.run.case["turns"] = ["/why poisoned", "/why wrong plan"]
        self.run.turns[0]["hermes_argv"].append("poison")
        self.assertEqual(hermes.harvest(self.run)["x_turn_entries"], [{"turn": 0, "skill": "how", "entry": "injected"}])
        self.assertEqual(hermes.build_trace(captured)["x_turn_entries"], [{"turn": 0, "skill": "how", "entry": "injected"}])

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
