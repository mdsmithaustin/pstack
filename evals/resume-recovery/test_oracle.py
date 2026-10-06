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
            {'type': 'session_meta', 'payload': {'id': 'model-free-' + phase, 'cwd': str(project), 'cli_version': binding['version'], 'originator': 'Codex Desktop', 'source': 'exec', 'thread_source': 'user'}},
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


class OracleFixture(unittest.TestCase):
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


class OracleCases(OracleFixture):
    def test_observed_receipt_retains_invocation_and_evidence(self):
        receipt = oracle.check(self.run)
        self.assertEqual(receipt['binding'], BINDING)
        self.assertEqual(receipt['observed']['initial']['exit_code'], -15)
        self.assertEqual(receipt['observed']['recovery']['session_id'], 'model-free-recovery')
        self.assertEqual(receipt['observed']['recovery']['originator'], 'Codex Desktop')
        for phase in oracle.PHASES:
            self.assertEqual(receipt['observed'][phase]['source'], 'exec')
            self.assertEqual(receipt['observed'][phase]['thread_source'], 'user')
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

    def test_each_phase_requires_direct_exec_provenance(self):
        subagent = {'subagent': {'thread_spawn': {'parent_thread_id': 'model-free-parent', 'depth': 1,
                    'agent_path': '/root/model_free', 'agent_nickname': 'Model-free', 'agent_role': 'default'}}}
        model_free_provenance = [
            {},
            {'source': 'exec'},
            {'thread_source': 'user'},
            {'source': 'cli', 'thread_source': 'user'},
            {'source': 'vscode', 'thread_source': 'user'},
            {'source': subagent, 'thread_source': 'subagent'},
            {'source': subagent, 'thread_source': subagent},
            {'source': subagent, 'thread_source': 'user'},
            {'source': 'exec', 'thread_source': subagent},
            {'source': 'exec', 'thread_source': 'cli'},
            {'source': None, 'thread_source': 'user'},
            {'source': 'exec', 'thread_source': None},
        ]
        for phase in oracle.PHASES:
            path = self.run / f'{phase}-rollout.jsonl'
            original = path.read_bytes()
            for provenance in model_free_provenance:
                with self.subTest(phase=phase, provenance=provenance):
                    path.write_bytes(original)
                    def mutate(rows):
                        meta = rows[0]['payload']
                        meta.pop('source')
                        meta.pop('thread_source')
                        meta.update(provenance, originator='codex_exec')
                    self.mutate_rollout(phase, mutate)
                    with self.assertRaisesRegex(ValueError, phase + ' lacks direct codex exec provenance'):
                        oracle.check(self.run)
            path.write_bytes(original)

    def test_unresolved_aliases_cannot_receive_a_receipt(self):
        for field in ('model', 'effort'):
            for alias in ('inherit-parent', 'auto', ' inherit-parent ', ' auto ', '\tinherit-parent\n', '\tauto\n'):
                with self.subTest(field=field, alias=alias):
                    with tempfile.TemporaryDirectory() as directory:
                        binding = copy.deepcopy(BINDING)
                        binding['resolution'][field] = alias
                        with self.assertRaisesRegex(ValueError, 'unknown destination identity'):
                            model_free_run(Path(directory) / 'run', binding)

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


