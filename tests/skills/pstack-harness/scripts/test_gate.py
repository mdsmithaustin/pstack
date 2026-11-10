import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
SCRIPT = ROOT / 'skills/pstack-harness/scripts/gate.py'


class GateEvidence(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.repo = Path(self.directory.name)
        self.git('init', '-q')
        self.git('config', 'user.email', 't@t')
        self.git('config', 'user.name', 'Test')
        (self.repo / 'a.txt').write_text('one\n')
        self.git('add', 'a.txt')
        self.git('commit', '-q', '-m', 'first')

    def git(self, *args):
        subprocess.run(['git', '-C', str(self.repo), *args], check=True, capture_output=True)

    def gate(self, *args):
        return subprocess.run([sys.executable, str(SCRIPT), '--project', str(self.repo), *args], capture_output=True, text=True)

    def test_unrecorded_gate_is_missing(self):
        done = self.gate('check', 'cleanup')
        self.assertEqual(done.returncode, 1)
        self.assertIn('missing cleanup', done.stdout)

    def test_recorded_gate_is_current_for_the_same_tree(self):
        self.assertEqual(self.gate('record', 'cleanup', '--note', 'no cuts').returncode, 0)
        done = self.gate('check', 'cleanup')
        self.assertEqual(done.returncode, 0, done.stdout)
        self.assertIn('current cleanup: pass', done.stdout)

    def test_an_edit_makes_the_evidence_stale_and_names_the_path(self):
        self.gate('record', 'cleanup')
        (self.repo / 'a.txt').write_text('two\n')
        (self.repo / 'new.txt').write_text('untracked\n')
        done = self.gate('check', 'cleanup')
        self.assertEqual(done.returncode, 1)
        self.assertIn('stale cleanup', done.stdout)
        self.assertIn('  a.txt', done.stdout)
        self.assertIn('  new.txt', done.stdout)

    def test_committing_the_same_content_keeps_the_evidence_current(self):
        (self.repo / 'a.txt').write_text('two\n')
        self.gate('record', 'cleanup')
        self.git('commit', '-q', '-am', 'second')
        self.assertEqual(self.gate('check', 'cleanup').returncode, 0)
        self.assertEqual(self.gate('--tree', 'HEAD', 'check', 'cleanup').returncode, 0)

    def test_a_recorded_failure_does_not_pass(self):
        self.gate('record', 'scrutiny', '--result', 'fail', '--note', 'spec gap')
        done = self.gate('check', 'scrutiny')
        self.assertEqual(done.returncode, 1)
        self.assertIn('failed scrutiny', done.stdout)

    def test_recording_leaves_the_index_and_work_tree_alone(self):
        (self.repo / 'new.txt').write_text('untracked\n')
        before = subprocess.run(['git', '-C', str(self.repo), 'status', '--porcelain'], capture_output=True, text=True).stdout
        self.gate('record', 'cleanup')
        after = subprocess.run(['git', '-C', str(self.repo), 'status', '--porcelain'], capture_output=True, text=True).stdout
        self.assertEqual(before, after)

    def test_list_reports_each_gate(self):
        self.gate('record', 'cleanup')
        self.gate('record', 'documentation')
        (self.repo / 'a.txt').write_text('two\n')
        self.gate('record', 'cleanup')
        self.assertEqual(self.gate('list').stdout.splitlines(), ['cleanup: pass (current)', 'documentation: pass (stale)'])

    def test_concurrent_records_keep_every_gate(self):
        names = [f'gate-{index}' for index in range(12)]
        running = [subprocess.Popen([sys.executable, str(SCRIPT), '--project', str(self.repo), 'record', name],
                                    stdout=subprocess.DEVNULL, stderr=subprocess.PIPE) for name in names]
        for process in running:
            _, errors = process.communicate()
            self.assertEqual(process.returncode, 0, errors)
        listed = [line.split(':')[0] for line in self.gate('list').stdout.splitlines()]
        self.assertEqual(sorted(listed), sorted(names))
        self.assertEqual(list((self.repo / '.git/pstack').glob('*.tmp')), [])
        self.assertFalse((self.repo / '.git/pstack/gates.lock').exists())

    def test_a_stale_lock_is_cleared(self):
        import os
        import time
        lock = self.repo / '.git/pstack/gates.lock'
        lock.mkdir(parents=True)
        old = time.time() - 600
        os.utime(lock, (old, old))
        self.assertEqual(self.gate('record', 'cleanup').returncode, 0)

    def test_outside_a_repository_is_a_usage_error(self):
        with tempfile.TemporaryDirectory() as directory:
            done = subprocess.run([sys.executable, str(SCRIPT), '--project', directory, 'check', 'cleanup'], capture_output=True, text=True)
            self.assertEqual(done.returncode, 2)


if __name__ == '__main__':
    unittest.main()
