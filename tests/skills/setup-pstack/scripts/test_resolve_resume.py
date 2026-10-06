import copy
import hashlib
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
import oracle

write_json = oracle.write_json

RESOLVER_UNIT_STUB = '''import hashlib, json, sys
from pathlib import Path
assert sys.argv[1:3] == ['check', '--run']
run = Path(sys.argv[3])
if not (run / 'resolver-unit-evidence.json').is_file():
    print('resolver-unit evidence missing', file=sys.stderr)
    raise SystemExit(1)
receipt = json.loads((run / 'resolver-unit-authority.json').read_text())
receipt['oracle_sha256'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
print(json.dumps(receipt))
'''


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
        driver = self.root / 'skill-ci/tools/run_runner.py'
        driver.parent.mkdir(parents=True)
        driver.write_text("raise RuntimeError('resolver-unit preparation must not launch a driver')\n")
        (driver.parent.parent / 'runner.lock').write_text('git+https://github.com/mdsmithaustin/skill-eval-harness.git@' + oracle.PIN + '\n')
        wrapper = self.root / 'wrapper'
        wrapper.write_text("raise RuntimeError('resolver-unit preparation must not launch a provider')\n")
        self.binding = {'harness': 'codex',
                        'resolution': {'role': 'feature', 'arm': 1, 'model': 'gpt-6.1-sol', 'effort': 'high', 'source': 'workspace ## codex'},
                        'route': 'skill-ci-pinned-runner', 'version': 'resolver-unit-version',
                        'permission_context': {'runner': {'pin': oracle.PIN,
                                                         'driver': {'path': str(driver), 'sha256': hashlib.sha256(driver.read_bytes()).hexdigest()},
                                                         'wrapper': {'path': str(wrapper), 'sha256': hashlib.sha256(wrapper.read_bytes()).hexdigest()},
                                                         'option': str(wrapper)}}}

    def resolve(self, *extra, expected_status=1):
        result = subprocess.run([sys.executable, str(SCRIPT), '--source', 'claude-code', '--role', 'feature', '--arm', '1',
                                 '--project', str(self.project), '--user-file', str(self.user), '--contexts', str(self.contexts), *extra],
                                env=self.environment, capture_output=True, text=True)
        self.assertEqual(result.returncode, expected_status, result.stderr + result.stdout)
        return json.loads(result.stdout) if result.stdout else result.stderr

    def context_for(self, run):
        write_json(self.contexts, {'codex': {'available': True, 'route': self.binding['route'], 'version': self.binding['version'],
                                          'permission_context': self.binding['permission_context'], 'eval_run': str(run)}})

    def resolver_unit_stub_run(self):
        run = self.root / 'resolver-unit-run'
        run.mkdir()
        self.stub = self.root / 'resolver-unit-checker.py'
        self.stub.write_text(RESOLVER_UNIT_STUB)
        receipt = {'suite': 'pstack-resume-runner-v2', 'oracle_sha256': hashlib.sha256(self.stub.read_bytes()).hexdigest(),
                   'fixture_sha256': 'resolver-unit-stub', 'binding': self.binding,
                   'observed': {'resolver_unit_stub': True}, 'evidence_sha256': {}}
        write_json(run / 'receipt.json', receipt)
        write_json(run / 'resolver-unit-authority.json', receipt)
        write_json(run / 'resolver-unit-evidence.json', {'resolver_unit_stub': True})
        self.context_for(run)
        return run

    def prepared_run(self):
        run = self.root / 'prepared-case'
        binding_file = self.root / 'binding.json'
        write_json(binding_file, self.binding)
        result = subprocess.run([sys.executable, str(ORACLE), 'prepare', '--run', str(run), '--binding', str(binding_file)],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), (run / 'command.txt').read_text().strip())
        self.context_for(run)
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
        self.prepared_run()
        data = self.resolve()
        self.assertEqual(data['candidates'][0]['reason'], 'current external oracle is required')
        contexts = json.loads(self.contexts.read_text())
        for key, value in (('available', False), ('route', None), ('version', None)):
            with self.subTest(key=key):
                changed = copy.deepcopy(contexts)
                changed['codex'][key] = value
                write_json(self.contexts, changed)
                data = self.resolve('--oracle', str(ORACLE))
                self.assertEqual(data['candidates'][0]['reason'], 'destination availability, route or version is unobserved')

    def test_resolver_unit_stub_receipt_recheck_is_read_only(self):
        run = self.resolver_unit_stub_run()
        before = {path.relative_to(run).as_posix(): path.read_bytes() for path in run.rglob('*') if path.is_file()}
        data = self.resolve('--oracle', str(self.stub), expected_status=0)
        candidate = data['candidates'][0]
        self.assertTrue(candidate['eligible'])
        self.assertEqual(candidate['resolution'], {'role': 'feature', 'arm': 1, 'model': 'gpt-6.1-sol', 'effort': 'high', 'source': 'workspace ## codex'})
        self.assertEqual(candidate['eval_receipt']['observed'], {'resolver_unit_stub': True})
        after = {path.relative_to(run).as_posix(): path.read_bytes() for path in run.rglob('*') if path.is_file()}
        self.assertEqual(after, before)

    def test_forged_pass_boolean_is_rejected_by_real_cli(self):
        run = self.resolver_unit_stub_run()
        write_json(run / 'receipt.json', {'passed': True, 'binding': self.binding})
        data = self.resolve('--oracle', str(self.stub))
        self.assertEqual(data['candidates'][0]['reason'], 'stale or forged eval receipt')

    def test_changed_resolution_role_arm_effort_or_source_is_rejected(self):
        self.resolver_unit_stub_run()
        for text, role, arm in [('## codex\nfeature: gpt-6.1-sol@xhigh\n', 'feature', '1'),
                                ('## codex\nfeature: gpt-6-luna@high\n', 'feature', '1'),
                                ('feature: gpt-6.1-sol@high\n', 'feature', '1'),
                                ('## codex\nrefactoring: gpt-6.1-sol@high\n', 'refactoring', '1'),
                                ('## codex\narena runners: gpt-6.1-sol@high,gpt-6.1-sol@high\n', 'arena runners', '2')]:
            with self.subTest(role=role, arm=arm, text=text):
                self.config.write_text(text)
                data = self.resolve('--oracle', str(self.stub), '--role', role, '--arm', arm)
                self.assertEqual(data['candidates'][0]['reason'], 'eval binding does not match exact current resolution or route context')

    def test_stale_or_forged_evidence_is_rejected(self):
        run = self.resolver_unit_stub_run()
        path = run / 'receipt.json'
        original = path.read_bytes()
        receipt = json.loads(original)
        receipt['oracle_sha256'] = 'old'
        write_json(path, receipt)
        data = self.resolve('--oracle', str(self.stub))
        self.assertEqual(data['candidates'][0]['reason'], 'stale or forged eval receipt')
        path.write_bytes(original)
        receipt = json.loads(original)
        receipt['suite'] = 'pstack-resume-v1'
        write_json(path, receipt)
        write_json(run / 'resolver-unit-authority.json', receipt)
        data = self.resolve('--oracle', str(self.stub))
        self.assertEqual(data['candidates'][0]['reason'], 'unsupported eval suite')
        (run / 'resolver-unit-evidence.json').unlink()
        data = self.resolve('--oracle', str(self.stub))
        self.assertIn('current oracle rejected evidence', data['candidates'][0]['reason'])

    def test_prior_oracle_receipt_is_ineligible_after_checker_change(self):
        self.resolver_unit_stub_run()
        checker = self.root / 'checker'
        checker.mkdir()
        source = checker / 'oracle.py'
        source.write_bytes(self.stub.read_bytes() + b'\n')
        data = self.resolve('--oracle', str(source))
        self.assertEqual(data['candidates'][0]['reason'], 'stale or forged eval receipt')
        self.assertFalse(data['candidates'][0]['eligible'])

    def test_real_prepared_case_and_forged_receipt_never_certify(self):
        run = self.prepared_run()
        before = {path.relative_to(run).as_posix(): path.read_bytes() for path in run.rglob('*') if path.is_file()}
        for action in ('assess', 'check'):
            result = subprocess.run([sys.executable, str(ORACLE), action, '--run', str(run)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            if action == 'assess':
                self.assertEqual(json.loads(result.stdout)['kind'], 'gap_report')
                self.assertIn('runner capture is absent', json.loads(result.stdout)['gaps'])
            else:
                self.assertEqual(result.stdout, '')
                self.assertIn('runner capture is absent', result.stderr)
        self.assertEqual({path.relative_to(run).as_posix(): path.read_bytes() for path in run.rglob('*') if path.is_file()}, before)
        self.assertFalse((run / 'receipt.json').exists())
        write_json(run / 'receipt.json', {'passed': True, 'binding': self.binding})
        candidate = self.resolve('--oracle', str(ORACLE))['candidates'][0]
        self.assertFalse(candidate['eligible'])
        self.assertIn('current oracle rejected evidence: eval rejected: runner capture is absent', candidate['reason'])
        invoices = run / 'inputs/invoices.json'
        original = invoices.read_bytes()
        invoices.write_text('[]')
        candidate = self.resolve('--oracle', str(ORACLE))['candidates'][0]
        self.assertFalse(candidate['eligible'])
        self.assertEqual(candidate['reason'], 'current oracle rejected evidence: eval rejected: prepared input changed: inputs/invoices.json')
        invoices.write_bytes(original)
        row = json.loads((run / 'tasks.jsonl').read_text())
        base = run / 'runs' / row['run_dir']
        base.mkdir(parents=True)
        for key, value in (('runtime_model', 'gpt-6.1-sol'), ('runtime_effort', 'high'), ('certificate', {'passed': True})):
            with self.subTest(key=key):
                write_json(base / 'recovery.json', {'schema_version': 1, key: value})
                candidate = self.resolve('--oracle', str(ORACLE))['candidates'][0]
                self.assertFalse(candidate['eligible'])
                self.assertEqual(candidate['reason'], 'current oracle rejected evidence: eval rejected: unsupported producer certification or runtime claim')

    def test_version_drift_and_disappearing_checker_fail(self):
        self.resolver_unit_stub_run()
        contexts = json.loads(self.contexts.read_text())
        contexts['codex']['version'] = 'another-version'
        write_json(self.contexts, contexts)
        data = self.resolve('--oracle', str(self.stub))
        self.assertEqual(data['candidates'][0]['reason'], 'eval binding does not match exact current resolution or route context')
        self.context_for(self.root / 'resolver-unit-run')
        self.stub.unlink()
        data = self.resolve('--oracle', str(self.stub))
        self.assertIn('current oracle rejected evidence', data['candidates'][0]['reason'])

    def test_route_and_permission_context_drift_fail(self):
        self.resolver_unit_stub_run()
        original = json.loads(self.contexts.read_text())
        for changes in ({'route': 'native'}, {'permission_context': {'sandbox': 'read-only', 'approval': 'never'}}):
            with self.subTest(changes=changes):
                value = copy.deepcopy(original)
                value['codex'].update(changes)
                write_json(self.contexts, value)
                data = self.resolve('--oracle', str(self.stub))
                self.assertEqual(data['candidates'][0]['reason'], 'eval binding does not match exact current resolution or route context')

    def test_bad_context_json_is_a_cli_error(self):
        self.contexts.write_text('[]')
        self.assertIn('contexts must map', self.resolve(expected_status=2))

    def test_relative_evidence_path_is_denied(self):
        self.prepared_run()
        contexts = json.loads(self.contexts.read_text())
        contexts['codex']['eval_run'] = 'model-free-run'
        write_json(self.contexts, contexts)
        data = self.resolve('--oracle', str(ORACLE))
        self.assertEqual(data['candidates'][0]['reason'], 'eval_run must be an absolute retained evidence path')


if __name__ == '__main__':
    unittest.main()
