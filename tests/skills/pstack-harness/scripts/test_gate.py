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

    def test_outside_a_repository_is_a_usage_error(self):
        with tempfile.TemporaryDirectory() as directory:
            done = subprocess.run([sys.executable, str(SCRIPT), '--project', directory, 'check', 'cleanup'], capture_output=True, text=True)
            self.assertEqual(done.returncode, 2)


if __name__ == '__main__':
    unittest.main()
