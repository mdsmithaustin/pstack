import json
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'skills/pstack-harness/scripts/loading-path.py'
BASELINE = 'b5622490de2db0b32108bc071df32ae477f117fe'
PREFIX = 'skills/pstack-harness/'


class HarnessLoadingPaths(unittest.TestCase):
    def receipt(self, action, *options):
        result = subprocess.run(
            [sys.executable, str(SCRIPT), '--baseline', BASELINE, '--action', action, *options],
            capture_output=True, text=True, check=True,
        )
        return json.loads(result.stdout)

    def test_worklist_declares_only_the_shared_contract_and_worklist(self):
        report = self.receipt('worklist')
        self.assertEqual([row['path'] for row in report['after']['files']], [
            PREFIX + 'SKILL.md', PREFIX + 'references/worklist.md',
        ])
        self.assertEqual(report['before'], {
            'files': [{'path': PREFIX + 'SKILL.md', 'bytes': 25150}], 'bytes': 25150,
        })
        self.assertLess(report['after']['bytes'], report['before']['bytes'])

    def test_each_spawn_declares_the_shared_safety_and_one_runtime(self):
        for runtime in ('claude-code', 'codex', 'hermes', 'grok', 'other'):
            with self.subTest(runtime=runtime):
                report = self.receipt('spawn', '--runtime', runtime)
                self.assertEqual([row['path'] for row in report['after']['files']], [
                    PREFIX + 'SKILL.md', PREFIX + 'references/roles.md',
                    PREFIX + 'references/delegation.md', PREFIX + 'references/portable-paths.md',
                    PREFIX + f'references/{"other-runtime" if runtime == "other" else runtime}.md',
                ])

                self.assertEqual([row['path'] for row in report['before']['files']], [
                    PREFIX + 'SKILL.md', PREFIX + 'references/portable-paths.md',
                ])

    def test_persona_spawn_adds_the_persona_contract(self):
        report = self.receipt('spawn', '--runtime', 'codex', '--persona')
        self.assertEqual([row['path'] for row in report['after']['files']], [
            PREFIX + 'SKILL.md', PREFIX + 'references/roles.md',
            PREFIX + 'references/delegation.md', PREFIX + 'references/portable-paths.md',
            PREFIX + 'references/codex.md', PREFIX + 'references/named-roles.md',
        ])
        self.assertEqual([row['path'] for row in report['before']['files']], [
            PREFIX + 'SKILL.md', PREFIX + 'references/named-roles.md',
            PREFIX + 'references/portable-paths.md',
        ])

    def test_other_actions_declare_their_own_procedure(self):
        for action, reference in (
            ('question', 'questions'), ('role-handoff', 'roles'), ('loop', 'loops'),
            ('portable-paths', 'portable-paths'),
        ):
            with self.subTest(action=action):
                report = self.receipt(action)
                self.assertEqual([row['path'] for row in report['after']['files']], [
                    PREFIX + 'SKILL.md', PREFIX + f'references/{reference}.md',
                ])

    def test_transcript_selects_only_the_current_runtime(self):
        report = self.receipt('transcript', '--runtime', 'hermes')
        self.assertEqual([row['path'] for row in report['after']['files']], [
            PREFIX + 'SKILL.md', PREFIX + 'references/transcripts.md',
            PREFIX + 'references/transcripts-hermes.md',
        ])

    def test_invalid_routes_fail_instead_of_emitting_an_empty_success(self):
        for options in (
            ['--action', 'unknown'], ['--action', 'spawn'],
            ['--action', 'transcript'], ['--action', 'worklist', '--persona'],
        ):
            with self.subTest(options=options):
                result = subprocess.run(
                    [sys.executable, str(SCRIPT), '--baseline', BASELINE, *options],
                    capture_output=True, text=True,
                )
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, '')
                self.assertIn('error:', result.stderr)


if __name__ == '__main__':
    unittest.main()
