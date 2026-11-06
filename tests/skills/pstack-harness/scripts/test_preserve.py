import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
SCRIPT = ROOT / 'skills/pstack-harness/scripts/preserve.py'

MODULE = "def parse(value):\n    return value\n"
TESTS = textwrap.dedent('''\
    import unittest
    from mod import parse


    class Parse(unittest.TestCase):
        def test_plain(self):
            self.assertEqual(parse("a"), "a")

        def test_scheme_kept(self):
            self.assertEqual(parse("ignored://sink"), "ignored://sink")
    ''')
NARROWED = "def parse(value):\n    if value.startswith('ignored://'):\n        raise ValueError(value)\n    return value\n"


def git(repo, *args):
    subprocess.run(['git', '-C', str(repo), *args], check=True, capture_output=True,
                   env={**os.environ, 'GIT_AUTHOR_NAME': 't', 'GIT_AUTHOR_EMAIL': 't@x', 'GIT_COMMITTER_NAME': 't', 'GIT_COMMITTER_EMAIL': 't@x'})


class Preserve(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        git(self.repo, 'init', '-q')
        (self.repo / 'mod.py').write_text(MODULE)
        (self.repo / 'tests').mkdir()
        (self.repo / 'tests/test_mod.py').write_text(TESTS)
        git(self.repo, 'add', '-A')
        git(self.repo, 'commit', '-q', '-m', 'start')

    def tearDown(self):
        self.tmp.cleanup()

    def run_preserve(self, *extra):
        return subprocess.run(
            [sys.executable, str(SCRIPT), '--since', 'HEAD', '--project', str(self.repo), '--python', sys.executable, *extra],
            capture_output=True, text=True,
        )

    def test_unchanged_code_passes(self):
        result = self.run_preserve()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('All earlier tests still pass unedited.', result.stdout)

    def test_narrowed_code_fails_on_the_earlier_test(self):
        (self.repo / 'mod.py').write_text(NARROWED)
        result = self.run_preserve()
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn('test_scheme_kept', result.stdout)
        self.assertIn('allowed reason', result.stdout)

    def test_editing_the_working_tree_test_does_not_hide_the_failure(self):
        (self.repo / 'mod.py').write_text(NARROWED)
        (self.repo / 'tests/test_mod.py').write_text(TESTS.replace('self.assertEqual(parse("ignored://sink"), "ignored://sink")',
                                                                   'self.assertRaises(ValueError, parse, "ignored://sink")'))
        result = self.run_preserve()
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn('test_scheme_kept', result.stdout)

    def test_renamed_module_is_reported_as_an_error_not_a_failure(self):
        (self.repo / 'mod.py').rename(self.repo / 'core.py')
        result = self.run_preserve()
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn('ERROR', result.stdout)
        self.assertIn('could not run', result.stdout)

    def test_report_only_exits_zero_with_the_same_report(self):
        (self.repo / 'mod.py').write_text(NARROWED)
        result = self.run_preserve('--report-only')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('test_scheme_kept', result.stdout)

    def test_commit_without_tests_exits_two(self):
        git(self.repo, 'rm', '-q', '-r', 'tests')
        git(self.repo, 'commit', '-q', '-m', 'no tests')
        result = self.run_preserve()
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn('nothing to preserve', result.stdout)

    def test_tests_directory_without_init_is_discovered(self):
        self.assertFalse((self.repo / 'tests/__init__.py').exists())
        (self.repo / 'mod.py').write_text(NARROWED)
        result = self.run_preserve()
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn('test_scheme_kept', result.stdout)
        self.assertNotIn('no tests discovered', result.stdout)

    def test_root_level_test_file_is_discovered(self):
        (self.repo / 'test_root.py').write_text(TESTS)
        git(self.repo, 'add', '-A')
        git(self.repo, 'commit', '-q', '-m', 'root test')
        (self.repo / 'mod.py').write_text(NARROWED)
        result = self.run_preserve()
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertEqual(result.stdout.count('test_scheme_kept'), 2, result.stdout)

    def test_unknown_commit_exits_two(self):
        result = subprocess.run([sys.executable, str(SCRIPT), '--since', 'nope', '--project', str(self.repo)],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn('not a commit', result.stderr)


if __name__ == '__main__':
    unittest.main()
