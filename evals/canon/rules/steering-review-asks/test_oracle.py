import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from check import RULES, grade, load_oracle
from shared import PROJECT_IMAGES, Workspace

sys.path.insert(0, str(RULES.parent))
import workspace  # noqa: E402

RULE = "steering-review-asks"


def oracle():
    load_oracle(RULE)
    return sys.modules[f"canon_oracle_{RULE}"]


def image_built(name):
    images = json.loads(PROJECT_IMAGES.read_text()) if PROJECT_IMAGES.is_file() else {}
    try:
        return name in images and subprocess.run(["docker", "image", "inspect", images[name]["id"]],
                                                 capture_output=True, timeout=60, check=False).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


class SkippedGraderTests(unittest.TestCase):
    """A grader-owned test that an agent-side conftest or marker skips never ran,
    so its dimension must fail instead of passing."""

    def graded(self, results):
        module = oracle()
        with tempfile.TemporaryDirectory() as directory, mock.patch.object(module, "project_test_results", return_value=results):
            return module.graded(Workspace(Path(directory), "", None), "image", {}, {
                "tests/test_x.py::test_a": "functional", "tests/test_x.py::test_b": "constraint:C2",
            }, {})

    def test_a_skipped_parameter_fails_its_dimension_and_says_why(self):
        self.assertEqual(self.graded({
            "tests.test_x::test_a[1]": "passed", "tests.test_x::test_a[2]": "skipped", "tests.test_x::test_b": "passed",
        }), ["functional: tests/test_x.py::test_a skipped (a skipped grader-owned test never ran)"])

    def test_a_failed_parameter_outranks_a_skipped_one(self):
        self.assertEqual(self.graded({
            "tests.test_x::test_a": "passed", "tests.test_x::test_b[1]": "skipped", "tests.test_x::test_b[2]": "failed",
        }), ["constraint:C2: tests/test_x.py::test_b failed"])


class CopyAssertionTests(unittest.TestCase):
    """C3 wants an assertion on what Copy writes, not a mention of the clipboard."""
    BUBBLE = ["expect(bubble).not.toHaveTextContent(TAIL);", "expect(bubble).toHaveTextContent(HEAD);"]

    def failures(self, *lines):
        return oracle().tests_assert_hidden_text_and_copy({"web/src/chat.test.tsx": [*self.BUBBLE, *lines]})

    def test_a_clipboard_stub_with_no_expectation_asserts_nothing(self):
        self.assertEqual(self.failures(
            "const writeText = vi.fn();",
            'vi.stubGlobal("navigator", { clipboard: { writeText } });',
            'fireEvent.click(screen.getByRole("button", { name: /^copy$/i }));',
        ), ["constraint:C3: no added web test asserts what Copy writes"])

    def test_a_bare_called_check_does_not_assert_the_copied_value(self):
        self.assertEqual(self.failures(
            "const writeText = vi.fn();",
            "expect(writeText).toHaveBeenCalled();",
            "expect(writeText).toHaveBeenCalledTimes(1);",
        ), ["constraint:C3: no added web test asserts what Copy writes"])

    def test_a_spy_asserted_with_the_payload_counts(self):
        self.assertEqual(self.failures("const writeText = vi.fn();", "expect(writeText).toHaveBeenCalledWith(LONG_TEXT);"), [])

    def test_a_spy_call_argument_compared_to_the_prompt_counts(self):
        self.assertEqual(self.failures("expect(navigator.clipboard.writeText.mock.calls[0][0]).toBe(LONG_TEXT);"), [])

    def test_a_payload_captured_by_the_stub_and_compared_counts(self):
        self.assertEqual(self.failures(
            "const written: string[] = [];",
            "vi.stubGlobal(\"navigator\", { clipboard: { writeText: vi.fn((text: string) => {",
            "  written.push(text);",
            "  return Promise.resolve();",
            "}) } });",
            "expect(written[0]).toBe(LONG_TEXT);",
        ), [])

    def test_a_captured_payload_that_is_never_compared_does_not_count(self):
        self.assertEqual(self.failures(
            "const written: string[] = [];",
            "vi.stubGlobal(\"navigator\", { clipboard: { writeText: vi.fn((text: string) => {",
            "  written.push(text);",
            "}) } });",
            "expect(bubble).toBeDefined();",
        ), ["constraint:C3: no added web test asserts what Copy writes"])


