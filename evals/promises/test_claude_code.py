import json
import hashlib
import os
import platform
import subprocess
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

import live
from harnesses import claude_code


def session_rows(cwd):
    return [
        {"type": "user", "cwd": cwd, "message": {"role": "user", "content": "/poteto-mode fix it"}},
        {"type": "assistant", "cwd": cwd, "message": {"role": "assistant", "content": [
            {"type": "tool_use", "id": "toolu_a", "name": "Read", "input": {"file_path": f"{cwd}/a.py"}},
            {"type": "tool_use", "id": "toolu_b", "name": "Read", "input": {"file_path": f"{cwd}/b.py"}}]}},
        {"type": "user", "cwd": cwd, "message": {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": "toolu_b", "content": "b"},
            {"type": "tool_result", "tool_use_id": "toolu_a", "content": "a"}]}},
    ]


class LoadJsonl(unittest.TestCase):
    def test_literal_unicode_stays_inside_ordered_jsonl_records(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "rows.jsonl"
            for separator in ("\u0085", "\u2028", "\u2029"):
                for newline in ("\n", "\r\n"):
                    with self.subTest(separator=repr(separator), newline=repr(newline)):
                        rows = [
                            {"id": "first", "message": {"content": f"before{separator}after"}},
                            {"id": "last", "message": {"content": "escaped\r\n\t\f\v\u001c\u001d\u001e"}},
                        ]
                        physical_rows = [json.dumps(rows[0], ensure_ascii=False), "", " \t", "{malformed}",
                                         json.dumps(rows[1], ensure_ascii=False)]
                        path.write_bytes(newline.join(physical_rows).encode("utf-8"))
                        self.assertEqual(claude_code.load_jsonl(path), rows)

    def test_invalid_utf8_is_replaced_without_losing_adjacent_records(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "rows.jsonl"
            path.write_bytes(b'{"id":"first","text":"before\xffafter"}\nnot-json\n{"id":"last","text":"kept"}')
            self.assertEqual(claude_code.load_jsonl(path), [
                {"id": "first", "text": "before\ufffdafter"},
                {"id": "last", "text": "kept"},
            ])

    def test_empty_and_missing_files_keep_their_existing_results(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "rows.jsonl"
            path.write_bytes(b"")
            self.assertEqual(claude_code.load_jsonl(path), [])
            with self.assertRaises(FileNotFoundError):
                claude_code.load_jsonl(Path(tmp) / "missing.jsonl")


class RecordedReads(unittest.TestCase):
    def test_shell_paths_are_recorded_without_opening_the_host(self):
        with patch.object(Path, "is_file", side_effect=AssertionError("host path queried")), \
                patch.object(Path, "resolve", side_effect=AssertionError("host path resolved")):
            self.assertEqual(claude_code.shell_reads("cat inside.py; cd ../other; head missing.py; cat /outside/canary", "/fixture/project"),
                             ["/fixture/project/inside.py", "/fixture/other/missing.py", "/outside/canary"])

    def test_native_read_paths_keep_lexical_identity(self):
        rows = [{"type": "assistant", "message": {"content": [
            {"type": "tool_use", "name": "Read", "input": {"file_path": "dir/../inside.py"}},
            {"type": "tool_use", "name": "Read", "input": {"file_path": "/outside/link/canary"}},
        ]}}]
        with patch.object(Path, "resolve", side_effect=AssertionError("host path resolved")):
            self.assertEqual(claude_code.files_read(rows, "/fixture/project"),
                             ["/fixture/project/inside.py", "/outside/link/canary"])


class Harvest(unittest.TestCase):
    def test_claude_tool_events_keep_their_call_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            session = str(uuid.uuid4())
            case = {"id": "x", "fixture": "tally", "entry": "poteto-mode", "turns": ["fix it"]}
            run = live.Run(root, "claude-code", case, "0" * 40, 60)
            run.project.mkdir(parents=True)
            transcripts = root / "transcripts" / "slug"
            transcripts.mkdir(parents=True)
            rows = session_rows(str(run.project))
            (transcripts / f"{session}.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n")
            run.turns = [{"session_id": session, "stream": str(root / "stream-0.jsonl"), "argv": ["claude"], "exit_code": 0, "timed_out": False, "duration_s": 1.0}]
            trace = claude_code.harvest(run)
        ids = [(e["kind"], e.get("id")) for e in trace["events"] if e["kind"] in ("tool_call", "tool_result")]
        self.assertEqual(ids, [("tool_call", "toolu_a"), ("tool_call", "toolu_b"),
                               ("tool_result", "toolu_b"), ("tool_result", "toolu_a")])

    def test_literal_unicode_survives_lead_stream_and_child_harvest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            session = str(uuid.uuid4())
            case = {"id": "x", "fixture": "tally", "entry": "poteto-mode", "turns": ["fix it"]}
            run = live.Run(root, "claude-code", case, "0" * 40, 60)
            run.project.mkdir(parents=True)
            transcripts = root / "transcripts" / "slug"
            children = transcripts / session / "subagents"
            children.mkdir(parents=True)
            prompt = "Review\u2028guide\u0085promises\u2029and evidence."
            child_reply = "persona: poteto-agent\nChild\u2029reply\u0085with\u2028evidence."
            fallback = "Lead\u0085final\u2028reply\u2029from transcript."
            stream_reply = "Stream\u2028final\u2029reply\u0085from result."
            result = "Child\u2029result\u2028with\u0085evidence."
            rows = session_rows(str(run.project)) + [
                {"type": "assistant", "message": {"role": "assistant", "content": [
                    {"type": "tool_use", "id": "toolu_child", "name": "Agent", "input": {
                        "subagent_type": "poteto-agent", "model": "sonnet", "prompt": prompt}}]}},
                {"type": "user", "message": {"role": "user", "content": [
                    {"type": "tool_result", "tool_use_id": "toolu_child", "content": result}]}},
                {"type": "assistant", "message": {"role": "assistant", "content": [
                    {"type": "text", "text": fallback}]}},
            ]
            child = [{"type": "assistant", "perTurnEffort": "high", "message": {
                "role": "assistant", "model": "child-model", "content": [
                    {"type": "text", "text": child_reply},
                    {"type": "tool_use", "id": "toolu_child_read", "name": "Read", "input": {
                        "file_path": str(run.project / "child.py")}}]}}]
            child_path = children / "agent-child.jsonl"
            for path, records in ((transcripts / f"{session}.jsonl", rows), (child_path, child)):
                path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in records), encoding="utf-8")
            (children / "agent-child.meta.json").write_text(json.dumps({
                "toolUseId": "toolu_child", "agentType": "poteto-agent", "model": "sonnet"}))
            stream = root / "stream-0.jsonl"
            init = {"type": "system", "subtype": "init", "claude_code_version": "test-version",
                    "model": "lead-model", "tools": ["Read", "Agent"], "text": "Init\u0085data."}
            run.turns = [{"session_id": session, "stream": str(stream), "argv": ["claude"], "exit_code": 0,
                          "timed_out": False, "duration_s": 1.0}]
            for with_result, expected_reply in ((True, stream_reply), (False, fallback)):
                with self.subTest(with_stream_result=with_result):
                    records = [init] + ([{"type": "result", "result": stream_reply, "total_cost_usd": 0.125}]
                                        if with_result else [])
                    stream.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in records), encoding="utf-8")
                    trace = claude_code.harvest(run)
                    self.assertEqual([(e["seq"], e["kind"], e.get("name"), e.get("id")) for e in trace["events"]], [
                        (0, "user", None, None),
                        (1, "tool_call", "Read", "toolu_a"),
                        (2, "tool_call", "Read", "toolu_b"),
                        (3, "tool_result", "Read", "toolu_b"),
                        (4, "tool_result", "Read", "toolu_a"),
                        (5, "tool_call", "Agent", "toolu_child"),
                        (6, "tool_result", "Agent", "toolu_child"),
                        (7, "text", None, None),
                    ])
                    self.assertEqual(trace["events"][5]["input"]["prompt"], prompt)
                    self.assertEqual(trace["events"][6]["output_head"], result)
                    self.assertEqual(trace["events"][7]["text"], fallback)
                    self.assertEqual(trace["spawns"], [{
                        "seq": 5, "turn": 0, "tool": "Agent", "subagent_type": "poteto-agent", "persona": "poteto-agent",
                        "model": "sonnet", "effort": None, "prompt_head": prompt, "transcript": str(child_path),
                        "observed": {"models": ["child-model"], "efforts": ["high"]},
                        "x_child_first_reply": child_reply, "x_persona_line": "poteto-agent",
                    }])
                    self.assertEqual(trace["x_files_read_by"]["agent-child"], [str((run.project / "child.py").resolve())])
                    self.assertEqual(trace["final_reply"], expected_reply)
                    self.assertEqual(trace["x_cost_usd"], 0.125 if with_result else 0)
                    self.assertEqual(trace["cli_version"], "test-version")
                    self.assertEqual(trace["model"], "lead-model")
                    self.assertEqual(trace["x_init_tools"], ["Read", "Agent"])
                    self.assertEqual(trace["x_session_id"], session)


