import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[4] / 'skills/setup-pstack/scripts/check-models-config.py'
spec = importlib.util.spec_from_file_location('models', SCRIPT)
models = importlib.util.module_from_spec(spec)
spec.loader.exec_module(models)


class ResumePriority(unittest.TestCase):
    def test_layering_is_per_source(self):
        workspace, _ = models.parse_resume_priority('# resume-priority: codex=hermes,grok\n')
        user, _ = models.parse_resume_priority('# resume-priority: codex=claude-code\n# resume-priority: grok=codex,hermes\n')
        self.assertEqual(models.resolve_priority('codex', workspace, user), ('codex', ('hermes', 'grok'), 'workspace'))
        self.assertEqual(models.resolve_priority('grok', workspace, user), ('grok', ('codex', 'hermes'), 'user'))
        self.assertEqual(models.resolve_priority('claude-code', workspace, user), ('claude-code', ('codex',), 'default'))
        self.assertEqual(models.resolve_priority('hermes', workspace, user), ('hermes', (), 'default'))

    def test_frontmatter_is_not_a_directive(self):
        priorities, findings = models.parse_resume_priority('---\n# resume-priority: codex=hermes\n---\n# resume-priority: codex=grok\n')
        self.assertEqual((priorities, findings), ({'codex': ('grok',)}, []))

    def test_priority_does_not_change_role_resolution(self):
        sections, findings = models.parse('# resume-priority: codex=hermes\nfeature: sonnet@high\n')
        self.assertEqual(findings, [])
        self.assertEqual(models.resolve_role('feature', 'codex', models.build_layers('codex', sections, {}, {})),
                         [models.ResolvedArm('feature', 1, 'gpt-6-sol', 'high', 'workspace flat', ('sonnet translated to gpt-6-sol',))])

    def test_invalid_directives_fail_lint_and_real_resolver(self):
        cases = {
            '#resume-priority: codex=hermes': 'malformed',
            '#  resume-priority: codex=hermes': 'malformed',
            '# resume-priority codex=hermes': 'malformed',
            '# resume-priority: codex=': 'malformed',
            '# resume-priority: codex=hermes,': 'unknown',
            '# resume-priority: codex=hermes, hermes': 'malformed',
            '# resume-priority: other=codex': 'unknown',
            '# resume-priority: codex=other': 'unknown',
            '# resume-priority: codex=codex': 'source',
            '# resume-priority: codex=hermes,hermes': 'duplicate',
            '# resume-priority: codex=hermes\n# resume-priority: codex=grok': 'duplicate',
        }
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            config = project / '.agents/pstack-models.md'
            config.parent.mkdir()
            for directive, diagnostic in cases.items():
                with self.subTest(directive=directive):
                    config.write_text(directive + '\nfeature: sonnet\n')
                    for command in ([str(config)], ['--resolve', '--harness', 'codex', '--project', str(project), '--user-file', str(project / 'absent'), 'feature']):
                        result = subprocess.run([sys.executable, str(SCRIPT), *command], text=True, capture_output=True)
                        self.assertEqual(result.returncode, 1)
                        self.assertIn(diagnostic, result.stdout + result.stderr)
                        if '--resolve' in command:
                            self.assertEqual(result.stdout, '')


if __name__ == '__main__':
    unittest.main()
