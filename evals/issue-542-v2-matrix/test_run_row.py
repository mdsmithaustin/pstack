import contextlib
import io
import json
import os
import signal
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import run_row

HERE = Path(__file__).resolve().parent
DRIVER = HERE / "run_row.py"
LOGIN = "fake-login-token"

STUB = f"""#!{sys.executable}
import json, os, stat, sys, time
home = os.environ["CODEX_HOME"]
login = os.path.join(home, "auth.json")
record = {{"mode": stat.S_IMODE(os.stat(login).st_mode), "content": open(login).read(), "pid": os.getpid()}}
open(os.path.join(home, "stub.json"), "w").write(json.dumps(record))
print(json.dumps({{"type": "thread.started", "thread_id": "stub-thread"}}), flush=True)
ACTION
"""


class Sandbox(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name).resolve()
        self.home = self.tmp / "home"
        (self.home / ".codex").mkdir(parents=True)
        (self.home / ".codex" / "auth.json").write_text(LOGIN)
        self.root = self.tmp / "run"
        self.login_copy = self.root / "codex-home" / "auth.json"

    def stub(self, action="sys.exit(0)"):
        bin_dir = self.tmp / "bin"
        bin_dir.mkdir(exist_ok=True)
        (bin_dir / "codex").write_text(STUB.replace("ACTION", action))
        (bin_dir / "codex").chmod(0o755)
        return {**os.environ, "HOME": str(self.home), "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}"}

    def run_in_process(self, env, *extra, root=None):
        argv = ["run_row.py", "how", "--root", str(root or self.root), *extra]
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch.dict(os.environ, env, clear=True), patch.object(sys, "argv", argv), \
                contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            try:
                run_row.main()
                code = 0
            except SystemExit as stop:
                code = stop.code
        return code, stdout.getvalue(), stderr.getvalue()

    def stub_record(self):
        return json.loads((self.root / "codex-home" / "stub.json").read_text())


class RefusesRootsInsideTheRepository(Sandbox):
    def refused(self, root):
        code, _, stderr = self.run_in_process(self.stub(), root=root)
        self.assertEqual(code, 2)
        self.assertIn("resolves inside the repository", stderr)
        return Path(root)

    def test_a_directory_in_the_repository(self):
        self.assertFalse(self.refused(run_row.REPO / "evals" / "scratch-run").exists())

    def test_the_repository_itself(self):
        self.refused(run_row.REPO)

    def test_a_symlink_that_leads_into_the_repository(self):
        link = self.tmp / "link"
        link.symlink_to(run_row.REPO / "evals")
        self.refused(link / "scratch-run")
        self.assertFalse((run_row.REPO / "evals" / "scratch-run").exists())

    def test_a_path_spelled_in_another_case_on_a_case_insensitive_disk(self):
        respelled = Path(str(run_row.REPO).swapcase())
        if not respelled.exists() or not respelled.samefile(run_row.REPO):
            self.skipTest("the disk tells the two spellings apart")
        self.assertTrue(run_row.inside_repository(respelled / "evals" / "scratch-run"))

    def make_worktree(self):
        main, worktree = self.tmp / "main", self.tmp / "worktree"
        git = ["git", "-c", "user.name=dev", "-c", "user.email=dev@example.com", "-C", str(main)]
        subprocess.run(["git", "init", "-q", str(main)], check=True)
        subprocess.run([*git, "commit", "-q", "--allow-empty", "-m", "init"], check=True)
        subprocess.run([*git, "worktree", "add", "-q", str(worktree), "-b", "side"], check=True)
        return main, worktree

    def test_a_directory_in_the_main_checkout_of_a_worktree(self):
        main, worktree = self.make_worktree()
        with patch.object(run_row, "REPO", worktree):
            self.assertFalse(self.refused(main / ".audit" / "run").exists())

    def test_a_sibling_whose_name_starts_with_the_repository_name_is_outside(self):
        main, worktree = self.make_worktree()
        with patch.object(run_row, "REPO", worktree):
            self.assertFalse(run_row.inside_repository(self.tmp / "main-extra" / "run"))
            self.assertFalse(run_row.inside_repository(self.tmp / "worktree-extra" / "run"))
            self.assertTrue(run_row.inside_repository(main / "run"))


