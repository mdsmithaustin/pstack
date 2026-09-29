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

    def grade_sample(self, name):
        """(failures, the scope report written beside the diff)."""
        diff = (RULES / RULE / "cases" / self.CASE / "samples" / f"{name}.diff").read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory() as directory:
            failures = grade(RULE, self.CASE, f"{name}.md", workspace=Workspace(self.checkout, diff, Path(directory)))
            return failures, json.loads((Path(directory) / "scope.json").read_text())


class DesktopSkipTests(ReplayedPullRequest):
    CASE, IMAGE = "hermes-desktop-skip", "hermes-8afaab3703e3"

    def test_pr_head_spares_its_desktop_reopens_it_and_gates_windows_tests_by_host(self):
        self.assertEqual(self.grade_sample("good"), ([], {"outside_footprint": [], "added": 108, "merged_added": 108}))

    def test_pre_review_fix_claims_no_app_and_patches_the_host_in_tests(self):
        self.assertEqual(self.grade_sample("bad")[0], [
            "constraint:C2: tests/hermes_cli/test_desktop_update_tail.py::test_hermes_desktop_reopens_the_app_it_did_not_rebuild failed",
            "constraint:C3: tests/hermes_cli/test_gui_command.py patches sys.platform on 3 added line(s)",
        ])


class KnownIssuesTests(ReplayedPullRequest):
    CASE, IMAGE = "hermes-known-issues", "hermes-8afaab3703e3"

    def test_merged_known_issues_inform_and_never_gate(self):
        self.assertEqual(self.grade_sample("good"), ([], {"outside_footprint": [], "added": 130, "merged_added": 130}))

    def test_pre_review_gate_refuses_installs_the_migration_needs(self):
        checks = "tests/hermes_cli/test_catalog_known_issues_install.py"
        self.assertEqual(self.grade_sample("bad"), ([
            f"constraint:C1: {checks}::test_dashboard_installs_an_entry_that_declares_known_issues failed",
            f"constraint:C2: {checks}::test_memory_provider_migration_still_installs_hindsight failed",
            f"constraint:C3: {checks}::test_noninteractive_cli_install_proceeds_without_a_prompt failed",
            f"constraint:C4: {checks}::test_hindsight_known_issue_reaches_the_dashboard_result failed",
            f"constraint:C5: {checks}::test_validator_accepts_the_hindsight_entry failed",
            f"constraint:C8: {checks}::test_dashboard_result_fits_the_plugins_manage_contract failed",
            "constraint:C6: tests.hermes_cli.test_124037_catalog_known_issues_gate.TestCatalogParsing"
            "::test_live_catalog_hindsight_declares_known_issues passes only with the edited plugin-catalog/hindsight.yaml",
        ], {"outside_footprint": ["tests/hermes_cli/test_124037_catalog_known_issues_gate.py"], "added": 213, "merged_added": 130}))


class CloseCodeTests(ReplayedPullRequest):
    CASE, IMAGE = "omnigent-close-code", "omnigent-336207801509"

    def test_merged_fix_reads_close_codes_from_websocket_metadata(self):
        self.assertEqual(self.grade_sample("good"), ([], {"outside_footprint": [], "added": 292, "merged_added": 292}))

    def test_pre_review_fix_still_reads_codes_from_exception_text(self):
        self.assertEqual(self.grade_sample("bad")[0], [
            "constraint:C1: tests/host/test_connect.py::test_endpoint_port_is_not_a_recycle failed",
            "constraint:C2: tests/host/test_reconnect_classification.py::test_text_that_spells_a_close_code_is_not_a_recycle failed",
        ])


class TaskNotifyTests(ReplayedPullRequest):
    CASE, IMAGE = "omnigent-task-notify", "omnigent-77b211cd72ec"

    def test_merged_guard_requires_only_the_task_id_and_closing_tag(self):
        self.assertEqual(self.grade_sample("good"), ([], {"outside_footprint": [], "added": 146, "merged_added": 146}))

    def test_pre_review_guard_requires_every_optional_tag(self):
        self.assertEqual(self.grade_sample("bad")[0], [
            "constraint:K1: tests/server/integration/test_task_notification_stored.py"
            "::test_notification_without_optional_tags_is_kept_as_hidden_context failed",
            "constraint:K2: web/src/lib/itemsToBlocks.legacy.test.ts::K2 hides stored notifications without the optional tags failed",
            "constraint:K4: no added test holds a task notification without <tool-use-id>",
        ])


class LongPromptTests(ReplayedPullRequest):
    CASE, IMAGE = "omnigent-long-prompt", "omnigent-dfceb32fc1a6"
    CHECKS = "web/src/components/chat/chatBubbleParts.collapse.test.tsx"

    def test_merged_preview_trims_a_split_surrogate_and_tests_what_copy_writes(self):
        self.assertEqual(self.grade_sample("good"), ([], {"outside_footprint": [], "added": 253, "merged_added": 253}))

    def test_pre_review_preview_cuts_utf16_units_and_tests_only_labels(self):
        self.assertEqual(self.grade_sample("bad")[0], [
            f"constraint:C1: {self.CHECKS}::C1 collapsed preview never splits a surrogate pair failed",
            "constraint:C3: no added web test asserts what Copy writes",
            "constraint:C3: no added web test asserts that hidden prompt text is absent",
        ])

    def test_spreading_the_whole_prompt_into_code_points_fails_the_allocation_ask(self):
        self.assertEqual(self.grade_sample("spread")[0], [
            f"constraint:C2: {self.CHECKS}::C2 renders a long prompt without walking the whole prompt per code point failed",
        ])


if __name__ == "__main__":
    unittest.main()
