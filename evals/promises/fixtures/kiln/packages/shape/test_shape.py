import unittest
from collections import namedtuple

from shape import between, busiest, group_by_tag, tag_sizes

Entry = namedtuple("Entry", "timestamp tag text")


class ShapeTest(unittest.TestCase):
    def setUp(self):
        self.entries = [
            Entry("2026-03-01T10:00", "ops", "second"),
            Entry("2026-03-01T09:00", "dev", "only"),
            Entry("2026-03-01T08:00", "ops", "first"),
        ]

    def test_groups_are_sorted_by_tag(self):
        groups = group_by_tag(self.entries)
        self.assertEqual([g.tag for g in groups], ["dev", "ops"])

    def test_entries_are_sorted_by_timestamp(self):
        ops = group_by_tag(self.entries)[1]
        self.assertEqual([e.text for e in ops.entries], ["first", "second"])

    def test_busiest_picks_the_largest_group(self):
        self.assertEqual(busiest(group_by_tag(self.entries)).tag, "ops")

    def test_between_keeps_the_window(self):
        ops = group_by_tag(self.entries)[1]
        kept = between(ops, "2026-03-01T09:00", "2026-03-01T11:00")
        self.assertEqual([e.text for e in kept], ["second"])

    def test_tag_sizes(self):
        self.assertEqual(tag_sizes(group_by_tag(self.entries)), {"dev": 1, "ops": 2})


if __name__ == "__main__":
    unittest.main()
