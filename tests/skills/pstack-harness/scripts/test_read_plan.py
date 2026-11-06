import importlib.util
import json
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
# Codex reports original_token_count as the byte count divided by 4, rounded up.
CODEX_BYTES_PER_TOKEN = 4
# The macOS python3 shim printed this much before each script run in Codex's read-only sandbox.
PYTHON3_WARNINGS = 420


def exec_result_bytes(output):
    result = {'chunk_id': '000000', 'wall_time_seconds': 0.000001, 'exit_code': 0,
              'original_token_count': len(output), 'output': output.decode('utf-8', 'replace')}
    return len(json.dumps(result, ensure_ascii=False).encode())


def shell(command):
    return subprocess.run(command, shell=True, capture_output=True, check=True).stdout


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

    def pages(self, path, cap):
        result = self.plan(path, cap)
        while True:
            self.assertEqual(result.returncode, 0, result.stderr)
            yield result.stdout
            last = result.stdout.decode().splitlines()[-1:]
            if not last or not last[0].startswith('python3 '):
                return
            result = subprocess.run(last[0], shell=True, capture_output=True)

    def commands(self, path, cap):
        return [line for page in self.pages(path, cap) for line in page.decode().splitlines()
                if not line.startswith('python3 ')]

    def read_within_cap(self, path, cap):
        for page in self.pages(path, cap):
            self.assertLessEqual(exec_result_bytes(page) + PYTHON3_WARNINGS, CODEX_BYTES_PER_TOKEN * cap)
        outputs = [shell(command) for command in self.commands(path, cap)]
        for output in outputs:
            self.assertLessEqual(exec_result_bytes(output), CODEX_BYTES_PER_TOKEN * cap)
        return outputs

    def test_each_output_fits_the_cap_and_the_outputs_rebuild_the_file(self):
        lines = [f'{n} {"é→" * (n % 9)} {"x" * (n * 7 % 61)}'.encode() for n in range(300)]
        lines[40] = b'word ' * 600
        lines[90] = b'y' * 2500
        content = b'\r\n'.join(lines) + b'\r\n\n\n'
        path = self.file(content)
        for cap in (250, 457, 2000, 10**6):
            with self.subTest(cap=cap):
                self.assertEqual(b''.join(self.read_within_cap(path, cap)), content)

    def test_whole_lines_pack_into_the_fewest_ranges_that_fit(self):
        path = self.file(b'123456789\n' * 6)
        for cap, ranges in ((110, ['1,3p', '4,6p']), (109, ['1,2p', '3,4p', '5,6p'])):
            with self.subTest(cap=cap):
                self.assertEqual([shlex.split(command) for command in self.commands(path, cap)],
                                 [['sed', '-n', lines, str(path)] for lines in ranges])

    def test_a_line_too_long_for_the_cap_is_read_in_pieces_cut_after_a_space(self):
        content = b'short\n' + b'wordier ' * 60 + b'\n' + b'y' * 700 + b'\n' + b'end\n'
        path = self.file(content)

        def piece(start, size):
            return ['tail', '-c', f'+{start}', str(path), '|', 'head', '-c', str(size)]
        expected = [['sed', '-n', '1,1p', str(path)], piece(7, 296), piece(303, 185),
                    piece(488, 300), piece(788, 300), piece(1088, 101), ['sed', '-n', '4,4p', str(path)]]
        self.assertEqual([shlex.split(command) for command in self.commands(path, 200)], expected)
        self.assertEqual(b''.join(shell(command) for command in self.commands(path, 200)), content)

    def test_lines_end_only_at_a_newline_as_in_sed(self):
        path = self.file(b'aa\rbb\ncc\n')
        self.assertEqual([shlex.split(command) for command in self.commands(path, 102)],
                         [['sed', '-n', '1,1p', str(path)], ['sed', '-n', '2,2p', str(path)]])
        self.assertEqual([shell(command) for command in self.commands(path, 102)], [b'aa\rbb\n', b'cc\n'])

    def test_a_path_with_shell_characters_reads_back_through_a_shell(self):
        content = b'alpha\nbeta\n' + b'gamma ' * 200 + b'\n'
        path = self.file(content, name='it\'s a "$HOME" `id` dir/SKILL.md')
        self.assertEqual(b''.join(self.read_within_cap(path, 300)), content)

    def test_a_long_plan_prints_in_pages_that_each_fit_the_cap(self):
        # Each 900-byte line fills the read budget at cap 400, so even short paths require paging.
        content = b''.join(f'{n:04} {"p" * 894}\n'.encode() for n in range(100))
        path = self.file(content)
        self.assertGreater(len(list(self.pages(path, 400))), 1)
        self.assertEqual(b''.join(self.read_within_cap(path, 400)), content)

    def test_an_empty_file_needs_no_command(self):
        self.assertEqual(self.read_within_cap(self.file(b''), 1000), [])

    def test_a_cap_of_100_or_less_exits_2_without_commands(self):
        result = self.plan(self.file(b'one\n'), 100)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, b'')
        self.assertIn(b'--max-output-tokens must be more than 100', result.stderr)

    def test_an_unreadable_path_exits_1_with_a_message(self):
        for path in (self.dir / 'missing.md', self.dir):
            with self.subTest(path=path.name):
                result = self.plan(path, 1000)
                self.assertEqual(result.returncode, 1)
                self.assertEqual(result.stdout, b'')
                self.assertIn(b'cannot read', result.stderr)
                self.assertNotIn(b'Traceback', result.stderr)

    def test_the_promise_oracle_counts_the_whole_plan_as_a_whole_read(self):
        commands = self.commands(self.file(NUMBERED), 700)
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
        for number, command in enumerate(self.commands(path, 700)):
            call = ROUTING.Command(str(number), command, str(self.dir), 2 * number, 2 * number + 1, None, 0, 'completed')
            parts = ROUTING.read_parts(call, self.dir, files)
            self.assertIsNotNone(parts, command)
            self.assertEqual(parts[0][3], shell(command))


if __name__ == '__main__':
    unittest.main()
