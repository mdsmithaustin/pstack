"""Native evidence contracts: complete actions, exact reads, explicit baselines."""
import json
import unittest
from pathlib import Path
from types import SimpleNamespace

import grade_boundary as boundary
from harnesses import codex
from test_recovery_obligations import child_rollout, parent_rollout, item, record, rollout
from test_oracles import FAIL, PASS, feature_case, grade, minimal


class NativeAcquisition(unittest.TestCase):
    def capture(self, *, prefix='', actions=b''):
        self.project = Path('/run/project')
        self.base, self.head = 'a' * 40, 'b' * 40
        command = f'git {boundary.RELAY_DIFF} {self.base} {self.head}'
        child = child_rollout(self.project, command, 'delivered bytes\n')
        rows = list(codex.records(child))
        rows[2]['payload']['input'] = prefix + rows[2]['payload']['input']
        child = rollout(*rows[:2]) + actions + rollout(*rows[2:])
        return codex.relay_review_inputs({'lead': parent_rollout(self.project)},
                                        {'child': child}, 'lead', self.project)

    def admitted(self, reviews):
        run = SimpleNamespace(project=self.project, root=Path('/run'), case={}, model=None, effort=None)
        state = {'record': {'turns': [{'session_id': 'lead',
                  'argv': ['codex', *codex.config_flags(run), '--']}]},
                 'run': {'path': '/run'}, 'project': {'path': str(self.project)}}
        return boundary._relay_review(state, self.base, self.head, 'c' * 40,
            b'delivered bytes\n', self.project, {'relay/store.py'}, ('lead', reviews, []))[0]

    def test_native_execution_pragma_keeps_exact_read_admissible(self):
        for prefix in ('', '// @exec: {"max_output_tokens": 24000}\n'):
            with self.subTest(prefix=prefix):
                self.assertEqual(len(self.admitted(self.capture(prefix=prefix))), 1)

    def test_pragma_does_not_admit_other_executed_code_or_bad_evidence(self):
        for prefix in ('// @exec: {"max_output_tokens": 24000}\ntext("extra");\n',
                       '// @exec: {}\n', '// @exec: {"max_output_tokens": 24000}\n// hidden\n',
                       '// @exec: {"max_output_tokens": 24000}; text("extra")\n'):
            with self.subTest(prefix=prefix):
                self.assertEqual(self.admitted(self.capture(prefix=prefix)), [])
        for field, value in (('output', 'truncated'), ('exit_code', 1), ('call', 'unrelated')):
            reviews = self.capture(prefix='// @exec: {"max_output_tokens": 24000}\n')
            reviews[0]['reads'][0][field] = value
            self.assertEqual(self.admitted(reviews), [])

    def test_oversized_actions_are_retained_whole(self):
        command = 'text(' + json.dumps('x' * 11457) + ')'
        reviews = self.capture(actions=rollout(item(type='custom_tool_call', name='exec',
                                                  call_id='large', input=command)))
        review, = reviews
        self.assertFalse(review['incomplete'])
        self.assertEqual(review['omitted']['actions'], 0)
        action = next(a for a in review['actions'] if a.get('id') == 'large')
        self.assertEqual(action['input']['code'], command)
        self.assertEqual(len(self.admitted(reviews)), 1)

    def test_capture_budget_exhaustion_stays_inconclusive(self):
        reviews = self.capture(actions=rollout(item(type='custom_tool_call', name='exec',
            call_id='large', input='x' * (160 * 8192 + 1))))
        self.assertTrue(reviews[0]['incomplete'])
        self.assertGreater(reviews[0]['omitted']['actions'], 0)
        self.assertEqual(self.admitted(reviews), [])

    def test_large_filechange_is_retained_and_disqualifies_reviewer(self):
        change = {'type': 'update', 'diff': 'x' * 10958}
        reviews = self.capture(actions=rollout(record('event_msg', type='item_completed',
            thread_id='review', item={'type': 'FileChange', 'id': 'edit', 'status': 'completed',
                                     'changes': {'/run/project/relay/store.py': change}})))
        self.assertFalse(reviews[0]['incomplete'])
        event = next(a for a in reviews[0]['actions'] if a.get('name') == 'FileChange')
        self.assertEqual(event['input']['changes']['/run/project/relay/store.py'], change)
        self.assertEqual(self.admitted(reviews), [])

    def test_total_action_budget_and_count_remain_bounded(self):
        for count, size in ((2, 700000), (161, 10)):
            with self.subTest(count=count, size=size):
                reviews = self.capture(actions=rollout(*[
                    item(type='custom_tool_call', name='exec', call_id=f'action-{i}', input='x' * size)
                    for i in range(count)]))
                review, = reviews
                self.assertTrue(review['incomplete'])
                self.assertLessEqual(sum(len(json.dumps(a).encode()) for a in review['actions']), 160 * 8192)
                self.assertLessEqual(len(review['actions']), 160)
                self.assertEqual(self.admitted(reviews), [])

    def test_explicit_baseline_opening_through_native_public_dispatch(self):
        for opening, expected in (
            ('playbooks/feature.md, baseline ' + 'a' * 40, PASS),
            ('playbooks/feature.md baseline abc1234', PASS),
            ('playbooks/feature.md baseline\tabc1234', PASS),
            ('playbooks/feature.md baseline', FAIL),
            ('playbooks/feature.md baseline\nabc1234', FAIL),
            ('playbooks/feature.md baseline; unrelated abc1234', FAIL),
            ('playbooks/feature.md baseline abc123g', FAIL),
            ('playbooks/feature.md baseline abc123', FAIL),
            ('playbooks/feature.md baseline ' + 'a' * 41, FAIL),
            ('playbooks/feature.md baseline no commits', FAIL),
            ('baseline abc1234', FAIL),
        ):
            with self.subTest(opening=opening):
                native = rollout(item(type='function_call', name='update_plan', call_id='plan',
                    arguments=json.dumps({'plan': [{'step': opening, 'status': 'in_progress'},
                                                  {'step': 'Implement and verify', 'status': 'pending'}]})))
                normalized = codex.harvest_rollout(native)
                trace = minimal(events=normalized['events'], worklist=normalized['worklist'], harness='codex')
                self.assertEqual(grade('worklist-opens-with-playbook-steps', trace, feature_case())['verdict'], expected)
