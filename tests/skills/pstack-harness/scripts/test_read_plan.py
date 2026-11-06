import importlib.util
import shlex
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
SCRIPT = ROOT / 'skills/pstack-harness/scripts/read-plan.py'


def load(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


PROMISES = load('promise_oracles', 'evals/promises/oracles.py')
ROUTING = load('routing_oracle', 'evals/harness-routing/oracle.py')
NUMBERED = b''.join(f'line {n} {"z" * 50}\n'.encode() for n in range(120))


class ReadPlan(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name).resolve()

    def file(self, content, name='skills/demo/SKILL.md'):
        path = self.dir / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return path

    def plan(self, path, cap):
        return subprocess.run([sys.executable, str(SCRIPT), str(path), '--max-output-tokens', str(cap)],
                              capture_output=True)

    def commands(self, path, cap):
        result = self.plan(path, cap)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout.decode().splitlines()

    def run_command(self, command, cap):
        output = subprocess.run(shlex.split(command), capture_output=True, check=True).stdout
        self.assertLessEqual(len(output), cap)
        return output

    def test_each_range_fits_the_cap_and_the_ranges_rebuild_the_file(self):
        lines = [f'{n} {"é→" * (n % 9)} {"x" * (n * 7 % 61)}'.encode() for n in range(300)]
        content = b'\r\n'.join(lines) + b'\r\n\n\n'
        path = self.file(content)
        for cap in (200, 457, 2000, 10**6):
            with self.subTest(cap=cap):
                commands = self.commands(path, cap)
                self.assertEqual(b''.join(self.run_command(command, cap) for command in commands), content)
                self.assertEqual(len(commands) > 1, cap < len(content))

    def test_a_line_longer_than_the_cap_exits_1_without_commands(self):
        long_line = b'y' * 5000 + b'\n'
        content = b'short\n' * 40 + long_line + b'short\n' * 40
        path = self.file(content)
        for cap in (4000, len(long_line) - 1):
            with self.subTest(cap=cap):
                result = self.plan(path, cap)
                self.assertEqual(result.returncode, 1)
                self.assertEqual(result.stdout, b'')
                self.assertIn(f'needs --max-output-tokens {len(long_line)} or more'.encode(), result.stderr)
                self.assertNotIn(b'Traceback', result.stderr)
        commands = self.commands(path, len(long_line))
        self.assertEqual(b''.join(self.run_command(command, len(long_line)) for command in commands), content)

    def test_a_last_line_without_a_newline_reads_back_exactly(self):
        path = self.file(b'one\ntwo')
        self.assertEqual([self.run_command(command, 7) for command in self.commands(path, 7)], [b'one\ntwo'])

    def test_an_empty_file_needs_no_command(self):
        self.assertEqual(self.commands(self.file(b''), 100), [])

    def test_a_path_with_spaces_and_quotes_reads_back(self):
        path = self.file(b'alpha\nbeta\n', name="odd dir/it's SKILL.md")
        commands = self.commands(path, 6)
        self.assertEqual([shlex.split(command)[-1] for command in commands], [str(path)] * 2)
        self.assertEqual(b''.join(self.run_command(command, 6) for command in commands), b'alpha\nbeta\n')

    def test_an_unreadable_path_exits_1_with_a_message(self):
        for path in (self.dir / 'missing.md', self.dir):
            with self.subTest(path=path.name):
                result = self.plan(path, 1000)
                self.assertEqual(result.returncode, 1)
                self.assertEqual(result.stdout, b'')
                self.assertIn(b'cannot read', result.stderr)
                self.assertNotIn(b'Traceback', result.stderr)

    def test_the_promise_oracle_counts_the_whole_plan_as_a_whole_read(self):
        commands = self.commands(self.file(NUMBERED), 1500)
        self.assertGreater(len(commands), 2)
        spans = []
        for command in commands:
            reads = [PROMISES.pipeline_read(stages, base, 'demo/SKILL.md')
                     for stages, base in PROMISES.pipelines(command)]
            self.assertEqual([kind for kind, _ in reads], ['span'], command)
            spans += reads[0][1]
            self.assertEqual(PROMISES.covers(spans, 120), command == commands[-1])

    def test_the_routing_oracle_matches_each_range_to_its_source_bytes(self):
        path = self.file(NUMBERED)
        files = {'skills/demo/SKILL.md': NUMBERED}
        for number, command in enumerate(self.commands(path, 1500)):
            call = ROUTING.Command(str(number), command, str(self.dir), 2 * number, 2 * number + 1, None, 0, 'completed')
            parts = ROUTING.read_parts(call, self.dir, files)
            self.assertIsNotNone(parts, command)
            self.assertEqual(parts[0][3], self.run_command(command, 1500))


if __name__ == '__main__':
    unittest.main()
