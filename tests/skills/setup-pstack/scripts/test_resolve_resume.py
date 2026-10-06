import copy
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
SCRIPT = ROOT / 'skills/setup-pstack/scripts/resolve-resume.py'
ORACLE = ROOT / 'evals/resume-recovery/oracle.py'
sys.path.insert(0, str(ORACLE.parent))
from test_oracle import BINDING, model_free_run, write_json


class ResumeCli(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.project = self.root / 'workspace'
        self.config = self.project / '.agents/pstack-models.md'
        self.config.parent.mkdir(parents=True)
        self.config.write_text('## codex\nfeature: gpt-6.1-sol@high\narena runners: gpt-6-sol@max,gpt-6-luna@high\n')
        self.user = self.root / 'user-models.md'
        self.contexts = self.root / 'contexts.json'
        write_json(self.contexts, {})
        self.environment = dict(os.environ, CODEX_HOME=str(self.root / 'absent-codex-home'))

    def resolve(self, *extra, expected_status=1):
        result = subprocess.run([sys.executable, str(SCRIPT), '--source', 'claude-code', '--role', 'feature', '--arm', '1',
                                 '--project', str(self.project), '--user-file', str(self.user), '--contexts', str(self.contexts), *extra],
                                env=self.environment, capture_output=True, text=True)
        self.assertEqual(result.returncode, expected_status, result.stderr + result.stdout)
        return json.loads(result.stdout) if result.stdout else result.stderr

    def instrument_run(self, binding=None):
        run = model_free_run(self.root / 'model-free-run', binding)
        binary = self.root / 'bin'
        binary.mkdir()
        version = binary / 'codex'
        version.write_text('#!/bin/sh\n[ "$1" = "--version" ] || exit 9\nprintf "codex-cli 0.160.1\\n"\n')
        version.chmod(0o755)
        self.environment['PATH'] = str(binary) + os.pathsep + self.environment.get('PATH', '')
        write_json(self.contexts, {'codex': {'available': True, 'route': 'codex-cli', 'version': '0.160.1',
                                          'permission_context': BINDING['permission_context'], 'eval_run': str(run)}})
        return run

    def test_exact_panel_arm_is_preserved(self):
        data = self.resolve('--role', 'arena runners', '--arm', '2')
        self.assertEqual(data['priority'], {'source': 'claude-code', 'destinations': ['codex'], 'configured_source': 'default'})
        self.assertEqual(data['candidates'][0]['resolution'], {'role': 'arena runners', 'arm': 2, 'model': 'gpt-6-luna', 'effort': 'high', 'source': 'workspace ## codex'})
        self.assertFalse(data['candidates'][0]['eligible'])

    def test_missing_arm_is_not_substituted(self):
        data = self.resolve('--role', 'arena runners', '--arm', '3')
        self.assertEqual(data['candidates'][0]['reason'], 'saved arm 3 does not exist')
        self.assertIsNone(data['candidates'][0]['resolution'])

    def test_invalid_saved_roles_and_single_arms_are_cli_errors(self):
        for extra in (['--role', 'guess'], ['--arm', '0'], ['--arm', '2']):
            with self.subTest(extra=extra):
                self.assertIn('error:', self.resolve(*extra, expected_status=2))

    def test_actual_priority_layering_uses_other_sources_from_user(self):
        self.config.write_text('# resume-priority: claude-code=hermes,grok\n## hermes\nfeature: actual-model@high\n')
        self.user.write_text('# resume-priority: claude-code=codex\n# resume-priority: codex=hermes\n')
        data = self.resolve()
        self.assertEqual([item['harness'] for item in data['candidates']], ['hermes', 'grok'])
        self.assertEqual(data['priority']['configured_source'], 'workspace')
        other = self.resolve('--source', 'codex')
        self.assertEqual(other['priority'], {'source': 'codex', 'destinations': ['hermes'], 'configured_source': 'user'})

    def test_malformed_priority_stops_before_output(self):
        self.config.write_text('# resume-priority: codex=codex\n')
        self.assertIn('cannot include its source', self.resolve(expected_status=2))

    def test_unknown_inherited_model_or_effort_is_ineligible(self):
        for text in ('## codex\nfeature: inherit-parent@high\n', '## claude-code\nfeature: sonnet\n'):
            with self.subTest(text=text):
                self.config.write_text(text)
                data = self.resolve('--source', 'codex' if 'claude-code' in text else 'claude-code')
                self.assertEqual(data['candidates'][0]['reason'], 'destination identity is not concrete')

    def test_missing_current_oracle_and_unavailable_destination_fail(self):
        self.instrument_run()
        data = self.resolve()
        self.assertEqual(data['candidates'][0]['reason'], 'current external oracle is required')
        contexts = json.loads(self.contexts.read_text())
        contexts['codex']['available'] = False
        write_json(self.contexts, contexts)
        data = self.resolve('--oracle', str(ORACLE))
        self.assertEqual(data['candidates'][0]['reason'], 'destination availability, route or version is unobserved')

    def test_model_free_instrument_roundtrip_is_read_only(self):
        run = self.instrument_run()
        before = {path.relative_to(run).as_posix(): path.read_bytes() for path in run.rglob('*') if path.is_file()}
        data = self.resolve('--oracle', str(ORACLE), expected_status=0)
        candidate = data['candidates'][0]
        self.assertTrue(candidate['eligible'])
        self.assertEqual(candidate['resolution'], BINDING['resolution'])
        self.assertEqual(candidate['eval_receipt']['observed']['recovery']['session_id'], 'model-free-recovery')
        after = {path.relative_to(run).as_posix(): path.read_bytes() for path in run.rglob('*') if path.is_file()}
        self.assertEqual(after, before)

    def test_forged_pass_boolean_is_rejected_by_real_cli(self):
        run = self.instrument_run()
        write_json(run / 'receipt.json', {'passed': True, 'binding': BINDING})
        data = self.resolve('--oracle', str(ORACLE))
        self.assertEqual(data['candidates'][0]['reason'], 'stale or forged eval receipt')

    def test_changed_resolution_role_arm_effort_or_source_is_rejected(self):
        self.instrument_run()
        for text, role, arm in [('## codex\nfeature: gpt-6.1-sol@xhigh\n', 'feature', '1'),
                                ('feature: gpt-6.1-sol@high\n', 'feature', '1'),
                                ('## codex\nrefactoring: gpt-6.1-sol@high\n', 'refactoring', '1'),
                                ('## codex\narena runners: gpt-6.1-sol@high,gpt-6.1-sol@high\n', 'arena runners', '2')]:
            with self.subTest(role=role, arm=arm, text=text):
                self.config.write_text(text)
                data = self.resolve('--oracle', str(ORACLE), '--role', role, '--arm', arm)
                self.assertEqual(data['candidates'][0]['reason'], 'eval binding does not match exact current resolution or route context')

    def test_stale_or_forged_evidence_is_rejected(self):
        run = self.instrument_run()
        path = run / 'receipt.json'
        original = path.read_bytes()
        receipt = json.loads(original)
        receipt['oracle_sha256'] = 'old'
        write_json(path, receipt)
        data = self.resolve('--oracle', str(ORACLE))
        self.assertEqual(data['candidates'][0]['reason'], 'stale or forged eval receipt')
        path.write_bytes(original)
        (run / 'project/published.json').unlink()
        data = self.resolve('--oracle', str(ORACLE))
        self.assertIn('current oracle rejected evidence', data['candidates'][0]['reason'])

    def test_cli_version_drift_and_disappearing_executable_fail(self):
        self.instrument_run()
        binary = self.root / 'bin/codex'
        binary.write_text('#!/bin/sh\nprintf "codex-cli old\\n"\n')
        data = self.resolve('--oracle', str(ORACLE))
        self.assertEqual(data['candidates'][0]['reason'], 'current destination CLI version differs or is unavailable')
        self.environment['PATH'] = str(self.root / 'missing-path')
        data = self.resolve('--oracle', str(ORACLE))
        self.assertIn('No such file or directory', data['candidates'][0]['reason'])

    def test_route_and_permission_context_drift_fail(self):
        self.instrument_run()
        original = json.loads(self.contexts.read_text())
        for changes in ({'route': 'native'}, {'permission_context': {'sandbox': 'read-only', 'approval': 'never'}}):
            with self.subTest(changes=changes):
                value = copy.deepcopy(original)
                value['codex'].update(changes)
                write_json(self.contexts, value)
                data = self.resolve('--oracle', str(ORACLE))
                self.assertEqual(data['candidates'][0]['reason'], 'eval binding does not match exact current resolution or route context')

    def test_bad_context_json_is_a_cli_error(self):
        self.contexts.write_text('[]')
        self.assertIn('contexts must map', self.resolve(expected_status=2))

    def test_relative_evidence_path_is_denied(self):
        self.instrument_run()
        contexts = json.loads(self.contexts.read_text())
        contexts['codex']['eval_run'] = 'model-free-run'
        write_json(self.contexts, contexts)
        data = self.resolve('--oracle', str(ORACLE))
        self.assertEqual(data['candidates'][0]['reason'], 'eval_run must be an absolute retained evidence path')


if __name__ == '__main__':
    unittest.main()