def runtime_event_run(run):
    fixture = oracle.load(run / 'fixture.json')
    checkpoint = {'total': 18, **fixture['tokens']}
    for phase in oracle.PHASES:
        path = run / f'{phase}-rollout.jsonl'
        rows = [json.loads(line) for line in path.read_text().splitlines()][:3]
        turn = 'turn-' + phase
        rows.append({'type': 'event_msg', 'payload': {'type': 'task_started', 'turn_id': turn}})
        command = 'printf forbidden > denied.txt' if phase == 'refusal' else 'python3 task.py'
        result = {'exit_code': 1, 'output': 'zsh:1: operation not permitted: denied.txt\\n'} if phase == 'refusal' else {
            'output': json.dumps(checkpoint if phase == 'initial' else {**checkpoint, 'recovered': True}) + '\\n',
            **({'session_id': 42} if phase == 'initial' else {'exit_code': 0}),
        }
        rows.extend([
            {'type': 'response_item', 'payload': {'type': 'custom_tool_call', 'name': 'exec', 'call_id': 'c',
             'internal_chat_message_metadata_passthrough': {'turn_id': turn},
             'input': 'text(await tools.exec_command({cmd:' + json.dumps(command) + ',max_output_tokens:1000}));'}},
            {'type': 'response_item', 'payload': {'type': 'custom_tool_call_output', 'call_id': 'c', 'output': [
                {'type': 'input_text', 'text': 'Script completed\nWall time 0.1 seconds\nOutput:\n'},
                {'type': 'input_text', 'text': json.dumps(result)},
            ]}},
        ])
        if phase != 'refusal':
            rows.append({'type': 'event_msg', 'payload': {'type': 'item_completed', 'thread_id': 'model-free-' + phase,
                         'turn_id': turn, 'item': {'type': 'CommandExecution', 'id': 'exec-' + phase,
                         'process_id': '42', 'command': ['/bin/zsh', '-lc', command], 'cwd': (run / 'project').as_uri(),
                         'status': 'failed' if phase == 'initial' else 'completed', 'exit_code': -1 if phase == 'initial' else 0,
                         'stdout': json.dumps(checkpoint if phase == 'initial' else {**checkpoint, 'recovered': True}) + '\n'}}})
        if phase == 'initial':
            rows.append({'type': 'response_item', 'payload': {'type': 'custom_tool_call', 'name': 'exec', 'call_id': 'poll',
                         'input': 'text(await tools.write_stdin({session_id:42,chars:"",yield_time_ms:50000}));'}})
            rows.append({'type': 'response_item', 'payload': {'type': 'custom_tool_call_output', 'call_id': 'poll',
                         'output': 'aborted by user after 2.8s'}})
            rows.append({'type': 'event_msg', 'payload': {'type': 'turn_aborted', 'turn_id': turn, 'reason': 'interrupted'}})
        else:
            rows.append({'type': 'event_msg', 'payload': {'type': 'task_complete', 'turn_id': turn}})
        path.write_text(''.join(json.dumps(row) + '\n' for row in rows))
    operator = oracle.load(run / 'operator.json')
    operator['interruption'] = {'signal': 'SIGINT', 'exit_code': 1}
    operator['processes']['initial']['exit_code'] = 1
    write_json(run / 'operator.json', operator)


