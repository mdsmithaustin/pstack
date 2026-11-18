import contextlib
import io
import json
import os
import shutil
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
CLEANUP_SIGNALS = (signal.SIGINT, signal.SIGTERM, signal.SIGHUP, signal.SIGQUIT)

STUB = f"""#!{sys.executable}
import json, os, signal, stat, sys, time
PRELUDE
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

    def stub(self, action="sys.exit(0)", prelude=""):
        bin_dir = self.tmp / "bin"
        bin_dir.mkdir(exist_ok=True)
        (bin_dir / "codex").write_text(STUB.replace("PRELUDE", prelude).replace("ACTION", action))
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

    def make_worktrees(self):
        main, worktree, other = self.tmp / "main", self.tmp / "worktree", self.tmp / "other tree"
        git = ["git", "-c", "user.name=dev", "-c", "user.email=dev@example.com", "-C", str(main)]
        subprocess.run(["git", "init", "-q", str(main)], check=True)
        subprocess.run([*git, "commit", "-q", "--allow-empty", "-m", "init"], check=True)
        subprocess.run([*git, "worktree", "add", "-q", str(worktree), "-b", "side"], check=True)
        subprocess.run([*git, "worktree", "add", "-q", str(other), "-b", "elsewhere"], check=True)
        return main, worktree, other

    def test_a_directory_in_the_main_checkout_of_a_worktree(self):
        main, worktree, _ = self.make_worktrees()
        with patch.object(run_row, "REPO", worktree):
            self.assertFalse(self.refused(main / ".audit" / "run").exists())

    def test_a_directory_in_a_linked_worktree_outside_the_repository(self):
        main, worktree, other = self.make_worktrees()
        for current in (main, worktree):
            with self.subTest(checkout=current.name), patch.object(run_row, "REPO", current):
                self.assertFalse(self.refused(other / "run").exists())

    def test_a_worktree_whose_directory_is_gone_does_not_break_the_check(self):
        main, worktree, other = self.make_worktrees()
        shutil.rmtree(other)
        with patch.object(run_row, "REPO", worktree):
            self.assertFalse(run_row.inside_repository(self.tmp / "outside" / "run"))
            self.assertTrue(run_row.inside_repository(main / "run"))

    def test_a_sibling_whose_name_starts_with_the_repository_name_is_outside(self):
        main, worktree, _ = self.make_worktrees()
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
        handlers = [signal.getsignal(number) for number in CLEANUP_SIGNALS]
        code, stdout, _ = self.run_in_process(self.stub())
        self.assertEqual([signal.getsignal(number) for number in CLEANUP_SIGNALS], handlers)
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

    def start_driver(self, env, **popen):
        (self.root / "codex-home").mkdir(parents=True, exist_ok=True)
        driver = subprocess.Popen([sys.executable, str(DRIVER), "how", "--root", str(self.root)], env=env,
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE, **popen)
        record = self.root / "codex-home" / "stub.json"
        deadline = time.monotonic() + 60
        while not record.exists() and driver.poll() is None and time.monotonic() < deadline:
            time.sleep(0.1)
        self.assertTrue(record.exists(), "the stub codex never started")
        self.assertEqual(stat.S_IMODE(self.login_copy.stat().st_mode), 0o600)
        pid = json.loads(record.read_text())["pid"]
        record.unlink()
        return driver, pid

    def assert_stopped_clean(self, driver, pid, code):
        driver.communicate(timeout=30)
        self.assertEqual(driver.returncode, code)
        self.assertFalse(self.login_copy.exists())
        with self.assertRaises(ProcessLookupError):
            os.kill(pid, 0)

    def test_it_is_gone_after_the_driver_is_signalled(self):
        env = self.stub("time.sleep(120)")
        for number in CLEANUP_SIGNALS:
            with self.subTest(signal=number.name):
                driver, pid = self.start_driver(env)
                driver.send_signal(number)
                self.assert_stopped_clean(driver, pid, 128 + number)

    def test_it_is_gone_after_the_process_group_gets_a_hangup(self):
        for handler in (signal.SIG_DFL, signal.SIG_IGN):
            with self.subTest(child_hangup_handler=handler.name):
                env = self.stub("time.sleep(120)", f"signal.signal(signal.SIGHUP, signal.{handler.name})")
                driver, pid = self.start_driver(env, start_new_session=True)
                os.killpg(driver.pid, signal.SIGHUP)
                self.assert_stopped_clean(driver, pid, 128 + signal.SIGHUP)

    def test_a_second_signal_during_cleanup_does_not_leave_it(self):
        unlink, cleaning = Path.unlink, []
        def unlink_after_another_signal(path, *args, **kwargs):
            if cleaning:
                os.kill(os.getpid(), signal.SIGTERM)
            unlink(path, *args, **kwargs)
        self.addCleanup(signal.signal, signal.SIGHUP, signal.signal(signal.SIGHUP, signal.SIG_IGN))
        self.login_copy.parent.mkdir(parents=True)
        with patch.object(Path, "unlink", autospec=True, side_effect=unlink_after_another_signal):
            with self.assertRaises(SystemExit) as stopped:
                with run_row.private_login(self.home / ".codex" / "auth.json", self.login_copy):
                    cleaning.append(True)
                    os.kill(os.getpid(), signal.SIGHUP)
                    time.sleep(5)
        self.assertEqual(stopped.exception.code, 128 + signal.SIGHUP)
        self.assertFalse(self.login_copy.exists())


class PlantedLoginPath(Sandbox):
    def plant(self, make):
        self.login_copy.parent.mkdir(parents=True)
        make(self.login_copy)
        self.run_in_process(self.stub())
        self.assertEqual(self.stub_record()["mode"], 0o600)
        self.assertEqual(self.stub_record()["content"], LOGIN)
        self.assertFalse(self.login_copy.is_symlink() or self.login_copy.exists())

    def test_a_symlink_to_a_file_is_not_written_through(self):
        victim = self.tmp / "victim"
        victim.write_text("keep")
        self.plant(lambda path: path.symlink_to(victim))
        self.assertEqual(victim.read_text(), "keep")

    def test_a_dangling_symlink_creates_nothing_at_its_target(self):
        target = self.tmp / "absent"
        self.plant(lambda path: path.symlink_to(target))
        self.assertFalse(target.exists())

    def test_a_hard_link_to_another_file_is_not_written_through(self):
        victim = self.tmp / "victim"
        victim.write_text("keep")
        self.plant(lambda path: os.link(victim, path))
        self.assertEqual(victim.read_text(), "keep")

    def test_a_symlink_planted_after_the_unlink_is_not_written_through(self):
        victim = self.tmp / "victim"
        victim.write_text("keep")
        unlink, planted = Path.unlink, []
        def unlink_then_plant(path, *args, **kwargs):
            unlink(path, *args, **kwargs)
            if not planted:
                planted.append(path)
                path.symlink_to(victim)
        self.login_copy.parent.mkdir(parents=True)
        with patch.object(Path, "unlink", autospec=True, side_effect=unlink_then_plant):
            with self.assertRaises(FileExistsError):
                with run_row.private_login(self.home / ".codex" / "auth.json", self.login_copy):
                    self.fail("the login was copied through a planted link")
        self.assertEqual(victim.read_text(), "keep")
        self.assertFalse(self.login_copy.is_symlink() or self.login_copy.exists())

    def test_a_codex_home_that_is_a_symlink_is_refused_before_anything_is_written(self):
        elsewhere = self.tmp / "elsewhere"
        elsewhere.mkdir()
        self.root.mkdir()
        (self.root / "codex-home").symlink_to(elsewhere)
        code, _, stderr = self.run_in_process(self.stub())
        self.assertEqual(code, 2)
        self.assertIn("codex-home", stderr)
        self.assertEqual(list(elsewhere.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
