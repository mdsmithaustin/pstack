import json
import tempfile
import unittest
from pathlib import Path

from sync_job_loader import ConfigError, load_job


class LoadJobTest(unittest.TestCase):
    def write(self, config):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        path = Path(folder.name) / "job.json"
        path.write_text(json.dumps(config), encoding="utf-8")
        return path

    def test_nightly_loads(self):
        job = load_job(Path(__file__).parent.parent / "jobs" / "nightly.json")
        self.assertEqual(job, {"source": "/srv/app/data", "destination": "/mnt/copies/nightly", "keep": 14})

    def test_keep_defaults_to_seven(self):
        job = load_job(self.write({"source": "/srv/app/data", "destination": "backup://store/nightly"}))
        self.assertEqual(job["keep"], 7)

    def test_missing_destination_is_rejected(self):
        with self.assertRaises(ConfigError):
            load_job(self.write({"source": "/srv/app/data"}))
