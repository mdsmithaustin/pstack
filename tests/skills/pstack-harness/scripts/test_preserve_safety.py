import json
import os
import shutil
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


class PreserveSafety(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='preserve-safety-')
        self.addCleanup(self.temporary.cleanup)
        self.repo = Path(self.temporary.name).resolve()
        self.git('init', '-q')
        (self.repo / 'tests').mkdir()
        self.test = self.repo / 'tests/test_example.py'
        self.fixture = self.repo / 'tests/example.dat'
        self.test.write_text(BASELINE)
        self.fixture.write_bytes(b'baseline fixture\x00\xff')
        (self.repo / 'module.py').write_text('VALUE = "baseline"\n')
        self.commit()

    def git(self, *args):
        return subprocess.run(['git', '-C', str(self.repo), *args], check=True, capture_output=True,
                              env={**os.environ, 'GIT_AUTHOR_NAME': 't', 'GIT_AUTHOR_EMAIL': 't@x',
                                   'GIT_COMMITTER_NAME': 't', 'GIT_COMMITTER_EMAIL': 't@x'})

    def commit(self):
        self.git('add', '-A')
        self.git('commit', '-q', '-m', 'baseline')

    def argv(self, *extra):
        return [sys.executable, str(SCRIPT), '--project', str(self.repo), *extra]

    def run_preserve(self, *extra):
        return subprocess.run(self.argv('--since', 'HEAD', '--python', sys.executable, *extra),
                              capture_output=True, text=True, timeout=15)

    @property
    def backup(self):
        return Path(self.git('rev-parse', '--absolute-git-dir').stdout.decode().strip()) / 'preserve-backup'

    def recover(self, backup=None):
        return subprocess.run(self.argv('--recover', str(backup or self.backup)),
                              capture_output=True, text=True, timeout=15)

    def wait_for_child(self, child):
        deadline = time.monotonic() + 5
        while True:
            try:
                os.killpg(child, 0)
            except ProcessLookupError:
                return
            except PermissionError:
                pass
            if time.monotonic() >= deadline:
                self.fail('owned command process group did not exit')
            time.sleep(0.01)

    def edit(self):
        self.edited_test = BASELINE + '\nEDITED = "uncommitted test"\n'
        self.edited_fixture = b'uncommitted fixture\x00\xfe'
        self.test.write_text(self.edited_test)
        self.fixture.write_bytes(self.edited_fixture)
        (self.repo / 'module.py').write_text('VALUE = "uncommitted code"\n')

    def assert_edits(self):
        self.assertEqual(self.test.read_text(), self.edited_test)
        self.assertEqual(self.fixture.read_bytes(), self.edited_fixture)
        self.assertEqual((self.repo / 'module.py').read_text(), 'VALUE = "uncommitted code"\n')

    def active_command(self, ignore_term=False):
        command = textwrap.dedent('''\
            import json, os, signal, sys, time
            from pathlib import Path

            def terminate(signum, frame):
                time.sleep(0.15)
                Path('tests/test_example.py').write_text('child wrote during termination')
                Path('tests/example.dat').write_bytes(b'child fixture during termination')
                Path('child-finished').write_text('finished')
                sys.exit(0)

            signal.signal(signal.SIGTERM, terminate)
            assert Path('tests/test_example.py').read_text() == BASELINE
            assert Path('tests/example.dat').read_bytes() == b'baseline fixture\\x00\\xff'
            assert Path('module.py').read_text() == 'VALUE = "uncommitted code"\\n'
            Path('ready.json').write_text(json.dumps({'pid': os.getpid()}))
            time.sleep(60)
            ''').replace('== BASELINE', '== ' + repr(BASELINE))
        if ignore_term:
            command = command.replace('signal.signal(signal.SIGTERM, terminate)',
                                      'signal.signal(signal.SIGTERM, signal.SIG_IGN)')
        proc = subprocess.Popen(self.argv('--since', 'HEAD', '--python', sys.executable, '--command', sys.executable, '-c', command),
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.addCleanup(self.stop_process, proc)
        deadline = time.monotonic() + 10
        while not (self.repo / 'ready.json').exists():
            if proc.poll() is not None:
                self.fail('preserve stopped before readiness: ' + repr(proc.communicate(timeout=2)))
            if time.monotonic() >= deadline:
                self.fail('selected command never confirmed baseline files')
            time.sleep(0.01)
        child = json.loads((self.repo / 'ready.json').read_text())['pid']
        self.addCleanup(self.stop_child, child)
        return proc, child

    @staticmethod
    def stop_process(proc):
        if proc.poll() is None:
            proc.kill()
        try:
            proc.communicate(timeout=3)
        except subprocess.TimeoutExpired:
            pass

    @staticmethod
    def stop_child(pid):
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass

    def test_setup_class_error_with_a_reason_cannot_waive_zero_execution(self):
        self.test.write_text(textwrap.dedent('''\
            import unittest

            class Example(unittest.TestCase):
                @classmethod
                def setUpClass(cls):
                    raise RuntimeError('setup prevented every body')

                def test_ok(self):
                    self.assertTrue(True)
            '''))
        self.commit()
        reasons = self.repo / 'reasons.txt'
        reasons.write_text('setUpClass (tests.test_example.Example)\n  input: an unavailable setup\n'
                           '  quote: "The setup is unavailable."\n')
        result = self.run_preserve('--reasons', str(reasons))
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn('nothing was checked', result.stdout)
        self.assertIn('ERROR  setUpClass', result.stdout)

    def test_sigterm_waits_for_command_and_restores_test_fixture_and_code(self):
        self.edit()
        proc, child = self.active_command()
        proc.send_signal(signal.SIGTERM)
        proc.wait(timeout=10)
        if proc.returncode == -signal.SIGTERM:
            self.stop_child(child)
        stdout, stderr = proc.communicate(timeout=10)
        self.assertEqual(proc.returncode, 128 + signal.SIGTERM, stdout + stderr)
        self.assertTrue((self.repo / 'child-finished').exists())
        self.assert_edits()
        self.assertFalse(self.backup.exists())
        self.wait_for_child(child)

    def test_interrupt_and_hangup_restore_the_active_overlay(self):
        for signum in (signal.SIGINT, signal.SIGHUP):
            with self.subTest(signum=signum):
                (self.repo / 'ready.json').unlink(missing_ok=True)
                (self.repo / 'child-finished').unlink(missing_ok=True)
                self.edit()
                proc, child = self.active_command()
                proc.send_signal(signum)
                stdout, stderr = proc.communicate(timeout=10)
                self.assertEqual(proc.returncode, 128 + signum, stdout + stderr)
                self.assertTrue((self.repo / 'child-finished').exists())
                self.assert_edits()
                self.wait_for_child(child)

    def test_unresponsive_command_is_killed_before_source_restoration(self):
        self.edit()
        proc, child = self.active_command(ignore_term=True)
        proc.send_signal(signal.SIGTERM)
        stdout, stderr = proc.communicate(timeout=10)
        self.assertEqual(proc.returncode, 143, stdout + stderr)
        self.assertFalse((self.repo / 'child-finished').exists())
        self.wait_for_child(child)
        self.assert_edits()

    def test_command_descendant_cannot_write_after_the_command_exits(self):
        self.edit()
        descendant = textwrap.dedent('''\
            import json, os, signal, time
            from pathlib import Path
            def late_write(signum, frame):
                time.sleep(0.3)
                Path('tests/test_example.py').write_text('late descendant write')
                Path('tests/example.dat').write_bytes(b'late descendant fixture')
            signal.signal(signal.SIGTERM, late_write)
            Path('descendant.json').write_text(json.dumps({'pid': os.getpid(), 'group': os.getpgrp()}))
            time.sleep(60)
            ''')
        command = textwrap.dedent('''\
            import subprocess, sys, time
            from pathlib import Path
            subprocess.Popen([sys.executable, '-c', DESCENDANT], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            deadline = time.monotonic() + 5
            while not Path('descendant.json').exists():
                if time.monotonic() >= deadline:
                    sys.exit('descendant readiness timed out')
                time.sleep(0.01)
            sys.exit(subprocess.run([sys.executable, '-m', 'unittest', 'tests/test_example.py']).returncode)
            ''').replace('DESCENDANT', repr(descendant))
        result = self.run_preserve('--command', sys.executable, '-c', command)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        group = json.loads((self.repo / 'descendant.json').read_text())['group']
        self.wait_for_child(group)
        self.assert_edits()

    def test_backup_is_complete_before_the_selected_command_can_run(self):
        self.edit()
        proc, child = self.active_command()
        manifest = json.loads((self.backup / 'manifest.json').read_text())
        self.assertEqual(manifest['project'], str(self.repo))
        self.assertEqual(manifest['command'], child)
        self.assertEqual((self.backup / manifest['saved']['tests/test_example.py']['backup']).read_text(), self.edited_test)
        self.assertEqual((self.backup / manifest['saved']['tests/example.dat']['backup']).read_bytes(), self.edited_fixture)
        self.assertNotIn('module.py', manifest['saved'])
        self.assertEqual(self.backup.stat().st_mode & 0o777, 0o700)
        recovery = self.recover()
        self.assertEqual(recovery.returncode, 2, recovery.stdout + recovery.stderr)
        self.assertIn(f'preservation process {proc.pid} still exists', recovery.stderr)
        proc.send_signal(signal.SIGTERM)
        stdout, stderr = proc.communicate(timeout=10)
        self.assertEqual(proc.returncode, 143, stdout + stderr)
        self.assert_edits()

    def test_sigkill_retains_backup_blocks_new_overlay_and_supports_recovery(self):
        self.edit()
        proc, child = self.active_command()
        proc.kill()
        proc.wait(timeout=5)
        before = (self.backup / 'manifest.json').read_bytes()
        retry = self.run_preserve()
        self.assertEqual(retry.returncode, 2, retry.stdout + retry.stderr)
        self.assertIn('pending preservation backup', retry.stderr)
        self.assertEqual((self.backup / 'manifest.json').read_bytes(), before)
        active_recovery = self.recover()
        self.assertEqual(active_recovery.returncode, 2, active_recovery.stdout + active_recovery.stderr)
        self.assertIn('still exists', active_recovery.stderr)
        self.stop_child(child)
        proc.communicate(timeout=10)
        self.wait_for_child(child)
        result = self.recover()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assert_edits()
        self.assertFalse(self.backup.exists())
        repeated = self.recover()
        self.assertEqual(repeated.returncode, 0, repeated.stdout + repeated.stderr)
        self.assert_edits()

    def failed_restore(self):
        self.edit()
        command = textwrap.dedent('''\
            import subprocess, sys
            from pathlib import Path
            result = subprocess.run([sys.executable, '-m', 'unittest', 'tests/test_example.py'])
            Path('tests/test_example.py').unlink()
            Path('tests/test_example.py').mkdir()
            Path('tests/example.dat').write_bytes(b'changed fixture')
            sys.exit(result.returncode)
            ''')
        result = self.run_preserve('--command', sys.executable, '-c', command)
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn('restoration incomplete; backup retained', result.stderr)
        self.assertTrue(self.test.is_dir())
        self.assertEqual(self.fixture.read_bytes(), self.edited_fixture)
        manifest = json.loads((self.backup / 'manifest.json').read_text())
        saved = self.backup / manifest['saved']['tests/test_example.py']['backup']
        self.assertEqual(saved.read_text(), self.edited_test)
        return manifest

    def test_failed_restore_keeps_original_bytes_until_repeated_recovery_succeeds(self):
        self.failed_restore()
        repeated = self.recover()
        self.assertEqual(repeated.returncode, 2, repeated.stdout + repeated.stderr)
        self.assertTrue(self.backup.exists())
        self.test.rmdir()
        result = self.recover()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assert_edits()
        self.assertEqual(self.recover().returncode, 0)

    def test_recovery_refuses_foreign_paths_projects_and_invalid_manifest_paths(self):
        manifest = self.failed_restore()
        original = (self.backup / 'manifest.json').read_bytes()
        foreign = self.repo / 'foreign-backup'
        foreign.mkdir()
        result = self.recover(foreign)
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("this worktree's backup directory", result.stderr)
        for replacement in (
                {**manifest, 'project': str(self.repo.parent)},
                {**manifest, 'saved': {'../outside.py': {'backup': '0', 'mode': 0o644}}},
                {**manifest, 'saved': {'.git/config': {'backup': '0', 'mode': 0o644}}},
                {**manifest, 'saved': {'tests/test_example.py': {'backup': '../outside', 'mode': 0o644}}},
                {**manifest, 'made_dirs': ['../outside']},
        ):
            with self.subTest(replacement=replacement):
                (self.backup / 'manifest.json').write_text(json.dumps(replacement))
                result = self.recover()
                self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                self.assertIn('invalid recovery manifest', result.stderr)
                self.assertTrue(self.test.is_dir())
        (self.backup / 'manifest.json').write_bytes(original)
        self.test.rmdir()
        self.assertEqual(self.recover().returncode, 0)
        self.assert_edits()

    def test_restoration_refuses_changed_symlinks_and_keeps_backups(self):
        self.edit()
        outside = self.repo / 'outside.dat'
        outside.write_bytes(b'outside content')
        command = "from pathlib import Path; p = Path('tests/example.dat'); p.unlink(); p.symlink_to('../outside.dat')"
        result = self.run_preserve('--command', sys.executable, '-c', command)
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertEqual(outside.read_bytes(), b'outside content')
        self.assertTrue(self.backup.exists())
        self.fixture.unlink()
        self.assertEqual(self.recover().returncode, 0)
        self.assert_edits()

    def test_command_start_error_restores_source_bytes_and_mode(self):
        self.edit()
        self.test.chmod(0o751)
        result = self.run_preserve('--command', str(self.repo / 'missing-executable'))
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assert_edits()
        self.assertEqual(self.test.stat().st_mode & 0o777, 0o751)
        self.assertFalse(self.backup.exists())

    def test_backup_cleanup_failure_keeps_completed_state_and_does_not_replay_restoration(self):
        self.edit()
        extra = self.backup / 'unexpected.dat'
        command = ("import subprocess, sys; from pathlib import Path; "
                   f"Path({str(extra)!r}).write_bytes(b'keep this evidence'); "
                   "sys.exit(subprocess.run([sys.executable, '-m', 'unittest', 'tests/test_example.py']).returncode)")
        result = self.run_preserve('--command', sys.executable, '-c', command)
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn('restored working tree and backup retained', result.stderr)
        self.assert_edits()
        manifest = json.loads((self.backup / 'manifest.json').read_text())
        self.assertTrue(manifest['restored'])
        self.assertEqual(extra.read_bytes(), b'keep this evidence')
        for entry in manifest['saved'].values():
            if entry['backup'] is not None:
                self.assertTrue((self.backup / entry['backup']).is_file())
        subsequent = self.edited_test + 'SUBSEQUENT = "keep this edit too"\n'
        self.test.write_text(subsequent)
        extra.unlink()
        result = self.recover()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.test.read_text(), subsequent)
        self.assertEqual(self.fixture.read_bytes(), self.edited_fixture)
        self.assertFalse(self.backup.exists())

    def test_missing_files_and_directories_are_removed_after_the_run(self):
        self.test.unlink()
        self.fixture.unlink()
        (self.repo / 'tests').rmdir()
        result = self.run_preserve()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse((self.repo / 'tests').exists())
        self.assertFalse(self.backup.exists())

    def test_new_files_in_created_directories_survive_failed_cleanup(self):
        self.test.unlink()
        self.fixture.unlink()
        (self.repo / 'tests').rmdir()
        command = "from pathlib import Path; Path('tests/new-data.dat').write_bytes(b'new data')"
        result = self.run_preserve('--command', sys.executable, '-c', command)
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertEqual((self.repo / 'tests/new-data.dat').read_bytes(), b'new data')
        self.assertTrue(self.backup.exists())
        (self.repo / 'tests/new-data.dat').unlink()
        self.assertEqual(self.recover().returncode, 0)
        self.assertFalse((self.repo / 'tests').exists())

    def test_created_directory_cleanup_refuses_replaced_ancestor_links_during_recovery(self):
        nested = self.repo / 'tests/nested'
        nested.mkdir()
        (nested / 'test_nested.py').write_text(BASELINE)
        self.commit()
        shutil.rmtree(self.repo / 'tests')
        code = b'VALUE = "keep the uncommitted application edit"\n'
        (self.repo / 'module.py').write_bytes(code)
        outside_temporary = tempfile.TemporaryDirectory(prefix='preserve-outside-')
        self.addCleanup(outside_temporary.cleanup)
        outside = Path(outside_temporary.name).resolve()
        (outside / 'nested').mkdir()
        sentinel = outside / 'keep.dat'
        sentinel.write_bytes(b'outside data\x00\xff')
        command = textwrap.dedent('''\
            import os, shutil, unittest
            class Swap(unittest.TestCase):
                def test_swap(self):
                    shutil.rmtree('tests')
                    os.symlink(OUTSIDE, 'tests')
            if __name__ == '__main__':
                unittest.main()
            ''').replace('OUTSIDE', repr(str(outside)))
        result = self.run_preserve('--command', sys.executable, '-c', command)
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertTrue((outside / 'nested').is_dir(), result.stdout + result.stderr)
        self.assertEqual(sentinel.read_bytes(), b'outside data\x00\xff')
        self.assertTrue(self.backup.is_dir())
        manifest = (self.backup / 'manifest.json').read_bytes()
        retry = self.recover()
        self.assertEqual(retry.returncode, 2, retry.stdout + retry.stderr)
        self.assertTrue((outside / 'nested').is_dir(), retry.stdout + retry.stderr)
        self.assertEqual(sentinel.read_bytes(), b'outside data\x00\xff')
        self.assertEqual((self.backup / 'manifest.json').read_bytes(), manifest)
        (self.repo / 'tests').unlink()
        result = self.recover()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.recover().returncode, 0)
        self.assertFalse((self.repo / 'tests').exists())
        self.assertTrue((outside / 'nested').is_dir())
        self.assertEqual(sentinel.read_bytes(), b'outside data\x00\xff')
        self.assertEqual((self.repo / 'module.py').read_bytes(), code)
        self.assertFalse(self.backup.exists())

    def test_setup_error_stays_waivable_when_another_body_executes(self):
        self.test.write_text(textwrap.dedent('''\
            import unittest

            class Example(unittest.TestCase):
                @classmethod
                def setUpClass(cls):
                    raise RuntimeError('one class is unavailable')
                def test_unavailable(self):
                    self.fail('setup prevents this body')

            class Available(unittest.TestCase):
                def test_ok(self):
                    self.assertTrue(True)
                @unittest.skip('one case is unavailable')
                def test_skip(self):
                    self.fail('this body is skipped')
            '''))
        self.commit()
        reasons = self.repo / 'reasons.txt'
        reasons.write_text('setUpClass (tests.test_example.Example)\n  input: an unavailable setup\n'
                           '  quote: "The setup is unavailable."\n')
        result = self.run_preserve('--reasons', str(reasons))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('1 test(s) waived', result.stdout)
        self.assertNotIn('nothing was checked', result.stdout)

    def test_recovery_rejects_execution_flags_and_does_not_touch_source(self):
        self.edit()
        for extra in (('--since', 'HEAD'), ('--report-only',), ('--reasons', 'unused'),
                      ('--python', sys.executable), ('--command', 'unused')):
            with self.subTest(extra=extra):
                result = subprocess.run(self.argv('--recover', str(self.backup), *extra),
                                        capture_output=True, text=True, timeout=5)
                self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                self.assert_edits()


if __name__ == '__main__':
    unittest.main()
