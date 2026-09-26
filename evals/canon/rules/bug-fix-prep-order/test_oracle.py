import re
import unittest

from check import RULES, grade

RULE = "bug-fix-prep-order"
COUPON, PAGES = "member-coupon", "orders-pagination"


def commits(case, sample):
    text = (RULES / RULE / "cases" / case / "samples" / sample).read_text()
    return re.findall(r'<commit message="[^"]*">.*?</commit>\n', text, re.DOTALL)


class MemberCouponTests(unittest.TestCase):
    def test_refactor_then_repro_then_fix_passes(self):
        self.assertEqual(grade(RULE, COUPON, "good.md"), [])

    def test_fixing_both_copies_fails(self):
        self.assertEqual(grade(RULE, COUPON, "bad.md"), ["the discount logic is still in 2 functions when the fix lands"])

    def test_repro_before_refactor_fails(self):
        refactor, repro, fix = commits(COUPON, "good.md")
        self.assertEqual(
            grade(RULE, COUPON, text=repro + refactor + fix),
            ["commit 2 ('Move per-unit pricing into one function') refactors but changes totals or leaves the suite red"],
        )

    def test_refactor_and_repro_in_one_commit_fails(self):
        refactor, repro, fix = commits(COUPON, "good.md")
        merged = refactor.replace("</commit>\n", "") + repro.split(">\n", 1)[1]
        self.assertEqual(
            grade(RULE, COUPON, text=merged + fix),
            ["commit 1 ('Move per-unit pricing into one function') lands the refactor and the failing repro together"],
        )

    def test_fix_without_repro_fails(self):
        refactor, _, fix = commits(COUPON, "good.md")
        self.assertEqual(
            grade(RULE, COUPON, text=refactor + fix),
            ["the suite is green right before the fix; no failing repro lands first"],
        )


class OrdersPaginationTests(unittest.TestCase):
    def test_repro_then_one_line_fix_passes(self):
        self.assertEqual(grade(RULE, PAGES, "good.md"), [])

    def test_refactor_before_one_line_fix_fails(self):
        self.assertEqual(
            grade(RULE, PAGES, "bad.md"),
            ["commit 1 ('Gather paging math into a Pager') changes code without changing paging; a refactor ships beside a one-line fix"],
        )

    def test_fix_folded_into_a_reshape_fails(self):
        _, repro, fix = commits(PAGES, "bad.md")
        self.assertEqual(
            grade(RULE, PAGES, text=repro + fix),
            ["commit 2 ('Round page count up instead of always adding a page') restructures the code inside the fix"],
        )


if __name__ == "__main__":
    unittest.main()