class KnownIssueProseTests(unittest.TestCase):
    """prose() runs inside the container, so the test compiles its source out of the oracle."""

    @classmethod
    def setUpClass(cls):
        source = oracle().KNOWN_ISSUES_CHECKS
        namespace = {"dataclasses": __import__("dataclasses")}
        exec(source[source.index("def prose("):source.index("class Installs")], namespace)
        cls.prose = staticmethod(namespace["prose"])

    def test_a_short_top_level_string_is_one_sentence(self):
        self.assertEqual(self.prose("Local  embedded\nunsupported."), ["Local embedded unsupported."])

    def test_a_blank_top_level_string_is_no_sentence(self):
        self.assertEqual(self.prose("  \n"), [])

    def test_a_structured_record_keeps_prose_and_drops_short_metadata(self):
        self.assertEqual(self.prose({"kind": "embedded", "severity": "high", "summary": "Embedded mode loops on this pin."}),
                         ["Embedded mode loops on this pin."])


class WindowsTestTests(unittest.TestCase):
    """C3: Windows behaviour gets a @pytest.mark.platforms("windows") test and no sys.platform patch."""
    FILE = "tests/hermes_cli/test_gui_command.py"
    NO_MARK = 'constraint:C3: no added test is marked @pytest.mark.platforms("windows")'

    def failures(self, *lines, path=FILE):
        return oracle().tests_never_patch_the_host({path: list(lines)})

    def test_a_diff_with_no_windows_marked_test_fails(self):
        self.assertEqual(self.failures("def test_posix_swap(tmp_path):", "    assert True"), [self.NO_MARK])

    def test_an_unmarked_windows_only_test_fails(self):
        self.assertEqual(self.failures("def test_windows_stop_spares_the_desktop(tmp_path):", "    assert _stop() == [300]"),
                         [self.NO_MARK])

    def test_a_marked_windows_test_passes(self):
        self.assertEqual(self.failures('@pytest.mark.platforms("windows")', "def test_windows_stop(tmp_path):", "    pass"), [])

    def test_a_windows_mark_beside_other_hosts_passes(self):
        self.assertEqual(self.failures("@pytest.mark.platforms('posix', 'windows')", "def test_stop(tmp_path):", "    pass"), [])

    def test_a_mark_outside_a_test_file_does_not_count(self):
        self.assertEqual(self.failures('@pytest.mark.platforms("windows")', path="hermes_cli/main_desktop.py"), [self.NO_MARK])

    def test_a_multiline_platform_patch_is_caught(self):
        self.assertEqual(self.failures(
            '@pytest.mark.platforms("windows")',
            "def test_stop(monkeypatch):",
            "    monkeypatch.setattr(",
            "        sys,",
            '        "platform",',
            '        "win32",',
            "    )",
        ), [f"constraint:C3: {self.FILE} patches sys.platform on 1 added line(s)"])

    def test_a_string_target_platform_patch_is_caught(self):
        self.assertEqual(self.failures(
            '@pytest.mark.platforms("windows")',
            'monkeypatch.setattr("sys.platform", "win32")',
        ), [f"constraint:C3: {self.FILE} patches sys.platform on 1 added line(s)"])

    def test_a_multiline_string_target_platform_patch_is_caught(self):
        self.assertEqual(self.failures(
            '@pytest.mark.platforms("windows")',
            "monkeypatch.setattr(",
            "    'sys.platform',",
            '    "win32",',
            "    raising=False,",
            ")",
        ), [f"constraint:C3: {self.FILE} patches sys.platform on 1 added line(s)"])

    def test_a_single_line_platform_patch_is_still_caught(self):
        self.assertEqual(self.failures(
            '@pytest.mark.platforms("windows")',
            'monkeypatch.setattr(main_desktop.sys, "platform", "win32")',
        ), [f"constraint:C3: {self.FILE} patches sys.platform on 1 added line(s)"])

    def test_a_module_qualified_platform_patch_is_caught(self):
        for patch in ('patch("hermes_cli.main_desktop.sys.platform", "win32")',
                      "monkeypatch.setattr('hermes_cli.main_desktop.sys.platform', 'win32')",
                      'mock.patch.object(main_desktop.sys, "platform", "win32")'):
            with self.subTest(patch):
                self.assertEqual(self.failures('@pytest.mark.platforms("windows")', patch),
                                 [f"constraint:C3: {self.FILE} patches sys.platform on 1 added line(s)"])


