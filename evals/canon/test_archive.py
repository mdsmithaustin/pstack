import io
import json
from pathlib import Path
import subprocess
import tarfile
import unittest


ROOT = Path(__file__).resolve().parents[2]


class ArchivedSource(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.record = json.loads((ROOT / "evals/archive/canon.json").read_text())
        cls.commit = cls.record["source_commit"]
        cls.source = cls.record["source_path"]
        archive = subprocess.check_output(
            ["git", "-C", str(ROOT), "archive", cls.commit, cls.source])
        with tarfile.open(fileobj=io.BytesIO(archive)) as tree:
            cls.files = {member.name: tree.extractfile(member).read()
                         for member in tree.getmembers() if member.isfile()}

    def test_pinned_source_can_be_recovered(self):
        tree = subprocess.check_output(
            ["git", "-C", str(ROOT), "rev-parse", f"{self.commit}:{self.source}"],
            text=True).strip()
        self.assertEqual(tree, self.record["source_tree"])
        self.assertEqual(len(self.files), self.record["source_files"])

    def test_all_historical_configurations_remain_in_the_snapshot(self):
        rules = sorted(str(Path(path).parent.relative_to("evals/canon/rules"))
                       for path in self.files if path.endswith("/rule.json"))
        self.assertEqual(rules, self.record["historical_configurations"])
        self.assertEqual(len(rules), 68)

    def test_current_source_matches_the_declared_archive_split(self):
        retained = set(self.record["retained_paths"])
        self.assertEqual(len(retained), len(self.record["retained_paths"]))
        self.assertTrue(retained <= self.files.keys())
        self.assertEqual(len(self.files.keys() - retained), self.record["archived_files"])
        present = {path for path in self.files if (ROOT / path).is_file()}
        self.assertEqual(present, retained)


if __name__ == "__main__":
    unittest.main()
