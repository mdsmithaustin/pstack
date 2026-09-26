import json
import sys
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import review_cases  # noqa: E402
import screen  # noqa: E402
import workspace  # noqa: E402
from shared import review_names  # noqa: E402

CASE_COUNT = 8


def mirror_has(spec):
    return workspace.has_commit(workspace.mirror_path(spec["workspace"]["repo"]), spec["workspace"]["commit"])


class ReviewCaseTests(unittest.TestCase):
    def test_the_repository_ships_all_eight_review_cases(self):
        self.assertEqual(len(review_cases.review_cases()), CASE_COUNT)

    def test_every_review_case_is_well_formed_and_blind(self):
        for name, root, spec in review_cases.review_cases():
            with self.subTest(case=name):
                self.assertEqual(review_cases.shape_problems(name.split("/")[0], root, spec), [])

    def test_samples_that_name_the_location_pass_the_precheck(self):
        for name, root, _ in review_cases.review_cases():
            with self.subTest(case=name):
                self.assertEqual(review_cases.precheck_problems(name.split("/")[0], root), [])

    def test_the_pull_request_applies_and_stays_reviewable_in_size(self):
        mirrored = [(name, root, spec) for name, root, spec in review_cases.review_cases() if mirror_has(spec)]
        if not mirrored:
            self.skipTest("no review case has a local workspace mirror")
        for name, root, spec in mirrored:
            with self.subTest(case=name), tempfile.TemporaryDirectory() as directory:
                lines, _ = review_cases.size(Path(directory) / "repo", *review_cases.build(root, spec, Path(directory) / "repo"))
                self.assertTrue(review_cases.MIN_LINES <= lines <= review_cases.MAX_LINES, f"{lines} changed lines")

    def test_a_case_missing_its_review_block_fails_shape(self):
        with tempfile.TemporaryDirectory() as directory:
            problems = review_cases.shape_problems("scratch-rule", Path(directory), {"kind": "positive"})
        self.assertEqual(problems, ["review must have exactly ['body_file', 'branch', 'patch', 'title'], not None"])

    def test_a_sample_that_never_names_the_symbol_fails_the_precheck(self):
        rule = f"scratch-{uuid.uuid4().hex}"
        with tempfile.TemporaryDirectory() as directory:
            rules_root = Path(directory) / "rules"
            case_root = rules_root / rule / "cases" / "widget-review"
            (case_root / "samples").mkdir(parents=True)
            (rules_root / rule / "oracle.py").write_text(
                'CHECKS = {"widget-review": lambda answer, project: '
                '[] if "apply_discount" in answer else '
                '["the review does not name the file or symbol under review"]}\n'
            )
            (case_root / "samples" / "review-bad.md").write_text("LGTM")
            (case_root / "samples" / "labels.json").write_text(json.dumps({"review-bad.md": "FOUND"}))
            with mock.patch.object(screen, "RULES", rules_root):
                problems = review_cases.precheck_problems(rule, case_root)
        self.assertEqual(problems, ["the precheck fails review-bad.md (FOUND): ['the review does not name the file or symbol under review']"])


class ReviewNamesTests(unittest.TestCase):
    def test_a_review_that_names_the_symbol_passes(self):
        self.assertEqual(review_names("`_parse_tag_filter` should say label.", (r"_parse_tag_filter",)), [])

    def test_a_review_that_never_names_it_fails(self):
        self.assertEqual(review_names("LGTM", (r"_parse_tag_filter",)), ["the review does not name the file or symbol under review"])


if __name__ == "__main__":
    unittest.main()
