import json
import os
from pathlib import Path
import stat
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import application


class RecordingTransport:
    def __init__(self, test, mode="success"):
        self.test, self.mode, self.commands = test, mode, []
        self.name, self.payload = None, None
        self.before_restore_modes, self.cloned_files = {}, {}
        self.original = application._command

    def __call__(self, argv, **kwargs):
        argv = list(map(str, argv))
        self.commands.append((argv, kwargs.get("timeout", application.PHASE_TIMEOUT_S)))
        if argv[0] != "sbx":
            result = self.original(argv, **kwargs)
            if argv[0] == "git" and "checkout-index" in argv:
                root = Path(argv[argv.index("-C") + 1])
                for key, tree in (("project", root / "project"), ("skills", root / ".agents/skills")):
                    if tree.exists():
                        for path in tree.rglob("*"):
                            path.chmod(stat.S_IMODE(path.stat().st_mode) | 0o020)
                        self.before_restore_modes[key] = {p.relative_to(tree).as_posix(): stat.S_IMODE(p.stat().st_mode) for p in tree.rglob("*")}
                if self.mode.startswith("clone_"):
                    tree = root / ("project" if self.mode.endswith("project") else ".agents/skills")
                    target = next(p for p in tree.rglob("*") if p.is_file())
                    if "content" in self.mode:
                        target.write_text("tampered")
                    else:
                        target.rename(target.with_name("unexpected"))
            return result
        args = argv[1:]
        if args[:2] == ["template", "ls"]:
            return self.reply({"images": [{"repository": "namespace/prepared", "tag": "test", "id": "abc"}]})
        if args[0] == "create":
            self.name = args[args.index("--name") + 1]
            claim = json.loads((Path(args[-1]).parent / "claim.json").read_text())
            self.test.assertEqual(claim["sandbox"], self.name)
            self.test.assertEqual(sorted(p.name for p in Path(args[-1]).iterdir()), ([".agents"] if claim["spec"]["skills"] else []) + [".git", "project"])
            staging = Path(args[-1])
            cloned = staging.with_name("transport-clone")
            self.original(["git", "clone", "--no-local", staging, cloned],
                          env=application._git_env())
            shutil.rmtree(staging)
            cloned.rename(staging)
            for key, tree in (("project", staging / "project"), ("skills", staging / ".agents/skills")):
                if tree.exists():
                    self.cloned_files[key] = {p.relative_to(tree).as_posix(): p.read_bytes() for p in tree.rglob("*") if p.is_file()}
            return self.reply()
        if args[0] == "policy":
            return subprocess.CompletedProcess(argv, 2 if self.mode == "policy_error" else 1, b'{"allowed":false}', b"")
        if args[0] == "cp":
            if args[1].endswith("input.json"):
                self.payload = json.loads(Path(args[1]).read_text())
            elif args[1].startswith(self.name + ":"):
                Path(args[2]).write_bytes(Path(application.REMOTE + ".tar").read_bytes())
            return self.reply()
        if args[0] == "exec":
            operation = args[-2]
            if operation == "setup":
                return self.reply(application._inside_setup(self.payload))
            if operation == "run":
                if self.mode == "outer_timeout":
                    raise subprocess.TimeoutExpired(argv, 1)
                if self.mode == "interrupt_before_status":
                    raise KeyboardInterrupt
                application._inside_run(self.payload)
                if self.mode == "interrupt_after_status":
                    raise KeyboardInterrupt
                return self.reply()
            if operation == "kill":
                application._kill_native()
                return self.reply()
            if operation == "harvest":
                if self.mode == "guidance_changed":
                    (Path(self.payload["root"]) / ".agents/skills/guide/SKILL.md").write_text("changed")
                application._inside_harvest(self.payload)
                return self.reply()
        if args[0] == "rm":
            if self.mode == "cleanup_failure":
                raise application.ApplicationError("removal refused")
            self.name = None
            return self.reply()
        if args[0] == "ls":
            return self.reply({"sandboxes": [] if self.name is None else [{"name": self.name}]})
        raise AssertionError(argv)

    @staticmethod
    def reply(value=None):
        return subprocess.CompletedProcess([], 0, json.dumps(value).encode() if value is not None else b"", b"")


class ApplicationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        source = self.root / "source"
        source.mkdir()
        (source / "old.txt").write_text("delete me")
        (source / "app.py").write_text("original")
        (source / "app.py").chmod(0o755)
        self.project = application.Snapshot.freeze(source, self.root / "project-snapshot")
        skills = self.root / "skills/guide"
        skills.mkdir(parents=True)
        (skills / "SKILL.md").write_text("Use the project tests.")
        self.skills = application.Snapshot.freeze(skills.parent, self.root / "skills-snapshot")
        self.request = application.Request(application.Runtime("namespace/prepared:test", "requested-model", "high", 1), self.project, self.skills, "Implement the task.")
        self.addCleanup(mock.patch.stopall)
        mock.patch.object(application, "REMOTE", str(self.root / "remote")).start()
        self.bin = self.root / "bin"
        self.bin.mkdir()
        mock.patch.dict(os.environ, {"PATH": str(self.bin) + os.pathsep + os.environ["PATH"]}).start()

    def native(self, mode):
        script = '''#!/usr/bin/env python3
import json, os, pathlib, subprocess, sys, time
if sys.argv[1:] == ['--version']:
    print('codex-cli 0.162.0')
elif sys.argv[1:] == ['exec', '--help']:
    print('--ignore-user-config --ignore-rules --json')
elif sys.argv[1:] == ['features', 'list']:
    print('multi_agent stable true')
else:
    mode = MODE
    if mode == 'mcp_config_validation':
        servers = {}
        for index, argument in enumerate(sys.argv[:-1]):
            if argument == '-c':
                key, _, value = sys.argv[index + 1].partition('=')
                if key == 'mcp_servers':
                    servers = json.loads(value)
                elif key.startswith('mcp_servers.'):
                    name, field = key[len('mcp_servers.'):].rsplit('.', 1)
                    servers.setdefault(name, {})[field] = json.loads(value)
        if any(not any(key in server for key in ('url', 'command')) for server in servers.values()):
            print('invalid transport', file=sys.stderr)
            sys.exit(1)
    if mode == 'preserve_inputs':
        print(json.dumps({'type': 'turn.completed'}))
        sys.exit(0)
    root = pathlib.Path.cwd()
    (root.parent / 'native-record.json').write_text(json.dumps({'argv': sys.argv[1:], 'home': os.environ['HOME'], 'codex_home': os.environ['CODEX_HOME'], 'gh': os.environ.get('GH_TOKEN'), 'prompt': sys.stdin.read()}))
    (root / 'app.py').write_text('implemented')
    (root / 'app.py').chmod(0o700)
    (root / 'old.txt').unlink()
    (root / 'new.txt').write_text('new data')
    if mode == 'timeout':
        child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'])
        (root.parent / 'child.pid').write_text(str(child.pid))
        time.sleep(30)
    if mode == 'malformed':
        print('not a native event')
    elif mode == 'missing_terminal':
        print(json.dumps({'type': 'thread.started', 'thread_id': 'test'}))
    else:
        print(json.dumps({'type': 'turn.completed', 'usage': {'input_tokens': 12, 'output_tokens': 3}}))
    sys.exit(7 if mode == 'nonzero' else 0)
'''.replace("MODE", repr(mode))
        path = self.bin / "codex"
        path.write_text(script)
        path.chmod(0o755)

    def run_attempt(self, mode="success", slot="attempt"):
        self.native(mode)
        transport = RecordingTransport(self, mode)
        with mock.patch.object(application, "_command", transport):
            result = application.run_application(self.request, self.root / slot)
        return result, transport

    def test_success_records_native_facts_and_replays_complete_application(self):
        result, transport = self.run_attempt()
        self.assertEqual((result.state, result.native_valid, result.usage), ("completed", True, {"input_tokens": 12, "output_tokens": 3}))
        replay = application.replay(result.capture, self.root / "replayed")
        self.assertEqual({p.name: p.read_text() for p in replay.iterdir()}, {"app.py": "implemented", "new.txt": "new data"})
        self.assertEqual(stat.S_IMODE((replay / "app.py").stat().st_mode), 0o700)
        record = json.loads((self.root / "attempt/staging/native-record.json").read_text())
        self.assertEqual((record["home"], record["codex_home"], record["gh"], record["prompt"]), (application.REMOTE + "-home", application.REMOTE + "-home/.codex", None, "Implement the task."))
        self.assertIn('features.multi_agent=true', record["argv"])
        self.assertIn('features.apps=false', record["argv"])
        self.assertIn('features.hooks=false', record["argv"])
        self.assertIn('features.skip_host_skill_discovery=true', record["argv"])
        receipt = json.loads(result.receipt.read_text())
        self.assertEqual((receipt["cleanup_confirmed"], receipt["observed_model"], receipt["setup"]["cli_version"]), (True, None, "codex-cli 0.162.0"))
        self.assertGreater(result.native_elapsed_s, 0)
        self.assertLess(result.native_elapsed_s, result.elapsed_s)
        self.assertEqual(receipt["native_elapsed_s"], result.native_elapsed_s)
        self.assertEqual([c[0][1] for c in transport.commands if c[0][0] == "sbx"][-2:], ["rm", "ls"])
        self.assertTrue(all(timeout > 0 for _, timeout in transport.commands))

    def test_interrupt_preserves_capture_without_accepting_native_success(self):
        for mode in ("interrupt_before_status", "interrupt_after_status"):
            with self.subTest(mode=mode), mock.patch.object(application, "REMOTE", str(self.root / mode)):
                result, _ = self.run_attempt(mode, mode)
            self.assertEqual((result.state, result.native_valid), ("interrupted", False))
            self.assertIsNotNone(result.capture)
            self.assertTrue(json.loads(result.receipt.read_text())["cleanup_confirmed"])
            if mode == "interrupt_before_status":
                self.assertIsNone(result.native_elapsed_s)

    def test_clone_restores_exact_modes_for_both_inputs(self):
        for snapshot in (self.project, self.skills):
            source = self.root / (snapshot.directory.name + "-writable")
            application.replay(snapshot, source)
            for path in source.rglob("*"):
                path.chmod(0o770 if path.is_dir() else 0o640)
            replacement = application.Snapshot.freeze(source, self.root / (snapshot.directory.name + "-mixed"))
            if snapshot == self.project:
                self.project = replacement
            else:
                self.skills = replacement
        self.request = application.Request(self.request.runtime, self.project, self.skills, self.request.prompt)
        result, transport = self.run_attempt("preserve_inputs")
        self.assertEqual((result.state, result.native_valid), ("completed", True))
        self.assertEqual(application._scan(self.root / "attempt/staging/.agents/skills"), application._inventory(self.skills))
        self.assertEqual(application._scan(self.root / "attempt/staging/project"), application._inventory(self.project))
        observed = json.loads(result.receipt.read_text())["setup"]["clone_inventories"]
        for key in ("project", "skills"):
            self.assertEqual({e["path"]: e["mode"] for e in observed[key]}, transport.before_restore_modes[key])
            self.assertTrue(all(e["mode"] & 0o020 for e in observed[key]))
        self.assertNotEqual({e["path"]: e["mode"] for e in observed["project"]}["app.py"], 0o640)

    def test_clone_rejects_path_and_content_changes_in_both_inputs(self):
        for tree in ("project", "skills"):
            for change in ("content", "path"):
                mode = "clone_" + change + "_" + tree
                with self.subTest(mode=mode), mock.patch.object(application, "REMOTE", str(self.root / mode)):
                    result, transport = self.run_attempt(mode, mode)
                self.assertEqual((result.state, result.native_valid, result.capture), ("setup_failed", False, None))
                self.assertIn("paths or content changed", json.loads(result.receipt.read_text())["error"])
                self.assertFalse(any(c[0][-2] == "run" for c in transport.commands if len(c[0]) > 2))

    def test_initial_and_maintenance_preserve_ignored_files_and_empty_directories(self):
        expected = {".gitignore": "build/\n", "build/output": "build result\n",
                    ".pytest_cache/.gitignore": "*\n", ".pytest_cache/result": "cache result\n",
                    "host-ignored.dat": "host ignored\n", "xdg-ignored.dat": "xdg ignored\n"}
        for tree, snapshot in (("project", self.project), ("skills", self.skills)):
            source = application.replay(snapshot, self.root / (tree + "-with-cache"))
            for name, content in expected.items():
                path = source / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content)
            (source / "empty/nested").mkdir(parents=True)
            (source / "empty").chmod(0o750)
            (source / "empty/nested").chmod(0o770)
            frozen = application.Snapshot.freeze(source, self.root / (tree + "-with-cache-snapshot"))
            if tree == "project":
                self.project = frozen
            else:
                self.skills = frozen
        host = self.root / "host"
        (host / ".config/git").mkdir(parents=True)
        (host / ".config/git/ignore").write_text("xdg-ignored.dat\n")
        excludes = host / "excludes"
        excludes.write_text("host-ignored.dat\n")
        config = host / ".gitconfig"
        config.write_text('[core]\nexcludesFile = ' + json.dumps(str(excludes)) + '\n[commit]\ngpgsign = true\n[gpg]\nprogram = /nonexistent-canon-signing-program\n')
        self.request = application.Request(self.request.runtime, self.project, self.skills, self.request.prompt)
        with mock.patch.dict(os.environ, {"HOME": str(host), "XDG_CONFIG_HOME": str(host / ".config"),
                                         "GIT_CONFIG_GLOBAL": str(config), "GIT_CONFIG_NOSYSTEM": "1"}):
            for phase in ("initial", "maintenance"):
                with self.subTest(phase=phase), mock.patch.object(application, "REMOTE", str(self.root / phase)):
                    result, _ = self.run_attempt("preserve_inputs", phase)
                self.assertEqual((result.state, result.native_valid), ("completed", True))
                replayed = application.replay(result.capture, self.root / (phase + "-replay"))
                for tree in (replayed, self.root / phase / "staging/.agents/skills"):
                    for name, content in expected.items():
                        self.assertEqual((tree / name).read_text(), content)
                    self.assertEqual(list((tree / "empty/nested").iterdir()), [])
                    self.assertEqual(stat.S_IMODE((tree / "empty").stat().st_mode), 0o750)
                    self.assertEqual(stat.S_IMODE((tree / "empty/nested").stat().st_mode), 0o770)
                self.request = application.Request(self.request.runtime, result.capture, self.skills, self.request.prompt)

    def test_initial_and_maintenance_preserve_bytes_despite_nested_and_host_attributes(self):
        expected = {".gitattributes": b"*.txt text eol=crlf\n*.id ident\n",
                    "lf.txt": b"alpha\nbeta\n", "crlf.txt": b"one\r\ntwo\r\n",
                    "marker.id": b"$Id$\n", "global.host": b"host line\n",
                    "nested/.gitattributes": b"* text=auto eol=lf\n",
                    "nested/lf.txt": b"nested line\n", "nested/crlf.txt": b"nested line\r\n"}
        for tree, snapshot in (("project", self.project), ("skills", self.skills)):
            source = application.replay(snapshot, self.root / (tree + "-attributes"))
            for name, content in expected.items():
                path = source / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(content)
            frozen = application.Snapshot.freeze(source, self.root / (tree + "-attributes-snapshot"))
            if tree == "project":
                self.project = frozen
            else:
                self.skills = frozen
        host = self.root / "attribute-host"
        (host / "git").mkdir(parents=True)
        (host / "git/attributes").write_text("*.host text eol=crlf\n")
        self.request = application.Request(self.request.runtime, self.project, self.skills, self.request.prompt)
        with mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": str(host)}):
            for phase in ("initial", "maintenance"):
                with self.subTest(phase=phase), mock.patch.object(application, "REMOTE", str(self.root / phase)):
                    result, transport = self.run_attempt("preserve_inputs", phase)
                self.assertEqual((result.state, result.native_valid), ("completed", True))
                replayed = application.replay(result.capture, self.root / (phase + "-attributes-replay"))
                for key, tree in (("project", replayed), ("skills", self.root / phase / "staging/.agents/skills")):
                    self.assertEqual(transport.cloned_files[key]["lf.txt"], b"alpha\r\nbeta\r\n")
                    self.assertEqual(transport.cloned_files[key]["global.host"], b"host line\r\n")
                    for name, content in expected.items():
                        self.assertEqual((tree / name).read_bytes(), content)
                self.request = application.Request(self.request.runtime, result.capture, self.skills, self.request.prompt)

    def test_staging_ignores_inherited_git_repository_and_config_redirection(self):
        redirected = self.root / "redirected"
        redirected.mkdir()
        (redirected / "sentinel").write_bytes(b"unrelated repository data")
        env = {"GIT_DIR": str(redirected / "metadata"), "GIT_WORK_TREE": str(redirected),
               "GIT_INDEX_FILE": str(redirected / "index"), "GIT_COMMON_DIR": str(redirected / "common"),
               "GIT_OBJECT_DIRECTORY": str(redirected / "objects"), "GIT_CONFIG": str(redirected / "config"),
               "GIT_CONFIG_GLOBAL": str(redirected / "global-config"), "GIT_CONFIG_SYSTEM": str(redirected / "system-config"),
               "GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "commit.gpgsign", "GIT_CONFIG_VALUE_0": "true",
               "GIT_CONFIG_PARAMETERS": "'gpg.program'='/nonexistent-canon-signing-program'"}
        with mock.patch.dict(os.environ, env):
            result, _ = self.run_attempt("preserve_inputs")
        self.assertEqual((result.state, result.native_valid), ("completed", True))
        self.assertEqual({p.name: p.read_bytes() for p in redirected.iterdir()}, {"sentinel": b"unrelated repository data"})

    def test_entirely_empty_project_and_guidance_trees_survive_clone(self):
        source = self.root / "empty-source"
        source.mkdir()
        empty = application.Snapshot.freeze(source, self.root / "empty-snapshot")
        self.request = application.Request(self.request.runtime, empty, empty, self.request.prompt)
        result, _ = self.run_attempt("preserve_inputs")
        self.assertEqual((result.state, result.native_valid), ("completed", True))
        self.assertEqual(list(application.replay(result.capture, self.root / "empty-replay").iterdir()), [])

    def test_template_short_alias_is_rejected_but_exact_id_is_accepted(self):
        for template, expected in (("prepared:test", "setup_failed"), ("abc", "completed")):
            self.request = application.Request(application.Runtime(template, "requested-model", "high", 1), self.project, self.skills, self.request.prompt)
            with self.subTest(template=template), mock.patch.object(application, "REMOTE", str(self.root / template)):
                result, _ = self.run_attempt(slot=template)
            self.assertEqual(result.state, expected)

    def test_native_arm_has_no_assigned_skill_tree(self):
        self.request = application.Request(self.request.runtime, self.project, None, self.request.prompt)
        result, _ = self.run_attempt()
        self.assertEqual((result.state, result.native_valid), ("completed", True))
        self.assertFalse((self.root / "attempt/staging/.agents").exists())
        self.assertEqual(application.replay(result.capture, self.root / "native-replay").joinpath("app.py").read_text(), "implemented")

    def test_mcp_configuration_allows_native_application(self):
        result, _ = self.run_attempt("mcp_config_validation")
        self.assertEqual((result.state, result.native_valid), ("completed", True))
        replay = application.replay(result.capture, self.root / "mcp-replay")
        self.assertEqual((replay / "app.py").read_text(), "implemented")

    def test_native_failures_keep_a_valid_capture_for_maintenance(self):
        for mode in ("nonzero", "malformed", "missing_terminal", "timeout", "outer_timeout"):
            with self.subTest(mode=mode):
                remote = str(self.root / mode)
                with mock.patch.object(application, "REMOTE", remote):
                    result, _ = self.run_attempt(mode, mode + "-attempt")
                self.assertEqual(result.native_valid, False)
                self.assertEqual(result.state, "timeout" if "timeout" in mode else "native_failed")
                replay = application.replay(result.capture, self.root / (mode + "-replay"))
                self.assertEqual((replay / "app.py").read_text(), "original" if mode == "outer_timeout" else "implemented")
                if mode == "timeout":
                    self.assert_process_stopped(int((self.root / (mode + "-attempt/staging/child.pid")).read_text()))

    def test_spent_slot_does_not_create_or_retry_a_sandbox(self):
        slot = self.root / "spent"
        slot.mkdir()
        with mock.patch.object(application, "_command", side_effect=AssertionError("must not run")):
            with self.assertRaises(application.SpentAttemptError):
                application.run_application(self.request, slot)
        self.assertEqual(list(slot.iterdir()), [])

    def test_policy_transport_failure_cannot_count_as_denial(self):
        result, transport = self.run_attempt("policy_error")
        self.assertEqual((result.state, result.native_valid, result.capture), ("setup_failed", False, None))
        self.assertEqual(json.loads(result.receipt.read_text())["error"], "sandbox lacks default-deny network policy")
        self.assertFalse((self.root / "attempt/staging/native-record.json").exists())
        self.assertEqual([c[0][1] for c in transport.commands if c[0][0] == "sbx"][-2:], ["rm", "ls"])

    def test_cleanup_failure_cannot_be_native_success(self):
        result, _ = self.run_attempt("cleanup_failure")
        self.assertEqual((result.state, result.native_valid, result.capture), ("cleanup_failed", False, None))
        receipt = json.loads(result.receipt.read_text())
        self.assertEqual(receipt["cleanup_confirmed"], False)
        private_capture = application.Snapshot(Path(receipt["capture"]["directory"]), receipt["capture"]["sha256"])
        self.assertEqual(application.replay(private_capture, self.root / "replayed").joinpath("new.txt").read_text(), "new data")

    def test_changed_assigned_guidance_invalidates_attempt(self):
        result, _ = self.run_attempt("guidance_changed")
        self.assertEqual((result.state, result.native_valid), ("capture_failed", False))
        self.assertEqual(json.loads(result.receipt.read_text())["error"], "assigned guidance changed")

    def test_parent_capture_is_the_exact_next_application_input(self):
        first, _ = self.run_attempt()
        parent = application.replay(first.capture, self.root / "maintenance-parent")
        self.assertEqual((parent / "app.py").read_text(), "implemented")
        self.assertFalse((parent / "old.txt").exists())
        second = application.Snapshot.freeze(parent, self.root / "maintenance-snapshot")
        self.assertEqual(second.sha256, first.capture.sha256)

    def test_tampered_input_fails_before_native_effects_and_spends_slot(self):
        blob = next((self.skills.directory / "blobs").iterdir())
        blob.chmod(0o644)
        blob.write_text("tampered")
        blob.chmod(0o444)
        with mock.patch.object(application, "_command", side_effect=AssertionError("must not run")):
            result = application.run_application(self.request, self.root / "tampered")
        self.assertEqual((result.state, result.native_valid, result.capture), ("setup_failed", False, None))
        self.assertIn("digest mismatch", json.loads(result.receipt.read_text())["error"])

    def test_snapshot_rejects_unsafe_entries_and_size_excess(self):
        for kind in ("symlink", "fifo", "oversize"):
            source = self.root / kind
            source.mkdir()
            path = source / "bad"
            if kind == "symlink":
                path.symlink_to(self.root / "source/app.py")
            elif kind == "fifo":
                os.mkfifo(path)
            else:
                with path.open("wb") as handle:
                    handle.truncate(application.MAX_FILE_BYTES + 1)
            with self.subTest(kind=kind), self.assertRaises(application.ApplicationError):
                application.Snapshot.freeze(source, self.root / (kind + "-snapshot"))

    def test_replay_rejects_content_and_manifest_mode_tampering(self):
        blob = next((self.project.directory / "blobs").iterdir())
        blob.chmod(0o644)
        blob.write_bytes(b"corrupted")
        blob.chmod(0o444)
        with self.assertRaisesRegex(application.ApplicationError, "blob digest mismatch"):
            application.replay(self.project, self.root / "bad-replay")
        self.assertFalse((self.root / "bad-replay").exists())
        manifest = self.skills.directory / "manifest.json"
        manifest.chmod(0o644)
        entries = json.loads(manifest.read_text())
        entries[-1]["mode"] = 0o777
        manifest.write_text(json.dumps(entries))
        manifest.chmod(0o444)
        with self.assertRaisesRegex(application.ApplicationError, "manifest digest mismatch"):
            application.replay(self.skills, self.root / "mode-replay")


    def test_duplicate_contents_share_storage_and_replay_both_modes(self):
        source = self.root / "duplicates"
        source.mkdir()
        for name, mode in (("one", 0o644), ("two", 0o755)):
            (source / name).write_text("same")
            (source / name).chmod(mode)
        snapshot = application.Snapshot.freeze(source, self.root / "duplicates-snapshot")
        replayed = application.replay(snapshot, self.root / "duplicates-replay")
        self.assertEqual([(p.name, p.read_text(), stat.S_IMODE(p.stat().st_mode)) for p in sorted(replayed.iterdir())], [("one", "same", 0o644), ("two", "same", 0o755)])
        self.assertEqual(len(list((snapshot.directory / "blobs").iterdir())), 1)

    def test_snapshot_store_modes_cannot_be_mutated(self):
        blob = next((self.project.directory / "blobs").iterdir())
        blob.chmod(0o644)
        with self.assertRaisesRegex(application.ApplicationError, "blob mode mismatch"):
            application.replay(self.project, self.root / "mutable-replay")
        self.assertFalse((self.root / "mutable-replay").exists())

    def test_harvest_rejects_traversal_and_symlinks_before_writing(self):
        for kind in ("traversal", "symlink"):
            archive = self.root / (kind + ".tar")
            with tarfile.open(archive, "w") as tar:
                info = tarfile.TarInfo("../escape" if kind == "traversal" else "link")
                if kind == "symlink":
                    info.type = tarfile.SYMTYPE
                    info.linkname = "/etc/passwd"
                tar.addfile(info)
            destination = self.root / (kind + "-unpacked")
            with self.subTest(kind=kind), self.assertRaises(application.ApplicationError):
                application._unpack(archive, destination)
            self.assertFalse(destination.exists())

    def assert_process_stopped(self, pid):
        status = subprocess.run(["ps", "-o", "stat=", "-p", str(pid)], capture_output=True, text=True, timeout=2)
        self.assertTrue(status.returncode == 1 or status.stdout.strip().startswith("Z"), status.stdout)

    def test_outer_deadline_kills_the_host_process_group(self):
        pid_file = self.root / "outer-child.pid"
        script = "import pathlib,subprocess,sys,time; p=subprocess.Popen([sys.executable,'-c','import time; time.sleep(30)']); pathlib.Path(sys.argv[1]).write_text(str(p.pid)); time.sleep(30)"
        with self.assertRaises(subprocess.TimeoutExpired):
            application._command([sys.executable, "-c", script, pid_file], timeout=0.3)
        self.assert_process_stopped(int(pid_file.read_text()))


if __name__ == "__main__":
    unittest.main()
