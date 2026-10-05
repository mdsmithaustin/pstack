import json
import copy
import os
import platform
import signal
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

import live
import oracles
import grade_boundary
from grade_boundary import GradeRefused, _Root, _Controller, _authorize_fixture, _authorize_retained, _before_turns, _seal

NATIVE = (platform.system(), platform.release(), platform.machine()) == ("Darwin", "25.6.0", "arm64")


class RuntimeAdmission(unittest.TestCase):
    def test_both_supported_git_digests_pass_and_unknown_digest_is_refused(self):
        git = Path("/Library/Developer/CommandLineTools/usr/bin/git")
        pins = tuple(pin for pin in grade_boundary.PINS if pin[0] == git)
        with mock.patch.object(grade_boundary, "PINS", pins), \
                mock.patch.object(grade_boundary.platform, "system", return_value="Darwin"), \
                mock.patch.object(grade_boundary.platform, "release", return_value="25.6.0"), \
                mock.patch.object(grade_boundary.platform, "machine", return_value="arm64"), \
                mock.patch.object(Path, "is_symlink", return_value=False), \
                mock.patch.object(Path, "is_file", return_value=True), \
                mock.patch.object(Path, "exists", return_value=True), \
                mock.patch.object(Path, "read_bytes", return_value=b"mock Git executable"), \
                mock.patch.object(grade_boundary.hashlib, "sha256") as hashed:
            for digest in ("a73bf622a2e470d5d57a4b1d5aef1e8680e67278018d4858a2f93825b7d595c7",
                           "be4afb2b003904725826250de9fb76567bbacf82323457b5a1ec26706b66bcae"):
                with self.subTest(digest=digest):
                    hashed.return_value.hexdigest.return_value = digest
                    self.assertIsNone(grade_boundary._runtime())
            hashed.return_value.hexdigest.return_value = "0" * 64
            with self.assertRaisesRegex(GradeRefused, "runtime fingerprint changed"):
                grade_boundary._runtime()


class BoundaryFixtures(unittest.TestCase):
    def setUp(self):
        retained = os.environ.get("PSTACK_GRADE_TEST_ARTIFACTS")
        if retained:
            self.assets = Path(tempfile.mkdtemp(prefix=self._testMethodName + "-", dir=retained)).resolve()
        else:
            temporary = tempfile.TemporaryDirectory(prefix="pstack-parent-grade-")
            self.addCleanup(temporary.cleanup)
            self.assets = Path(temporary.name).resolve()
        self.out = self.assets / "runs"
        self.root = self.out / "run"
        self.root.mkdir(parents=True)
        self.project = self.root / "w" / "project"
        self.project.mkdir(parents=True)
        self.outside = self.assets / "outside"
        self.outside.mkdir()
        self.read_marker = self.outside / "read-marker.txt"
        self.read_marker.write_bytes(b"private-canary-42\n")
        self.write_marker = self.outside / "write-marker.txt"
        self.write_marker.write_bytes(b"outside-original\n")

    def record(self, case, *, baseline=None):
        record = {"harness": "codex", "case": case["id"], "skills_at": "synthetic-no-model", "project": str(self.project)}
        if baseline is not None:
            record["baseline"] = baseline
        return record

    def trace(self):
        return {"harness": "codex", "exit_code": 0, "events": [], "worklist": [], "spawns": [],
                "final_reply": "Done.", "files_read": ["skills/deslop/SKILL.md"]}

    def git(self, *args, project=None):
        return live.git_run(project or self.project, *args, capture_output=True, text=True).stdout

    def repository(self, files=None):
        for name, data in (files or {"a.py": b"value = 1\n"}).items():
            target = self.project / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        self.git("init", "-q", "-b", "main")
        self.git("add", "-A")
        self.git("commit", "-qm", "initial import")
        return live.baseline(self.project)

    def authority(self, case=None, trace=None, *, record=None, worktrees=(), output=None):
        case = case or live.load_case("no-comments-run")
        return _authorize_fixture(self.root, self.project, case, record or self.record(case), trace or self.trace(),
                                  worktrees=worktrees, output=output)

    def deslop(self, checks=()):
        case = live.load_case("deslop-run")
        case.pop("history", None)
        case["expect"] = {"checks": list(checks)}
        return case


