import json
import os
import signal
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
SCRIPT = ROOT / 'skills/pstack-harness/scripts/preserve.py'
BASELINE = 'import unittest\n\nclass Example(unittest.TestCase):\n    def test_ok(self):\n        self.assertTrue(True)\n'


class PreserveLifecycleEdges(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='preserve-lifecycle-edges-')
        self.addCleanup(temporary.cleanup)
        self.repo = Path(temporary.name).resolve()
        self.git('init', '-q')
        (self.repo / 'tests').mkdir()
        self.test = self.repo / 'tests/test_example.py'
        self.fixture = self.repo / 'tests/example.dat'
        self.test.write_text(BASELINE)
        self.fixture.write_bytes(b'baseline fixture\x00\xff')
        self.git('add', '-A')
        self.git('commit', '-q', '-m', 'baseline')
        self.test.write_text(BASELINE + '\nEDITED = True\n')
        self.fixture.write_bytes(b'edited fixture\x00\xfe')
        self.test.chmod(0o751)
        self.fixture.chmod(0o640)

    def git(self, *args):
        return subprocess.run(['git', '-C', str(self.repo), *args], check=True, capture_output=True,
                              env={**os.environ, 'GIT_AUTHOR_NAME': 't', 'GIT_AUTHOR_EMAIL': 't@x',
                                   'GIT_COMMITTER_NAME': 't', 'GIT_COMMITTER_EMAIL': 't@x'})

    @property
    def backup(self):
        return self.repo / '.git/preserve-backup'

    def argv(self, *extra):
        return [sys.executable, str(SCRIPT), '--project', str(self.repo), '--since', 'HEAD',
                '--python', sys.executable, *extra]

    @staticmethod
    def snapshot(paths):
        return {path: (path.read_bytes(), path.stat().st_mode & 0o7777, path.stat().st_ino,
                       path.stat().st_nlink) for path in paths}

    def wait_file(self, path, proc):
        deadline = time.monotonic() + 5
        while not path.exists():
            if proc.poll() is not None:
                self.fail('preserve exited before child readiness: ' + repr(proc.communicate(timeout=2)))
            if time.monotonic() >= deadline:
                self.fail('owned descendant did not confirm readiness')
            time.sleep(0.01)
        return json.loads(path.read_text())

    def assert_group_stopped(self, group):
        deadline = time.monotonic() + 3
        while True:
            try:
                os.killpg(group, 0)
            except ProcessLookupError:
                return
            if time.monotonic() >= deadline:
                self.fail(f'owned command process group {group} still exists')
            time.sleep(0.01)

    def inherited_streams(self, ignore_term=False):
        child = textwrap.dedent('''\
            import json, os, signal, sys, time
            from pathlib import Path
            leader = os.getppid()
            def record(name, data):
                temporary = Path(name + '.tmp')
                temporary.write_text(json.dumps(data))
                temporary.replace(name)
            def observe_exit():
                if os.getppid() != leader:
                    record('leader-exited.json', {'leader': leader, 'parent': os.getppid()})
            def terminate(signum, frame):
                observe_exit()
                Path('tests/test_example.py').write_text('child termination write')
                Path('tests/example.dat').write_bytes(b'child termination fixture')
                print('FAIL: late_stdout (tests.lifecycle.Example)', flush=True)
                print('FAIL: late_stderr (tests.lifecycle.Example)', file=sys.stderr, flush=True)
                print('Ran 1 test in 0.001s\\nFAILED (failures=4)', file=sys.stderr, flush=True)
                sys.exit(0)
            signal.signal(signal.SIGTERM, signal.SIG_IGN if IGNORE_TERM else terminate)
            record('child-ready.json', {'pid': os.getpid(), 'group': os.getpgrp(), 'leader': leader})
            while os.getppid() == leader:
                time.sleep(0.005)
            observe_exit()
            while True:
                signal.pause()
            ''').replace('IGNORE_TERM', repr(ignore_term))
        command = textwrap.dedent('''\
            import subprocess, sys, time
            from pathlib import Path
            subprocess.Popen([sys.executable, '-c', CHILD])
            deadline = time.monotonic() + 5
            while not Path('child-ready.json').exists():
                if time.monotonic() >= deadline:
                    sys.exit('child readiness timed out')
                time.sleep(0.01)
            print('FAIL: early_stdout (tests.lifecycle.Example)', flush=True)
            print('x' * 262144, flush=True)
            print('FAIL: early_stderr (tests.lifecycle.Example)', file=sys.stderr, flush=True)
            print('y' * 262144, file=sys.stderr, flush=True)
            sys.exit(subprocess.run([sys.executable, '-m', 'unittest', 'tests/test_example.py']).returncode)
            ''').replace('CHILD', repr(child))
        expected = self.snapshot([self.test, self.fixture])
        proc = subprocess.Popen(self.argv('--command', sys.executable, '-c', command),
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        group = None
        try:
            ready = self.wait_file(self.repo / 'child-ready.json', proc)
            group = ready['group']
            self.assertEqual(group, ready['leader'])
            exited = self.wait_file(self.repo / 'leader-exited.json', proc)
            self.assertEqual(exited['leader'], group)
            self.assertNotEqual(exited['parent'], group)
            try:
                stdout, stderr = proc.communicate(timeout=6)
            except subprocess.TimeoutExpired:
                self.fail('leader exited but inherited streams blocked preservation; '
                          f'backup_exists={self.backup.exists()}, '
                          f'baseline_installed={self.test.read_text() == BASELINE}')
            self.assertEqual(proc.returncode, 1, stdout + stderr)
            names = ['early_stdout', 'early_stderr']
            if not ignore_term:
                names += ['late_stdout', 'late_stderr']
            for name in names:
                self.assertIn(f'FAILED {name} (tests.lifecycle.Example)', stdout)
            self.assert_group_stopped(group)
            actual = self.snapshot(expected)
            self.assertEqual({path: value[:2] for path, value in actual.items()},
                             {path: value[:2] for path, value in expected.items()})
            self.assertFalse(self.backup.exists())
        finally:
            if group is None and (self.repo / 'child-ready.json').exists():
                group = json.loads((self.repo / 'child-ready.json').read_text())['group']
            if group is not None:
                try:
                    os.killpg(group, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            proc.communicate(timeout=10)
            if group is not None:
                self.assert_group_stopped(group)

    def test_cli_drains_inherited_stdout_and_stderr_after_leader_exit(self):
        self.inherited_streams()

    def test_cli_kills_sigterm_ignoring_descendant_with_inherited_streams(self):
        self.inherited_streams(ignore_term=True)

    def refuse_hard_link(self, target, alias):
        os.link(target, alias)
        paths = [self.test, self.fixture, alias]
        expected = self.snapshot(paths)
        result = subprocess.run(self.argv('--command', sys.executable, '-c',
                                         "from pathlib import Path; Path('command-ran').touch()"),
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn('hard link', result.stderr)
        self.assertEqual(self.snapshot(paths), expected)
        self.assertFalse((self.repo / 'command-ran').exists())
        self.assertFalse(self.backup.exists())

    def test_cli_refuses_hard_linked_fixture_before_changing_earlier_test(self):
        self.refuse_hard_link(self.fixture, self.repo / 'outside-fixture.dat')

    def test_cli_refuses_hard_linked_test_before_any_overlay_write(self):
        self.refuse_hard_link(self.test, self.repo / 'outside-test.py')

    def test_cli_refuses_hard_link_shared_by_selected_paths(self):
        self.fixture.unlink()
        self.refuse_hard_link(self.test, self.fixture)

    def test_cli_refuses_hard_link_to_a_path_outside_the_repository(self):
        outside = tempfile.TemporaryDirectory(prefix='preserve-lifecycle-outside-')
        self.addCleanup(outside.cleanup)
        self.refuse_hard_link(self.fixture, Path(outside.name) / 'fixture.dat')


if __name__ == '__main__':
    unittest.main()
