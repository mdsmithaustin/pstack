"""Executable controls for the boundary case's durable partial-effect premise."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import live


class DeliveryRecoveryFixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.project = Path(self.temp.name) / "relay"
        live.make_project(live.load_case("feature-boundary-run"), self.project)
        self.feed = self.project / "feed.json"
        self.feed.write_text(json.dumps([
            {"id": "b", "name": "First"}, {"id": "a", "name": "Second"}
        ]))

    def run_python(self, script):
        return subprocess.run([sys.executable, "-c", script], cwd=self.project,
                              text=True, capture_output=True)

    def deliveries(self):
        journal = self.project / "out/deliveries.jsonl"
        return [json.loads(line) for line in journal.read_text().splitlines()] if journal.exists() else []

    def import_normally(self):
        result = self.run_python("from relay.ingest import import_feed; import_feed('feed.json', 'out')")
        self.assertEqual(result.returncode, 0, result.stderr)

    def assert_complete_delivery(self):
        # The case requires each input record once, in source order, including fields.
        self.assertEqual(self.deliveries(), [
            {"id": "b", "fields": {"name": "First"}},
            {"id": "a", "fields": {"name": "Second"}},
        ])

    def test_exit_after_synced_append_leaves_prefix_and_naive_restart_duplicates(self):
        interrupted = self.run_python('''
import os
from relay.ingest import import_feed
from relay.store import Store
original = Store.write

def exit_after_append(self, record):
    original(self, record)
    os._exit(75)

Store.write = exit_after_append
import_feed('feed.json', 'out')
''')
        self.assertEqual(interrupted.returncode, 75, interrupted.stderr)
        self.assertEqual(self.deliveries(), [{"id": "b", "fields": {"name": "First"}}])
        prefix = (self.project / "out/deliveries.jsonl").read_bytes()
        self.import_normally()
        self.assertTrue((self.project / "out/deliveries.jsonl").read_bytes().startswith(prefix))
        self.assertEqual([r["id"] for r in self.deliveries()], ["b", "b", "a"])
        with self.assertRaises(AssertionError):
            self.assert_complete_delivery()

    def test_retrying_whole_import_after_unacknowledged_write_is_unsafe(self):
        result = self.run_python('''
from relay.ingest import import_feed
from relay.retry import retry, Transient
from relay.store import Store
original = Store.write
failed = False

def ambiguous_write(self, record):
    global failed
    result = original(self, record)
    if not failed:
        failed = True
        raise Transient('write completed but acknowledgement was lost')
    return result

Store.write = ambiguous_write
retry(lambda: import_feed('feed.json', 'out'))
''')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual([r["id"] for r in self.deliveries()], ["b", "b", "a"])
        with self.assertRaises(AssertionError):
            self.assert_complete_delivery()

    def test_uninterrupted_delivery_preserves_input_order_and_summary_count(self):
        self.import_normally()
        self.assert_complete_delivery()
        result = self.run_python("from relay.summarize import summarize; print(summarize('feed.json', 'out')['already_stored'])")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "2")

    def test_empty_and_single_record_inputs(self):
        self.feed.write_text("[]")
        self.import_normally()
        self.assertEqual(self.deliveries(), [])
        self.feed.write_text('[{"id":"only","name":"One"}]')
        self.import_normally()
        self.assertEqual(self.deliveries(), [{"id": "only", "fields": {"name": "One"}}])
        self.import_normally()
        self.assertEqual([r["id"] for r in self.deliveries()], ["only", "only"])


if __name__ == "__main__":
    unittest.main()
