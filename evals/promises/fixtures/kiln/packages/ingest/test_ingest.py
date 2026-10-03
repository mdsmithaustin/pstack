import unittest

from ingest import Entry, count_skipped, newest, parse_line, read_entries, tags


class IngestTest(unittest.TestCase):
    def test_parse_line_splits_fields(self):
        entry = parse_line("2026-03-01T09:00 [ops] restarted the worker pool")
        self.assertEqual(entry, Entry("2026-03-01T09:00", "ops", "restarted the worker pool"))

    def test_parse_line_rejects_untagged_text(self):
        self.assertIsNone(parse_line("just some words"))

    def test_read_entries_skips_bad_lines(self):
        lines = ["2026-03-01T09:00 [ops] a", "junk", "2026-03-01T09:05 [dev] b"]
        self.assertEqual([e.tag for e in read_entries(lines)], ["ops", "dev"])

    def test_count_skipped_ignores_blank_lines(self):
        self.assertEqual(count_skipped(["junk", "", "2026-03-01T09:00 [ops] a"]), 1)

    def test_tags_keep_first_seen_order(self):
        entries = read_entries(["2026-03-01T09:00 [ops] a", "2026-03-01T09:01 [dev] b", "2026-03-01T09:02 [ops] c"])
        self.assertEqual(tags(entries), ["ops", "dev"])

    def test_newest_is_none_when_empty(self):
        self.assertIsNone(newest([]))


if __name__ == "__main__":
    unittest.main()
