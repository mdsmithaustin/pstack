import importlib.util
import os
import py_compile
import subprocess
import sys
import tempfile
import textwrap
import unittest
import venv
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
SCRIPT = ROOT / 'skills/pstack-harness/scripts/preserve.py'
HAS_PYTEST = importlib.util.find_spec('pytest') is not None

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

    def run_preserve(self, *extra, env=None):
        since = ['--since', 'HEAD'] if '--since' not in extra else []
        return subprocess.run(
            [sys.executable, str(SCRIPT), *since, '--project', str(self.repo), '--python', sys.executable, *extra],
            capture_output=True, text=True, env=env,
        )

    def test_project_command_uses_the_projects_test_selection(self):
        (self.repo / 'fixtures').mkdir()
        saved = self.repo / 'fixtures/test_saved.py'
        saved.write_text('import unavailable_example_dependency\n')
        git(self.repo, 'add', '-A')
        git(self.repo, 'commit', '-q', '-m', 'saved example')
        command = ('--command', sys.executable, '-m', 'unittest', 'discover', '-s', 'tests')
        result = self.run_preserve(*command)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("baseline Python test file(s) restored", result.stdout)
        self.assertIn("selected project test command passed", result.stdout)
        self.assertNotIn("All earlier tests still pass", result.stdout)
        (self.repo / 'mod.py').write_text(NARROWED)
        edited = TESTS.replace('ignored://sink', 'allowed://sink')
        (self.repo / 'tests/test_mod.py').write_text(edited)
        result = self.run_preserve(*command)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn('test_scheme_kept', result.stdout)
        self.assertEqual((self.repo / 'tests/test_mod.py').read_text(), edited)
        self.assertEqual(saved.read_text(), 'import unavailable_example_dependency\n')

    def test_project_command_that_runs_nothing_cannot_pass(self):
        result = self.run_preserve('--command', sys.executable, '-c', 'pass')
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn('nothing was checked', result.stdout)

    def test_a_suite_with_only_skipped_tests_cannot_pass(self):
        (self.repo / 'tests/test_mod.py').write_text(TESTS.replace(
            'class Parse', '@unittest.skip("no test body executes")\nclass Parse'))
        git(self.repo, 'add', '-A')
        git(self.repo, 'commit', '-q', '-m', 'all tests skipped')
        for command in ((), ('--command', sys.executable, '-m', 'unittest', 'discover', '-s', 'tests')):
            with self.subTest(command=command):
                result = self.run_preserve(*command)
                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                self.assertIn('nothing was checked', result.stdout)

    def test_project_command_with_executed_and_skipped_tests_passes(self):
        (self.repo / 'tests/test_mod.py').write_text(TESTS.replace(
            '    def test_plain', '    @unittest.skip("one case is unavailable")\n    def test_plain'))
        git(self.repo, 'add', '-A')
        git(self.repo, 'commit', '-q', '-m', 'one test skipped')
        result = self.run_preserve('--command', sys.executable, '-m', 'unittest', 'discover', '-s', 'tests')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('selected project test command passed', result.stdout)

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

    def test_commit_without_tests_satisfies_the_gate(self):
        git(self.repo, 'rm', '-q', '-r', 'tests')
        git(self.repo, 'commit', '-q', '-m', 'no tests')
        result = self.run_preserve()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('nothing to preserve', result.stdout)
        self.assertIn('own runner by hand', result.stdout)

    @unittest.skipUnless(HAS_PYTEST, 'requires pytest in the selected interpreter')
    def test_function_style_tests_without_a_pytest_marker_still_run(self):
        (self.repo / 'tests/test_mod.py').write_text("from mod import parse\n\n\ndef test_scheme_kept():\n    assert parse('ignored://sink') == 'ignored://sink'\n")
        git(self.repo, 'add', '-A')
        git(self.repo, 'commit', '-q', '-m', 'function tests')
        (self.repo / 'mod.py').write_text(NARROWED)
        result = self.run_preserve()
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn('test_scheme_kept', result.stdout)
        self.assertIn('with pytest', result.stdout)

    @unittest.skipUnless(HAS_PYTEST, 'requires pytest in the selected interpreter')
    def test_class_style_tests_without_a_pytest_marker_still_run(self):
        (self.repo / 'tests/test_mod.py').write_text(textwrap.dedent('''\
            from mod import parse

            class TestParse:
                def test_scheme_kept(self):
                    assert parse("ignored://sink") == "ignored://sink"
            '''))
        git(self.repo, 'add', '-A')
        git(self.repo, 'commit', '-q', '-m', 'class tests')
        (self.repo / 'mod.py').write_text(NARROWED)
        result = self.run_preserve()
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn('test_scheme_kept', result.stdout)
        self.assertIn('with pytest', result.stdout)

    def test_function_style_suite_requires_pytest_when_unavailable(self):
        (self.repo / 'tests/test_mod.py').write_text('def test_plain():\n    assert True\n')
        git(self.repo, 'add', '-A')
        git(self.repo, 'commit', '-q', '-m', 'function tests')
        isolated = self.repo / 'isolated'
        venv.EnvBuilder(with_pip=False).create(isolated)
        result = self.run_preserve('--python', str(isolated / 'bin/python'))
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn('pytest', result.stdout)
        self.assertIn('ERROR', result.stdout)
        self.assertNotIn('All earlier tests still pass', result.stdout)

    @unittest.skipUnless(HAS_PYTEST, 'requires pytest in the selected interpreter')
    def test_mixed_unittest_and_function_tests_all_run(self):
        (self.repo / 'tests/test_mod.py').write_text(TESTS.replace('"ignored://sink"', '"a"') + textwrap.dedent('''\

            def test_function_regression():
                assert parse("ignored://sink") == "ignored://sink"
            '''))
        git(self.repo, 'add', '-A')
        git(self.repo, 'commit', '-q', '-m', 'mixed tests')
        (self.repo / 'mod.py').write_text(NARROWED)
        result = self.run_preserve()
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn('test_function_regression', result.stdout)

    def test_cached_working_tree_tests_cannot_hide_a_regression(self):
        for runner in ('unittest', 'pytest') if HAS_PYTEST else ('unittest',):
            with self.subTest(runner=runner):
                if runner == 'pytest':
                    (self.repo / 'conftest.py').write_text('')
                (self.repo / 'mod.py').write_text(MODULE.replace('return value', 'return value.replace("ignored", "changed")'))
                edited = TESTS.replace('), "ignored://sink")', '), "changed://sink")')
                self.assertEqual(len(edited), len(TESTS))
                test_file = self.repo / 'tests/test_mod.py'
                test_file.write_text(edited)
                py_compile.compile(str(test_file), doraise=True,
                                   invalidation_mode=py_compile.PycInvalidationMode.UNCHECKED_HASH)
                result = self.run_preserve()
                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                self.assertIn('test_scheme_kept', result.stdout)
                self.assertEqual(test_file.read_text(), edited)

    def test_a_run_that_checks_nothing_is_an_error(self):
        (self.repo / 'tests/test_mod.py').write_text("import sys\nsys.exit(1)\n")
        git(self.repo, 'add', '-A')
        git(self.repo, 'commit', '-q', '-m', 'exits on import')
        result = self.run_preserve()
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn('ERROR', result.stdout)
        self.assertNotIn('All earlier tests still pass', result.stdout)

    def test_bare_name_shorthand_covers_only_one_failing_test(self):
        (self.repo / 'tests/test_other.py').write_text(TESTS.replace('class Parse', 'class Other'))
        git(self.repo, 'add', '-A')
        git(self.repo, 'commit', '-q', '-m', 'second module')
        (self.repo / 'mod.py').write_text(NARROWED)
        (self.repo / 'reasons.txt').write_text(self.REASON)
        result = self.run_preserve('--reasons', str(self.repo / 'reasons.txt'))
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn('2 test(s) have no reason', result.stdout)
        qualified = self.REASON.replace('test_scheme_kept\n', 'tests.test_mod.Parse.test_scheme_kept\ntests.test_other.Other.test_scheme_kept\n', 1)
        (self.repo / 'reasons.txt').write_text(qualified)
        result = self.run_preserve('--reasons', str(self.repo / 'reasons.txt'))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    @unittest.skipUnless(HAS_PYTEST, 'requires pytest in the selected interpreter')
    def test_pytest_collection_error_is_never_waived(self):
        (self.repo / 'conftest.py').write_text('')
        (self.repo / 'tests/test_mod.py').write_text("import pytest\nfrom mod import parse\n\n\ndef test_scheme_kept():\n    assert parse('ignored://sink') == 'ignored://sink'\n")
        git(self.repo, 'add', '-A')
        git(self.repo, 'commit', '-q', '-m', 'pytest suite')
        (self.repo / 'mod.py').rename(self.repo / 'core.py')
        (self.repo / 'reasons.txt').write_text("tests/test_mod.py\n  input: every input\n  quote: \"The module moved to core and the old tests are stale.\"\n")
        result = self.run_preserve('--reasons', str(self.repo / 'reasons.txt'))
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn('have no reason', result.stdout)

    def test_setup_failure_restores_the_files_already_replaced(self):
        (self.repo / 'tests/test_new.py').write_text(TESTS)
        git(self.repo, 'add', '-A')
        git(self.repo, 'commit', '-q', '-m', 'two test files')
        edited = TESTS.replace('"a"', '"b"')
        (self.repo / 'tests/test_mod.py').write_text(edited)
        (self.repo / 'tests/test_new.py').unlink()
        (self.repo / 'tests/test_new.py').mkdir()
        result = self.run_preserve()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual((self.repo / 'tests/test_mod.py').read_text(), edited)
        self.assertTrue((self.repo / 'tests/test_new.py').is_dir())

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

    def test_short_spec_sentences_are_valid_reasons(self):
        (self.repo / 'mod.py').write_text(NARROWED)
        for quote in ('Reject old values.', 'Destination is required.'):
            with self.subTest(quote=quote):
                reason = self.REASON.replace('Every destination starts with backup:// and names a store.', quote)
                (self.repo / 'reasons.txt').write_text(reason)
                result = self.run_preserve('--reasons', str(self.repo / 'reasons.txt'))
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

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
                     "test_scheme_kept\n  input: the old scheme\n  quote: \"\"\n"):
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

    def test_no_commits_baseline_satisfies_the_gate(self):
        for since in ('no commits', 'no-commits'):
            result = subprocess.run([sys.executable, str(SCRIPT), '--since', since, '--project', str(self.repo)], capture_output=True, text=True)
            with self.subTest(since=since):
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn('started with no commits', result.stdout)

    def test_symlinked_test_path_is_refused_with_the_tree_intact(self):
        (self.repo / 'tests/data.json').write_text('{"a": 1}')
        (self.repo / 'tests/test_alias.py').symlink_to('test_mod.py')
        git(self.repo, 'add', '-A')
        git(self.repo, 'commit', '-q', '-m', 'alias link')
        edited = TESTS.replace('"a"', '"b"')
        (self.repo / 'tests/test_mod.py').write_text(edited)
        result = self.run_preserve()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual((self.repo / 'tests/test_mod.py').read_text(), edited)
        self.assertTrue((self.repo / 'tests/test_alias.py').is_symlink())
        (self.repo / 'tests/test_alias.py').unlink()
        (self.repo / 'tests/test_alias.py').write_text(TESTS)
        git(self.repo, 'add', '-A')
        git(self.repo, 'commit', '-q', '-m', 'alias is a file now')
        (self.repo / 'tests/test_alias.py').unlink()
        (self.repo / 'tests/test_alias.py').symlink_to('test_mod.py')
        result = self.run_preserve()
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn('symlink', result.stderr)
        self.assertEqual((self.repo / 'tests/test_mod.py').read_text(), edited)

    @unittest.skipUnless(HAS_PYTEST, 'requires pytest in the selected interpreter')
    def test_parameterized_cases_need_their_own_names(self):
        (self.repo / 'conftest.py').write_text('')
        (self.repo / 'tests/test_mod.py').write_text(textwrap.dedent('''\
            import pytest
            from mod import parse


            @pytest.mark.parametrize("value", ["ignored://sink", "other://sink"])
            def test_scheme_kept(value):
                assert parse(value) == value
            '''))
        git(self.repo, 'add', '-A')
        git(self.repo, 'commit', '-q', '-m', 'parametrized')
        (self.repo / 'mod.py').write_text("def parse(value):\n    if '://' in value:\n        raise ValueError(value)\n    return value\n")
        (self.repo / 'reasons.txt').write_text('tests/test_mod.py::test_scheme_kept[ignored://sink]\n  input: the ignored scheme\n  quote: "Every destination starts with backup:// and names a store."\n')
        result = self.run_preserve('--reasons', str(self.repo / 'reasons.txt'))
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn('1 test(s) have no reason', result.stdout)

    @unittest.skipUnless(HAS_PYTEST, 'requires pytest in the selected interpreter')
    def test_parameter_ids_with_spaces_remain_distinct(self):
        (self.repo / 'tests/test_mod.py').write_text(textwrap.dedent('''\
            import pytest
            from mod import parse

            @pytest.mark.parametrize("value", ["a", "b"], ids=["bad a", "bad b"])
            def test_scheme_kept(value):
                assert parse(value) == value
            '''))
        git(self.repo, 'add', '-A')
        git(self.repo, 'commit', '-q', '-m', 'parameter ids with spaces')
        (self.repo / 'mod.py').write_text('def parse(value):\n    return "changed"\n')
        for wanted, status, missing in (
            ('tests/test_mod.py::test_scheme_kept[bad', 1, 2),
            ('tests/test_mod.py::test_scheme_kept[bad a]', 1, 1),
            ('tests/test_mod.py::test_scheme_kept[bad a]\ntests/test_mod.py::test_scheme_kept[bad b]', 0, 0),
        ):
            with self.subTest(wanted=wanted):
                reason = self.REASON.replace('test_scheme_kept\n', wanted + '\n', 1)
                (self.repo / 'reasons.txt').write_text(reason)
                result = self.run_preserve('--reasons', str(self.repo / 'reasons.txt'))
                self.assertEqual(result.returncode, status, result.stdout + result.stderr)
                self.assertIn('tests/test_mod.py::test_scheme_kept[bad a]', result.stdout)
                self.assertIn('tests/test_mod.py::test_scheme_kept[bad b]', result.stdout)
                if missing:
                    self.assertIn(f'{missing} test(s) have no reason', result.stdout)

    @unittest.skipUnless(HAS_PYTEST, 'requires pytest in the selected interpreter')
    def test_inherited_pytest_options_cannot_omit_tests(self):
        (self.repo / 'tests/test_mod.py').write_text(textwrap.dedent('''\
            import pytest
            from mod import parse

            def test_a_waived():
                assert parse("a") == "a"

            def test_z_uncovered():
                assert parse("z") == "z"
            '''))
        git(self.repo, 'add', '-A')
        git(self.repo, 'commit', '-q', '-m', 'two regressions')
        (self.repo / 'mod.py').write_text('def parse(value):\n    return "changed"\n')
        (self.repo / 'reasons.txt').write_text(self.REASON.replace('test_scheme_kept\n', 'test_a_waived\n', 1))
        for source in ('config', 'environment'):
            for options in ('-k test_a_waived', '-x'):
                with self.subTest(source=source, options=options):
                    (self.repo / 'pytest.ini').write_text('[pytest]\naddopts = ' + (options if source == 'config' else '') + '\n')
                    env = {**os.environ, 'PYTEST_ADDOPTS': options if source == 'environment' else ''}
                    result = self.run_preserve('--reasons', str(self.repo / 'reasons.txt'), env=env)
                    self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                    self.assertIn('test_z_uncovered', result.stdout)
                    self.assertIn('1 test(s) have no reason', result.stdout)

    def test_non_ascii_test_path_is_still_run(self):
        (self.repo / 'tést').mkdir()
        (self.repo / 'tést/__init__.py').write_text('')
        (self.repo / 'tést/test_more.py').write_text(TESTS)
        git(self.repo, 'add', '-A')
        git(self.repo, 'commit', '-q', '-m', 'non-ascii dir')
        (self.repo / 'mod.py').write_text(NARROWED)
        result = self.run_preserve()
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn('2 test file(s)', result.stdout)

    def test_unknown_commit_exits_two(self):
        result = subprocess.run([sys.executable, str(SCRIPT), '--since', 'nope', '--project', str(self.repo)],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn('not a commit', result.stderr)


if __name__ == '__main__':
    unittest.main()
