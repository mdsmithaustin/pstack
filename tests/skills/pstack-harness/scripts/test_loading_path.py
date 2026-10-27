import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
SCRIPT = ROOT / 'skills/pstack-harness/scripts/loading-path.py'
RECEIPTS = ROOT / 'docs/pstack-harness-loading-paths.json'
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

    def test_recorded_receipts_match_the_script(self):
        for entry in json.loads(RECEIPTS.read_text(encoding='utf-8')):
            options = ['--baseline', entry['baseline'], '--action', entry['action']]
            if entry['runtime']:
                options += ['--runtime', entry['runtime']]
            if entry['persona']:
                options.append('--persona')
            with self.subTest(options=options):
                result = subprocess.run(
                    [sys.executable, str(SCRIPT), *options], capture_output=True, text=True,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(
                    json.loads(result.stdout), entry,
                    'docs/pstack-harness-loading-paths.json is stale: regenerate this entry '
                    'with loading-path.py ' + ' '.join(options),
                )

    def test_help_lists_every_action_and_what_a_baseline_needs(self):
        result = subprocess.run(
            [sys.executable, str(SCRIPT), '--help'], capture_output=True, text=True, check=True,
        )
        help_text = ' '.join(result.stdout.split())
        guide = (ROOT / PREFIX / 'SKILL.md').read_text(encoding='utf-8')
        table = guide.split('## Runtime adapters\n', 1)[0]
        actions = re.findall(r'^\| `([^`]+)` \|', table, re.MULTILINE)
        self.assertTrue(actions)
        for action in actions:
            with self.subTest(action=action):
                self.assertRegex(help_text, rf'[{{,]{re.escape(action)}[,}}]')
        self.assertIn('Needs git on PATH and a pstack source checkout', help_text)
        self.assertIn('symlinked install', help_text)

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
        self.env.update(
            GIT_CEILING_DIRECTORIES=str(self.root.parent), GIT_CONFIG_GLOBAL=os.devnull,
            GIT_CONFIG_NOSYSTEM='1', LC_ALL='C',
        )

    def install(self, parent):
        skill = parent / 'skills/pstack-harness'
        shutil.copytree(ROOT / 'skills/pstack-harness', skill)
        return skill / 'scripts/loading-path.py'

    def git(self, *command):
        return subprocess.run(
            ['git', '-C', str(self.root), '-c', 'user.name=t', '-c', 'user.email=t@t',
             '-c', 'commit.gpgsign=false', *command],
            check=True, env=self.env, capture_output=True, text=True,
        ).stdout.strip()

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
        self.assertIn('not a git repository', result.stderr)
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
        script = self.install(self.root)
        self.git('init', '-q')
        self.git('commit', '-q', '--allow-empty', '-m', 'empty')
        missing = '0' * 40
        result = self.run_script(script, '--baseline', missing)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, '')
        self.assertIn(f'baseline {missing} is not a commit in {self.root}', result.stderr)
        self.assertNotIn('Traceback', result.stderr)

    def test_baseline_before_the_harness_existed_names_the_missing_file(self):
        self.git('init', '-q')
        self.git('commit', '-q', '--allow-empty', '-m', 'empty')
        result = self.run_script(self.install(self.root), '--baseline', 'HEAD')
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, '')
        self.assertIn('baseline HEAD has no ' + PREFIX + 'SKILL.md', result.stderr)
        self.assertIn("but not in 'HEAD'", result.stderr)
        self.assertNotIn('Traceback', result.stderr)

    def test_git_error_bytes_outside_the_locale_encoding_exit_with_a_message(self):
        script = self.install(self.root)
        self.git('init', '-q')
        self.git('commit', '-q', '--allow-empty', '-m', 'empty')
        tag = b'caf\xe9'
        with open(self.root / '.git/packed-refs', 'ab') as refs:
            refs.write(self.git('rev-parse', 'HEAD').encode() + b' refs/tags/' + tag + b'\n')
        absent_file = self.run_script(script, '--baseline', os.fsdecode(tag))
        self.env['GIT_DIR'] = os.fsdecode(b'/nonexistent/' + tag)
        no_repository = self.run_script(script, '--baseline', 'HEAD')
        for result, message in (
            (absent_file, 'has no ' + PREFIX + 'SKILL.md'), (no_repository, 'git cannot open'),
        ):
            with self.subTest(message):
                self.assertEqual(result.returncode, 1, result.stderr)
                self.assertEqual(result.stdout, '')
                self.assertIn(message, result.stderr)
                self.assertNotIn('Traceback', result.stderr)

    def test_dubious_ownership_is_named_with_gits_safe_directory_hint(self):
        script = self.install(self.root)
        self.git('init', '-q')
        self.git('commit', '-q', '--allow-empty', '-m', 'empty')
        self.env['GIT_TEST_ASSUME_DIFFERENT_OWNER'] = '1'
        result = self.run_script(script, '--baseline', 'HEAD')
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, '')
        self.assertIn(
            f'git refuses to open the repository that holds {self.root} because another user '
            'owns it', result.stderr)
        self.assertIn('safe.directory', result.stderr)
        self.assertIn('omit --baseline', result.stderr)
        self.assertNotIn('not a pstack source checkout', result.stderr)
        self.assertNotIn('Traceback', result.stderr)

    def test_symlinked_install_compares_against_the_target_repository(self):
        target = self.root / 'clone'
        project = self.root / 'project'
        self.install(target)
        guide = target / PREFIX / 'SKILL.md'
        current = guide.read_bytes()
        old = b'old guide\n'
        guide.write_bytes(old)
        self.git('-C', str(target), 'init', '-q')
        self.git('-C', str(target), 'add', '-A', '--force')
        self.git('-C', str(target), 'commit', '-qm', 'install')
        commit = self.git('-C', str(target), 'rev-parse', 'HEAD')
        guide.write_bytes(current)
        (project / 'skills').mkdir(parents=True)
        (project / 'skills/pstack-harness').symlink_to(target / PREFIX.rstrip('/'))
        self.git('-C', str(project), 'init', '-q')
        self.git('-C', str(project), 'commit', '-q', '--allow-empty', '-m', 'empty')
        result = self.run_script(project / 'skills/pstack-harness/scripts/loading-path.py',
                                 '--baseline', commit)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['before']['bytes'], len(old))
        missing = self.run_script(project / 'skills/pstack-harness/scripts/loading-path.py',
                                  '--baseline', '0' * 40)
        self.assertEqual(missing.returncode, 1)
        self.assertIn(f'is not a commit in {target}', missing.stderr)

    def test_copy_inside_another_repository_compares_its_own_history(self):
        script = self.install(self.root / '.claude')
        guide = self.root / '.claude' / PREFIX / 'SKILL.md'
        current = guide.read_bytes()
        old = b'old guide\n'
        guide.write_bytes(old)
        self.git('init', '-q')
        self.git('add', '-A', '--force')
        self.git('commit', '-qm', 'install')
        commit = self.git('rev-parse', 'HEAD')
        guide.write_bytes(current)
        result = self.run_script(script, '--baseline', commit)
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report['baseline'], commit)
        self.assertEqual(report['before']['files'], [
            {'path': PREFIX + 'SKILL.md', 'bytes': len(old)},
        ])


if __name__ == '__main__':
    unittest.main()