def new_file(path, content):
    """(diff, files) for a file that a diff adds whole."""
    lines = content.split("\n")
    diff = (f"diff --git a/{path} b/{path}\nnew file mode 100644\n--- /dev/null\n+++ b/{path}\n@@ -0,0 +1,{len(lines)} @@\n"
            + "".join(f"+{line}\n" for line in lines))
    return diff, {path: content.encode()}


class ExecutableOnlyTests(unittest.TestCase):
    """A static check credits executable code only, never a comment or a docstring."""
    PY = "tests/server/test_x.py"
    TS = "web/src/chat.test.tsx"
    FIXTURE = "<task-notification><task-id>x</task-id></task-notification>"
    K4 = ["constraint:K4: no added test holds a task notification without <tool-use-id>"]
    NO_MARK = 'constraint:C3: no added test is marked @pytest.mark.platforms("windows")'

    def run_static(self, name, path, content):
        module = oracle()
        return getattr(module, name)(module.executable_added(*new_file(path, content)))

    def test_executable_added_blanks_python_comments_and_docstrings_and_keeps_line_count(self):
        content = '"""module doc"""\nx = 1  # trailing\ndef f():\n    """doc\n    more"""\n    "bare"\n    return "kept # not a comment"\n# whole line'
        diff, files = new_file(self.PY, content)
        self.assertEqual([line.rstrip() for line in oracle().executable_added(diff, files)[self.PY]],
                         ["", "x = 1", "def f():", "", "", "", '    return "kept # not a comment"', ""])

    def test_executable_added_blanks_js_comments_and_keeps_string_slashes(self):
        content = 'const a = "http://x"; // tail\n/* block\n   more */\nconst b = `//t`;'
        diff, files = new_file(self.TS, content)
        self.assertEqual([line.rstrip() for line in oracle().executable_added(diff, files)[self.TS]],
                         ['const a = "http://x";', "", "", "const b = `//t`;"])

    def test_k4_ignores_a_fixture_in_a_comment(self):
        self.assertEqual(self.run_static("adds_minimal_fixture", self.PY, f"# {self.FIXTURE}"), self.K4)

    def test_k4_ignores_a_fixture_in_a_docstring_or_bare_string(self):
        self.assertEqual(self.run_static("adds_minimal_fixture", self.PY, f'def test_a():\n    """{self.FIXTURE}"""'), self.K4)
        self.assertEqual(self.run_static("adds_minimal_fixture", self.PY, f'"{self.FIXTURE}"'), self.K4)

    def test_k4_accepts_a_fixture_in_a_string_literal(self):
        self.assertEqual(self.run_static("adds_minimal_fixture", self.PY, f'NOTE = "{self.FIXTURE}"'), [])

    def test_a_platform_patch_in_a_comment_or_docstring_is_not_a_patch(self):
        content = ('@pytest.mark.platforms("windows")\ndef test_a(monkeypatch):\n    """monkeypatch.setattr(sys, \'platform\', \'win32\')"""\n'
                   '    # monkeypatch.setattr("sys.platform", "win32")')
        self.assertEqual(self.run_static("tests_never_patch_the_host", self.PY, content), [])

    def test_a_windows_mark_in_a_comment_or_docstring_is_not_a_mark(self):
        self.assertEqual(self.run_static("tests_never_patch_the_host", self.PY, '# @pytest.mark.platforms("windows")'), [self.NO_MARK])
        self.assertEqual(self.run_static("tests_never_patch_the_host", self.PY,
                                         'def test_a():\n    """@pytest.mark.platforms("windows")"""'), [self.NO_MARK])

    def test_hidden_text_and_copy_assertions_in_js_comments_do_not_count(self):
        content = ("// expect(writeText).toHaveBeenCalledWith(LONG_TEXT);\n"
                   "/* expect(bubble).not.toHaveTextContent(TAIL);\n   expect(bubble).toHaveTextContent(HEAD); */")
        self.assertEqual(self.run_static("tests_assert_hidden_text_and_copy", self.TS, content), [
            "constraint:C3: no added web test asserts what Copy writes",
            "constraint:C3: no added web test asserts that hidden prompt text is absent",
            "constraint:C3: no added web test asserts that prompt text is present",
        ])

    def test_hidden_text_and_copy_assertions_in_code_still_count(self):
        content = ("expect(writeText).toHaveBeenCalledWith(LONG_TEXT);\n"
                   "expect(bubble).not.toHaveTextContent(TAIL);\nexpect(bubble).toHaveTextContent(HEAD);")
        self.assertEqual(self.run_static("tests_assert_hidden_text_and_copy", self.TS, content), [])


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

    def grade_sample(self, name, edit=lambda diff: diff):
        """(failures, the scope report written beside the diff), over the sample's diff passed through edit."""
        diff = edit((RULES / RULE / "cases" / self.CASE / "samples" / f"{name}.diff").read_text(encoding="utf-8"))
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
            'constraint:C3: no added test is marked @pytest.mark.platforms("windows")',
        ])


    def test_an_unparseable_extra_test_file_cannot_hide_a_platform_patch(self):
        extra = "tests/hermes_cli/test_extra.py"
        broken = f'def test_x(:\n    # a comment\n    monkeypatch.setattr(sys, "platform", "win32")'
        self.assertEqual(self.grade_sample("good", lambda diff: diff + new_file(extra, broken)[0])[0], [
            f"constraint:C3: {extra} patches sys.platform on 1 added line(s)",
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


    def test_weakening_the_generated_files_test_does_not_hide_stale_contracts(self):
        weakened = (
            "diff --git a/tests/tui_gateway/contracts/test_generated.py b/tests/tui_gateway/contracts/test_generated.py\n"
            "--- a/tests/tui_gateway/contracts/test_generated.py\n"
            "+++ b/tests/tui_gateway/contracts/test_generated.py\n"
            "@@ -30,7 +30,7 @@\n"
            '     """Both committed artefacts equal an in-memory regeneration (byte-for-byte)."""\n'
            "     stale = [path.relative_to(REPO) for path, text in gen.render_all().items()\n"
            '              if (path.read_text(encoding="utf-8") if path.exists() else None) != text]\n'
            '-    assert not stale, f"stale generated contract files {stale}: run scripts/gen_gateway_contracts.py"\n'
            "+    assert True\n"
            " \n"
            " \n"
            " # The emitter inventory the old gateway-events.json scan used, kept as the completeness oracle:\n")

        def edit(diff):
            sections = re.split(r"(?m)^(?=diff --git )", diff)
            return "".join(section for section in sections if "gateway-contract" not in section.split("\n", 1)[0]) + weakened

        self.assertEqual(self.grade_sample("good", edit)[0], [
            "constraint:C8: tests/tui_gateway/contracts/test_generated.py::test_generated_files_are_current failed",
        ])


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


    def test_a_route_that_marks_every_external_user_message_meta_hides_a_real_question(self):
        route_marks_all = (
            "@@ -4917,6 +4917,8 @@\n"
            "     :returns: Store-assigned conversation item id.\n"
            '     """\n'
            "     item = _parse_external_conversation_item(body)\n"
            '+    if item.type == "message" and isinstance(item.data, MessageData) and item.data.role == "user":\n'
            "+        item.data.is_meta = True\n"
            "     # A native user message round-tripping back from the transcript:\n"
            "     # drain its optimistic pending-input entry (FIFO) and fold the\n"
            "     # entry's file blocks (image / file) into the item BEFORE persisting.\n"
            "@@ -8439,6 +8441,8 @@")
        failures = self.grade_sample("good", lambda diff: diff.replace("@@ -8439,6 +8439,8 @@", route_marks_all, 1))[0]
        self.assertEqual(failures, [
            "constraint:K3: tests/server/integration/test_task_notification_stored.py"
            "::test_stored_user_message_that_only_opens_with_the_tag_is_not_meta failed",
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
