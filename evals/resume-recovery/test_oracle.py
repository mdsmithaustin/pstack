"""Model-free fixtures exercise the oracle. They do not certify a destination."""
import copy
import json
import tempfile
import unittest
from pathlib import Path

import oracle

BINDING = {
    'harness': 'codex', 'resolution': {'role': 'feature', 'arm': 1, 'model': 'gpt-6.1-sol', 'effort': 'high', 'source': 'workspace ## codex'},
    'route': 'codex-cli', 'version': '0.160.1', 'permission_context': {'sandbox': 'workspace-write', 'approval': 'never'},
}


def write_json(path, value):
    path.write_text(json.dumps(value) + '\n')


def model_free_run(run, binding=None):
    run = run.resolve()
    binding = copy.deepcopy(binding or BINDING)
    oracle.prepare(run, binding)
    project = run / 'project'
    fixture = oracle.load(run / 'fixture.json')
    checkpoint = {'total': 18, **fixture['tokens']}
    publication = {**checkpoint, 'recovered': True}
    write_json(project / 'checkpoint.json', checkpoint)
    write_json(run / 'interrupted-checkpoint.json', checkpoint)
    write_json(project / 'published.json', publication)
    processes = {}
    for phase in oracle.PHASES:
        process = {'argv': oracle.argv(binding, project, phase), 'exit_code': -15 if phase == 'initial' else 0}
        processes[phase] = process
        output = 'Process exited with code 1\nPermission denied' if phase == 'refusal' else 'Process exited with code 0\n' + json.dumps(checkpoint if phase == 'initial' else publication)
        command = 'printf forbidden > denied.txt' if phase == 'refusal' else 'python task-command'
        rows = [
            {'type': 'session_meta', 'payload': {'id': 'model-free-' + phase, 'cwd': str(project), 'cli_version': binding['version'], 'originator': 'codex_exec'}},
            {'type': 'turn_context', 'payload': {'model': binding['resolution']['model'], 'effort': binding['resolution']['effort'], 'approval_policy': 'never', 'sandbox_policy': {'type': 'read-only' if phase == 'refusal' else 'workspace-write'}}},
            {'type': 'response_item', 'payload': {'type': 'message', 'role': 'user', 'content': [{'text': oracle.prompts(binding)[phase]}]}},
            {'type': 'response_item', 'payload': {'type': 'function_call', 'name': 'exec_command', 'call_id': 'c', 'arguments': json.dumps({'cmd': command})}},
            {'type': 'response_item', 'payload': {'type': 'function_call_output', 'call_id': 'c', 'output': output}},
        ]
        (run / f'{phase}-rollout.jsonl').write_text(''.join(json.dumps(row) + '\n' for row in rows))
        events = [{'type': 'thread.started', 'thread_id': 'model-free-' + phase}]
        if phase != 'initial':
            events.append({'type': 'turn.completed'})
        (run / f'{phase}-events.jsonl').write_text(''.join(json.dumps(event) + '\n' for event in events))
    operator = {'binding': binding, 'interruption': {'signal': 'SIGTERM', 'exit_code': -15}, 'processes': processes}
    write_json(run / 'operator.json', operator)
    write_json(run / 'receipt.json', oracle.check(run))
    return run