class ValidatesBeforeCopying(Sandbox):
    def test_a_bad_timeout_creates_nothing(self):
        code, _, stderr = self.run_in_process(self.stub(), "--timeout", "0")
        self.assertEqual(code, 2)
        self.assertIn("--timeout", stderr)
        self.assertFalse(self.root.exists())

    def test_a_missing_login_creates_nothing(self):
        (self.home / ".codex" / "auth.json").unlink()
        code, _, stderr = self.run_in_process(self.stub())
        self.assertEqual(code, 2)
        self.assertIn("no Codex login", stderr)
        self.assertFalse(self.root.exists())

    def test_a_root_that_is_a_file_creates_nothing_else(self):
        self.root.write_text("")
        code, _, stderr = self.run_in_process(self.stub())
        self.assertEqual(code, 2)
        self.assertIn("not a directory", stderr)


class LoginCopy(Sandbox):
    def test_it_is_private_while_codex_runs_and_gone_after_success(self):
        handlers = [signal.getsignal(number) for number in (signal.SIGINT, signal.SIGTERM)]
        code, stdout, _ = self.run_in_process(self.stub())
        self.assertEqual([signal.getsignal(number) for number in (signal.SIGINT, signal.SIGTERM)], handlers)
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(stdout), [{"index": 0, "exit": 0, "session": "stub-thread"}])
        self.assertEqual(self.stub_record()["mode"], 0o600)
        self.assertEqual(self.stub_record()["content"], LOGIN)
        self.assertFalse(self.login_copy.exists())

    def test_it_is_gone_after_codex_fails(self):
        code, stdout, _ = self.run_in_process(self.stub("sys.exit(3)"))
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(stdout)[0]["exit"], 3)
        self.assertFalse(self.login_copy.exists())

    def test_it_is_gone_after_the_driver_raises(self):
        with patch.object(run_row, "thread_id", side_effect=RuntimeError("boom")):
            with self.assertRaises(RuntimeError):
                self.run_in_process(self.stub())
        self.assertEqual(self.stub_record()["mode"], 0o600)
        self.assertFalse(self.login_copy.exists())

    def test_a_loose_copy_left_by_an_earlier_run_is_tightened(self):
        self.login_copy.parent.mkdir(parents=True)
        self.login_copy.write_text("stale")
        self.login_copy.chmod(0o644)
        self.run_in_process(self.stub())
        self.assertEqual(self.stub_record()["mode"], 0o600)
        self.assertEqual(self.stub_record()["content"], LOGIN)
        self.assertFalse(self.login_copy.exists())

    def test_it_is_gone_after_the_driver_is_signalled(self):
        env = self.stub("time.sleep(120)")
        for number in (signal.SIGTERM, signal.SIGINT):
            with self.subTest(signal=number.name):
                (self.root / "codex-home").mkdir(parents=True, exist_ok=True)
                driver = subprocess.Popen([sys.executable, str(DRIVER), "how", "--root", str(self.root)], env=env,
                                          stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                record = self.root / "codex-home" / "stub.json"
                deadline = time.monotonic() + 60
                while not record.exists() and driver.poll() is None and time.monotonic() < deadline:
                    time.sleep(0.1)
                self.assertTrue(record.exists(), "the stub codex never started")
                self.assertEqual(stat.S_IMODE(self.login_copy.stat().st_mode), 0o600)
                stub_pid = json.loads(record.read_text())["pid"]
                driver.send_signal(number)
                driver.communicate(timeout=30)
                self.assertEqual(driver.returncode, 128 + number)
                self.assertFalse(self.login_copy.exists())
                with self.assertRaises(ProcessLookupError):
                    os.kill(stub_pid, 0)
                record.unlink()


if __name__ == "__main__":
    unittest.main()
