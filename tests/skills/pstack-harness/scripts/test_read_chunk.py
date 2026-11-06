import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
SCRIPT = ROOT / 'skills/pstack-harness/scripts/read-chunk.py'
FOOTER = re.compile(rb'\[read-chunk\.py: chunk (\d+) of (\d+), lines (\d+)-(\d+) of (\d+)\]\n\Z')


class ReadChunk(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)

    def file(self, content):
        path = self.dir / 'SKILL.md'
        path.write_bytes(content)
        return path

    def run_script(self, path, budget, *options):
        return subprocess.run(
            [sys.executable, str(SCRIPT), str(path), '--max-output-tokens', str(budget), *options],
            capture_output=True,
        )

    def read_every_chunk(self, path, budget):
        bodies, chunk, count = [], 1, 1
        while chunk <= count:
            result = self.run_script(path, budget, '--chunk', str(chunk))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertLessEqual(len(result.stdout), budget)
            start = result.stdout[:-1].rfind(b'\n') + 1
            footer = FOOTER.match(result.stdout, start)
            self.assertIsNotNone(footer, result.stdout[-200:])
            self.assertEqual(int(footer[1]), chunk)
            count = int(footer[2])
            bodies.append(result.stdout[:start])
            chunk += 1
        return bodies

    def test_chunks_fit_the_cap_and_rebuild_the_file(self):
        lines = [f'{n} {"é→" * (n % 9)} {"x" * (n * 7 % 61)}'.encode() for n in range(300)]
        content = b'\r\n'.join(lines) + b'\r\n\n\n'
        path = self.file(content)
        for budget in (300, 457, 2000, 10**6):
            with self.subTest(budget=budget):
                bodies = self.read_every_chunk(path, budget)
                self.assertEqual(b''.join(bodies), content)
                self.assertEqual(len(bodies) > 1, budget < len(content))

    def test_a_line_too_long_for_the_cap_exits_1_without_content(self):
        long_line = b'y' * 5000 + b'\n'
        content = b'short\n' * 40 + long_line + b'short\n' * 40
        path = self.file(content)
        for budget in (4000, len(long_line)):
            with self.subTest(budget=budget):
                result = self.run_script(path, budget)
                self.assertEqual(result.returncode, 1)
                self.assertEqual(result.stdout, b'')
                self.assertNotIn(b'Traceback', result.stderr)
        needed = int(re.search(rb'needs --max-output-tokens (\d+) or more', result.stderr)[1])
        self.assertEqual(b''.join(self.read_every_chunk(path, needed)), content)

    def test_a_last_line_without_a_newline_keeps_the_footer_on_its_own_line(self):
        result = self.run_script(self.file(b'one\ntwo'), 1000)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, b'one\ntwo\n[read-chunk.py: chunk 1 of 1, lines 1-2 of 2]\n')

    def test_an_empty_file_prints_only_the_footer(self):
        result = self.run_script(self.file(b''), 1000)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, b'[read-chunk.py: chunk 1 of 1, lines 0-0 of 0]\n')

    def test_a_chunk_outside_the_file_is_a_usage_error(self):
        path = self.file(b'line\n' * 100)
        count = len(self.read_every_chunk(path, 200))
        for chunk in (0, count + 1):
            with self.subTest(chunk=chunk):
                result = self.run_script(path, 200, '--chunk', str(chunk))
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, b'')
                self.assertIn(b'error:', result.stderr)

    def test_an_unreadable_path_exits_1_with_a_message(self):
        for path in (self.dir / 'missing.md', self.dir):
            with self.subTest(path=path.name):
                result = self.run_script(path, 1000)
                self.assertEqual(result.returncode, 1)
                self.assertEqual(result.stdout, b'')
                self.assertIn(b'cannot read', result.stderr)
                self.assertNotIn(b'Traceback', result.stderr)


if __name__ == '__main__':
    unittest.main()
