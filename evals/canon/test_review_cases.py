import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import review_cases  # noqa: E402
import workspace  # noqa: E402
from shared import review_names  # noqa: E402

CASES = review_cases.review_cases()


def mirror_has(spec):
    return workspace.has_commit(workspace.mirror_path(spec["workspace"]["repo"]), spec["workspace"]["commit"])


class ReviewCaseTests(unittest.TestCase):
    def test_every_review_case_is_well_formed_and_blind(self):
        for name, root, spec in CASES:
            with self.subTest(case=name):
                self.assertEqual(review_cases.shape_problems(name.split("/")[0], root, spec), [])

    def test_samples_that_name_the_location_pass_the_precheck(self):
        for name, root, _ in CASES:
            with self.subTest(case=name):
                self.assertEqual(review_cases.precheck_problems(name.split("/")[0], root), [])

    def test_the_pull_request_applies_and_stays_reviewable_in_size(self):
        for name, root, spec in CASES:
            if not mirror_has(spec):
                continue
            with self.subTest(case=name), tempfile.TemporaryDirectory() as directory:
                lines, _ = review_cases.size(Path(directory) / "repo", *review_cases.build(root, spec, Path(directory) / "repo"))
                self.assertTrue(review_cases.MIN_LINES <= lines <= review_cases.MAX_LINES, f"{lines} changed lines")


class ReviewNamesTests(unittest.TestCase):
    def test_a_review_that_names_the_symbol_passes(self):
        self.assertEqual(review_names("`_parse_tag_filter` should say label.", (r"_parse_tag_filter",)), [])

    def test_a_review_that_never_names_it_fails(self):
        self.assertEqual(review_names("LGTM", (r"_parse_tag_filter",)), ["the review does not name the file or symbol under review"])


if __name__ == "__main__":
    unittest.main()
