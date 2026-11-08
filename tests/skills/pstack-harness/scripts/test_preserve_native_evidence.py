import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
SCRIPT = ROOT / 'skills/pstack-harness/scripts/preserve.py'
OUTCOMES = '''\
import unittest
from behavior import known_bug, policy

class NativeEvidence(unittest.TestCase):
    @unittest.expectedFailure
    def test_known_bug(self):
        self.assertEqual(known_bug(), 'fixed')

    def test_policy(self):
        self.assertEqual(policy(), 'allowed')
'''
CACHED_TEST = '''\
import unittest
from pathlib import Path

class CachedEvidence(unittest.TestCase):
    def test_baseline_assertion(self):
        self.assertEqual(Path('behavior.txt').read_text(), 'old')
'''


class PreserveNativeEvidence(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='preserve-native-evidence-')
        self.addCleanup(temporary.cleanup)
        self.repo = Path(temporary.name).resolve()
        self.env = dict(os.environ, GIT_AUTHOR_NAME='t', GIT_AUTHOR_EMAIL='t@x',
                        GIT_COMMITTER_NAME='t', GIT_COMMITTER_EMAIL='t@x')
        for key in ('PYTHONPYCACHEPREFIX', 'PYTHONDONTWRITEBYTECODE', 'PYTHONPATH'):
            self.env.pop(key, None)
        self.git('init', '-q')

    def git(self, *args):
        return subprocess.run(['git', '-C', str(self.repo), *args], check=True,
                              capture_output=True, env=self.env, timeout=10)

    def write(self, name, source):
        path = self.repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source)
        return path

    def commit(self):
        self.git('add', '-A')
        self.git('commit', '-q', '-m', 'baseline')

    def run_command(self, argv):
        return subprocess.run(argv, cwd=self.repo, capture_output=True, text=True,
                              env=self.env, timeout=20)

    def preserve(self, *extra):
        return self.run_command([sys.executable, str(SCRIPT), '--since', 'HEAD',
                                 '--project', str(self.repo), '--python', sys.executable, *extra])

    def assert_exit(self, result, expected):
        self.assertEqual(result.returncode, expected, result.stdout + result.stderr)

    def outcomes_baseline(self):
        self.write('behavior.py', "def known_bug():\n    return 'broken'\ndef policy():\n    return 'allowed'\n")
        test = self.write('tests/test_native.py', OUTCOMES)
        self.commit()
        return test

    def test_another_failures_reason_cannot_hide_an_unexpected_success(self):
        test = self.outcomes_baseline()
        self.assert_exit(self.preserve(), 0)
        self.write('behavior.py', "def known_bug():\n    return 'fixed'\ndef policy():\n    return 'rejected'\n")
        edited = (OUTCOMES + '\n# current test edits must survive the check\n').encode()
        test.write_bytes(edited)
        test.chmod(0o751)
        reasons = self.write('reasons.txt', '''\
tests/test_native.py::NativeEvidence::test_policy
  input: the formerly allowed policy
  quote: "Reject this policy."
''')
        result = self.preserve('--reasons', str(reasons))
        self.assert_exit(result, 1)
        self.assertIn('FAILED test_known_bug (tests.test_native.NativeEvidence.test_known_bug)', result.stdout)
        self.assertIn('FAILED test_policy (tests.test_native.NativeEvidence.test_policy)', result.stdout)
        self.assertIn('1 test(s) have no reason', result.stdout)
        self.assertEqual(test.read_bytes(), edited)
        self.assertEqual(test.stat().st_mode & 0o777, 0o751)

        reasons.write_text(reasons.read_text() + '''\
tests/test_native.py::NativeEvidence::test_known_bug
  input: the known bug now succeeds
  quote: "Account for this changed expectation separately."
''')
        result = self.preserve('--reasons', str(reasons))
        self.assert_exit(result, 0)
        self.assertIn('2 test(s) waived, each with an input and a quoted sentence', result.stdout)
        self.assertEqual(test.read_bytes(), edited)
        self.assertEqual(test.stat().st_mode & 0o777, 0o751)

    def test_native_and_direct_unexpected_success_keep_their_test_identity(self):
        test = self.outcomes_baseline()
        command = ('--command', sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-v')
        self.assert_exit(self.preserve(*command), 0)
        self.write('behavior.py', "def known_bug():\n    return 'fixed'\ndef policy():\n    return 'allowed'\n")
        original = test.read_bytes()
        for extra in ((), command):
            with self.subTest(extra=extra):
                result = self.preserve(*extra)
                self.assert_exit(result, 1)
                self.assertIn('FAILED test_known_bug (', result.stdout)
                self.assertNotIn('exited 1 before running the tests', result.stdout)
                self.assertEqual(test.read_bytes(), original)

    def test_direct_interpreter_options_cannot_load_cached_current_assertions(self):
        test = self.write('tests/test_native.py', CACHED_TEST)
        self.write('tests/test_unselected.py', 'raise RuntimeError("unselected module ran")\n')
        self.write('behavior.txt', 'old')
        self.commit()
        selection = ('-m', 'unittest', 'discover', '-s', 'tests', '-p', 'test_native.py', '-v')
        self.assert_exit(self.preserve('--command', sys.executable, *selection), 0)
        self.write('behavior.txt', 'new')
        edited = CACHED_TEST.replace("'old'", "'new'").encode()
        self.assertEqual(len(edited), len(CACHED_TEST.encode()))
        caller_cache = self.repo / 'caller-cache'
        variants = (('-E',), ('-I',), ('-X', f'pycache_prefix={caller_cache}'),
                    (f'-Xpycache_prefix={caller_cache}',),
                    ('-X', 'pycache_prefix'), ('-Xpycache_prefix',),
                    ('-E', '-X', f'pycache_prefix={caller_cache}'),
                    ('-I', '-X', f'pycache_prefix={caller_cache}'))
        for options in variants:
            with self.subTest(options=options):
                test.write_bytes(edited)
                test.chmod(0o751)
                os.utime(test, ns=(1700000000000000000, 1700000000000000000))
                self.assertEqual(test.stat().st_mtime_ns, 1700000000000000000)
                compile_result = self.run_command([sys.executable, *options, '-c',
                    'import py_compile,sys; print(py_compile.compile(sys.argv[1], doraise=True, '
                    'invalidation_mode=py_compile.PycInvalidationMode.UNCHECKED_HASH))', str(test)])
                self.assert_exit(compile_result, 0)
                cache = Path(compile_result.stdout.strip())
                cached_bytes = cache.read_bytes()
                self.assertEqual(int.from_bytes(cached_bytes[4:8], 'little'), 1)
                test.write_bytes(CACHED_TEST.encode())
                stale = self.run_command([sys.executable, *options, *selection])
                self.assert_exit(stale, 0)
                self.assertIn('test_baseline_assertion', stale.stderr)
                self.assertIn('Ran 1 test', stale.stderr)
                test.write_bytes(edited)
                os.utime(test, ns=(1700000000000000000, 1700000000000000000))

                result = self.preserve('--command', sys.executable, *options, *selection)
                self.assert_exit(result, 1)
                self.assertIn('FAILED test_baseline_assertion (test_native.CachedEvidence.test_baseline_assertion)', result.stdout)
                self.assertNotIn('unselected module ran', result.stdout)
                self.assertEqual(test.read_bytes(), edited)
                self.assertEqual(test.stat().st_mode & 0o777, 0o751)
                self.assertEqual(cache.read_bytes(), cached_bytes)

    def test_cache_override_keeps_other_interpreter_options(self):
        self.write('tests/test_native.py', '''\
import sys
import unittest

class InterpreterEvidence(unittest.TestCase):
    def test_options(self):
        self.assertEqual(sys.flags.optimize, 1)
        self.assertEqual(sys._xoptions['native_evidence'], 'kept')
        self.assertIn('ignore::UserWarning', sys.warnoptions)
''')
        self.commit()
        result = self.preserve('--command', sys.executable, '-W', 'ignore::UserWarning',
                               '-X', 'native_evidence=kept', '-O',
                               '-X', f'pycache_prefix={self.repo / "caller-cache"}',
                               '-m', 'unittest', 'discover', '-s', 'tests', '-v')
        self.assert_exit(result, 0)


if __name__ == '__main__':
    unittest.main()