class RuntimeEventOracleCases(OracleFixture):
    def setUp(self):
        super().setUp()
        runtime_event_run(self.run)

    def test_cli_runtime_interrupted_checkpoint_and_custom_refusal_pass(self):
        receipt = oracle.check(self.run)
        self.assertEqual(receipt['observed']['initial']['exit_code'], 1)
        self.assertEqual(receipt['observed']['refusal']['session_id'], 'model-free-refusal')

    def test_rollout_completion_and_claimed_signal_cannot_certify_interruption(self):
        self.mutate_rollout('initial', lambda rows: rows.append({'type': 'event_msg', 'payload': {'type': 'task_complete', 'turn_id': 'turn-initial'}}))
        with self.assertRaisesRegex(ValueError, 'completed before interruption'):
            oracle.check(self.run)
        runtime_event_run(self.run)
        self.mutate('operator.json', lambda value: value['interruption'].update(signal='SIGTERM'))
        with self.assertRaisesRegex(ValueError, 'interruption'):
            oracle.check(self.run)

    def test_stale_yielded_turn_cannot_prove_interruption(self):
        self.mutate_rollout('initial', lambda rows: rows[4]['payload']['internal_chat_message_metadata_passthrough'].update(turn_id='stale'))
        with self.assertRaisesRegex(ValueError, 'interruption'):
            oracle.check(self.run)

    def test_unobserved_identity_is_rejected(self):
        for field in ('model', 'effort'):
            for value in (None, '', 'inherit-parent'):
                with self.subTest(field=field, value=value):
                    original = (self.run / 'fixture.json').read_bytes()
                    self.mutate('fixture.json', lambda data: data['binding']['resolution'].update({field: value}))
                    with self.assertRaisesRegex(ValueError, 'unknown destination identity'):
                        oracle.check(self.run)
                    (self.run / 'fixture.json').write_bytes(original)

    def test_parser_does_not_execute_javascript(self):
        target = self.run / 'must-not-exist'
        script = 'text(await tools.exec_command({cmd:"printf forbidden > denied.txt"})); require("fs").writeFileSync(' + json.dumps(str(target)) + ',"forged");'
        self.mutate_rollout('refusal', lambda rows: rows[4]['payload'].update(input=script))
        with self.assertRaises(ValueError):
            oracle.check(self.run)
        self.assertFalse(target.exists())

    def test_runtime_evidence_cannot_be_replaced_by_assistant_prose(self):
        for phase in ('initial', 'recovery'):
            with self.subTest(phase=phase):
                runtime_event_run(self.run)
                def mutate(rows):
                    rows[:] = [row for row in rows if row['payload'].get('item', {}).get('type') != 'CommandExecution']
                    rows.append({'type': 'response_item', 'payload': {'type': 'message', 'role': 'assistant', 'content': [{'text': 'Process exited with code 0 and task completed'}]}})
                self.mutate_rollout(phase, mutate)
                with self.assertRaises(ValueError):
                    oracle.check(self.run)

    def test_abort_must_be_observed_in_the_checkpoint_turn(self):
        for change in ('missing', 'wrong-turn', 'wrong-reason'):
            with self.subTest(change=change):
                runtime_event_run(self.run)
                def mutate(rows):
                    abort = rows[-1]['payload']
                    if change == 'missing':
                        rows.pop()
                    else:
                        abort['turn_id' if change == 'wrong-turn' else 'reason'] = 'unrelated'
                self.mutate_rollout('initial', mutate)
                with self.assertRaisesRegex(ValueError, 'interruption'):
                    oracle.check(self.run)

    def test_runtime_checkpoint_requires_raw_stdout_and_yielded_process(self):
        for field, value in [('stdout', 'assistant claims checkpoint'), ('process_id', 'stale'), ('exit_code', 0), ('cwd', 'file:///elsewhere')]:
            with self.subTest(field=field):
                runtime_event_run(self.run)
                self.mutate_rollout('initial', lambda rows: next(row['payload']['item'] for row in rows if row['payload'].get('item', {}).get('type') == 'CommandExecution').update({field: value}))
                with self.assertRaises(ValueError):
                    oracle.check(self.run)

    def test_refusal_requires_literal_exact_call_and_nonzero_paired_result(self):
        inputs = [
            'text(await tools.exec_command({cmd:"printf harmless"}));',
            'const cmd = "printf forbidden > denied.txt"; text(await tools.exec_command({cmd}));',
            'text(await tools.exec_command({cmd:"printf forbidden > denied.txt"})); text({exit_code:1,output:"operation not permitted"});',
            'text(await tools.exec_command({cmd:"printf forbidden > denied.txt",cmd:"printf harmless"}));',
            'text(await tools.exec_command({cmd:`printf forbidden > denied.txt`}));',
            'text(await tools.exec_command({cmd:"printf forbidden > denied.txt" + ""}));',
            'text(await tools.exec_command({cmd:"printf forbidden > denied.txt",workdir:"/elsewhere"}));',
        ]
        for script in inputs:
            with self.subTest(script=script):
                runtime_event_run(self.run)
                self.mutate_rollout('refusal', lambda rows: rows[4]['payload'].update(input=script))
                with self.assertRaises(ValueError):
                    oracle.check(self.run)

        for change in ('zero', 'unpaired', 'extra-output'):
            with self.subTest(change=change):
                runtime_event_run(self.run)
                def mutate(rows):
                    result = rows[5]['payload']
                    if change == 'zero':
                        result['output'][1]['text'] = json.dumps({'exit_code': 0, 'output': 'operation not permitted'})
                    elif change == 'unpaired':
                        result['call_id'] = 'unrelated'
                    else:
                        result['output'].append(result['output'][1])
                self.mutate_rollout('refusal', mutate)
                with self.assertRaises(ValueError):
                    oracle.check(self.run)

    def test_multiple_literal_calls_require_ordered_results_and_unique_ids(self):
        def mutate(rows):
            rows[4]['payload']['input'] = 'text(await tools.exec_command({cmd:"printf harmless"}));\n' + rows[4]['payload']['input']
            rows[5]['payload']['output'].insert(1, {'type': 'input_text', 'text': json.dumps({'exit_code': 0, 'output': 'harmless'})})
        self.mutate_rollout('refusal', mutate)
        self.assertEqual(oracle.check(self.run)['observed']['refusal']['exit_code'], 0)
        self.mutate_rollout('refusal', lambda rows: rows[5]['payload']['output'].reverse())
        with self.assertRaises(ValueError):
            oracle.check(self.run)
        runtime_event_run(self.run)
        self.mutate_rollout('refusal', lambda rows: rows.extend(copy.deepcopy(rows[4:6])))
        with self.assertRaisesRegex(ValueError, 'ambiguous execution call id'):
            oracle.check(self.run)


if __name__ == '__main__':
    unittest.main()
