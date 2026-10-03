import tempfile
import unittest
from collections import namedtuple
from pathlib import Path

from publish import Written, file_name, index_text, publish

Block = namedtuple("Block", "tag text")


class PublishTest(unittest.TestCase):
    def test_file_name_is_lowercase_and_safe(self):
        self.assertEqual(file_name("Ops Team"), "ops-team.txt")

    def test_writes_one_file_per_block(self):
        with tempfile.TemporaryDirectory() as out:
            written = publish([Block("ops", "a\n"), Block("dev", "bb\n")], Path(out) / "nested")
            self.assertEqual([w.path.name for w in written], ["ops.txt", "dev.txt"])
            self.assertEqual((Path(out) / "nested" / "dev.txt").read_text(), "bb\n")
            self.assertEqual(written[1].size, 3)

    def test_index_lists_files_and_total(self):
        written = [Written(Path("ops.txt"), 10), Written(Path("dev.txt"), 5)]
        self.assertEqual(index_text(written), "ops.txt\t10\ndev.txt\t5\ntotal\t15\n")


if __name__ == "__main__":
    unittest.main()
