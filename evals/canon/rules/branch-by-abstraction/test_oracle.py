import unittest

from check import RULES, grade

RULE, SWAP, SMALL = "branch-by-abstraction", "http-client-swap", "http-client-small"
GOOD_SWAP = (RULES / RULE / "cases" / SWAP / "samples" / "good.md").read_text(encoding="utf-8")


class HttpClientSwapTests(unittest.TestCase):
    def test_plan_ending_in_deletion_passes(self):
        self.assertEqual(grade(RULE, SWAP, "good.md"), [])

    def test_old_and_new_left_side_by_side_fails(self):
        self.assertEqual(
            grade(RULE, SWAP, "bad.md"),
            ["final PR in the plan does not delete httpclient", "plan never deletes app/http_v2.py"],
        )

    def test_interface_kept_after_the_swap_fails(self):
        kept = GOOD_SWAP.replace(" and delete `app/api.py`, since one implementation remains", "")
        self.assertNotEqual(kept, GOOD_SWAP)
        self.assertEqual(grade(RULE, SWAP, text=kept), ["plan never deletes app/api.py"])

    def test_one_pr_plan_fails(self):
        start, end = GOOD_SWAP.index("<plan>"), GOOD_SWAP.index("</plan>")
        single = GOOD_SWAP[:start] + "<plan>\n1. Move every caller and delete `app/httpclient.py`.\n" + GOOD_SWAP[end:]
        self.assertEqual(grade(RULE, SWAP, text=single), ["plan has 1 PR(s)"])

    def test_red_commit_fails(self):
        broken = GOOD_SWAP.replace("return httpclient.post_json(path, body)", "return None")
        self.assertEqual(
            grade(RULE, SWAP, text=broken),
            ["suite fails after commit 2 ('Move billing callers to app.api')"],
        )


class HttpClientSmallTests(unittest.TestCase):
    def test_one_change_that_deletes_httpclient_passes(self):
        self.assertEqual(grade(RULE, SMALL, "good.md"), [])

    def test_interface_in_front_of_httpclient_fails(self):
        self.assertEqual(
            grade(RULE, SMALL, "bad.md"),
            [
                "app/httpclient.py still exists",
                "app/api.py still imports app.httpclient",
                "adds module app/api.py between the callers and platform_http",
                "no module uses platform_http",
            ],
        )


if __name__ == "__main__":
    unittest.main()
