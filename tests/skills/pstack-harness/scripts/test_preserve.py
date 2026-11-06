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
        since = ['--since', 'HEAD'] if '--since' not in extra else []
        return subprocess.run(
            [sys.executable, str(SCRIPT), *since, '--project', str(self.repo), '--python', sys.executable, *extra],
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
        self.assertEqual((self.repo / 'tests/test_mod.py').read_text(), TESTS)

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
        self.assertEqual(sum('test_scheme_kept' in l for l in result.stdout.splitlines()), 2, result.stdout)

    def test_tests_prefixed_root_file_is_a_test_file(self):
        (self.repo / 'tests_root.py').write_text(TESTS)
        git(self.repo, 'rm', '-q', '-r', 'tests')
        git(self.repo, 'add', '-A')
        git(self.repo, 'commit', '-q', '-m', 'tests_ prefix')
        (self.repo / 'mod.py').write_text(NARROWED)
        result = self.run_preserve()
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn('test_scheme_kept', result.stdout)

    def test_file_relative_cli_test_runs_in_place(self):
        (self.repo / 'cli.py').write_text("import sys\nprint('ok' if sys.argv[1:] == ['x'] else 'bad')\n")
        (self.repo / 'tests/test_cli.py').write_text(textwrap.dedent('''\
            import subprocess, sys, unittest
            from pathlib import Path

            class Cli(unittest.TestCase):
                def test_runs(self):
                    cli = Path(__file__).resolve().parent.parent / "cli.py"
                    out = subprocess.run([sys.executable, str(cli), "x"], capture_output=True, text=True)
                    self.assertEqual(out.stdout.strip(), "ok")
            '''))
        git(self.repo, 'add', '-A')
        git(self.repo, 'commit', '-q', '-m', 'cli test')
        result = self.run_preserve()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('run in place', result.stdout)

    def test_working_tree_is_restored_after_the_run(self):
        edited = TESTS.replace('"a"', '"b"')
        (self.repo / 'tests/test_mod.py').write_text(edited)
        (self.repo / 'tests/test_new.py').write_text(TESTS)
        self.run_preserve()
        self.assertEqual((self.repo / 'tests/test_mod.py').read_text(), edited)
        self.assertTrue((self.repo / 'tests/test_new.py').exists())
        git(self.repo, 'rm', '-q', '-r', '-f', 'tests')
        git(self.repo, 'commit', '-q', '-m', 'drop tests')
        (self.repo / 'tests').mkdir(exist_ok=True)
        (self.repo / 'tests/test_new.py').write_text(TESTS)
        result = self.run_preserve('--since', 'HEAD~1')
        self.assertIn(result.returncode, (0, 1), result.stdout + result.stderr)
        self.assertEqual(sorted(p.name for p in (self.repo / 'tests').iterdir() if p.name != '__pycache__'), ['test_new.py'])

    REASON = textwrap.dedent('''\
        # the scheme test sends a value the new spec forbids
        test_scheme_kept
          input: a destination with the ignored:// scheme
          quote: "Every destination starts with backup:// and names a store."
        ''')

    def test_reasons_block_naming_each_failure_waives_it(self):
        (self.repo / 'mod.py').write_text(NARROWED)
        (self.repo / 'reasons.txt').write_text(self.REASON)
        result = self.run_preserve('--reasons', str(self.repo / 'reasons.txt'))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('1 test(s) waived', result.stdout)
        self.assertIn('reason: input a destination with the ignored:// scheme', result.stdout)

    def test_failure_without_a_block_still_fails(self):
        (self.repo / 'mod.py').write_text("def parse(value):\n    raise ValueError(value)\n")
        (self.repo / 'reasons.txt').write_text(self.REASON)
        result = self.run_preserve('--reasons', str(self.repo / 'reasons.txt'))
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn('test_plain', result.stdout)
        self.assertIn('1 test(s) have no reason', result.stdout)

    def test_a_file_that_cannot_run_is_never_waived(self):
        (self.repo / 'mod.py').rename(self.repo / 'core.py')
        (self.repo / 'reasons.txt').write_text("test_mod\n  input: every input\n  quote: \"The module moved to core and the old tests are stale.\"\n")
        result = self.run_preserve('--reasons', str(self.repo / 'reasons.txt'))
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn('have no reason', result.stdout)

    def test_block_without_input_or_quoted_sentence_is_unusable(self):
        (self.repo / 'mod.py').write_text(NARROWED)
        for body in ("test_scheme_kept\n  quote: \"Every destination starts with backup:// and names a store.\"\n",
                     "test_scheme_kept\n  input: the old scheme\n  quote: the schema changed\n",
                     "test_scheme_kept\n  input: the old scheme\n  quote: \"backup:// only\"\n"):
            (self.repo / 'reasons.txt').write_text(body)
            with self.subTest(body=body.splitlines()[-1]):
                result = self.run_preserve('--reasons', str(self.repo / 'reasons.txt'))
                self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                self.assertIn('not a usable reasons file', result.stderr)

    def test_block_naming_no_failing_test_is_reported(self):
        (self.repo / 'reasons.txt').write_text(self.REASON)
        result = self.run_preserve('--reasons', str(self.repo / 'reasons.txt'))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('names no failing test: test_scheme_kept', result.stdout)
        self.assertIn('All earlier tests still pass unedited.', result.stdout)

    def test_pytest_ids_and_unittest_ids_both_match_a_block(self):
        (self.repo / 'mod.py').write_text(NARROWED)
        for wanted in ('tests/test_mod.py::Parse::test_scheme_kept', 'test_scheme_kept (tests.test_mod.Parse.test_scheme_kept)'):
            (self.repo / 'reasons.txt').write_text(self.REASON.replace('test_scheme_kept\n', wanted + '\n', 1))
            with self.subTest(wanted=wanted):
                result = self.run_preserve('--reasons', str(self.repo / 'reasons.txt'))
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_unknown_commit_exits_two(self):
        result = subprocess.run([sys.executable, str(SCRIPT), '--since', 'nope', '--project', str(self.repo)],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn('not a commit', result.stderr)


if __name__ == '__main__':
    unittest.main()