class PrivateEvidence(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        case = {"id": "x", "fixture": "tally", "turns": ["first", "second"]}
        self.run = live.Run(self.root, "claude-code", case, "0" * 40, 60)
        self.run.project.mkdir(parents=True)
        binary = self.root / "native.bin"
        binary.write_bytes(b"test executable identity")
        digest = hashlib.sha256(binary.read_bytes()).hexdigest()
        runtime = claude_code.HostRuntime(binary, "test", self.root / "outside-home", "test-user", (), (),
                                          ((binary, digest),), "/usr/bin:/bin", "/bin/sh")
        self.state = claude_code._bind_paths(self.run, runtime)
        self.session = self.state.session
        self.native = self.state.paths.config / "projects" / "slug"
        self.native.mkdir(parents=True)
        self.lead = self.native / f"{self.session}.jsonl"
        self.lead.write_text(json.dumps({"type": "assistant", "message": {"content": "first"}}) + "\n")

    def test_copy_preserves_native_sources_and_publishes_a_whole_snapshot(self):
        child = self.native / self.session / "subagents" / "agent-child.jsonl"
        child.parent.mkdir(parents=True)
        child.write_text('{"type":"assistant","message":{"content":"child"}}\n')
        first_root, first = claude_code._evidence(self.run, self.session)
        self.assertEqual(first[Path("slug") / self.lead.name], self.lead.read_bytes())
        self.assertEqual((first_root / "slug" / self.session / "subagents" / child.name).read_bytes(), child.read_bytes())
        self.assertEqual(claude_code._evidence(self.run, self.session), (first_root, first))
        replay = live.Run(self.root, "claude-code", self.run.case, "0" * 40, 60)
        self.assertEqual(claude_code._evidence(replay, self.session), (first_root, first))
        self.lead.write_text('{"type":"assistant","message":{"content":"resumed"}}\n')
        second_root, second = claude_code._evidence(self.run, self.session)
        self.assertEqual(second[Path("slug") / self.lead.name], b'{"type":"assistant","message":{"content":"resumed"}}\n')
        self.assertEqual((first_root / "slug" / self.lead.name).read_bytes(), first[Path("slug") / self.lead.name])
        self.assertNotEqual(first_root, second_root)

    def test_unsafe_native_files_do_not_publish_or_touch_outside_data(self):
        outside = self.root / "outside.jsonl"
        outside.write_text("outside unchanged")
        child = self.native / self.session / "subagents" / "agent-child.jsonl"
        child.parent.mkdir(parents=True)
        for unsafe in ("symlink", "hardlink", "fifo"):
            with self.subTest(unsafe=unsafe):
                if unsafe == "symlink":
                    child.symlink_to(outside)
                elif unsafe == "hardlink":
                    os.link(outside, child)
                else:
                    os.mkfifo(child)
                with self.assertRaises((claude_code.IsolationUnavailable, OSError)):
                    claude_code._evidence(self.run, self.session)
                self.assertEqual(list(self.state.paths.transcripts.iterdir()), [])
                self.assertEqual(outside.read_text(), "outside unchanged")
                child.unlink()
        child.write_text("inside regular evidence")
        _, evidence = claude_code._evidence(self.run, self.session)
        self.assertEqual(evidence[Path("slug") / self.session / "subagents" / child.name], b"inside regular evidence")

    def test_duplicate_leads_and_replaced_roots_fail_closed(self):
        duplicate = self.state.paths.config / "projects" / "duplicate"
        duplicate.mkdir()
        (duplicate / self.lead.name).write_text("duplicate")
        with self.assertRaisesRegex(claude_code.IsolationUnavailable, "found 2"):
            claude_code._evidence(self.run, self.session)
        (duplicate / self.lead.name).unlink()
        duplicate.rmdir()
        self.assertEqual(claude_code._command(self.run, "first", 0).session, self.session)
        original = self.state.paths.config
        original.rename(self.root / "old-config")
        original.mkdir()
        with self.assertRaisesRegex(claude_code.IsolationUnavailable, "replaced"):
            claude_code._command(self.run, "first", 0)

    def test_changed_binary_and_unprepared_runs_refuse_launch(self):
        self.assertEqual(claude_code._command(self.run, "first", 0).session, self.session)
        self.state.runtime.binary.write_text("changed")
        with self.assertRaisesRegex(claude_code.IsolationUnavailable, "executable changed"):
            claude_code._command(self.run, "first", 0)
        unprepared = live.Run(self.root, "claude-code", self.run.case, "0" * 40, 60)
        with self.assertRaisesRegex(claude_code.IsolationUnavailable, "preparation state"):
            claude_code._command(unprepared, "first", 0)

    def test_environment_and_stream_readers_ignore_candidate_path_authority(self):
        with patch.dict(os.environ, {"CLAUDE_CONFIG_DIR": "/outside/config", "PATH": "/outside/bin"}):
            env = claude_code.child_env(self.run)
        self.assertEqual(env["CLAUDE_CONFIG_DIR"], str(self.root / "claude-config"))
        self.assertEqual(env["PATH"], "/usr/bin:/bin")
        (self.root / "stream-0.jsonl").write_text('{"type":"result","result":"inside result"}\n')
        self.assertEqual(claude_code._stream_rows(self.root, 0), [{"type": "result", "result": "inside result"}])
        (self.root / "stream-0.jsonl").unlink()
        outside = self.root / "outside-stream"
        outside.write_text("outside unchanged")
        (self.root / "stream-0.jsonl").symlink_to(outside)
        with self.assertRaises(OSError):
            claude_code._stream_rows(self.root, 0)
        self.assertEqual(outside.read_text(), "outside unchanged")


class PreparedHarvest(unittest.TestCase):
    def prepare_run(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        case = {"id": "x", "fixture": "tally", "turns": ["first", "second"]}
        self.run = live.Run(self.root, "claude-code", case, "0" * 40, 60)
        self.run.project.mkdir(parents=True)
        binary = self.root / "native.bin"
        binary.write_bytes(b"test executable identity")
        runtime = claude_code.HostRuntime(binary, "test", self.root / "outside-home", "test-user", (), (),
                                          ((binary, hashlib.sha256(binary.read_bytes()).hexdigest()),),
                                          "/usr/bin:/bin", "/bin/sh")
        self.state = claude_code._bind_paths(self.run, runtime)
        self.native = self.state.paths.config / "projects" / "slug"
        self.native.mkdir(parents=True)
        self.lead = self.native / f"{self.state.session}.jsonl"
        self.lead.write_text("")

    def launch(self, blocks, result=None, exit_code=0, timed_out=False):
        index = len(self.run._claude_state.records)

        def execute(argv, cwd, env, timeout_s, stream, stderr):
            self.assertEqual(cwd, self.run.project)
            self.assertEqual(env["CLAUDE_CONFIG_DIR"], str(self.state.paths.config))
            self.assertEqual(argv[:2], ("/usr/bin/sandbox-exec", "-p"))
            self.assertEqual(argv[3:11], (str(self.state.runtime.binary), "-p", "--output-format", "stream-json",
                                        "--verbose", "--setting-sources", "project", "--strict-mcp-config"))
            self.assertEqual(argv[11:15], ("--mcp-config", '{"mcpServers":{}}', "--permission-mode", "bypassPermissions"))
            self.assertEqual(argv[15:17], ("--session-id" if index == 0 else "--resume", self.state.session))
            with self.lead.open("a") as lead:
                for row in ({"type": "user", "message": {"content": self.run.case["turns"][index]}},
                            {"type": "assistant", "message": {"model": "lead-model", "content": blocks}}):
                    lead.write(json.dumps(row) + "\n")
            stream.write_text(json.dumps(result) + "\n" if result is not None else "")
            stderr.write_text("")
            return {"argv": list(argv), "exit_code": exit_code, "timed_out": timed_out, "duration_s": 1.0}

        with patch.object(live, "execute", side_effect=execute):
            record = claude_code.turn(self.run, self.run.case["turns"][index], index)
        self.assertEqual(record["session_id"], self.state.session)
        self.run.turns = [{"session_id": "untrusted", "argv": [], "exit_code": 99}]

    def test_foreground_command_data_keeps_prepared_and_replayed_evidence_complete(self):
        for command in ("printf '%s\\n' 'A&B'", r"echo \&", "echo ok 2>&1", "echo ok >&2", "echo ok &>/dev/null"):
            with self.subTest(command=command):
                self.prepare_run()
                self.launch([{"type": "tool_use", "id": "bash", "name": "Bash", "input": {"command": command}},
                             {"type": "text", "text": "native final"}],
                            {"type": "result", "subtype": "success", "result": "completed foreground"})
                trace = claude_code.harvest(self.run)
                self.assertEqual(trace["final_reply"], "completed foreground")
                self.assertEqual(trace["events"][1]["input"], {"command": command})
                self.assertEqual(trace["x_evidence_complete"], True)
                self.assertEqual(trace["x_turn_exit_codes"], [0])
                self.assertEqual(len(trace["transcript_paths"]), 1)
                self.assertEqual(Path(trace["transcript_paths"][0]).read_bytes(), self.lead.read_bytes())
                replay = live.Run(self.root, "claude-code", self.run.case, "0" * 40, 60)
                replay.turns = list(self.run._claude_state.records)
                self.assertEqual(claude_code.harvest(replay), trace)

    def test_missing_or_error_result_and_timeout_keep_observed_events_incomplete(self):
        for result, exit_code, timed_out in ((None, 0, False),
                ({"type": "result", "subtype": "error", "result": "native error"}, 0, False),
                ({"type": "result", "subtype": "success", "result": "native result"}, 1, False),
                ({"type": "result", "subtype": "success", "result": "native result"}, 0, True)):
            with self.subTest(result=result, exit_code=exit_code, timed_out=timed_out):
                self.prepare_run()
                self.launch([{"type": "text", "text": "observed final"}], result, exit_code, timed_out)
                trace = claude_code.harvest(self.run)
                self.assertEqual(trace["events"][-1]["text"], "observed final")
                self.assertEqual(trace["x_evidence_complete"], False)
                self.assertEqual(trace["x_timed_out"], timed_out)
                self.assertEqual(trace["x_turn_exit_codes"], [exit_code])

    def test_child_evidence_and_native_background_flags_control_completion(self):
        for tool in ("Agent", "Task", "Bash"):
            for background in (False, True):
                with self.subTest(tool=tool, background=background):
                    self.prepare_run()
                    self.launch([{"type": "tool_use", "id": "child", "name": tool, "input": {
                        "command": "echo ok", "prompt": "child prompt", "run_in_background": background}}],
                        {"type": "result", "subtype": "success", "result": "lead completed"})
                    missing = claude_code.harvest(self.run)
                    self.assertEqual(missing["final_reply"], "lead completed")
                    self.assertEqual(missing["x_evidence_complete"], tool == "Bash" and not background)
                    if tool != "Bash":
                        children = self.native / self.state.session / "subagents"
                        children.mkdir(parents=True)
                        (children / "agent-child.meta.json").write_text(json.dumps({"toolUseId": "child", "agentType": "poteto-agent"}))
                        metadata_only = claude_code.harvest(self.run)
                        self.assertEqual(metadata_only["spawns"][0]["subagent_type"], "poteto-agent")
                        self.assertEqual(metadata_only["x_evidence_complete"], False)
                        (children / "agent-child.jsonl").write_text(json.dumps({"type": "assistant", "message": {
                            "model": "child-model", "content": [{"type": "text", "text": "persona: poteto-agent\nChild completed."}]}}) + "\n")
                        complete = claude_code.harvest(self.run)
                        self.assertEqual(complete["spawns"][0]["observed"], {"models": ["child-model"], "efforts": []})
                        self.assertEqual(complete["x_evidence_complete"], not background)

    def test_resume_retains_first_snapshot_and_requires_each_native_result(self):
        self.prepare_run()
        self.launch([{"type": "text", "text": "first native"}],
                    {"type": "result", "subtype": "success", "result": "first result"})
        first = claude_code.harvest(self.run)
        retained = Path(first["transcript_paths"][0]).read_bytes()
        self.launch([{"type": "text", "text": "second native"}])
        second = claude_code.harvest(self.run)
        self.assertEqual(first["x_evidence_complete"], True)
        self.assertEqual(second["x_evidence_complete"], False)
        self.assertEqual(second["final_reply"], "second native")
        self.assertEqual([e["turn"] for e in second["events"]], [0, 0, 1, 1])
        self.assertEqual(Path(first["transcript_paths"][0]).read_bytes(), retained)
        self.assertNotEqual(first["x_evidence_snapshot"], second["x_evidence_snapshot"])

    def test_missing_native_lead_or_projects_aborts_public_harvest(self):
        self.prepare_run()
        self.launch([{"type": "text", "text": "observed final"}],
                    {"type": "result", "subtype": "success", "result": "native result"})
        self.lead.unlink()
        with self.assertRaisesRegex(claude_code.IsolationUnavailable, "found 0"):
            claude_code.harvest(self.run)
        self.native.rmdir()
        self.native.parent.rmdir()
        with self.assertRaisesRegex(claude_code.IsolationUnavailable, "unsafe directory"):
            claude_code.harvest(self.run)
        self.assertEqual(list(self.state.paths.transcripts.iterdir()), [])


@unittest.skipUnless(platform.system() == "Darwin" and os.access("/usr/bin/sandbox-exec", os.X_OK),
                     "requires Darwin sandbox-exec")
class NativeFilesystem(unittest.TestCase):
    def test_policy_confines_filesystem_operations_and_preserves_project_root(self):
        for confined in (True, False):
            with self.subTest(confined=confined), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp).resolve()
                run = live.Run(root / "run", "claude-code", {"fixture": "tally"}, "0" * 40, 60)
                run.project.mkdir(parents=True)
                runtime = claude_code.HostRuntime(
                    Path("/bin/sh"), "test", root / "home", "test-user",
                    tuple(Path(p) for p in ("/", "/bin/sh", "/bin/cat", "/bin/mv", "/dev/null")),
                    (Path("/System/Library"), Path("/usr/lib")), (), "/usr/bin:/bin", "/bin/sh")
                state = claude_code._bind_paths(run, runtime)
                env = claude_code.child_env(run)
                prefix = ["/usr/bin/sandbox-exec", "-p", claude_code._policy(state, 0)] if confined else []
                inside = run.project / "inside.txt"
                inside.write_bytes(b"inside-before\n")
                outside = root / "outside.txt"
                outside.write_bytes(b"outside-before\n")
                link = run.project / "outward-link"
                link.symlink_to(outside)
                identity = run.project.stat()
                done = subprocess.run(prefix + [
                    "/bin/sh", "-c",
                    '/bin/cat "$1" && printf "inside-after\\n" > "$1" && '
                    '/bin/mv "$1" "$2" && /bin/mv "$2" "$1" && /bin/cat "$1"',
                    "sh", str(inside), str(run.project / "moved.txt")],
                    cwd=run.project, env=env, capture_output=True, timeout=10)
                self.assertEqual(done.returncode, 0, (done.stdout, done.stderr))
                self.assertEqual(done.stdout, b"inside-before\ninside-after\n")
                self.assertEqual(inside.read_bytes(), b"inside-after\n")
                write = 'printf "outside-after\\n" > "$1" && /bin/cat "$1"'
                operations = (
                    ("absolute-read", ["/bin/cat", str(outside)], b"outside-before\n"),
                    ("absolute-write", ["/bin/sh", "-c", write, "sh", str(outside)], b"outside-after\n"),
                    ("symlink-read", ["/bin/cat", str(link)], b"outside-before\n"),
                    ("symlink-write", ["/bin/sh", "-c", write, "sh", str(link)], b"outside-after\n"),
                    ("descendant-read", ["/bin/sh", "-c", '/bin/sh -c \'/bin/cat "$1"\' sh "$1"',
                                         "sh", str(outside)], b"outside-before\n"),
                    ("descendant-write", ["/bin/sh", "-c", '/bin/sh -c "$1" sh "$2"',
                                          "sh", write, str(outside)], b"outside-after\n"),
                )
                for operation, argv, expected in operations:
                    with self.subTest(operation=operation):
                        outside.write_bytes(b"outside-before\n")
                        done = subprocess.run(prefix + argv, cwd=run.project, env=env,
                                              capture_output=True, timeout=10)
                        if confined:
                            self.assertNotEqual(done.returncode, 0, (done.stdout, done.stderr))
                            self.assertEqual(done.stdout, b"")
                        else:
                            self.assertEqual(done.returncode, 0, (done.stdout, done.stderr))
                            self.assertEqual(done.stdout, expected)
                        self.assertEqual(outside.read_bytes(), b"outside-before\n" if confined else expected)
                        self.assertEqual(inside.read_bytes(), b"inside-after\n")
                        current = run.project.stat()
                        self.assertEqual((current.st_dev, current.st_ino), (identity.st_dev, identity.st_ino))
                        self.assertFalse(run.project.is_symlink())
                outside.write_bytes(b"outside-before\n")
                displaced = state.paths.config / "displaced-project"
                replacement = state.paths.config / "replacement-project"
                replacement.mkdir()
                (replacement / "inside.txt").write_bytes(b"replacement\n")
                replacement_identity = replacement.stat()
                for operation, argv in (
                    ("unlink-root", ["/bin/mv", str(run.project), str(displaced)]),
                    ("replace-root", ["/bin/sh", "-c", '/bin/mv "$1" "$2" && /bin/mv "$3" "$1"',
                                      "sh", str(run.project), str(displaced), str(replacement)]),
                ):
                    with self.subTest(operation=operation):
                        done = subprocess.run(prefix + argv, cwd=state.paths.tmp, env=env,
                                              capture_output=True, timeout=10)
                        self.assertEqual(done.stdout, b"")
                        self.assertEqual(outside.read_bytes(), b"outside-before\n")
                        if confined:
                            self.assertNotEqual(done.returncode, 0, (done.stdout, done.stderr))
                            current = run.project.stat()
                            self.assertEqual((current.st_dev, current.st_ino), (identity.st_dev, identity.st_ino))
                            self.assertFalse(run.project.is_symlink())
                            self.assertEqual(inside.read_bytes(), b"inside-after\n")
                            self.assertFalse(displaced.exists())
                        else:
                            self.assertEqual(done.returncode, 0, (done.stdout, done.stderr))
                            moved = displaced.stat()
                            self.assertEqual((moved.st_dev, moved.st_ino), (identity.st_dev, identity.st_ino))
                            self.assertEqual((displaced / "inside.txt").read_bytes(), b"inside-after\n")
                            if operation == "unlink-root":
                                self.assertFalse(run.project.exists())
                                displaced.rename(run.project)
                            else:
                                current = run.project.stat()
                                self.assertEqual((current.st_dev, current.st_ino),
                                                 (replacement_identity.st_dev, replacement_identity.st_ino))
                                self.assertEqual(inside.read_bytes(), b"replacement\n")


@unittest.skipUnless((platform.system(), platform.release(), platform.machine(), str(Path.home())) ==
                     ("Darwin", "25.6.0", "arm64", "/Users/msmith1"), "requires the measured Claude runtime")
class NativeGit(unittest.TestCase):
    def test_confined_path_resolves_native_git_without_the_selection_shim(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            run = live.Run(root, "claude-code", {"fixture": "tally"}, "0" * 40, 60)
            run.project.mkdir(parents=True)
            state = claude_code._bind_paths(run, claude_code._host_runtime())
            done = subprocess.run(["/usr/bin/sandbox-exec", "-p", claude_code._policy(state, 0),
                                   "/bin/sh", "-c", "command -v git"], cwd=run.project,
                                  env=claude_code.child_env(run), capture_output=True, text=True, timeout=10)
            self.assertEqual(done.returncode, 0, done.stderr)
            self.assertEqual(done.stdout, "/Library/Developer/CommandLineTools/usr/bin/git\n")


if __name__ == "__main__":
    unittest.main()
