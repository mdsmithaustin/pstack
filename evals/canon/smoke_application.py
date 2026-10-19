import json
import os
from pathlib import Path
import signal
import shutil
import threading
import time
import unittest
from unittest import mock

import application


class NativeLifecycleSmoke(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(os.environ["CANON_APPLICATION_EVIDENCE"]).absolute()
        cls.root.mkdir(parents=True)
        cls.runtime = application.Runtime(
            os.environ["CANON_APPLICATION_TEMPLATE"], "gpt-6.1-sol", "high", 120)

    @classmethod
    def tearDownClass(cls):
        for path in [cls.root / "source", *cls.root.glob("*-source"),
                     *cls.root.glob("*-replay"), *cls.root.glob("*/staging")]:
            if path.exists():
                shutil.rmtree(path)

    def check_result(self, result, state, valid):
        receipt = json.loads(result.receipt.read_text())
        self.assertEqual((result.state, result.native_valid), (state, valid), receipt)
        self.assertTrue(receipt["cleanup_confirmed"], receipt)
        self.assertIsNone(receipt["observed_model"])
        if result.native_elapsed_s is not None:
            self.assertGreater(result.native_elapsed_s, 0)
            self.assertLess(result.native_elapsed_s, result.elapsed_s)
            self.assertEqual(receipt["native_elapsed_s"], result.native_elapsed_s)
        return receipt

    def failure_input(self, name):
        source = self.root / (name + "-source")
        source.mkdir()
        (source / "sentinel").write_bytes(b"preserved\r\n")
        return application.Snapshot.freeze(source, self.root / (name + "-input"))

    def check_failure_capture(self, result, name):
        replayed = application.replay(result.capture, self.root / (name + "-replay"))
        self.assertEqual((replayed / "sentinel").read_bytes(), b"preserved\r\n")

    def test_native_failure_preserves_capture(self):
        project = self.failure_input("failure")
        runtime = application.Runtime(self.runtime.template, "invalid-synthetic-smoke-model", "high", 30)
        result = application.run_application(
            application.Request(runtime, project, None, "Reply only OK."), self.root / "failure")
        receipt = self.check_result(result, "native_failed", False)
        self.assertTrue(receipt["native"]["failure_event"])
        self.assertIsNone(result.usage)
        self.check_failure_capture(result, "failure")

    def test_timeout_preserves_capture(self):
        project = self.failure_input("timeout")
        runtime = application.Runtime(self.runtime.template, self.runtime.model, "high", 1)
        result = application.run_application(application.Request(
            runtime, project, None, "Run sleep 30, then reply OK. Do not change files."),
            self.root / "timeout")
        self.check_result(result, "timeout", False)
        self.assertIsNotNone(result.native_elapsed_s)
        self.check_failure_capture(result, "timeout")

    def test_interrupt_preserves_capture(self):
        project = self.failure_input("interrupt")
        original = application._command
        interrupted = threading.Event()
        stop = threading.Event()

        def command(argv, **kwargs):
            args = list(map(str, argv))
            if args[:2] == ["sbx", "exec"] and args[-2:] == ["run", application.REMOTE + ".json"]:
                def interrupt_when_started():
                    deadline = time.monotonic() + 20
                    while not stop.wait(0.2) and time.monotonic() < deadline:
                        probe = original(["sbx", "exec", args[2], "test", "-s",
                                          application.REMOTE + ".pid"], check=False, timeout=5)
                        if probe.returncode == 0:
                            interrupted.set()
                            os.kill(os.getpid(), signal.SIGINT)
                            return
                worker = threading.Thread(target=interrupt_when_started)
                worker.start()
                try:
                    return original(argv, **kwargs)
                finally:
                    stop.set()
                    worker.join(timeout=10)
            return original(argv, **kwargs)

        with mock.patch.object(application, "_command", side_effect=command):
            result = application.run_application(application.Request(
                self.runtime, project, None, "Run sleep 30, then reply OK. Do not change files."),
                self.root / "interrupt")
        self.assertTrue(interrupted.is_set(), "native PID was never observed before interrupt")
        self.check_result(result, "interrupted", False)
        self.check_failure_capture(result, "interrupt")

    def test_changed_guidance_and_cleanup_failure(self):
        original = application._command
        for mode in ("guidance", "cleanup"):
            with self.subTest(mode=mode):
                project = self.failure_input(mode)
                source = self.root / (mode + "-skills-source")
                (source / "smoke").mkdir(parents=True)
                (source / "smoke/SKILL.md").write_text(
                    "---\nname: smoke\ndescription: Disposable smoke fixture.\n---\nPreserve files.\n")
                skills = application.Snapshot.freeze(source, self.root / (mode + "-skills"))
                owned = []
                injected = []

                def command(argv, **kwargs):
                    args = list(map(str, argv))
                    if args[:2] == ["sbx", "create"]:
                        owned.append(args[args.index("--name") + 1])
                    if mode == "guidance" and args[:2] == ["sbx", "exec"] and args[-2:] == ["harvest", application.REMOTE + ".json"]:
                        code = ("import json,pathlib; p=json.loads(pathlib.Path(" +
                                repr(application.REMOTE + ".json") + ").read_text()); "
                                "(pathlib.Path(p['root'])/'.agents/skills/smoke/SKILL.md').write_text('changed')")
                        original(["sbx", "exec", args[2], "python3", "-c", code])
                        injected.append(mode)
                    if mode == "cleanup" and args[:2] == ["sbx", "rm"]:
                        injected.append(mode)
                        raise application.ApplicationError("injected removal failure")
                    return original(argv, **kwargs)

                try:
                    with mock.patch.object(application, "_command", side_effect=command):
                        result = application.run_application(application.Request(
                            self.runtime, project, skills, "Reply OK. Do not change files."), self.root / mode)
                    self.assertEqual(injected, [mode])
                    receipt = json.loads(result.receipt.read_text())
                    self.assertTrue(receipt["native"]["native_valid"], receipt)
                    self.assertFalse(result.native_valid)
                    if mode == "guidance":
                        self.check_result(result, "capture_failed", False)
                        self.assertEqual(receipt["error"], "assigned guidance changed")
                        self.check_failure_capture(result, mode)
                    else:
                        self.assertEqual(result.state, "cleanup_failed")
                        self.assertIsNone(result.capture)
                        self.assertFalse(receipt["cleanup_confirmed"])
                        private = application.Snapshot(Path(receipt["capture"]["directory"]),
                                                       receipt["capture"]["sha256"])
                        replayed = application.replay(private, self.root / "cleanup-private-replay")
                        self.assertEqual((replayed / "sentinel").read_bytes(), b"preserved\r\n")
                finally:
                    listing = json.loads(original(["sbx", "ls", "--json"]).stdout)
                    remaining = set(owned) & {row["name"] for row in listing["sandboxes"]}
                    for name in remaining:
                        original(["sbx", "rm", "--force", name])
                    listing = json.loads(original(["sbx", "ls", "--json"]).stdout)
                    self.assertFalse(set(owned) & {row["name"] for row in listing["sandboxes"]})
                    (self.root / (mode + "-final-cleanup.json")).write_text(json.dumps(listing))

    def test_completion_and_exact_capture_maintenance(self):
        source = self.root / "source"
        source.mkdir()
        (source / "remove.txt").write_bytes(b"obsolete\n")
        (source / "preserve.bin").write_bytes(b"\x00\xffalpha\r\nbeta\n")
        (source / "preserve.bin").chmod(0o640)
        (source / "empty/nested").mkdir(parents=True)
        project = application.Snapshot.freeze(source, self.root / "input")
        prompts = (
            'Write result.txt with exactly the bytes "initial\\n" and delete remove.txt. '
            'Preserve all other files, bytes, modes, and directories. Do this directly; no delegation.',
            'Read result.txt and verify it contains "initial\\n". Replace its bytes with '
            '"maintained\\n" and create done.txt with exactly "done\\n". Preserve all other '
            'files, bytes, modes, and directories. Do this directly; no delegation.',
        )
        for phase, prompt, expected in zip(("initial", "maintenance"), prompts,
                                           (b"initial\n", b"maintained\n")):
            with self.subTest(phase=phase):
                result = application.run_application(
                    application.Request(self.runtime, project, None, prompt), self.root / phase)
                receipt = self.check_result(result, "completed", True)
                self.assertEqual(receipt["spec"]["project"], project.sha256)
                self.assertIsNotNone(result.native_elapsed_s)
                replayed = application.replay(result.capture, self.root / (phase + "-replay"))
                self.assertEqual((replayed / "result.txt").read_bytes(), expected)
                self.assertFalse((replayed / "remove.txt").exists())
                self.assertEqual((replayed / "preserve.bin").read_bytes(), b"\x00\xffalpha\r\nbeta\n")
                self.assertEqual((replayed / "preserve.bin").stat().st_mode & 0o777, 0o640)
                self.assertEqual(list((replayed / "empty/nested").iterdir()), [])
                if phase == "maintenance":
                    self.assertEqual((replayed / "done.txt").read_bytes(), b"done\n")
                events = [json.loads(line) for line in
                          (result.receipt.parent / "harvest/native.stdout").read_bytes().splitlines()]
                completed = [event for event in events if event.get("type") == "turn.completed"]
                self.assertEqual(len(completed), 1)
                self.assertIsInstance(completed[0].get("usage"), dict)
                self.assertEqual(result.usage, completed[0]["usage"])
                self.assertEqual(receipt["usage"], completed[0]["usage"])
                project = result.capture


if __name__ == "__main__":
    unittest.main(verbosity=2)