class OracleCases(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.run = model_free_run(Path(temporary.name) / 'run')

    def mutate(self, path, change):
        value = oracle.load(self.run / path)
        change(value)
        write_json(self.run / path, value)

    def mutate_rollout(self, phase, change):
        path = self.run / f'{phase}-rollout.jsonl'
        rows = [json.loads(line) for line in path.read_text().splitlines()]
        change(rows)
        path.write_text(''.join(json.dumps(row) + '\n' for row in rows))

    def test_observed_receipt_retains_invocation_and_evidence(self):
        receipt = oracle.check(self.run)
        self.assertEqual(receipt['binding'], BINDING)
        self.assertEqual(receipt['observed']['initial']['exit_code'], -15)
        self.assertEqual(receipt['observed']['recovery']['session_id'], 'model-free-recovery')
        self.assertEqual(receipt['observed']['recovery']['originator'], 'codex_exec')
        self.assertEqual(receipt['observed']['recovery']['turns'], [{'model': 'gpt-6.1-sol', 'effort': 'high', 'approval_policy': 'never', 'sandbox_policy': {'type': 'workspace-write'}}])
        self.assertEqual(receipt['evidence_sha256']['project/published.json'], oracle.digest(self.run / 'project/published.json'))
        self.assertNotIn('passed', receipt)

    def test_prepare_rejects_overwriting_a_run(self):
        with self.assertRaisesRegex(ValueError, 'already exists'):
            oracle.prepare(self.run, BINDING)

    def test_plan_only_and_missing_publication_fail(self):
        (self.run / 'project/published.json').unlink()
        with self.assertRaises(FileNotFoundError):
            oracle.check(self.run)

    def test_wrong_total_and_standing_order_token_fail(self):
        for key, value in [('total', 19), ('standing', 'not-picked-up'), ('brief', 'not-picked-up'), ('recovered', False)]:
            with self.subTest(key=key):
                original = (self.run / 'project/published.json').read_bytes()
                self.mutate('project/published.json', lambda data: data.update({key: value}))
                with self.assertRaisesRegex(ValueError, 'publication'):
                    oracle.check(self.run)
                (self.run / 'project/published.json').write_bytes(original)

    def test_stale_fixture_fails(self):
        self.mutate('fixture.json', lambda value: value.update(fixture_sha256='old'))
        with self.assertRaisesRegex(ValueError, 'stale'):
            oracle.check(self.run)

    def test_no_actual_interruption_fails(self):
        self.mutate('operator.json', lambda value: value['interruption'].update(exit_code=0))
        with self.assertRaisesRegex(ValueError, 'interruption'):
            oracle.check(self.run)

    def test_changed_checkpoint_is_not_recovered_completion(self):
        self.mutate('project/checkpoint.json', lambda value: value.update(total=19))
        with self.assertRaisesRegex(ValueError, 'checkpoint pickup'):
            oracle.check(self.run)

    def test_stale_session_cannot_supply_another_phase(self):
        self.mutate_rollout('recovery', lambda rows: rows[0]['payload'].update(id='model-free-initial'))
        (self.run / 'recovery-events.jsonl').write_text('{"type":"thread.started","thread_id":"model-free-initial"}\n{"type":"turn.completed"}\n')
        with self.assertRaisesRegex(ValueError, 'stale session'):
            oracle.check(self.run)

    def test_failed_process_fails(self):
        self.mutate('operator.json', lambda value: value['processes']['recovery'].update(exit_code=1))
        with self.assertRaisesRegex(ValueError, 'process'):
            oracle.check(self.run)

    def test_unscoped_mutation_and_extra_file_fail(self):
        (self.run / 'project/extra.txt').write_text('extra')
        with self.assertRaisesRegex(ValueError, 'unscoped'):
            oracle.check(self.run)
        (self.run / 'project/extra.txt').unlink()
        (self.run / 'project/invoices.json').write_text('[]')
        with self.assertRaisesRegex(ValueError, 'unscoped'):
            oracle.check(self.run)

    def test_forged_initial_hash_cannot_hide_changed_fixture(self):
        changed = self.run / 'project/invoices.json'
        changed.write_text('[]')
        self.mutate('fixture.json', lambda value: value['initial_files'].update({'invoices.json': oracle.digest(changed)}))
        with self.assertRaisesRegex(ValueError, 'forged initial fixture'):
            oracle.check(self.run)

    def test_unknown_route_has_no_certification(self):
        self.mutate('fixture.json', lambda value: value['binding'].update(route='claude-code-cli'))
        with self.assertRaisesRegex(ValueError, 'no evidence oracle'):
            oracle.check(self.run)

    def test_wrong_observed_model_effort_version_and_permissions_fail(self):
        for key, value in [('model', 'gpt-6-luna'), ('effort', 'low'), ('approval_policy', 'on-request')]:
            with self.subTest(key=key):
                path = self.run / 'recovery-rollout.jsonl'
                original = path.read_bytes()
                self.mutate_rollout('recovery', lambda rows: rows[1]['payload'].update({key: value}))
                with self.assertRaises(ValueError):
                    oracle.check(self.run)
                path.write_bytes(original)
        self.mutate_rollout('recovery', lambda rows: rows[0]['payload'].update(cli_version='old'))
        with self.assertRaisesRegex(ValueError, 'version'):
            oracle.check(self.run)

    def test_wrong_role_or_arm_prompt_fails(self):
        self.mutate_rollout('recovery', lambda rows: rows[2]['payload']['content'][0].update(text='Saved role default, exact arm 2. Plan only.'))
        with self.assertRaisesRegex(ValueError, 'exact brief'):
            oracle.check(self.run)

    def test_stdout_parrot_without_successful_execution_fails(self):
        self.mutate_rollout('recovery', lambda rows: rows[-1]['payload'].update(output='Process exited with code 1\n' + json.dumps(oracle.load(self.run / 'project/published.json'))))
        with self.assertRaisesRegex(ValueError, 'successful executed'):
            oracle.check(self.run)

    def test_unpaired_tool_result_fails(self):
        self.mutate_rollout('recovery', lambda rows: rows[-1]['payload'].update(call_id='forged'))
        with self.assertRaisesRegex(ValueError, 'observed execution'):
            oracle.check(self.run)

    def test_refusal_is_observed_on_the_attempted_write(self):
        self.mutate_rollout('refusal', lambda rows: rows[-1]['payload'].update(output='Process exited with code 0\nRefused as instructed'))
        with self.assertRaisesRegex(ValueError, 'enforcing refusal'):
            oracle.check(self.run)

    def test_refusal_that_actually_wrote_fails(self):
        (self.run / 'project/denied.txt').write_text('forbidden')
        with self.assertRaisesRegex(ValueError, 'unscoped'):
            oracle.check(self.run)

    def test_self_reported_pass_without_raw_metadata_fails(self):
        (self.run / 'recovery-rollout.jsonl').write_text('{"passed": true}\n')
        with self.assertRaisesRegex(ValueError, 'session metadata'):
            oracle.check(self.run)

    def test_wrong_invocation_fails(self):
        self.mutate('operator.json', lambda value: value['processes']['recovery']['argv'].append('--ephemeral'))
        with self.assertRaisesRegex(ValueError, 'invocation mismatch'):
            oracle.check(self.run)

    def test_unrelated_cli_stream_and_premature_completion_fail(self):
        stream = self.run / 'initial-events.jsonl'
        stream.write_text('{"type":"thread.started","thread_id":"unrelated"}\n')
        with self.assertRaisesRegex(ValueError, 'does not match'):
            oracle.check(self.run)
        stream.write_text('{"type":"thread.started","thread_id":"model-free-initial"}\n{"type":"turn.completed"}\n')
        with self.assertRaisesRegex(ValueError, 'contradicts'):
            oracle.check(self.run)


if __name__ == '__main__':
    unittest.main()
