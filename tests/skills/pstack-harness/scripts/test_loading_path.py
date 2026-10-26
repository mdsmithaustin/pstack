import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
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


class CopiesOutsideTheSourceCheckout(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve()
        self.env = {key: value for key, value in os.environ.items() if not key.startswith('GIT_')}
        self.env['GIT_CEILING_DIRECTORIES'] = str(self.root.parent)

    def install(self, parent):
        skill = parent / 'skills/pstack-harness'
        shutil.copytree(ROOT / 'skills/pstack-harness', skill)
        return skill / 'scripts/loading-path.py'

    def git(self, *command):
        subprocess.run(
            ['git', '-C', str(self.root), '-c', 'user.name=t', '-c', 'user.email=t@t',
             '-c', 'commit.gpgsign=false', *command],
            check=True, env=self.env,
        )

    def run_script(self, script, *options):
        return subprocess.run(
            [sys.executable, str(script), '--action', 'worklist', *options],
            capture_output=True, text=True, env=self.env,
        )

    def test_installed_copy_reports_the_current_route_without_a_baseline(self):
        script = self.install(self.root)
        result = self.run_script(script)
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertIsNone(report['baseline'])
        self.assertIsNone(report['before'])
        self.assertEqual(report['after']['files'], [
            {'path': PREFIX + name, 'bytes': (self.root / PREFIX / name).stat().st_size}
            for name in ('SKILL.md', 'references/worklist.md')
        ])

    def test_installed_copy_explains_that_a_baseline_needs_a_checkout(self):
        result = self.run_script(self.install(self.root), '--baseline', BASELINE)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, '')
        self.assertIn(f'git cannot open {self.root} as a repository', result.stderr)
        self.assertIn('omit --baseline', result.stderr)
        self.assertNotIn('Traceback', result.stderr)

    def test_installed_copy_without_git_explains_that_a_baseline_needs_it(self):
        script = self.install(self.root)
        self.env['PATH'] = str(self.root)
        result = self.run_script(script, '--baseline', BASELINE)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, '')
        self.assertIn('--baseline needs git', result.stderr)
        self.assertNotIn('Traceback', result.stderr)

    def test_unavailable_baseline_names_the_missing_commit(self):
        missing = '0' * 40
        result = self.run_script(SCRIPT, '--baseline', missing)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, '')
        self.assertIn(f'baseline {missing} is not a commit in {ROOT}', result.stderr)
        self.assertNotIn('Traceback', result.stderr)

    def test_baseline_before_the_harness_existed_names_the_missing_file(self):
        self.git('init', '-q')
        self.git('commit', '-q', '--allow-empty', '-m', 'empty')
        result = self.run_script(self.install(self.root), '--baseline', 'HEAD')
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, '')
        self.assertIn('baseline HEAD has no ' + PREFIX + 'SKILL.md', result.stderr)
        self.assertNotIn('Traceback', result.stderr)

    def test_copy_inside_another_repository_compares_its_own_history(self):
        script = self.install(self.root / '.claude')
        self.git('init', '-q')
        self.git('add', '-A')
        self.git('commit', '-qm', 'install')
        result = self.run_script(script, '--baseline', 'HEAD')
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report['before']['files'], report['after']['files'][:1])


if __name__ == '__main__':
    unittest.main()