class ControllerBoundary(BoundaryFixtures):
    def test_concurrent_first_initializers_preserve_both_registered_authorizations(self):
        script = self.assets / "initialize.py"
        script.write_text("import sys, time\nfrom pathlib import Path\n"
            f"sys.path.insert(0, {str(live.HERE)!r})\n"
            "from grade_boundary import _Controller, _Root\n"
            "assets, actor = Path(sys.argv[1]), sys.argv[2]\n"
            "read = _Root.read\n"
            "def paused_read(self, name):\n"
            " try: return read(self, name)\n"
            " except FileNotFoundError:\n"
            "  if name == 'key.json':\n"
            "   (assets / ('missing-' + actor)).touch()\n"
            "   if actor == '1':\n"
            "    deadline = time.monotonic() + 10\n"
            "    while not (assets / 'release').exists():\n"
            "     if time.monotonic() >= deadline: raise TimeoutError('initializer release missing')\n"
            "     time.sleep(0.01)\n"
            "  raise\n"
            "_Root.read = paused_read\n"
            "(assets / ('started-' + actor)).touch()\n"
            "controller = _Controller(assets / 'shared-out', create=True)\n"
            "controller.save({'id': actor * 32, 'actor': actor})\n"
            "print(actor)\n")
        processes = []
        try:
            for actor, marker in (("1", "missing-1"), ("2", "started-2")):
                process = subprocess.Popen([live.sys.executable, str(script), str(self.assets), actor],
                                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                processes.append(process)
                deadline = time.monotonic() + 5
                while not (self.assets / marker).exists() and process.poll() is None and time.monotonic() < deadline:
                    time.sleep(0.01)
                self.assertTrue((self.assets / marker).exists(), f"initializer {actor} did not reach {marker}")
            try:
                processes[1].communicate(timeout=1)
            except subprocess.TimeoutExpired:
                pass
            (self.assets / "release").touch()
            for actor, process in zip(("1", "2"), processes):
                stdout, stderr = process.communicate(timeout=5)
                (self.assets / f"initializer-{actor}.stdout").write_text(stdout)
                (self.assets / f"initializer-{actor}.stderr").write_text(stderr)
                self.assertEqual(process.returncode, 0, stderr)
                self.assertEqual(stdout, actor + "\n")
            controller = _Controller(self.assets / "shared-out")
            self.addCleanup(controller.root.close)
            states = [controller.load(actor * 32)[1] for actor in ("1", "2")]
            self.assertEqual(states, [{"id": "1" * 32, "actor": "1"}, {"id": "2" * 32, "actor": "2"}])
        finally:
            (self.assets / "release").touch()
            for process in processes:
                if process.poll() is None:
                    process.kill()
                process.communicate()

    def test_raw_run_storage_cannot_overlap_any_candidate_writable_root(self):
        case = self.deslop()
        output = self.assets / "diagnostic"
        output.mkdir()
        controller = _Controller(self.out, create=True)
        self.addCleanup(controller.root.close)
        for project, worktrees, allocations in ((self.root, (), ()), (self.root.parent, (), ()),
                                                 (self.project, (self.root,), ()), (self.project, (), (self.out,))):
            with self.subTest(project=project, worktrees=worktrees, allocations=allocations), \
                 self.assertRaisesRegex(GradeRefused, "raw run storage overlaps"):
                controller.issue(self.root, project, case, {**self.record(case), "project": str(project)},
                                 worktrees=worktrees, allocations=allocations, output=output)

    def test_turn_projection_preserves_trusted_fields_and_rejects_other_shapes(self):
        case = self.deslop()
        turns = [{"index": 0, "session_id": "session-0", "argv": ["codex", "first"], "exit_code": 0,
                  "timed_out": False, "duration_s": 0.25, "stream": "transport-0"},
                 {"index": 1, "session_id": "session-1", "argv": ["codex", "second"], "exit_code": -9,
                  "timed_out": True, "duration_s": 0.5, "stream": "transport-1"}]
        projected = [{"index": 0, "session_id": "session-0", "argv": ["codex", "first"], "exit_code": 0,
                      "timed_out": False, "duration_s": 0.25},
                     {"index": 1, "session_id": "session-1", "argv": ["codex", "second"], "exit_code": -9,
                      "timed_out": True, "duration_s": 0.5}]
        for harness in ("codex", "grok", "claude-code", "hermes"):
            record = {**self.record(case), "harness": harness, "turns": turns, "baseline": ["trusted-base"]}
            authority = self.authority(case, {**self.trace(), "harness": harness}, record=record)
            _seal(authority, record, {**self.trace(), "harness": harness, "x_turns": turns})
            if harness not in ("codex", "grok"):
                with self.assertRaisesRegex(GradeRefused, "x_turns conflicts"):
                    _seal(authority, record, {**self.trace(), "x_turns": projected})
                continue
            _seal(authority, record, {**self.trace(), "x_turns": projected})
            self.assertEqual(json.loads((self.root / "trace.json").read_text())["x_turns"], projected)
            mutations = []
            for key, value in (("index", 4), ("session_id", "forged"), ("argv", ["codex", "forged"]),
                               ("exit_code", 7), ("exit_code", False), ("timed_out", True), ("timed_out", 0),
                               ("duration_s", 1.25)):
                changed = copy.deepcopy(projected)
                changed[0][key] = value
                mutations.append(changed)
            for key in projected[0]:
                changed = copy.deepcopy(projected)
                del changed[0][key]
                mutations.append(changed)
            mutations.extend([list(reversed(projected)), projected[:1], projected + [projected[0]],
                              [{**projected[0], "extra": "untrusted"}, projected[1]], {"0": projected[0]}])
            for changed in mutations:
                with self.subTest(harness=harness, turns=changed), self.assertRaisesRegex(GradeRefused, "x_turns conflicts"):
                    _seal(authority, record, {**self.trace(), "x_turns": changed})
            with self.assertRaisesRegex(GradeRefused, "x_baseline conflicts"):
                _seal(authority, record, {**self.trace(), "x_turns": projected, "x_baseline": ["forged-base"]})
            with self.assertRaisesRegex(GradeRefused, "pre-turn controller metadata"):
                _seal(authority, {**record, "baseline": ["forged-base"]}, self.trace())

    def test_a_path_cannot_issue_grade_authority(self):
        with self.assertRaisesRegex(GradeRefused, "path-based grading"):
            live.grade(self.root)
        self.assertEqual(self.write_marker.read_bytes(), b"outside-original\n")

    def test_record_project_cannot_expand_trusted_fixture_authority(self):
        case = live.load_case("no-comments-run")
        record = {**self.record(case), "project": str(self.outside)}
        with self.assertRaisesRegex(GradeRefused, "record project differs"):
            self.authority(case, record=record)
        self.assertEqual(self.read_marker.read_bytes(), b"private-canary-42\n")

    def test_controller_reader_rejects_symlinks_hardlinks_and_traversal(self):
        (self.project / "safe.txt").write_bytes(b"inside-positive\n")
        (self.project / "link.txt").symlink_to(self.read_marker)
        os.link(self.read_marker, self.project / "hard.txt")
        root = _Root.open(self.project)
        self.addCleanup(root.close)
        self.assertEqual(root.read("safe.txt"), b"inside-positive\n")
        for name in ("link.txt", "hard.txt", "../../outside/read-marker.txt"):
            with self.subTest(name=name), self.assertRaises(GradeRefused):
                root.read(name)

    def test_controller_publication_rejects_output_substitution(self):
        root = _Root.open(self.root)
        self.addCleanup(root.close)
        root.write("safe.json", b"inside-positive\n")
        self.assertEqual((self.root / "safe.json").read_bytes(), b"inside-positive\n")
        (self.root / "verdict.json").symlink_to(self.write_marker)
        with self.assertRaises(GradeRefused):
            root.write("verdict.json", b"changed\n")
        self.assertEqual(self.write_marker.read_bytes(), b"outside-original\n")

    def test_filesystem_errors_refuse_and_missing_inputs_stay_optional(self):
        (self.project / "safe.txt").write_bytes(b"inside-positive\n")
        root = _Root.open(self.project)
        self.addCleanup(root.close)
        self.assertEqual(root.info("safe.txt").st_size, 16)
        self.assertEqual(root.files(), [self.project / "safe.txt"])
        for operation, syscall in ((lambda: root.info("safe.txt"), "stat"),
                                   (root.files, "listdir"), (root.files, "stat")):
            with self.subTest(syscall=syscall), mock.patch("grade_boundary.os." + syscall,
                    side_effect=PermissionError("owned filesystem denial")):
                with self.assertRaises(GradeRefused) as refused:
                    operation()
                self.assertEqual(refused.exception.receipt["reason"], "unsafe_link")
        for operation in (root.info, root.read):
            with self.subTest(operation=operation.__name__), self.assertRaises(FileNotFoundError):
                operation("absent.txt")
        with mock.patch("grade_boundary.os.listdir", side_effect=TypeError("programming error")):
            with self.assertRaisesRegex(TypeError, "programming error"):
                root.files()
        self.assertEqual(root.read("safe.txt"), b"inside-positive\n")

    def test_publication_syscall_errors_refuse_before_replacing_prior_bytes(self):
        root = _Root.open(self.root)
        self.addCleanup(root.close)
        root.write("verdict.json", b"prior-verdict\n")
        original_open = os.open

        def denied_write_open(path, flags, *args, **kwargs):
            if flags & os.O_WRONLY:
                raise PermissionError("owned publication denial")
            return original_open(path, flags, *args, **kwargs)

        for syscall, failure in (("open", denied_write_open),
                                 ("fsync", OSError("owned publication I/O failure")),
                                 ("rename", PermissionError("owned publication denial"))):
            with self.subTest(syscall=syscall), mock.patch("grade_boundary.os." + syscall, side_effect=failure):
                with self.assertRaises(GradeRefused) as refused:
                    root.write("verdict.json", b"replacement-verdict\n")
                self.assertEqual(refused.exception.receipt["reason"], "output_unsafe")
            self.assertEqual((self.root / "verdict.json").read_bytes(), b"prior-verdict\n")
            self.assertEqual(root.files(), [self.root / "verdict.json"])
        root.write("verdict.json", b"replacement-verdict\n")
        self.assertEqual((self.root / "verdict.json").read_bytes(), b"replacement-verdict\n")

    def test_controller_detects_root_and_ancestor_replacement(self):
        root = _Root.open(self.project)
        self.addCleanup(root.close)
        parent = self.project.parent
        parent.rename(parent.with_name("old-workspace"))
        self.project.mkdir(parents=True)
        with self.assertRaisesRegex(GradeRefused, "root_replaced"):
            root.read("a.py")

    def test_candidate_manifest_cannot_change_controller_grants(self):
        authority = self.authority()
        controller = authority._controller
        path = controller.root.path / f"{authority._id}.json"
        envelope = json.loads(path.read_bytes())
        envelope["payload"]["project"]["path"] = str(self.outside)
        path.write_text(json.dumps(envelope))
        with self.assertRaisesRegex(GradeRefused, "signature does not match"):
            controller.load(authority._id)

    def test_unsupported_platform_refuses_without_an_unconfined_grade(self):
        authority = self.authority()
        with mock.patch("grade_boundary.platform.system", return_value="Linux"):
            with self.assertRaisesRegex(GradeRefused, "reviewed Darwin"):
                live.grade(authority)
        self.assertFalse((self.root / "verdict.json").exists())

    @unittest.skipUnless(NATIVE, "fresh admission requires the reviewed Darwin 25.6.0 arm64 runtime")
    def test_pre_turn_metadata_and_trace_augmentation_cannot_be_replaced(self):
        case = self.deslop()
        base = self.repository()
        run = live.Run(self.root, "codex", {**case, "fixture": "project"}, "fixed-pin", 60, baseline=base)
        authority = _before_turns(run)
        with self.assertRaisesRegex(GradeRefused, "pre-turn controller metadata"):
            _seal(authority, {**live.meta(run), "baseline": ["candidate-value"]}, self.trace())
        with self.assertRaisesRegex(GradeRefused, "x_baseline conflicts"):
            _seal(authority, live.meta(run), {**self.trace(), "x_baseline": ["candidate-value"]})
        with self.assertRaisesRegex(GradeRefused, "x_turns conflicts"):
            _seal(authority, live.meta(run), {**self.trace(), "x_turns": [{"exit_code": 0}]})

    def test_unknown_cli_run_id_refuses_without_loading_record_paths(self):
        controller = _Controller(self.out, create=True)
        with mock.patch("sys.stderr") as error:
            code = live.main(["grade", "--out", str(self.out), "0" * 32])
        self.assertEqual(code, 2)
        self.assertIn("unknown_authorization", "".join(c.args[0] for c in error.write.call_args_list))
        controller.root.close()


@unittest.skipUnless(NATIVE, "native parent grading requires the reviewed Darwin 25.6.0 arm64 runtime")
class NativeParentBoundary(BoundaryFixtures):
    def test_project_traversal_errors_return_cli_refusal_receipts(self):
        case = self.deslop()
        base = self.repository()
        authority = self.authority(case, record=self.record(case, baseline=base))
        positive = live.grade(authority)
        self.assertEqual(positive["promises"]["deslop-cleans-code-slop"]["verdict"], "PASS")
        prior = (self.root / "verdict.json").read_bytes()
        target = self.project / "unreadable"
        target.mkdir()
        (target / "owned.txt").write_bytes(b"owned-marker\n")
        target.chmod(0)
        try:
            result = subprocess.run([live.sys.executable, str(live.HERE / "live.py"), "grade", "--out", str(self.out),
                                     authority._id], capture_output=True, text=True, timeout=10)
            (self.assets / "project-traversal.stdout").write_text(result.stdout)
            (self.assets / "project-traversal.stderr").write_text(result.stderr)
            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertEqual(result.stdout, "")
            receipt = json.loads(result.stderr)["refusal"]
            self.assertEqual(receipt["reason"], "unsafe_link")
            self.assertEqual(receipt["run_id"], authority._id)
            self.assertEqual(json.loads((Path(receipt["attempt"]) / "refusal.json").read_text()), receipt)
            self.assertEqual((self.root / "verdict.json").read_bytes(), prior)
        finally:
            target.chmod(0o700)
        self.assertEqual((target / "owned.txt").read_bytes(), b"owned-marker\n")

    def test_malformed_registered_worktree_metadata_returns_cli_refusal_receipts(self):
        base = self.repository()
        sibling = self.assets / "approved-sibling"
        self.git("worktree", "add", "-q", "-b", "sibling", str(sibling))
        case = self.deslop()
        authority = self.authority(case, record=self.record(case, baseline=base), worktrees=(sibling,))
        positive = live.grade(authority)
        self.assertEqual(positive["promises"]["deslop-cleans-code-slop"]["verdict"], "PASS")
        prior = (self.root / "verdict.json").read_bytes()
        directory = Path((sibling / ".git").read_text().split("gitdir: ", 1)[1].strip())
        for target in (sibling / ".git", directory / "commondir", directory / "gitdir"):
            original = target.read_bytes()
            for encoding, malformed in (("utf8", b"\xff\xfe\x00owned-invalid-metadata"),
                                        ("nul", original + b"\x00owned-invalid-metadata")):
                with self.subTest(target=target, encoding=encoding):
                    backup = target.with_name(target.name + ".original")
                    target.rename(backup)
                    target.write_bytes(malformed)
                    try:
                        result = subprocess.run([live.sys.executable, str(live.HERE / "live.py"), "grade", "--out", str(self.out),
                                                 authority._id], capture_output=True, text=True, timeout=10)
                        (self.assets / f"malformed-{target.name}-{encoding}.stdout").write_text(result.stdout)
                        (self.assets / f"malformed-{target.name}-{encoding}.stderr").write_text(result.stderr)
                        self.assertEqual(result.returncode, 2, result.stderr)
                        self.assertEqual(result.stdout, "")
                        receipt = json.loads(result.stderr)["refusal"]
                        self.assertEqual(receipt["reason"], "unapproved_git")
                        self.assertEqual(receipt["run_id"], authority._id)
                        self.assertEqual(json.loads((Path(receipt["attempt"]) / "refusal.json").read_text()), receipt)
                        self.assertEqual((self.root / "verdict.json").read_bytes(), prior)
                        self.assertEqual(backup.read_bytes(), original)
                        self.assertEqual(target.read_bytes(), malformed)
                    finally:
                        target.unlink()
                        backup.rename(target)

    def test_missing_sealed_inputs_return_cli_refusal_receipts(self):
        case = self.deslop()
        base = self.repository()
        authority = self.authority(case, record=self.record(case, baseline=base))
        positive = live.grade(authority)
        self.assertEqual(positive["promises"]["deslop-cleans-code-slop"]["verdict"], "PASS")
        prior = (self.root / "verdict.json").read_bytes()
        diagnostic = self.assets / "diagnostic"
        diagnostic.mkdir()
        (diagnostic / "verdict.json").write_bytes(prior)
        retained = _authorize_retained(self.assets / "retained-out", self.root, project=self.project,
                                      original_project=self.project, output=diagnostic, case=case)
        for name in ("run.json", "trace.json", "verdict.json"):
            with self.subTest(name=name):
                target = self.root / name
                backup = target.with_name(name + ".original")
                contents = target.read_bytes()
                target.rename(backup)
                handle, out, output = ((retained, self.assets / "retained-out", diagnostic) if name == "verdict.json"
                                       else (authority, self.out, self.root))
                try:
                    result = subprocess.run([live.sys.executable, str(live.HERE / "live.py"), "grade", "--out", str(out),
                                             handle._id], capture_output=True, text=True, timeout=10)
                    (self.assets / f"missing-{name}.stdout").write_text(result.stdout)
                    (self.assets / f"missing-{name}.stderr").write_text(result.stderr)
                    self.assertEqual(result.returncode, 2, result.stderr)
                    self.assertEqual(result.stdout, "")
                    receipt = json.loads(result.stderr)["refusal"]
                    self.assertEqual(receipt["reason"], "input_changed")
                    self.assertEqual(receipt["run_id"], handle._id)
                    self.assertIn(str(target), receipt["detail"])
                    self.assertEqual(json.loads((Path(receipt["attempt"]) / "refusal.json").read_text()), receipt)
                    self.assertEqual((output / "verdict.json").read_bytes(), prior)
                    self.assertEqual(backup.read_bytes(), contents)
                    self.assertFalse(target.exists())
                finally:
                    backup.rename(target)

    def test_completed_scratch_links_and_sockets_do_not_change_repeat_grades(self):
        base = self.repository({"a.py": b"value = 1\n", "check.py":
            b"import os, socket, sys\nos.chdir(os.environ['HOME'])\n"
            b"if sys.argv[1] == 'link': os.symlink('owned-target', 'harmless-link')\n"
            b"else: s=socket.socket(socket.AF_UNIX); s.bind('harmless.sock')\nprint('inside-positive')\n"})
        for name in ("link", "socket"):
            with self.subTest(name=name):
                case = self.deslop([{"cmd": f"python3 check.py {name}", "stdout": "inside-positive\n"}])
                authority = self.authority(case, record=self.record(case, baseline=base))
                first = live.grade(authority)
                self.assertEqual(first["promises"]["deslop-cleans-code-slop"]["verdict"], "PASS")
                before = {n: (self.root / n).read_bytes() for n in ("run.json", "trace.json", "verdict.json")}
                self.assertEqual(live.grade(authority), first)
                self.assertEqual({n: (self.root / n).read_bytes() for n in before}, before)
                scratches = list((authority._controller.root.path / authority._id).glob("*/scratch"))
                self.assertEqual(len(scratches), 2)
                self.assertTrue(all((p / "harmless-link").is_symlink() if name == "link" else
                                    (p / "harmless.sock").is_socket() for p in scratches))

    def test_protected_input_links_still_refuse_on_repeat_grades(self):
        case = self.deslop()
        base = self.repository()
        authority = self.authority(case, record=self.record(case, baseline=base))
        positive = live.grade(authority)
        self.assertEqual(positive["promises"]["deslop-cleans-code-slop"]["verdict"], "PASS")
        prior = (self.root / "verdict.json").read_bytes()
        private = authority._controller.root.path / authority._id
        for name in ("code", "references", "fallback"):
            with self.subTest(name=name):
                link = private / name / "outside-link"
                link.symlink_to(self.read_marker)
                try:
                    with self.assertRaisesRegex(GradeRefused, "unsafe_link"):
                        live.grade(authority)
                    self.assertEqual((self.root / "verdict.json").read_bytes(), prior)
                    self.assertEqual(self.read_marker.read_bytes(), b"private-canary-42\n")
                finally:
                    link.unlink()

    def test_detached_descendant_pipes_do_not_block_timeout_verdicts(self):
        (self.project / "child.py").write_text("import os, pathlib, sys, time\n"
            "pathlib.Path('child-' + sys.argv[1] + '.pid').write_text(str(os.getpid()))\ntime.sleep(8)\n")
        (self.project / "parent.py").write_text("import subprocess, sys, time\n"
            "subprocess.Popen([sys.executable, 'child.py', sys.argv[1]], start_new_session=True)\n"
            "if sys.argv[1] == 'sleep': time.sleep(8)\n")
        base = self.repository()
        for mode in ("sleep", "exit"):
            with self.subTest(mode=mode):
                command = f"python3 parent.py {mode}"
                case = self.deslop([{"cmd": command, "timeout_s": 0.3}])
                authority = self.authority(case, record=self.record(case, baseline=base))
                try:
                    result = subprocess.run([live.sys.executable, str(live.HERE / "live.py"), "grade", "--out", str(self.out),
                                             authority._id], capture_output=True, text=True, timeout=3)
                    (self.assets / f"timeout-{mode}.stdout").write_text(result.stdout)
                    (self.assets / f"timeout-{mode}.stderr").write_text(result.stderr)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    failures = json.loads(result.stdout)["promises"]["deslop-cleans-code-slop"]["failures"]
                    self.assertIn(f"check failed after the pass: {command} timed out after 0.3s", failures)
                finally:
                    pid_file = self.project / f"child-{mode}.pid"
                    if pid_file.exists():
                        try:
                            os.kill(int(pid_file.read_text()), signal.SIGKILL)
                        except ProcessLookupError:
                            pass

    def test_retained_raw_project_refuses_before_checks_can_change_sealed_inputs(self):
        self.project = self.root
        (self.project / "check.py").write_text("from pathlib import Path\n"
            "for name in ('run.json', 'trace.json'): Path(name).write_text('candidate-changed')\nprint('inside-positive')\n")
        base = self.repository()
        case = self.deslop([{"cmd": "python3 check.py", "stdout": "inside-positive\n"}])
        for name, value in (("run.json", self.record(case, baseline=base)), ("trace.json", self.trace()), ("verdict.json", {})):
            (self.root / name).write_text(json.dumps(value))
        before = {name: (self.root / name).read_bytes() for name in ("run.json", "trace.json", "verdict.json")}
        output = self.assets / "diagnostic"
        output.mkdir()
        with self.assertRaisesRegex(GradeRefused, "raw run storage overlaps"):
            authority = _authorize_retained(self.out, self.root, project=self.project, original_project=self.project,
                                           output=output, case=case)
            live.grade(authority)
        self.assertEqual({name: (self.root / name).read_bytes() for name in before}, before)
        self.assertFalse((output / "verdict.json").exists())

    def test_missing_registered_worktree_metadata_returns_cli_refusal_receipts(self):
        base = self.repository()
        sibling = self.assets / "approved-sibling"
        self.git("worktree", "add", "-q", "-b", "sibling", str(sibling))
        case = self.deslop()
        authority = self.authority(case, record=self.record(case, baseline=base), worktrees=(sibling,))
        positive = live.grade(authority)
        self.assertEqual(positive["promises"]["deslop-cleans-code-slop"]["verdict"], "PASS")
        prior_verdict = (self.root / "verdict.json").read_bytes()
        directory = Path((sibling / ".git").read_text().split("gitdir: ", 1)[1].strip())
        for target in (sibling / ".git", directory / "commondir", directory / "gitdir"):
            with self.subTest(target=target):
                contents = target.read_bytes()
                target.unlink()
                try:
                    result = subprocess.run([live.sys.executable, str(live.HERE / "live.py"), "grade", "--out", str(self.out),
                                             authority._id], capture_output=True, text=True, timeout=10)
                    (self.assets / f"missing-{target.name}.stdout").write_text(result.stdout)
                    (self.assets / f"missing-{target.name}.stderr").write_text(result.stderr)
                    self.assertEqual(result.returncode, 2, result.stderr)
                    receipt = json.loads(result.stderr)["refusal"]
                    self.assertEqual(receipt["reason"], "unapproved_git")
                    self.assertEqual(receipt["run_id"], authority._id)
                    self.assertEqual(json.loads((Path(receipt["attempt"]) / "refusal.json").read_text()), receipt)
                    self.assertEqual((self.root / "verdict.json").read_bytes(), prior_verdict)
                finally:
                    target.write_bytes(contents)

    def test_regular_project_grades_and_publishes_exact_existing_verdict_bytes(self):
        case = live.load_case("no-comments-run")
        trace = {**self.trace(), "spawns": [{"seq": 0, "persona": "comment-sicko"}], "final_reply": "offer to encode"}
        (self.project / "inside.py").write_text("value = 1\n")
        expected = {"case": case["id"], "harness": "codex", "skills_at": "synthetic-no-model",
                    "promises": {case["promises"][0]: oracles.check(case["promises"][0], trace, case, self.project)}}
        result = live.grade(self.authority(case, trace))
        self.assertEqual(result, expected)
        self.assertEqual((self.root / "verdict.json").read_bytes(), (json.dumps(expected, indent=1) + "\n").encode())

    def test_original_project_link_shape_refuses_without_outside_reads(self):
        (self.project / "outside.py").symlink_to(self.read_marker)
        authority = self.authority()
        with self.assertRaisesRegex(GradeRefused, "unsafe_link"):
            live.grade(authority)
        self.assertEqual(self.read_marker.read_bytes(), b"private-canary-42\n")
        self.assertFalse((self.root / "verdict.json").exists())

    def test_original_verdict_link_shape_refuses_without_outside_writes(self):
        (self.root / "verdict.json").symlink_to(self.write_marker)
        authority = self.authority()
        with self.assertRaisesRegex(GradeRefused, "unsafe_link"):
            live.grade(authority)
        self.assertEqual(self.write_marker.read_bytes(), b"outside-original\n")

    def test_raw_run_and_trace_links_and_changed_metadata_refuse(self):
        authority = self.authority()
        for name in ("run.json", "trace.json"):
            original = (self.root / name).read_bytes()
            (self.root / name).unlink()
            (self.root / name).symlink_to(self.read_marker)
            with self.subTest(name=name), self.assertRaisesRegex(GradeRefused, "unsafe_link"):
                live.grade(authority)
            (self.root / name).unlink()
            (self.root / name).write_bytes(original)
        (self.root / "run.json").write_text('{}\n')
        with self.assertRaisesRegex(GradeRefused, "input_changed"):
            live.grade(authority)
        self.assertEqual(self.read_marker.read_bytes(), b"private-canary-42\n")

    def test_actual_checks_preserve_exact_stdout_nonzero_and_timeout_results(self):
        (self.project / "check.py").write_text("import sys, time\n"
            "if sys.argv[1] == 'ok': print('inside-positive')\n"
            "if sys.argv[1] == 'bad': print('actual-failure', file=sys.stderr); sys.exit(7)\n"
            "if sys.argv[1] == 'timeout': time.sleep(5)\n")
        base = self.repository({"a.py": b"value = 1\n"})
        case = self.deslop([{"cmd": "python3 check.py ok", "stdout": "inside-positive\n"},
                           {"cmd": "python3 check.py ok", "stdout": "different\n"},
                           {"cmd": "python3 check.py bad"}, {"cmd": "python3 check.py timeout", "timeout_s": 0.1}])
        result = live.grade(self.authority(case, record=self.record(case, baseline=base)))
        self.assertEqual(result["promises"]["deslop-cleans-code-slop"]["failures"], [
            "check failed after the pass: python3 check.py ok printed 'inside-positive\\n', expected 'different\\n'",
            "check failed after the pass: python3 check.py bad exited 7: ['actual-failure']",
            "check failed after the pass: python3 check.py timeout timed out after 0.1s"])

    def test_fixture_nested_descendants_and_new_links_cannot_access_outside_bytes(self):
        (self.project / "check.py").write_text("import pathlib, subprocess, sys\n"
            "outside_read, outside_write = map(pathlib.Path, sys.argv[1:])\n"
            "if __name__ == '__main__':\n"
            "    code = 'import pathlib, sys; r,w=map(pathlib.Path,sys.argv[1:]); result=[]\\n'\n"
            "    code += 'for op in (lambda:r.read_bytes(),lambda:w.write_bytes(b\\\"changed\\\")):\\n'\n"
            "    code += ' try: op(); result.append(\\\"escaped\\\")\\n except PermissionError: result.append(\\\"denied\\\")\\n'\n"
            "    code += 'pathlib.Path(\\\"inside-positive.txt\\\").write_text(\\\"inside-positive\\\"); print(\\\" \\\".join(result))'\n"
            "    link=pathlib.Path('new-link'); link.symlink_to(outside_read)\n"
            "    p=subprocess.run([sys.executable,'-c',code,str(link),str(outside_write)],capture_output=True,text=True)\n"
            "    print(p.stdout, end=''); sys.exit(p.returncode)\n")
        base = self.repository({"a.py": b"value = 1\n"})
        case = self.deslop([{"cmd": f"python3 check.py {self.read_marker} {self.write_marker}", "stdout": "denied denied\n"}])
        result = live.grade(self.authority(case, record=self.record(case, baseline=base)))
        self.assertEqual(result["promises"]["deslop-cleans-code-slop"]["verdict"], "PASS")
        self.assertEqual((self.project / "inside-positive.txt").read_text(), "inside-positive")
        self.assertEqual(self.read_marker.read_bytes(), b"private-canary-42\n")
        self.assertEqual(self.write_marker.read_bytes(), b"outside-original\n")

    def test_descendant_that_outlives_its_parent_remains_confined(self):
        child = self.project / "child.py"
        child.write_text("import pathlib, sys, time\n"
            "time.sleep(0.2)\nresults=[]\n"
            "for op in (lambda:pathlib.Path(sys.argv[1]).read_bytes(),lambda:pathlib.Path(sys.argv[2]).write_bytes(b'changed')):\n"
            " try: op(); results.append('escaped')\n except PermissionError: results.append('denied')\n"
            "pathlib.Path('descendant-positive.txt').write_text(' '.join(results))\n")
        (self.project / "parent.py").write_text("import subprocess, sys\n"
            "subprocess.Popen([sys.executable,'child.py',*sys.argv[1:]],start_new_session=True,"
            "stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)\nprint('parent complete')\n")
        base = self.repository()
        case = self.deslop([{"cmd": f"python3 parent.py {self.read_marker} {self.write_marker}", "stdout": "parent complete\n"}])
        result = live.grade(self.authority(case, record=self.record(case, baseline=base)))
        positive = self.project / "descendant-positive.txt"
        deadline = time.monotonic() + 5
        while not positive.exists() and time.monotonic() < deadline:
            time.sleep(0.02)
        self.assertEqual(result["promises"]["deslop-cleans-code-slop"]["verdict"], "PASS")
        self.assertEqual(positive.read_text(), "denied denied")
        self.assertEqual(self.read_marker.read_bytes(), b"private-canary-42\n")
        self.assertEqual(self.write_marker.read_bytes(), b"outside-original\n")

    def test_check_cannot_import_an_outside_hardlink(self):
        (self.project / "check.py").write_text("import os, pathlib, sys\n"
            "try:\n"
            " os.link(sys.argv[1], 'imported-hardlink'); print(pathlib.Path('imported-hardlink').read_text())\n"
            "except PermissionError: print('denied')\n"
            "pathlib.Path('hardlink-positive.txt').write_text('inside-positive')\n")
        base = self.repository()
        case = self.deslop([{"cmd": f"python3 check.py {self.read_marker}", "stdout": "denied\n"}])
        result = live.grade(self.authority(case, record=self.record(case, baseline=base)))
        self.assertEqual(result["promises"]["deslop-cleans-code-slop"]["verdict"], "PASS")
        self.assertEqual((self.project / "hardlink-positive.txt").read_text(), "inside-positive")
        self.assertEqual(self.read_marker.read_bytes(), b"private-canary-42\n")

    def test_fixture_cannot_replace_project_or_owned_workspace_roots(self):
        (self.project / "check.py").write_text("import pathlib\nresults=[]\n"
            f"for path in (pathlib.Path({str(self.project)!r}), pathlib.Path({str(self.project.parent)!r})):\n"
            " try: path.rename(path.with_name(path.name + '-replaced')); results.append('escaped')\n"
            " except PermissionError: results.append('denied')\n"
            "pathlib.Path('anchor-positive.txt').write_text('inside-positive'); print(' '.join(results))\n")
        base = self.repository()
        case = self.deslop([{"cmd": "python3 check.py", "stdout": "denied denied\n"}])
        result = live.grade(self.authority(case, record=self.record(case, baseline=base)))
        self.assertEqual(result["promises"]["deslop-cleans-code-slop"]["verdict"], "PASS")
        self.assertEqual((self.project / "anchor-positive.txt").read_text(), "inside-positive")

    def test_check_has_no_controller_or_authority_descriptors(self):
        (self.project / "fds.py").write_text("import os, stat\nopened=[]\n"
            "for fd in range(3, 256):\n"
            " try:\n"
            "  info=os.fstat(fd)\n"
            "  if not stat.S_ISSOCK(info.st_mode) or os.get_inheritable(fd): opened.append(fd)\n"
            " except OSError: pass\n"
            "with open('fd-positive.txt','w') as inside: inside.write('inside-positive')\nprint(opened)\n")
        base = self.repository()
        case = self.deslop([{"cmd": "python3 fds.py", "stdout": "[]\n"}])
        result = live.grade(self.authority(case, record=self.record(case, baseline=base)))
        self.assertEqual(result["promises"]["deslop-cleans-code-slop"]["verdict"], "PASS")
        self.assertEqual((self.project / "fd-positive.txt").read_text(), "inside-positive")

    def test_all_route_cases_keep_bounded_incomplete_trace_grades(self):
        absent = self.root / "absent"
        for path in sorted(live.CASES.glob("route-*/case.json")):
            case = live.load_case(path.parent.name)
            trace = {**self.trace(), "exit_code": -9, "final_reply": "", "x_timed_out": True,
                     "x_turns": [{"exit_code": 0}, {"exit_code": -9, "timed_out": True}], "x_baseline": None}
            record = {**self.record(case), "project": str(absent), "turns": trace["x_turns"]}
            expected = {pid: oracles.check(pid, trace, case, absent) for pid in case["promises"]}
            authority = _authorize_fixture(self.root, absent, case, record, trace)
            with self.subTest(case=case["id"]):
                self.assertEqual(live.grade(authority)["promises"], expected)

    def test_git_fsmonitor_helper_cannot_access_outside_bytes(self):
        helper = self.project / "helper.py"
        helper.write_text(f"#!{Path(live.sys.executable).resolve()}\nimport pathlib\nresults=[]\n"
            f"for op in (lambda:pathlib.Path({str(self.read_marker)!r}).read_bytes(), lambda:pathlib.Path({str(self.write_marker)!r}).write_bytes(b'changed')):\n"
            " try: op(); results.append('escaped')\n except PermissionError: results.append('denied')\n"
            f"pathlib.Path({str(self.project / 'git-positive.txt')!r}).write_text(' '.join(results))\nprint('token\\0', end='')\n")
        helper.chmod(0o755)
        base = self.repository({"a.py": b"value = 1\n"})
        self.git("config", "core.fsmonitor", str(helper))
        case = self.deslop()
        live.grade(self.authority(case, record=self.record(case, baseline=base)))
        self.assertEqual((self.project / "git-positive.txt").read_text(), "denied denied")
        self.assertEqual(self.write_marker.read_bytes(), b"outside-original\n")
        self.assertEqual(self.read_marker.read_bytes(), b"private-canary-42\n")

    def test_approved_sibling_and_in_project_worktrees_keep_commit_and_path_evidence(self):
        base = self.repository()
        sibling = self.assets / "approved-sibling"
        nested = self.project / ".agents" / "approved-nested"
        self.git("worktree", "add", "-q", "-b", "sibling", str(sibling))
        self.git("worktree", "add", "-q", "-b", "nested", str(nested))
        (sibling / "README.md").write_text("no dash\n")
        self.git("add", "README.md", project=sibling)
        self.git("commit", "-qm", "sibling change", project=sibling)
        (nested / "README.md").write_text("also no dash\n")
        self.git("add", "README.md", project=nested)
        self.git("commit", "-qm", "nested change", project=nested)
        case = {**live.load_case("deslop-run"), "promises": ["unslop-takes-target-and-rules"], "expect": {"only": ["README.md"]}}
        record = self.record(case, baseline=base)
        trace = {**self.trace(), "x_baseline": base}
        expected = oracles.check(case["promises"][0], trace, case, self.project)
        result = live.grade(self.authority(case, trace, record=record, worktrees=(sibling, nested)))
        self.assertEqual(result["promises"][case["promises"][0]], expected)
        self.assertEqual(result["promises"][case["promises"][0]]["verdict"], "PASS")

    def test_discovered_unallocated_sibling_refuses_before_content_access(self):
        base = self.repository()
        sibling = self.outside / "unapproved"
        self.git("worktree", "add", "-q", "-b", "unapproved", str(sibling))
        case = self.deslop()
        with self.assertRaisesRegex(GradeRefused, "unapproved_worktree"):
            live.grade(self.authority(case, record=self.record(case, baseline=base)))
        self.assertEqual(self.read_marker.read_bytes(), b"private-canary-42\n")

    def test_fresh_owned_workspace_admits_allocated_worktree_members(self):
        case = self.deslop()
        case["fixture"] = "project"
        base = self.repository()
        run = live.Run(self.root, "codex", case, "fixed-pin", 60, baseline=base)
        authority = _before_turns(run)
        sibling = self.project.parent / "allocated"
        self.git("worktree", "add", "-q", "-b", "allocated", str(sibling))
        _seal(authority, live.meta(run), self.trace())
        result = live.grade(authority)
        self.assertEqual(result["promises"]["deslop-cleans-code-slop"]["verdict"], "PASS")

    def test_recorded_and_legacy_baselines_and_absent_project_keep_existing_grades(self):
        case = self.deslop()
        base = self.repository({"a.py": b"value = 1\n", "binary.bin": b"\xff\x00\xfe"})
        for record in (self.record(case), self.record(case, baseline=base)):
            result = live.grade(self.authority(case, record=record))
            self.assertEqual(result["promises"]["deslop-cleans-code-slop"]["verdict"], "PASS")
        absent = self.root / "absent"
        record = {**self.record(case), "project": str(absent)}
        authority = _authorize_fixture(self.root, absent, case, record, self.trace())
        result = live.grade(authority)
        self.assertEqual(result["promises"]["deslop-cleans-code-slop"]["failures"],
                         ["no project to inspect; this pass is graded on the tree, not the reply"])

    def test_installed_skill_bytes_at_admission_are_used_in_selection_order(self):
        case = live.load_case("route-feature")
        first = "Candidate first opener."
        step = "Candidate first step."
        trace = {**self.trace(), "files_read": [], "worklist": [{"seq": 0, "carrier": "test", "items": [
            {"text": first, "state": "in progress"}, {"text": step, "state": "pending"}]}]}
        for directory, label in ((".claude/skills", "first"), (".agents/skills", "second")):
            skill = self.project / directory / "poteto-mode" / "SKILL.md"
            skill.parent.mkdir(parents=True)
            skill.write_text(f"candidate {label} admission\n")
            playbook = skill.parent / "playbooks" / "feature.md"
            playbook.parent.mkdir()
            playbook.write_text(f"### Feature\n\nCandidate {label} opener.\n\n1. Candidate {label} step.\n")
        expected = {pid: oracles.check(pid, trace, case, self.project) for pid in case["promises"]}
        authority = self.authority(case, trace)
        result = live.grade(authority)
        self.assertEqual(result["promises"], expected)
        self.assertEqual({p["verdict"] for p in result["promises"].values()}, {"PASS"})
        attempts = [p for p in (authority._controller.root.path / authority._id).iterdir() if (p / "installed").exists()]
        self.assertEqual(len(attempts), 1)
        self.assertEqual((attempts[0] / "installed/skills/poteto-mode/SKILL.md").read_bytes(), b"candidate first admission\n")
        (self.project / ".claude/skills/poteto-mode/SKILL.md").write_bytes(b"candidate edit before next admission\n")
        self.assertEqual(live.grade(authority)["promises"], expected)
        captured = {p.read_bytes() for p in (authority._controller.root.path / authority._id).glob("*/installed/skills/poteto-mode/SKILL.md")}
        self.assertEqual(captured, {b"candidate first admission\n", b"candidate edit before next admission\n"})

    def test_registered_cli_grade_uses_controller_lookup(self):
        case = live.load_case("no-comments-run")
        authority = self.authority(case)
        expected = live.grade(authority)
        done = subprocess.run([live.sys.executable, str(live.HERE / "live.py"), "grade", "--out", str(self.out), authority._id],
                              capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(json.loads(done.stdout), expected)

    def test_matching_required_skill_directory_refuses_instead_of_omitting_it(self):
        skill = self.project / ".claude/skills/poteto-mode/SKILL.md"
        skill.parent.mkdir(parents=True)
        skill.write_text("candidate admission\n")
        (skill.parent / "playbooks/malformed.md").mkdir(parents=True)
        authority = self.authority()
        with self.assertRaisesRegex(GradeRefused, "unsafe_object"):
            live.grade(authority)

    def test_decision_log_glob_keeps_matching_directory_evidence(self):
        case = live.load_case("overnight-run")
        case["promises"] = ["overnight-contract-routes-to-figure-it-out"]
        trace = {**self.trace(), "events": [{"seq": 0, "kind": "tool_call", "name": "Read",
                                             "input": {"file_path": "/w/.claude/skills/figure-it-out/SKILL.md"}}]}
        (self.project / ".audit/decisions.tsv").mkdir(parents=True)
        expected = oracles.check(case["promises"][0], trace, case, self.project)
        result = live.grade(self.authority(case, trace))
        self.assertEqual(result["promises"][case["promises"][0]], expected)
        self.assertEqual(expected["verdict"], "PASS")

    def test_checks_cannot_change_sealed_metadata_references_skills_or_output(self):
        (self.project / "protect.py").write_text("import pathlib, sys\n"
            "results=[]\n"
            "for name in sys.argv[1:]:\n"
            " try: pathlib.Path(name).write_bytes(b'changed'); results.append('escaped')\n"
            " except PermissionError: results.append('denied')\n"
            "pathlib.Path('inside-protected-positive.txt').write_text('inside-positive')\n"
            "for name in pathlib.Path(sys.argv[1]).parent.parent.parent.glob('.runs-grade-controller/*/*/installed/skills/poteto-mode/SKILL.md'):\n"
            " try: name.write_bytes(b'changed'); results.append('escaped')\n"
            " except PermissionError: results.append('denied')\n"
            "print(' '.join(results))\n")
        installed = self.project / ".claude/skills/poteto-mode/SKILL.md"
        installed.parent.mkdir(parents=True)
        installed.write_bytes(b"protected installed admission\n")
        base = self.repository({"a.py": b"value = 1\n"})
        case = self.deslop()
        authority = self.authority(case, record=self.record(case, baseline=base))
        private = authority._controller.root.path / authority._id
        targets = [self.root / "run.json", self.root / "trace.json", self.root / "verdict.json",
                   private / "references/cases/deslop-run/expected/roster/load.py", private / "fallback/skills/poteto-mode/SKILL.md"]
        before = {p: p.read_bytes() for p in targets if p.exists()}
        _, state = authority._controller.load(authority._id)
        state["case"]["expect"]["checks"] = [{"cmd": "python3 protect.py " + " ".join(map(str, targets)),
                                               "stdout": "denied denied denied denied denied denied\n"}]
        authority._controller.save(state)
        result = live.grade(authority)
        self.assertEqual(result["promises"]["deslop-cleans-code-slop"]["verdict"], "PASS")
        self.assertEqual({p: p.read_bytes() for p in before}, before)
        self.assertEqual((self.project / "inside-protected-positive.txt").read_text(), "inside-positive")
        captured = list(private.glob("*/installed/skills/poteto-mode/SKILL.md"))
        self.assertEqual(len(captured), 1)
        self.assertEqual(captured[0].read_bytes(), b"protected installed admission\n")

    def test_checks_cannot_link_frozen_inputs_into_writable_project(self):
        (self.project / "alias.py").write_text("import os, pathlib, sys\n"
            "targets=[pathlib.Path(name) for name in sys.argv[1:]]\n"
            "targets.extend(pathlib.Path(sys.argv[1]).parent.parent.parent.glob('.runs-grade-controller/*/*/installed/skills/poteto-mode/SKILL.md'))\n"
            "results=[]\n"
            "for index, source in enumerate(targets):\n"
            " alias=pathlib.Path(f'frozen-alias-{index}.txt')\n"
            " try: os.link(source, alias); alias.write_bytes(b'changed'); results.append('escaped')\n"
            " except PermissionError: results.append('denied')\n"
            "pathlib.Path('inside-alias-positive.txt').write_text('inside-positive')\n"
            "print(' '.join(results))\n")
        installed = self.project / ".claude/skills/poteto-mode/SKILL.md"
        installed.parent.mkdir(parents=True)
        installed.write_bytes(b"frozen installed marker\n")
        base = self.repository()
        case = self.deslop()
        authority = self.authority(case, record=self.record(case, baseline=base))
        private = authority._controller.root.path / authority._id
        targets = [self.root / "run.json", self.root / "trace.json",
                   private / "references/cases/deslop-run/expected/roster/load.py", private / "fallback/skills/poteto-mode/SKILL.md"]
        before = {p: (p.read_bytes(), p.stat().st_nlink) for p in targets}
        _, state = authority._controller.load(authority._id)
        state["case"]["expect"]["checks"] = [{"cmd": "python3 alias.py " + " ".join(map(str, targets)),
                                               "stdout": "denied denied denied denied denied\n"}]
        authority._controller.save(state)
        result = live.grade(authority)
        self.assertEqual(result["promises"]["deslop-cleans-code-slop"]["verdict"], "PASS")
        self.assertEqual({p: (p.read_bytes(), p.stat().st_nlink) for p in targets}, before)
        self.assertFalse(list(self.project.glob("frozen-alias-*.txt")))
        self.assertEqual((self.project / "inside-alias-positive.txt").read_text(), "inside-positive")
        captured = list(private.glob("*/installed/skills/poteto-mode/SKILL.md"))
        self.assertEqual(len(captured), 1)
        self.assertEqual((captured[0].read_bytes(), captured[0].stat().st_nlink), (b"frozen installed marker\n", 1))

    def test_retained_diagnostics_preserve_raw_grades_and_require_reviewed_mapping(self):
        case = live.load_case("no-comments-run")
        authority = self.authority(case)
        live.grade(authority)
        raw = {name: (self.root / name).read_bytes() for name in ("run.json", "trace.json", "verdict.json")}
        output = self.assets / "diagnostics"
        output.mkdir()
        retained = _authorize_retained(self.out, self.root, project=self.project, original_project=self.project,
                                       output=output, case=case)
        result = live.grade(retained)
        self.assertEqual(json.loads((output / "verdict.json").read_bytes()), result)
        self.assertEqual({name: (self.root / name).read_bytes() for name in raw}, raw)
        with self.assertRaisesRegex(GradeRefused, "reviewed original mapping"):
            _authorize_retained(self.out, self.root, project=self.project, original_project=self.outside,
                                output=output, case=case)

    def test_unavailable_native_launch_and_changed_runtime_refuse_without_verdict(self):
        authority = self.authority()
        with mock.patch("grade_boundary.PINS", ((Path("/usr/bin/false"), ("0" * 64,)),)):
            with self.assertRaisesRegex(GradeRefused, "fingerprint changed"):
                live.grade(authority)
        with mock.patch("grade_boundary.subprocess.Popen", side_effect=OSError("native launch unavailable")):
            with self.assertRaises(GradeRefused):
                live.grade(authority)
        self.assertFalse((self.root / "verdict.json").exists())


@unittest.skipUnless(NATIVE, "native parent grading requires the reviewed Darwin 25.6.0 arm64 runtime")
class ParentGradeRegression(unittest.TestCase):
    def test_parent_grade_does_not_follow_project_and_verdict_links(self):
        with tempfile.TemporaryDirectory(prefix="pstack-parent-grade-") as temp:
            assets = Path(temp).resolve()
            root = assets / "run"
            case = live.load_case("no-comments-run")
            project = root / "w" / case["fixture"]
            project.mkdir(parents=True)
            outside = assets / "outside"
            outside.mkdir()
            read_marker = outside / "read-marker.txt"
            read_marker.write_text("# read the rows\n")
            write_marker = outside / "write-marker.json"
            write_marker.write_text("{}\n")
            (project / "outside.py").symlink_to(read_marker)
            (root / "verdict.json").symlink_to(write_marker)
            record = {"harness": "codex", "case": case["id"], "skills_at": "synthetic-no-model",
                      "project": str(project)}
            trace = {"harness": "codex", "exit_code": 0, "events": [], "worklist": [],
                     "spawns": [{"seq": 0, "persona": "comment-sicko", "prompt_head": "comment-sicko"}],
                     "final_reply": "", "files_read": []}
            (root / "run.json").write_text(json.dumps(record))
            (root / "trace.json").write_text(json.dumps(trace))
            try:
                authority = _authorize_fixture(root, project, case, record, trace)
                graded = live.grade(authority)
            except GradeRefused as refusal:
                self.assertEqual(refusal.receipt["reason"], "unsafe_link")
                graded = {}
            self.assertNotIn("# read the rows", json.dumps(graded))
            self.assertEqual(write_marker.read_bytes(), b"{}\n")


if __name__ == "__main__":
    unittest.main()
