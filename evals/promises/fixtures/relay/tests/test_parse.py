import json
import unittest
from pathlib import Path

from relay.oldparse import parse_legacy
from relay.parse import parse

CASES = Path(__file__).parent / "cases"


def flatten(record):
    return {"id": record.id, **record.fields}


class ParseCasesTest(unittest.TestCase):
    def test_every_case_matches_its_expected_file(self):
        inputs = sorted(CASES.glob("*.txt"))
        self.assertGreaterEqual(len(inputs), 4)
        for path in inputs:
            expected = json.loads(path.with_suffix(".expected").read_text())
            text = path.read_text()
            with self.subTest(case=path.stem, parser="parse"):
                self.assertEqual([flatten(r) for r in parse(text)], expected)
            with self.subTest(case=path.stem, parser="parse_legacy"):
                self.assertEqual(parse_legacy(text), expected)


if __name__ == "__main__":
    unittest.main()
