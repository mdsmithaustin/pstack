import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from check import RULES, grade
from shared import PROJECT_IMAGES, Workspace

sys.path.insert(0, str(RULES.parent))
import workspace  # noqa: E402

RULE = "steering-review-asks"


def image_built(name):
    images = json.loads(PROJECT_IMAGES.read_text()) if PROJECT_IMAGES.is_file() else {}
    try:
        return name in images and subprocess.run(["docker", "image", "inspect", images[name]["id"]],
                                                 capture_output=True, timeout=60, check=False).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


class ReplayedPullRequest(unittest.TestCase):
    """Grades one case's samples on its pinned checkout in its dependency image."""
    CASE = IMAGE = None

    @classmethod
    def setUpClass(cls):
        root = RULES / RULE / "cases" / cls.CASE
        spec = workspace.parse_spec(root, json.loads((root / "case.json").read_text())["workspace"])
        if not workspace.has_commit(workspace.mirror_path(spec.repo), spec.commit):
            raise unittest.SkipTest(f"needs {spec.repo} {spec.commit}; run workspace.py fetch {spec.repo} {spec.commit}")
        if not image_built(cls.IMAGE):
            raise unittest.SkipTest(f"needs the {cls.IMAGE} image; build it with images/build.py")
        cls.checkout = workspace.reference_checkout(spec)[0]

    def grade_sample(self, name, harvest=None):
        diff = (RULES / RULE / "cases" / self.CASE / "samples" / f"{name}.diff").read_text(encoding="utf-8")
        return grade(RULE, self.CASE, f"{name}.md", workspace=Workspace(self.checkout, diff, harvest))

    def scope_of(self, name):
        with tempfile.TemporaryDirectory() as directory:
            self.grade_sample(name, Path(directory))
            return json.loads((Path(directory) / "scope.json").read_text())


class CloseCodeTests(ReplayedPullRequest):
    CASE, IMAGE = "omnigent-close-code", "omnigent-336207801509"

    def test_merged_fix_reads_close_codes_from_websocket_metadata(self):
        self.assertEqual(self.grade_sample("good"), [])

    def test_pre_review_fix_still_reads_codes_from_exception_text(self):
        self.assertEqual(self.grade_sample("bad"), [
            "constraint:C1: tests/host/test_connect.py::test_endpoint_port_is_not_a_recycle failed",
            "constraint:C2: tests/host/test_reconnect_classification.py::test_text_that_spells_a_close_code_is_not_a_recycle failed",
        ])

    def test_scope_is_reported_beside_the_diff_and_never_fails(self):
        self.assertEqual(self.scope_of("bad"), {"outside_footprint": [], "added": 272, "merged_added": 292})


class TaskNotifyTests(ReplayedPullRequest):
    CASE, IMAGE = "omnigent-task-notify", "omnigent-77b211cd72ec"

    def test_merged_guard_requires_only_the_task_id_and_closing_tag(self):
        self.assertEqual(self.grade_sample("good"), [])

    def test_pre_review_guard_requires_every_optional_tag(self):
        self.assertEqual(self.grade_sample("bad"), [
            "constraint:K1: tests/test_task_notification_context.py::test_notification_without_optional_tags_is_kept_as_hidden_context failed",
            "constraint:K2: web/src/lib/itemsToBlocks.legacy.test.ts::K2 hides stored notifications without the optional tags failed",
            "constraint:K4: no added test holds a task notification without <tool-use-id>",
        ])


class LongPromptTests(ReplayedPullRequest):
    CASE, IMAGE = "omnigent-long-prompt", "omnigent-dfceb32fc1a6"

    def test_merged_preview_trims_a_split_surrogate_and_tests_what_copy_writes(self):
        self.assertEqual(self.grade_sample("good"), [])

    def test_pre_review_preview_cuts_utf16_units_and_tests_only_labels(self):
        self.assertEqual(self.grade_sample("bad"), [
            "constraint:C1: web/src/components/chat/chatBubbleParts.collapse.test.tsx::C1 collapsed preview never splits a surrogate pair failed",
            "constraint:C3: no added web test asserts what Copy writes",
            "constraint:C3: no added web test asserts that hidden prompt text is absent",
        ])

    def test_spreading_the_whole_prompt_into_code_points_fails_the_allocation_ask(self):
        self.assertEqual(self.grade_sample("spread"), [
            "constraint:C2: web/src/components/chat/chatBubbleParts.collapse.test.tsx::C2 renders a long prompt without walking "
            "the whole prompt per code point failed",
        ])


if __name__ == "__main__":
    unittest.main()
