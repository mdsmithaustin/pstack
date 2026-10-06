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
NORMAL_SCRIPT = SCRIPT.with_name('check-models-config.py')
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

    def normal(self, harness, role, work_model, expected_status=0):
        result = subprocess.run([sys.executable, str(NORMAL_SCRIPT), '--resolve', '--harness', harness,
                                 '--project', str(self.project), '--user-file', str(self.user),
                                 *(['--work-model', work_model] if work_model is not None else []), role],
                                env=self.environment, capture_output=True, text=True)
        self.assertEqual(result.returncode, expected_status, result.stderr + result.stdout)
        return [json.loads(line) for line in result.stdout.splitlines()] if result.stdout else result.stderr

    def saved_input(self, work_model):
        path = self.root / 'resolution-input.json'
        write_json(path, {'workModel': work_model})
        return ['--resolution-input', str(path)]

    def test_real_cli_reviewer_resolution_parity(self):
        catalog = Path(self.environment['CODEX_HOME']) / 'models_cache.json'
        catalog.parent.mkdir()
        write_json(catalog, {'models': [
            {'slug': slug, 'supported_reasoning_levels': [{'effort': level} for level in levels]}
            for slug, levels in [('gpt-6.1-sol', ['low', 'medium', 'high', 'xhigh', 'max', 'ultra']),
                                 ('gpt-6-sol', ['low', 'medium', 'high', 'xhigh', 'max', 'ultra']),
                                 ('gpt-6-astra', ['high']), ('gpt-6-luna', ['low', 'medium', 'high', 'xhigh', 'max'])]
        ]})
        for harness, config, work, expected in [
            ('codex', 'trail reviewer: gpt-6.1-sol@high\nfeature: gpt-6-astra@high\n', 'gpt-6.1-sol@high',
             {'model': 'gpt-6-astra', 'effort': 'high', 'notes': ['trail reviewer matched work model gpt-6.1-sol; stepped up to gpt-6-astra'], 'step': 'up'}),
            ('codex', 'trail reviewer: gpt-6-astra@high\n', 'gpt-6-astra@xhigh',
             {'model': 'gpt-6.1-sol', 'effort': 'xhigh', 'notes': ['trail reviewer matched work model gpt-6-astra; stepped down to gpt-6.1-sol'], 'step': 'down'}),
            ('codex', 'trail reviewer: gpt-5.6-sol@high\n', 'gpt-5.6-sol@high',
             {'model': 'gpt-5.6-sol', 'effort': 'xhigh', 'notes': ['trail reviewer matched work model gpt-5.6-sol; the config allows no other model in its family, so this is a same-model review'], 'step': 'same-model'}),
            ('codex', 'trail reviewer: gpt-6.1-sol@high\n', 'gpt-6-luna@high',
             {'model': 'gpt-6.1-sol', 'effort': 'high'}),
            ('codex', 'trail reviewer: inherit-parent\n', 'gpt-6.1-sol@high',
             {'model': 'inherit-parent', 'effort': 'inherit-parent'}),
            ('codex', 'trail reviewer: gpt-6.1-sol@xhigh\nfeature: gpt-6-astra@high\n', 'gpt-6.1-sol',
             {'model': 'gpt-6-astra', 'effort': 'high', 'notes': ['trail reviewer matched work model gpt-6.1-sol; stepped up to gpt-6-astra'], 'step': 'up'}),
            ('codex', 'trail reviewer: gpt-6.1-sol@xhigh\nfeature: gpt-6-astra@high\n', 'gpt-6.1-sol@inherit-parent',
             {'model': 'gpt-6-astra', 'effort': 'high', 'notes': ['trail reviewer matched work model gpt-6.1-sol; stepped up to gpt-6-astra'], 'step': 'up'}),
            ('codex', 'trail reviewer: gpt-6-sol@high\nfeature: gpt-6-astra@high\n', 'opus',
             {'model': 'gpt-6-astra', 'effort': 'high', 'notes': ['trail reviewer matched work model gpt-6-sol; stepped up to gpt-6-astra'], 'step': 'up'}),
            ('codex', 'trail reviewer: gpt-6-sol@high\nfeature: gpt-6-astra@high\n', 'claude-opus-5-5[1m]@max',
             {'model': 'gpt-6-astra', 'effort': 'high', 'notes': ['trail reviewer matched work model gpt-6-sol; stepped up to gpt-6-astra'], 'step': 'up'}),
            ('hermes', 'trail reviewer: actual-model@high\n', 'opus@xhigh',
             {'model': 'actual-model', 'effort': 'high', 'notes': ['work model opus is not usable on hermes; no step applied']}),
            ('hermes', 'trail reviewer: opus@high\n', 'opus@xhigh',
             {'model': 'inherit-parent', 'effort': 'high', 'notes': ['opus is not usable on hermes', 'work model opus is not usable on hermes; no step applied']}),
            ('hermes', 'trail reviewer: claude-opus-5-5@high\n', 'claude-opus-5-5@high',
             {'model': 'claude-opus-5-5', 'effort': 'xhigh', 'notes': ['trail reviewer matched work model claude-opus-5-5; the config allows no other model in its family, so this is a same-model review'], 'step': 'same-model'}),
            ('claude-code', 'trail reviewer: fable@high\n', 'claude-fable-5-1@high',
             {'model': 'opus', 'effort': 'xhigh', 'notes': ['trail reviewer matched work model fable; stepped down to opus'], 'step': 'down'}),
            ('claude-code', 'trail reviewer: sonnet\n', 'sonnet@inherit-parent',
             {'model': 'opus', 'effort': 'inherit-parent', 'notes': ['trail reviewer matched work model sonnet; stepped up to opus'], 'step': 'up'}),
            ('grok', 'trail reviewer: grok-4.7@high\n', 'opus@xhigh',
             {'model': 'grok-4.7', 'effort': 'xhigh', 'notes': ['trail reviewer matched work model grok-4.7; the config allows no other model in its family, so this is a same-model review'], 'step': 'same-model'}),
            ('codex', 'trail reviewer: gpt-6.1-sol@high\n', 'auto',
             {'model': 'gpt-6.1-sol', 'effort': 'high'}),
            ('codex', 'trail reviewer: gpt-6.1-sol@high\n', 'inherit-parent@high',
             {'model': 'gpt-6.1-sol', 'effort': 'high'}),
            ('codex', 'trail reviewer: gpt-6.1-sol@high\n', 'gpt-9-zeta@high',
             {'model': 'gpt-6.1-sol', 'effort': 'high'}),
        ]:
            with self.subTest(harness=harness, work=work):
                source = 'hermes' if harness == 'grok' else 'grok'
                self.config.write_text(f'# resume-priority: {source}={harness}\n## {harness}\n{config}')
                expected = {'role': 'trail reviewer', 'arm': 1, **expected, 'source': f'workspace ## {harness}'}
                self.assertEqual(self.normal(harness, 'trail reviewer', work), [expected])
                actual = self.resolve('--source', source, '--role', 'trail reviewer', *self.saved_input(work))['candidates'][0]
                self.assertEqual(actual, {'harness': harness, 'resolution': expected, 'route': None, 'version': None,
                                          'eval_receipt': None, 'eligible': False,
                                          'reason': 'destination identity is not concrete' if 'inherit-parent' in (expected['model'], expected['effort'])
                                          else 'destination availability, route or version is unobserved'})

    def test_unknown_reviewer_input_is_distinct_from_successful_omission(self):
        self.config.write_text('## codex\ntrail reviewer: gpt-6.1-sol@high\n')
        missing = self.resolve('--role', 'trail reviewer')['candidates'][0]
        self.assertEqual(missing, {'harness': 'codex', 'resolution': None, 'route': None, 'version': None,
                                   'eval_receipt': None, 'eligible': False, 'reason': 'saved reviewer resolution input is unknown'})
        expected = {'role': 'trail reviewer', 'arm': 1, 'model': 'gpt-6.1-sol', 'effort': 'high', 'source': 'workspace ## codex'}
        self.assertEqual(self.normal('codex', 'trail reviewer', None), [expected])
        known = self.resolve('--role', 'trail reviewer', *self.saved_input(None))['candidates'][0]
        self.assertEqual(known['resolution'], expected)
        self.assertEqual(known['reason'], 'destination availability, route or version is unobserved')

    def test_feature_and_panel_resolution_remain_exact_with_saved_input(self):
        for role, arm, model, effort in [('feature', 1, 'gpt-6.1-sol', 'high'),
                                         ('arena runners', 1, 'gpt-6-sol', 'max'),
                                         ('arena runners', 2, 'gpt-6-luna', 'high')]:
            with self.subTest(role=role, arm=arm):
                expected = {'role': role, 'arm': arm, 'model': model, 'effort': effort, 'source': 'workspace ## codex'}
                for work in ('absent', 'gpt-6-sol@high', None):
                    extra = [] if work == 'absent' else self.saved_input(work)
                    actual = self.resolve('--role', role, '--arm', str(arm), *extra)['candidates'][0]
                    self.assertEqual(actual['resolution'], expected)
                    self.assertEqual(actual['reason'], 'destination availability, route or version is unobserved')
                self.assertEqual(self.normal('codex', role, 'gpt-6-sol@high')[arm - 1], expected)

    def test_invalid_destination_input_denies_without_retry_and_preserves_priority(self):
        self.config.write_text('# resume-priority: grok=claude-code,codex\n## claude-code\ntrail reviewer: opus@high\n## codex\ntrail reviewer: gpt-6.1-sol@high\nfeature: gpt-6-astra@high\n')
        for work, reason in [('gpt-6.1-sol@high', "argument --work-model: 'gpt-6.1-sol' is not a Claude Code model; use an alias (fable, opus, sonnet, haiku) or a claude-<alias>-... ID"),
                              ('opus[1m]@high', "argument --work-model: invalid model name 'opus[1m]'")]:
            with self.subTest(work=work):
                self.assertIn(reason, self.normal('claude-code', 'trail reviewer', work, expected_status=2))
                data = self.resolve('--source', 'grok', '--role', 'trail reviewer', *self.saved_input(work))
                self.assertEqual([item['harness'] for item in data['candidates']], ['claude-code', 'codex'])
                self.assertEqual(data['candidates'][0]['resolution'], None)
                self.assertEqual(data['candidates'][0]['reason'], reason)
                self.assertFalse(data['candidates'][0]['eligible'])
                if work.startswith('gpt-'):
                    self.assertEqual(data['candidates'][1]['resolution'], {
                        'role': 'trail reviewer', 'arm': 1, 'model': 'gpt-6-astra', 'effort': 'high', 'source': 'workspace ## codex',
                        'notes': ['trail reviewer matched work model gpt-6.1-sol; stepped up to gpt-6-astra'], 'step': 'up'})

    def test_malformed_saved_input_is_a_cli_error(self):
        path = self.root / 'resolution-input.json'
        for value in ([], {}, {'workModel': 4}, {'workModel': False}, {'workModel': 'opus@turbo'}, {'workModel': None, 'resolvedArm': {}}):
            with self.subTest(value=value):
                write_json(path, value)
                result = self.resolve('--resolution-input', str(path), expected_status=2)
                self.assertIn('resolution input' if value != {'workModel': 'opus@turbo'} else "unknown effort 'turbo'", result)
        path.write_text('{')
        self.assertIn('Expecting property name', self.resolve('--resolution-input', str(path), expected_status=2))
        path.unlink()
        self.assertIn('No such file', self.resolve('--resolution-input', str(path), expected_status=2))

    def test_input_grammar_is_checked_even_without_destination_candidates(self):
        self.assertEqual(self.resolve('--source', 'grok', '--role', 'trail reviewer', *self.saved_input(None)),
                         {'priority': {'source': 'grok', 'destinations': [], 'configured_source': 'default'}, 'candidates': []})
        result = self.resolve('--source', 'grok', '--role', 'trail reviewer', *self.saved_input('opus@turbo'), expected_status=2)
        self.assertEqual(result, "argument --work-model: unknown effort 'turbo'\n")

    def test_reviewer_resolver_unit_stub_compares_complete_five_key_binding(self):
        self.config.write_text('## codex\ntrail reviewer: gpt-6.1-sol@high\nfeature: gpt-6-astra@high\n')
        expected = {'role': 'trail reviewer', 'arm': 1, 'model': 'gpt-6-astra', 'effort': 'high', 'source': 'workspace ## codex',
                    'notes': ['trail reviewer matched work model gpt-6.1-sol; stepped up to gpt-6-astra'], 'step': 'up'}
        self.assertEqual(self.normal('codex', 'trail reviewer', 'gpt-6.1-sol@high'), [expected])
        self.binding['resolution'] = expected
        run = self.resolver_unit_stub_run()
        extra = ['--role', 'trail reviewer', '--oracle', str(self.stub), *self.saved_input('gpt-6.1-sol@high')]
        candidate = self.resolve(*extra, expected_status=0)['candidates'][0]
        self.assertEqual(candidate['resolution'], expected)
        self.assertEqual(candidate['eval_receipt']['binding'], self.binding)
        self.assertEqual(sorted(candidate['eval_receipt']['binding']), ['harness', 'permission_context', 'resolution', 'route', 'version'])
        original = json.loads((run / 'receipt.json').read_text())
        for field, value in [('notes', []), ('source', 'user ## codex'), ('step', 'down'), ('step', None), ('notes', None)]:
            with self.subTest(field=field, value=value):
                receipt = copy.deepcopy(original)
                if value is None:
                    del receipt['binding']['resolution'][field]
                else:
                    receipt['binding']['resolution'][field] = value
                write_json(run / 'receipt.json', receipt)
                write_json(run / 'resolver-unit-authority.json', receipt)
                denied = self.resolve(*extra)['candidates'][0]
                self.assertEqual(denied['resolution'], expected)
                self.assertEqual(denied['reason'], 'eval binding does not match exact current resolution or route context')
        write_json(run / 'receipt.json', original)
        write_json(run / 'resolver-unit-authority.json', original)
        changed_work = self.resolve('--role', 'trail reviewer', '--oracle', str(self.stub), *self.saved_input('gpt-6-luna@high'))['candidates'][0]
        self.assertEqual(changed_work['resolution'], {'role': 'trail reviewer', 'arm': 1, 'model': 'gpt-6.1-sol', 'effort': 'high', 'source': 'workspace ## codex'})
        self.assertEqual(changed_work['reason'], 'eval binding does not match exact current resolution or route context')

    def test_matching_unstepped_stub_cannot_supply_unknown_reviewer_input(self):
        self.config.write_text('## codex\ntrail reviewer: gpt-6.1-sol@high\n')
        self.binding['resolution'] = {'role': 'trail reviewer', 'arm': 1, 'model': 'gpt-6.1-sol', 'effort': 'high', 'source': 'workspace ## codex'}
        self.resolver_unit_stub_run()
        missing = self.resolve('--role', 'trail reviewer', '--oracle', str(self.stub))['candidates'][0]
        self.assertIsNone(missing['resolution'])
        self.assertIsNone(missing['eval_receipt'])
        self.assertEqual(missing['reason'], 'saved reviewer resolution input is unknown')
        known = self.resolve('--role', 'trail reviewer', '--oracle', str(self.stub), *self.saved_input(None), expected_status=0)['candidates'][0]
        self.assertEqual(known['resolution'], self.binding['resolution'])
        self.assertEqual(known['eval_receipt']['observed'], {'resolver_unit_stub': True})

    def test_known_null_records_successful_normal_caller_fallback(self):
        self.config.write_text('## claude-code\ntrail reviewer: opus@high\n')
        self.assertIn('is not a Claude Code model', self.normal('claude-code', 'trail reviewer', 'gpt-6.1-sol@high', expected_status=2))
        expected = {'role': 'trail reviewer', 'arm': 1, 'model': 'opus', 'effort': 'high', 'source': 'workspace ## claude-code'}
        self.assertEqual(self.normal('claude-code', 'trail reviewer', None), [expected])
        known = self.resolve('--source', 'codex', '--role', 'trail reviewer', *self.saved_input(None))['candidates'][0]
        self.assertEqual(known['resolution'], expected)
        self.assertEqual(known['reason'], 'destination availability, route or version is unobserved')

    def test_invalid_supplied_work_is_validated_for_feature_and_panel(self):
        self.config.write_text('## claude-code\nfeature: sonnet@high\narena runners: opus@high,sonnet@high\n')
        reason = "argument --work-model: 'gpt-6.1-sol' is not a Claude Code model; use an alias (fable, opus, sonnet, haiku) or a claude-<alias>-... ID"
        for role, arm in [('feature', 1), ('arena runners', 2)]:
            with self.subTest(role=role, arm=arm):
                self.assertIn(reason, self.normal('claude-code', role, 'gpt-6.1-sol@high', expected_status=2))
                candidate = self.resolve('--source', 'codex', '--role', role, '--arm', str(arm), *self.saved_input('gpt-6.1-sol@high'))['candidates'][0]
                self.assertEqual(candidate['resolution'], None)
                self.assertEqual(candidate['reason'], reason)
                self.assertFalse(candidate['eligible'])
        self.config.write_text('# resume-priority: codex=hermes\n## hermes\ntrail reviewer: actual-model@high\n')
        work = 'claude-opus-5-5[1m]@high'
        reason = "argument --work-model: invalid model name 'claude-opus-5-5[1m]'"
        self.assertIn(reason, self.normal('hermes', 'trail reviewer', work, expected_status=2))
        candidate = self.resolve('--source', 'codex', '--role', 'trail reviewer', *self.saved_input(work))['candidates'][0]
        self.assertEqual(candidate['reason'], reason)
        self.assertEqual(candidate['resolution'], None)


if __name__ == '__main__':
    unittest.main()
