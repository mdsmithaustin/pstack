import re
import unittest

from check import RULES, grade

RULE, CASE = "two-hats", "free-shipping"
ROOT = RULES / RULE / "cases" / CASE


def commit(message, files):
    body = "".join(f'<file path="{path}">\n{text}</file>\n' for path, text in files.items())
    return f'<commit message="{message}">\n{body}</commit>\n'


def good_files():
    good = (ROOT / "samples" / "good.md").read_text()
    blocks = re.findall(r'<commit message="[^"]*">(.*?)</commit>', good, re.DOTALL)
    return [dict(re.findall(r'<file path="([^"]+)">\n(.*?)</file>', block, re.DOTALL)) for block in blocks]


class FreeShippingTests(unittest.TestCase):
    def test_structure_then_behavior_passes(self):
        self.assertEqual(grade(RULE, CASE, "good.md"), [])

    def test_one_mixed_commit_fails(self):
        self.assertEqual(
            grade(RULE, CASE, "bad.md"),
            [
                "commit 1 ('Free shipping from $500 and clean up shipping rates') restructures the code and changes behavior or an existing expected value",
                "commit 1 ('Free shipping from $500 and clean up shipping rates') changes charges before any structure-only commit lands",
            ],
        )

    def test_behavior_before_structure_fails(self):
        original = (ROOT / "project" / "shipping.py").read_text()
        threshold = original.replace(
            '    weight = order["weight_kg"]\n',
            '    weight = order["weight_kg"]\n    if order["subtotal_cents"] >= 50000 and zone in ("domestic", "canada", "international"):\n        return 0\n',
        )
        _, feature = good_files()
        answer = commit("Ship orders of $500 or more free", {"shipping.py": threshold, "tests/test_shipping.py": feature["tests/test_shipping.py"]})
        answer += commit("Replace per-zone rate copies with one rate table", {"shipping.py": feature["shipping.py"]})
        self.assertEqual(
            grade(RULE, CASE, text=answer),
            ["commit 1 ('Ship orders of $500 or more free') changes charges before any structure-only commit lands"],
        )

    def test_cleanup_that_edits_an_expected_value_fails(self):
        structure, feature = good_files()
        edited = (ROOT / "project" / "tests" / "test_shipping.py").read_text().replace("5998", "5998.0")
        answer = commit("Rate table", {"shipping.py": structure["shipping.py"], "tests/test_shipping.py": edited})
        answer += commit("Free shipping", feature)
        self.assertEqual(
            grade(RULE, CASE, text=answer),
            [
                "commit 1 ('Rate table') restructures the code and changes behavior or an existing expected value",
                "commit 2 ('Free shipping') changes charges before any structure-only commit lands",
            ],
        )

    def test_skipping_the_cleanup_fails(self):
        original = (ROOT / "project" / "shipping.py").read_text()
        threshold = original.replace(
            '    weight = order["weight_kg"]\n',
            '    weight = order["weight_kg"]\n    if order["subtotal_cents"] >= 50000 and zone in ("domestic", "canada", "international"):\n        return 0\n',
        )
        _, feature = good_files()
        answer = commit("Free shipping", {"shipping.py": threshold, "tests/test_shipping.py": feature["tests/test_shipping.py"]})
        self.assertEqual(
            grade(RULE, CASE, text=answer),
            [
                "the per-zone rate logic is still copy-pasted",
                "commit 1 ('Free shipping') changes charges before any structure-only commit lands",
            ],
        )


if __name__ == "__main__":
    unittest.main()
