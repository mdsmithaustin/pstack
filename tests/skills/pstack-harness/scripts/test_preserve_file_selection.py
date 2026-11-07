import importlib.util
import os
import stat
import subprocess
import sys
import tempfile
import unittest
import venv
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
SCRIPT = ROOT / 'skills/pstack-harness/scripts/preserve.py'
HAS_PYTEST = importlib.util.find_spec('pytest') is not None
CONTRACT = 'from mod import VALUE\ndef check_contract():\n    assert VALUE == "baseline"\n'
EDITED = 'def check_contract():\n    assert True\n'
CONFIG = '[pytest]\npython_files = test_*.py check_*.py\npython_functions = test_* check_*\n'
UNITTEST = 'import unittest\nclass Example(unittest.TestCase):\n    def test_value(self):\n        self.assertEqual(__import__("mod").VALUE, "baseline")\n'


class PreserveFileSelection(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='preserve-file-selection-')
        self.addCleanup(temporary.cleanup)
        self.repo = Path(temporary.name).resolve()
        self.git('init', '-q')
        self.write('mod.py', 'VALUE = "baseline"\n')

    def git(self, *args):
        return subprocess.run(['git', '-C', str(self.repo), *args], check=True, capture_output=True,
                              env={**os.environ, 'GIT_AUTHOR_NAME': 't', 'GIT_AUTHOR_EMAIL': 't@x',
                                   'GIT_COMMITTER_NAME': 't', 'GIT_COMMITTER_EMAIL': 't@x'})

    def write(self, name, source):
        target = self.repo / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(source)

    def commit(self):
        self.git('add', '-A')
        self.git('commit', '-q', '-m', 'baseline')

    def snapshot(self):
        return {str(path.relative_to(self.repo)): (path.read_bytes(), stat.S_IMODE(path.stat().st_mode))
                for path in self.repo.rglob('*')
                if path.is_file() and not path.is_symlink() and '.git' not in path.relative_to(self.repo).parts
                and '__pycache__' not in path.parts}

    def preserve(self, *extra, python=None):
        before = self.snapshot()
        result = subprocess.run([sys.executable, str(SCRIPT), '--since', 'HEAD', '--project', str(self.repo),
                                 '--python', python or sys.executable, *extra], capture_output=True, text=True, timeout=30)
        self.assertEqual(before, self.snapshot(), result.stdout + result.stderr)
        self.assertFalse((self.repo / '.git/preserve-backup').exists(), result.stdout + result.stderr)
        return result

    def pytest_command(self, *selection):
        return ('--command', sys.executable, '-m', 'pytest', '-q', '-p', 'no:cacheprovider', *selection)

    def contract(self, *, mixed=False):
        self.write('pytest.ini', CONFIG)
        self.write('spec/check_contract.py', CONTRACT)
        if mixed:
            self.write('tests/test_visible.py', 'def test_visible():\n    assert True\n')
        self.commit()

    def assert_regression(self, result, *, automatic=True):
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        if automatic:
            self.assertIn('check_contract', result.stdout)
        self.assertIn('1 failed', result.stdout)

    @unittest.skipUnless(HAS_PYTEST, 'requires pytest in the selected interpreter')
    def test_configured_custom_file_extends_mixed_automatic_selection(self):
        self.contract(mixed=True)
        self.write('mod.py', 'VALUE = "regression"\n')
        result = self.preserve()
        self.assert_regression(result)
        self.assertIn('2 test file(s)', result.stdout)
        self.assertIn('1 failed, 1 passed', result.stdout)

    @unittest.skipUnless(HAS_PYTEST, 'requires pytest in the selected interpreter')
    def test_mixed_explicit_command_restores_edited_custom_file_and_mode(self):
        self.contract(mixed=True)
        self.write('mod.py', 'VALUE = "regression"\n')
        self.write('spec/check_contract.py', EDITED)
        (self.repo / 'spec/check_contract.py').chmod(0o751)
        result = self.preserve(*self.pytest_command())
        self.assert_regression(result, automatic=False)
        self.assertIn('2 baseline Python test file(s)', result.stdout)
        self.assertIn('1 failed, 1 passed', result.stdout)

    @unittest.skipUnless(HAS_PYTEST, 'requires pytest in the selected interpreter')
    def test_only_custom_file_runs_in_automatic_and_explicit_modes(self):
        self.contract()
        self.write('spec/check_contract.py', EDITED)
        for command in ((), self.pytest_command()):
            with self.subTest(command=command):
                result = self.preserve(*command)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn('1 passed', result.stdout)
                self.write('mod.py', 'VALUE = "regression"\n')
                self.assert_regression(self.preserve(*command), automatic=not command)
                self.write('mod.py', 'VALUE = "baseline"\n')

    @unittest.skipUnless(HAS_PYTEST, 'requires pytest in the selected interpreter')
    def test_current_naming_changes_do_not_replace_baseline_file_selection(self):
        self.contract(mixed=True)
        self.write('pytest.ini', '[pytest]\npython_files = test_visible.py\npython_functions = test_visible\n')
        self.write('spec/check_contract.py', EDITED)
        self.write('mod.py', 'VALUE = "regression"\n')
        self.assert_regression(self.preserve())

    @unittest.skipUnless(HAS_PYTEST, 'requires pytest in the selected interpreter')
    def test_deleted_baseline_path_returns_to_absent_after_current_rename(self):
        self.contract()
        (self.repo / 'spec/check_contract.py').unlink()
        self.write('spec/current_cases.py', EDITED)
        self.write('pytest.ini', '[pytest]\npython_files = current_cases.py\npython_functions = check_*\n')
        self.write('mod.py', 'VALUE = "regression"\n')
        self.assert_regression(self.preserve())
        self.assertFalse((self.repo / 'spec/check_contract.py').exists())
        self.assertEqual((self.repo / 'spec/current_cases.py').read_text(), EDITED)

    @unittest.skipUnless(HAS_PYTEST, 'requires pytest in the selected interpreter')
    def test_nested_config_selects_custom_file_with_current_config_deleted(self):
        self.write('spec/nested/pytest.ini', '[pytest]\npython_files = check_*.py\npython_functions = check_*\n')
        self.write('spec/nested/check_contract.py', CONTRACT)
        self.commit()
        (self.repo / 'spec/nested/pytest.ini').unlink()
        self.write('spec/nested/check_contract.py', EDITED)
        self.write('mod.py', 'VALUE = "regression"\n')
        self.assert_regression(self.preserve())
        self.assertFalse((self.repo / 'spec/nested/pytest.ini').exists())

    @unittest.skipUnless(HAS_PYTEST, 'requires pytest in the selected interpreter')
    def test_native_file_globs_match_original_paths(self):
        variants = (
            ('check_contract.py', 'spec/check_contract.py'),
            ('check_*.py', 'spec/check_contract.py'),
            ('check_?ontract.py', 'spec/check_contract.py'),
            ('[c]heck_contract.py', 'spec/check_contract.py'),
            ('spec/**/check_*.py', 'spec/deep/more/check_contract.py'),
            ('spec/*/check_*.py', 'spec/deep/more/check_contract.py'),
            (str(self.repo / 'spec/check_contract.py'), 'spec/check_contract.py'),
        )
        for pattern, path in variants:
            with self.subTest(pattern=pattern):
                self.write('pytest.ini', '[pytest]\npython_files = ' + pattern + '\npython_functions = check_*\n')
                self.write(path, CONTRACT)
                self.write('mod.py', 'VALUE = "baseline"\n')
                self.commit()
                self.write(path, EDITED)
                self.write('mod.py', 'VALUE = "regression"\n')
                self.assert_regression(self.preserve())
                (self.repo / path).unlink()

    @unittest.skipUnless(HAS_PYTEST, 'requires pytest in the selected interpreter')
    def test_native_config_formats_extend_custom_only_selection(self):
        import pytest

        options = 'python_files = check_*.py\npython_functions = check_*\n'
        toml = 'python_files = ["check_*.py"]\npython_functions = ["check_*"]\n'
        formats = [
            ('pytest.ini', '[pytest]\n' + options),
            ('.pytest.ini', '[pytest]\n' + options),
            ('tox.ini', '[pytest]\n' + options),
            ('setup.cfg', '[tool:pytest]\n' + options),
            ('pyproject.toml', '[tool.pytest.ini_options]\n' + toml),
        ]
        if int(pytest.__version__.split('.')[0]) >= 9:
            formats.extend((('pytest.toml', '[pytest]\n' + toml), ('.pytest.toml', '[pytest]\n' + toml),
                            ('pyproject.toml', '[tool.pytest]\n' + toml)))
        self.write('spec/check_contract.py', CONTRACT)
        for name, configuration in formats:
            with self.subTest(name=name, configuration=configuration):
                self.write(name, configuration)
                self.write('mod.py', 'VALUE = "baseline"\n')
                self.commit()
                (self.repo / name).unlink()
                self.write('spec/check_contract.py', EDITED)
                self.write('mod.py', 'VALUE = "regression"\n')
                self.assert_regression(self.preserve())
                self.write('spec/check_contract.py', CONTRACT)

    @unittest.skipUnless(HAS_PYTEST, 'requires pytest in the selected interpreter')
    def test_native_nearest_config_precedence_does_not_select_application_module(self):
        self.write('pytest.ini', '[pytest]\npython_files = check_*.py\npython_functions = check_*\n')
        self.write('spec/pytest.ini', '[pytest]\npython_files = contract_*.py\npython_functions = check_*\n')
        self.write('spec/contract_value.py', CONTRACT)
        self.write('spec/check_application.py', 'VALUE = "baseline"\n')
        self.commit()
        self.write('spec/check_application.py', 'VALUE = "current"\n')
        command = 'import unittest; from pathlib import Path; assert Path("spec/check_application.py").read_text() == \'VALUE = "current"\\n\'; unittest.main(module=None, argv=["unittest", "discover", "-s", "current"])'
        self.write('current/test_current.py', UNITTEST)
        result = self.preserve('--command', sys.executable, '-c', command)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('1 baseline Python test file(s)', result.stdout)

    @unittest.skipUnless(HAS_PYTEST, 'requires pytest in the selected interpreter')
    def test_broad_pattern_keeps_production_values_and_functions_current(self):
        self.write('pytest.ini', '[pytest]\npython_files = *.py\npython_functions = check_*\n')
        self.write('spec/check_contract.py', CONTRACT)
        for ordinary in ('', 'def parse(value):\n    return value\n'):
            with self.subTest(ordinary=bool(ordinary)):
                self.write('mod.py', 'VALUE = "baseline"\n' + ordinary)
                self.commit()
                self.write('mod.py', 'VALUE = "changed"\n' + ordinary)
                (self.repo / 'mod.py').chmod(0o751)
                native = subprocess.run([sys.executable, '-m', 'pytest', '-q', '-p', 'no:cacheprovider'],
                                        cwd=self.repo, capture_output=True, text=True, timeout=30)
                self.assertEqual(native.returncode, 1, native.stdout + native.stderr)
                self.assertIn('1 failed', native.stdout)
                for command in ((), self.pytest_command()):
                    with self.subTest(command=command):
                        result = self.preserve(*command)
                        self.assert_regression(result, automatic=not command)
                        self.assertIn('1 baseline Python test file(s)' if command else '1 test file(s)', result.stdout)

    @unittest.skipUnless(HAS_PYTEST, 'requires pytest in the selected interpreter')
    def test_custom_class_definitions_establish_additional_file_ownership(self):
        self.write('pytest.ini', '[pytest]\npython_files = behavior.py\npython_functions = check_*\npython_classes = Verify*\n')
        self.write('spec/behavior.py', 'from mod import VALUE\nclass VerifyBehavior:\n    def check_contract(self):\n        assert VALUE == "baseline"\n')
        self.commit()
        self.write('mod.py', 'VALUE = "regression"\n')
        self.assert_regression(self.preserve())

    @unittest.skipUnless(HAS_PYTEST, 'requires pytest in the selected interpreter')
    def test_unresolved_additional_file_ownership_refuses_before_overlay(self):
        variants = (
            'from unavailable_contracts import check_contract\n',
            'from unavailable_contracts import *\n',
            'from unavailable_contracts import ordinary_name\n',
            'VALUE = unknown_object\n',
            'def helper():\n    pass\ncheck_contract = helper\n',
            'for name in ("check_contract",):\n    globals()[name] = lambda: None\n',
            'class Behavior(ImportedBase):\n    pass\n',
        )
        self.write('pytest.ini', '[pytest]\npython_files = *.py\npython_functions = check_*\n')
        self.write('tests/test_visible.py', 'def test_visible():\n    assert True\n')
        for baseline in variants:
            with self.subTest(baseline=baseline):
                self.write('spec/cases.py', baseline)
                self.commit()
                self.write('spec/cases.py', '# current bytes must survive\n')
                (self.repo / 'spec/cases.py').chmod(0o751)
                for command in ((), ('--command', sys.executable, '-c',
                                     'from pathlib import Path; Path("command-launched").write_text("yes"); raise SystemExit(7)')):
                    with self.subTest(command=command):
                        result = self.preserve(*command)
                        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                        self.assertIn('test ownership is unresolved for spec/cases.py', result.stderr)
                        self.assertFalse((self.repo / 'command-launched').exists())

    @unittest.skipUnless(HAS_PYTEST, 'requires pytest in the selected interpreter')
    def test_metadata_imports_cannot_resolve_from_the_project(self):
        self.write('pytest.ini', '[pytest]\npython_files = cases.py\n')
        self.write('spec/cases.py', 'from unavailable_contracts import test_contract\n')
        self.write('ast.py', 'from pathlib import Path\nPath("project-ast-imported").write_text("yes")\n')
        self.commit()
        result = self.preserve()
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn('test ownership is unresolved for spec/cases.py', result.stderr)
        self.assertFalse((self.repo / 'project-ast-imported').exists())

    def test_stdlib_suite_without_pytest_keeps_application_code_current(self):
        isolated = self.repo / 'isolated'
        venv.EnvBuilder(with_pip=False).create(isolated)
        python = str(isolated / 'bin/python')
        self.write('tests/test_value.py', UNITTEST)
        self.write('tox.ini', '[tox]\nenvlist = py\n[testenv]\ncommands = python -m unittest discover\n')
        self.commit()
        self.write('mod.py', 'VALUE = "regression"\n')
        result = self.preserve(python=python)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn('with unittest', result.stdout)
        self.assertIn('test_value', result.stdout)

    def test_custom_pytest_config_without_dependency_fails_closed(self):
        isolated = self.repo / 'isolated'
        venv.EnvBuilder(with_pip=False).create(isolated)
        self.contract()
        result = self.preserve(python=str(isolated / 'bin/python'))
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn('baseline pytest file patterns', result.stderr)
        self.assertIn('pytest', result.stderr)

    @unittest.skipUnless(HAS_PYTEST, 'requires pytest in the selected interpreter')
    def test_invalid_baseline_config_cannot_omit_custom_test(self):
        self.write('pytest.ini', '[pytest]\npython_files = check_*.py\npython_files = other_*.py\n')
        self.write('spec/check_contract.py', CONTRACT)
        self.commit()
        result = self.preserve()
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn('baseline pytest file patterns', result.stderr)

    @unittest.skipUnless(HAS_PYTEST, 'requires pytest in the selected interpreter')
    def test_tracked_custom_symlink_is_excluded_from_overlay(self):
        self.write('pytest.ini', CONFIG)
        self.write('spec/real_contract.py', CONTRACT)
        (self.repo / 'spec/check_contract.py').symlink_to('real_contract.py')
        self.write('tests/test_visible.py', 'def test_visible():\n    assert True\n')
        self.commit()
        self.write('spec/real_contract.py', EDITED)
        result = self.preserve()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('1 test file(s)', result.stdout)
        self.assertTrue((self.repo / 'spec/check_contract.py').is_symlink())

    def test_explicit_empty_selection_executes_real_command_and_checks_nonzero(self):
        self.commit()
        self.write('current/test_current.py', UNITTEST)
        command = ('--command', sys.executable, '-m', 'unittest', 'discover', '-s', 'current')
        result = self.preserve(*command)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('0 baseline Python test file(s)', result.stdout)
        self.write('mod.py', 'VALUE = "regression"\n')
        result = self.preserve(*command)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn('test_value', result.stdout)

    def test_explicit_empty_selection_executes_exit_seven_command(self):
        self.commit()
        marker = self.repo / 'command-executed'
        result = subprocess.run([sys.executable, str(SCRIPT), '--since', 'HEAD', '--project', str(self.repo),
                                 '--python', sys.executable, '--command', sys.executable, '-c',
                                 'from pathlib import Path; Path("command-executed").write_text("yes"); raise SystemExit(7)'],
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertEqual(marker.read_text(), 'yes')
        self.assertIn('command exited 7', result.stdout)
        self.assertFalse((self.repo / '.git/preserve-backup').exists())

    def test_explicit_empty_selection_noop_cannot_pass(self):
        self.commit()
        result = self.preserve('--command', sys.executable, '-c', 'pass')
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn('nothing was checked', result.stdout)

    def test_automatic_empty_selection_keeps_no_baseline_semantics(self):
        self.commit()
        result = self.preserve()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('holds no Python test files', result.stdout)

    @unittest.skipUnless(HAS_PYTEST, 'requires pytest in the selected interpreter')
    def test_metadata_discovery_does_not_import_tests_or_conftest(self):
        self.write('pytest.ini', CONFIG)
        self.write('project_plugin.py', 'from pathlib import Path\np = Path("plugin-count")\np.write_text(p.read_text()+"x" if p.exists() else "x")\n')
        self.write('conftest.py', 'from pathlib import Path\np = Path("hook-count")\np.write_text(p.read_text()+"x" if p.exists() else "x")\n')
        self.write('spec/check_contract.py', 'from pathlib import Path\np = Path("import-count")\np.write_text(p.read_text()+"x" if p.exists() else "x")\ndef check_once():\n    assert p.read_text() == "x"\n    assert Path("hook-count").read_text() == "x"\n')
        self.commit()
        result = subprocess.run([sys.executable, str(SCRIPT), '--since', 'HEAD', '--project', str(self.repo),
                                 '--python', sys.executable], capture_output=True, text=True, timeout=30,
                                env={**os.environ, 'PYTEST_PLUGINS': 'project_plugin'})
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('1 passed', result.stdout)
        self.assertEqual((self.repo / 'import-count').read_text(), 'x')
        self.assertEqual((self.repo / 'hook-count').read_text(), 'x')
        self.assertEqual((self.repo / 'plugin-count').read_text(), 'x')
        self.assertFalse((self.repo / '.git/preserve-backup').exists())


if __name__ == '__main__':
    unittest.main()
