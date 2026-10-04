import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from harnesses import hermes
from test_hermes import HermesDatabase


class HarvestCustodyRegression(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="hermes-custody-")
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name).resolve()
        self.root = self.base / "run"
        self.project = self.root / "w" / "p"
        self.project.mkdir(parents=True)
        self.run = SimpleNamespace(root=self.root, project=self.project, case={"turns": ["go"]},
                                   turns=[{"session_id": "root", "exit_code": 0, "duration_s": 1}])
        hermes.profile(self.run).mkdir(parents=True)
        hermes.transcripts(self.run).mkdir()
        (self.root / "hermes.json").write_text(json.dumps({"image": "img", "cli_version": "1", "entry": None,
                                                         "preload": {}, "todo_eager": True, "todo_tools": "on"}))

    def database(self):
        path = hermes.profile(self.run) / "state.db"
        db = HermesDatabase(path)
        db.session("root")
        db.message("root", "user", "go")
        db.message("root", "assistant", "owned native reply")
        db.done()
        return path

    def test_source_alias_is_incomplete_without_copying_outside_bytes(self):
        outside = self.base / "outside-read"
        outside.write_bytes(b"owned-outside-read-canary\n")
        (hermes.profile(self.run) / "state.db").symlink_to(outside)
        trace = hermes.harvest(self.run)
        copies = list(self.root.rglob("state.db"))
        self.assertTrue(trace.get("x_harvest_error"), trace)
        self.assertEqual([p.read_bytes() for p in copies if not p.is_symlink()], [])
        self.assertEqual(outside.read_bytes(), b"owned-outside-read-canary\n")

    def test_legacy_destination_alias_cannot_overwrite_outside_bytes(self):
        self.database()
        outside = self.base / "outside-write"
        outside.write_bytes(b"owned-outside-write-canary\n")
        (hermes.transcripts(self.run) / "state.db").symlink_to(outside)
        trace = hermes.harvest(self.run)
        self.assertEqual(outside.read_bytes(), b"owned-outside-write-canary\n")
        self.assertEqual(trace["final_reply"], "owned native reply")

    def test_missing_main_cannot_reuse_previous_acquisition(self):
        path = self.database()
        self.assertEqual(hermes.harvest(self.run)["final_reply"], "owned native reply")
        path.unlink()
        trace = hermes.harvest(self.run)
        self.assertTrue(trace.get("x_harvest_error"), trace)
        self.assertEqual(trace["events"], [])


if __name__ == "__main__":
    unittest.main()
