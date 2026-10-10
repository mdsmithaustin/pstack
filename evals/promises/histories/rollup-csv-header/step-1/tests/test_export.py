import unittest

from rollup.export import HEADER, export, format_row


class ListSink:
    def __init__(self):
        self.lines = []

    def append(self, batch):
        self.lines.extend(batch)


class FormatRowTest(unittest.TestCase):
    def test_formats_total_and_trims_customer(self):
        row = {"id": "1001", "customer": "  ada lovelace", "qty": "3", "unit_price": "4.50"}
        self.assertEqual(format_row(row), "1001,Ada Lovelace,13.50")


class HeaderTest(unittest.TestCase):
    rows = [{"id": "1001", "customer": "ada", "qty": "1", "unit_price": "2"}]

    def test_header_comes_first_and_is_not_counted(self):
        sink = ListSink()
        self.assertEqual(export(self.rows, sink, header=True), 1)
        self.assertEqual(sink.lines, [HEADER, "1001,Ada,2.00\n"])

    def test_no_header_by_default(self):
        sink = ListSink()
        export(self.rows, sink)
        self.assertEqual(sink.lines, ["1001,Ada,2.00\n"])


if __name__ == "__main__":
    unittest.main()
