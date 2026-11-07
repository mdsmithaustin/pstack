import importlib.util
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
SCRIPT = ROOT / 'skills/pstack-harness/scripts/preserve.py'
HAS_PYTEST = importlib.util.find_spec('pytest') is not None
MIXED_SUBTESTS = '''\
import unittest
class Example(unittest.TestCase):
    def test_mixed(self):
        with self.subTest(value='pass'):
            self.assertTrue(True)
        with self.subTest(value='skip'):
            self.skipTest('unavailable')
'''
SKIPPED_METHOD = '''\
import unittest
class Example(unittest.TestCase):
    @unittest.skip('unavailable')
    def test_mixed(self):
        self.assertTrue(True)
'''


class PreserveCollectionEdges(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='preserve-collection-')
        self.addCleanup(temporary.cleanup)
        self.repo = Path(temporary.name).resolve()
        self.git('init', '-q')
        self.write('tests/test_example.py', MIXED_SUBTESTS)
        self.commit()

    def git(self, *args):
        return subprocess.run(['git', '-C', str(self.repo), *args], check=True, capture_output=True,
                              env={**os.environ, 'GIT_AUTHOR_NAME': 't', 'GIT_AUTHOR_EMAIL': 't@x',
                                   'GIT_COMMITTER_NAME': 't', 'GIT_COMMITTER_EMAIL': 't@x'})

    def write(self, name, source):
        path = self.repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source)

    def commit(self):
        self.git('add', '-A')
        self.git('commit', '--allow-empty', '-q', '-m', 'baseline')

    def preserve(self, *extra):
        return subprocess.run([sys.executable, str(SCRIPT), '--since', 'HEAD', '--project', str(self.repo),
                               '--python', sys.executable, *extra], capture_output=True, text=True, timeout=20)

    def assert_passes(self, result):
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn('nothing was checked', result.stdout)

    def assert_no_execution(self, result):
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn('nothing was checked', result.stdout)

    def command(self, *selection, options=()):
        return ('--command', sys.executable, *options, '-m', 'unittest', *selection)

    def test_native_mixed_subtests_execute_a_test(self):
        self.assert_passes(self.preserve())

    def test_direct_command_mixed_subtests_execute_a_test(self):
        self.assert_passes(self.preserve(*self.command('discover', '-s', 'tests')))

    def test_direct_command_preserves_supported_interpreter_options(self):
        self.write('tests/test_example.py', MIXED_SUBTESTS.replace(
            'self.assertTrue(True)', 'self.assertTrue(__import__("sys").flags.optimize == 1)'))
        self.commit()
        self.assert_passes(self.preserve(*self.command('discover', '-s', 'tests', options=('-O', '-W', 'default'))))

    def test_direct_command_resolves_the_interpreter_relative_to_the_project(self):
        (self.repo / 'selected-python').symlink_to(sys.executable)
        self.assert_passes(self.preserve('--command', './selected-python', '-m', 'unittest', 'discover', '-s', 'tests'))

    def test_direct_command_keeps_older_interpreter_import_modes(self):
        legacy = Path('/usr/bin/python3')
        if not legacy.is_file():
            self.skipTest('requires an installed Python 3.9 or 3.10')
        probe = subprocess.run([str(legacy), '-c', 'import sys; print(*sys.version_info[:2])'],
                               capture_output=True, text=True, timeout=10)
        self.assertEqual(probe.returncode, 0, probe.stdout + probe.stderr)
        version = tuple(map(int, probe.stdout.split()))
        if not (3, 9) <= version < (3, 11):
            self.skipTest('requires an installed Python 3.9 or 3.10')
        source = MIXED_SUBTESTS.replace('import unittest', 'import unittest\nimport sys\nfrom pathlib import Path')
        self.write('tests/test_example.py', source.replace(
            'self.assertTrue(True)', 'self.assertEqual(str(Path.cwd()) in sys.path, not sys.flags.isolated)'))
        self.commit()
        for options in ((), ('-I',)):
            with self.subTest(options=options):
                self.assert_passes(self.preserve('--python', str(legacy), '--command',
                                                 str(legacy), *options, '-m', 'unittest',
                                                 'discover', '-s', 'tests'))

    def test_direct_interpreter_start_failure_keeps_the_command_context(self):
        result = self.preserve(*self.command('discover', '-s', 'tests', options=('-X', 'int_max_str_digits=1')))
        self.assert_no_execution(result)
        self.assertIn('project command owns test selection', result.stdout)

    def test_native_and_direct_wholly_skipped_methods_fail(self):
        self.write('tests/test_example.py', SKIPPED_METHOD)
        self.commit()
        for command in ((), self.command('discover', '-s', 'tests')):
            with self.subTest(command=command):
                self.assert_no_execution(self.preserve(*command))

    def test_native_and_direct_multiple_skipped_subtests_do_not_hide_execution(self):
        self.write('tests/test_example.py', MIXED_SUBTESTS.replace("self.skipTest('unavailable')", "self.skipTest('unavailable')\n        with self.subTest(value='skip again'):\n            self.skipTest('unavailable')"))
        self.commit()
        for command in ((), self.command('discover', '-s', 'tests')):
            with self.subTest(command=command):
                self.assert_passes(self.preserve(*command))

    def test_native_and_direct_setup_errors_do_not_count_as_execution(self):
        self.write('tests/test_example.py', '''\
import unittest
class Example(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        raise RuntimeError('setup failed')
    def test_never_runs(self):
        self.fail('unreachable')
''')
        self.commit()
        for command in ((), self.command('discover', '-s', 'tests')):
            with self.subTest(command=command):
                result = self.preserve(*command)
                self.assert_no_execution(result)
                self.assertIn('setUpClass', result.stdout)

    def test_direct_command_keeps_explicit_selection(self):
        self.write('tests/__init__.py', '')
        self.write('tests/test_unrelated.py', 'raise RuntimeError("unselected module was imported")\n')
        self.commit()
        self.assert_passes(self.preserve(*self.command('tests.test_example.Example.test_mixed')))

    def test_direct_command_loads_package_module_and_load_tests_once(self):
        self.write('tests/__init__.py', 'from pathlib import Path\np = Path("package-count")\np.write_text(p.read_text()+"x" if p.exists() else "x")\n')
        self.write('tests/test_example.py', '''\
import unittest
from pathlib import Path
p = Path('module-count')
p.write_text(p.read_text()+'x' if p.exists() else 'x')
class Example(unittest.TestCase):
    def test_once(self):
        self.assertEqual(Path('package-count').read_text(), 'x')
        self.assertEqual(Path('module-count').read_text(), 'x')
        self.assertEqual(Path('hook-count').read_text(), 'x')
def load_tests(loader, tests, pattern):
    p = Path('hook-count')
    p.write_text(p.read_text()+'x' if p.exists() else 'x')
    return tests
''')
        self.commit()
        self.assert_passes(self.preserve(*self.command('tests.test_example')))
        for name in ('package-count', 'module-count', 'hook-count'):
            self.assertEqual((self.repo / name).read_text(), 'x')

    def test_native_package_initializers_execute_once(self):
        self.write('tests/__init__.py', 'from pathlib import Path\np = Path("package-count")\np.write_text(p.read_text()+"x" if p.exists() else "x")\n')
        self.write('tests/nested/__init__.py', 'from pathlib import Path\np = Path("nested-count")\np.write_text(p.read_text()+"x" if p.exists() else "x")\n')
        self.write('tests/nested/test_once.py', '''\
import unittest
from pathlib import Path
class Once(unittest.TestCase):
    def test_once(self):
        self.assertEqual(Path('package-count').read_text(), 'x')
        self.assertEqual(Path('nested-count').read_text(), 'x')
''')
        self.write('tests/test_example.py', 'import unittest\nclass Example(unittest.TestCase):\n    def test_ok(self):\n        self.assertTrue(True)\n')
        self.commit()
        self.assert_passes(self.preserve())
        self.assertEqual((self.repo / 'package-count').read_text(), 'x')
        self.assertEqual((self.repo / 'nested-count').read_text(), 'x')

    def test_generic_identical_summaries_cannot_establish_execution(self):
        summaries = []
        for source in (MIXED_SUBTESTS, SKIPPED_METHOD):
            self.write('tests/test_example.py', source)
            self.commit()
            raw = subprocess.run([sys.executable, '-m', 'unittest', 'discover', '-s', 'tests'],
                                 cwd=self.repo, capture_output=True, text=True, timeout=10)
            self.assertEqual(raw.returncode, 0, raw.stdout + raw.stderr)
            summaries.append(re.sub(r'in [0-9.]+s', 'in TIME', raw.stderr))
            result = self.preserve('--command', sys.executable, '-c',
                                   'import subprocess,sys; sys.exit(subprocess.run([sys.executable,"-m","unittest","discover","-s","tests"]).returncode)')
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn('ambiguous', result.stdout)
            self.assertIn('-m unittest', result.stdout)
        self.assertEqual(summaries[0], summaries[1])

    def test_generic_subtest_skips_cannot_produce_a_negative_execution_pass(self):
        self.write('tests/test_example.py', MIXED_SUBTESTS.replace("self.skipTest('unavailable')", "self.skipTest('unavailable')\n        with self.subTest(value='skip again'):\n            self.skipTest('unavailable')"))
        self.commit()
        result = self.preserve('--command', sys.executable, '-c',
                               'import subprocess,sys; sys.exit(subprocess.run([sys.executable,"-m","unittest","discover","-s","tests"]).returncode)')
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn('ambiguous', result.stdout)

    @unittest.skipUnless(HAS_PYTEST, 'requires pytest in the selected interpreter')
    def test_current_function_and_class_patterns_cannot_hide_baseline_tests(self):
        variants = (
            ('def test_plain():\n    assert True\ndef test_scheme_kept():\n    assert __import__("mod").VALUE == "baseline"\n', 'python_functions = test_plain'),
            ('class TestPlain:\n    def test_plain(self):\n        assert True\nclass TestRegression:\n    def test_scheme_kept(self):\n        assert __import__("mod").VALUE == "baseline"\n', 'python_classes = TestPlain'),
        )
        for source, setting in variants:
            with self.subTest(setting=setting):
                (self.repo / 'pytest.ini').unlink(missing_ok=True)
                self.write('mod.py', 'VALUE = "baseline"\n')
                self.write('tests/test_example.py', source)
                self.commit()
                current = '[pytest]\n' + setting + '\n'
                self.write('pytest.ini', current)
                self.write('mod.py', 'VALUE = "changed"\n')
                result = self.preserve()
                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                self.assertIn('test_scheme_kept', result.stdout)
                self.assertIn('1 failed, 1 passed', result.stdout)
                self.assertEqual((self.repo / 'pytest.ini').read_text(), current)

    @unittest.skipUnless(HAS_PYTEST, 'requires pytest in the selected interpreter')
    def test_baseline_custom_names_survive_current_default_patterns(self):
        (self.repo / 'tests/test_example.py').unlink()
        self.write('tests/cases.py', '''\
from mod import VALUE
class VerifyBehavior:
    def check_plain(self):
        assert True
    def check_regression(self):
        assert VALUE == 'baseline'
''')
        self.write('mod.py', 'VALUE = "baseline"\n')
        self.write('pytest.ini', '[pytest]\npython_files = cases.py\npython_functions = check_*\npython_classes = Verify*\n')
        self.commit()
        self.write('pytest.ini', '[pytest]\npython_files = test_*.py\npython_functions = test_*\npython_classes = Test*\n')
        self.assert_passes(self.preserve())
        self.write('mod.py', 'VALUE = "changed"\n')
        result = self.preserve()
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn('cases.py::VerifyBehavior::check_regression', result.stdout)
        self.assertIn('1 failed, 1 passed', result.stdout)

    @unittest.skipUnless(HAS_PYTEST, 'requires pytest in the selected interpreter')
    def test_nested_baseline_configuration_keeps_its_custom_names(self):
        (self.repo / 'tests/test_example.py').unlink()
        self.write('tests/nested/test_cases.py', 'from mod import VALUE\ndef test_plain():\n    assert True\nclass VerifyBehavior:\n    def check_regression(self):\n        assert VALUE == "baseline"\n')
        self.write('mod.py', 'VALUE = "baseline"\n')
        self.write('tests/nested/pytest.ini', '[pytest]\npython_functions = test_* check_*\npython_classes = Verify*\n')
        self.commit()
        current = '[pytest]\npython_functions = test_plain\npython_classes = Test*\n'
        self.write('tests/nested/pytest.ini', current)
        self.assert_passes(self.preserve())
        self.write('mod.py', 'VALUE = "changed"\n')
        result = self.preserve()
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn('VerifyBehavior::check_regression', result.stdout)
        self.assertIn('1 failed, 1 passed', result.stdout)
        self.assertEqual((self.repo / 'tests/nested/pytest.ini').read_text(), current)
        (self.repo / 'tests/nested/pytest.ini').unlink()
        result = self.preserve()
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn('VerifyBehavior::check_regression', result.stdout)
        self.assertFalse((self.repo / 'tests/nested/pytest.ini').exists())

    @unittest.skipUnless(HAS_PYTEST, 'requires pytest in the selected interpreter')
    def test_baseline_configuration_formats_keep_custom_names_when_current_config_is_deleted(self):
        import pytest

        (self.repo / 'tests/test_example.py').unlink()
        self.write('tests/cases.py', 'from mod import VALUE\nclass VerifyBehavior:\n    def check_regression(self):\n        assert VALUE == "baseline"\n')
        ini = 'python_files = cases.py\npython_functions = check_*\npython_classes = Verify*\n'
        formats = [
            ('pytest.ini', '[pytest]\n' + ini),
            ('.pytest.ini', '[pytest]\n' + ini),
            ('tox.ini', '[pytest]\n' + ini),
            ('setup.cfg', '[tool:pytest]\n' + ini),
            ('pyproject.toml', '[tool.pytest.ini_options]\npython_files = ["cases.py"]\npython_functions = ["check_*"]\npython_classes = ["Verify*"]\n'),
        ]
        if int(pytest.__version__.split('.')[0]) >= 9:
            formats.extend([
                ('pytest.toml', '[pytest]\npython_files = ["cases.py"]\npython_functions = ["check_*"]\npython_classes = ["Verify*"]\n'),
                ('.pytest.toml', '[pytest]\npython_files = ["cases.py"]\npython_functions = ["check_*"]\npython_classes = ["Verify*"]\n'),
                ('pyproject.toml', '[tool.pytest]\npython_files = ["cases.py"]\npython_functions = ["check_*"]\npython_classes = ["Verify*"]\n'),
            ])
        for name, configuration in formats:
            with self.subTest(name=name, configuration=configuration):
                self.write('mod.py', 'VALUE = "baseline"\n')
                self.write(name, configuration)
                self.commit()
                (self.repo / name).unlink()
                self.assert_passes(self.preserve())
                self.write('mod.py', 'VALUE = "changed"\n')
                result = self.preserve()
                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                self.assertIn('cases.py::VerifyBehavior::check_regression', result.stdout)
                self.assertFalse((self.repo / name).exists())
                self.commit()


if __name__ == '__main__':
    unittest.main()
