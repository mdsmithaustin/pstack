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
    BUBBLE = ["expect(bubble).not.toHaveTextContent(TAIL);", "expect(bubble).toHaveTextContent(TAIL);"]

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

    def test_a_called_with_check_that_passes_no_payload_does_not_count(self):
        for check in ("expect(writeText).toHaveBeenCalledWith();", "expect(navigator.clipboard.writeText).toHaveBeenCalledWith( );"):
            with self.subTest(check):
                self.assertEqual(self.failures("const writeText = vi.fn();", check),
                                 ["constraint:C3: no added web test asserts what Copy writes"])

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

    TRUNK_CREDITED_CAPTURES = (
        ("const writeText = vi.fn(); writeText.mockImplementation(async (t: string) => { written = t; });", "expect(written).toBe(LONG_TEXT);"),
        ("vi.mocked(navigator.clipboard.writeText).mockImplementation(async (t) => { written = t })", "expect(written).toBe(LONG_TEXT);"),
        ('vi.spyOn(navigator.clipboard, "writeText").mockImplementationOnce(async (t) => { written = t; });', "expect(written).toBe(LONG_TEXT);"),
        ("Object.assign(navigator, { clipboard: { writeText: vi.fn<(text: string) => Promise<void>>(async (t) => { written = t }) } });",
         "expect(written).toBe(LONG_TEXT);"),
        ("Object.assign(navigator, { clipboard: { writeText: vi.fn(async text => { written = text }) } });", "expect(written).toBe(LONG_TEXT);"),
        ('vi.spyOn(navigator.clipboard, "writeText").mockImplementation(text => { written = text })', "expect(written).toBe(LONG_TEXT);"),
        ("Object.assign(navigator, { clipboard: { writeText: vi.fn(async (t: string): Promise<void> => { written = t }) } });",
         "expect(written).toBe(LONG_TEXT);"),
        ("Object.assign(navigator, { clipboard: { writeText: vi.fn((t) => (written = t)) } });", "expect(written).toBe(LONG_TEXT);"),
        ("Object.assign(navigator, { clipboard: { writeText: vi.fn(text => written.push(text)) } });", "expect(written).toEqual([LONG_TEXT]);"),
        ("vi.spyOn(navigator.clipboard, 'writeText').mockImplementation(t => { written.push(t); return Promise.resolve(); });",
         "expect(written).toEqual([LONG_TEXT]);"),
        ("Object.assign(navigator, { clipboard: { writeText: vi.fn().mockImplementation(async (text: string) => { written = text; }) } });",
         "expect(written).toBe(LONG_TEXT);"),
        ('vi.spyOn(navigator.clipboard, "writeText").mockImplementation(async (text) => { written = text })', "expect(written).toBe(LONG_TEXT);"),
        ('vi.stubGlobal("navigator", { clipboard: { writeText: vi.fn((t) => Promise.resolve(written.push(t))) } });',
         "expect(written).toEqual([LONG_TEXT]);"),
        ('vi.stubGlobal("navigator", { clipboard: { writeText: vi.fn(async (text: string) => void written.push(text)) } });',
         "expect(written).toEqual([LONG_TEXT]);"),
    )

    def test_every_payload_capture_trunk_credits_still_counts(self):
        for stub, compared in self.TRUNK_CREDITED_CAPTURES:
            with self.subTest(stub):
                self.assertEqual(self.failures(stub, compared), [])

    def test_a_captured_payload_that_is_never_compared_does_not_count(self):
        self.assertEqual(self.failures(
            "const written: string[] = [];",
            "vi.stubGlobal(\"navigator\", { clipboard: { writeText: vi.fn((text: string) => {",
            "  written.push(text);",
            "}) } });",
            "expect(bubble).toBeDefined();",
        ), ["constraint:C3: no added web test asserts what Copy writes"])

    def test_a_spy_installed_under_another_name_and_asserted_with_the_payload_counts(self):
        self.assertEqual(self.failures(
            "const spy = vi.fn();",
            "Object.assign(navigator, { clipboard: { writeText: spy } });",
            "expect(spy).toHaveBeenCalledWith(LONG_TEXT);",
        ), [])

    def test_a_named_spy_on_writetext_asserted_with_the_payload_counts(self):
        self.assertEqual(self.failures(
            'const copied = vi.spyOn(navigator.clipboard, "writeText");',
            "expect(copied).toHaveBeenLastCalledWith(LONG_TEXT);",
        ), [])

    def test_a_writetext_spy_outside_the_clipboard_does_not_count(self):
        self.assertEqual(self.failures(
            "const spy = vi.fn();",
            "const editor = { writeText: spy };",
            "expect(spy).toHaveBeenCalledWith(LONG_TEXT);",
        ), ["constraint:C3: no added web test asserts what Copy writes"])

    def test_a_writetext_spy_after_an_unrelated_clipboard_mention_does_not_count(self):
        self.assertEqual(self.failures(
            "const clipboard = navigator.clipboard",
            "const editor = { writeText: spy }",
            "expect(spy).toHaveBeenCalledWith(LONG_TEXT)",
        ), ["constraint:C3: no added web test asserts what Copy writes"])

    def test_a_spy_installed_on_the_clipboard_object_counts_in_each_form(self):
        for install in ('Object.defineProperty(navigator, "clipboard", { value: { writeText: spy } });',
                        "Object.assign(navigator.clipboard, { writeText: spy });"):
            with self.subTest(install):
                self.assertEqual(self.failures(install, "expect(spy).toHaveBeenCalledWith(LONG_TEXT);"), [])

    def test_an_identity_check_on_a_clipboard_spy_does_not_assert_the_payload(self):
        self.assertEqual(self.failures(
            'const copied = vi.spyOn(navigator.clipboard, "writeText");',
            "expect(copied).toBe(originalSpy);",
        ), ["constraint:C3: no added web test asserts what Copy writes"])

    def test_an_identity_check_on_the_writetext_spy_itself_does_not_count(self):
        for check in ("expect(writeText).toBe(originalSpy);", "expect(navigator.clipboard.writeText).toEqual(spy);"):
            with self.subTest(check):
                self.assertEqual(self.failures("const writeText = vi.fn();", check),
                                 ["constraint:C3: no added web test asserts what Copy writes"])

    def test_a_spy_under_a_quoted_writetext_key_counts(self):
        self.assertEqual(self.failures('vi.stubGlobal("navigator", { clipboard: { "writeText": spy } });',
                                       "expect(spy).toHaveBeenCalledWith(LONG_TEXT);"), [])

    def test_a_clipboard_subject_and_a_later_matcher_on_another_assertion_do_not_join(self):
        self.assertEqual(self.failures("const writeText = vi.fn()", "expect(writeText).toBe(originalSpy)",
                                       "expect(unrelated).toHaveBeenCalledWith(LONG_TEXT)"),
                         ["constraint:C3: no added web test asserts what Copy writes"])

    def test_the_text_read_back_from_the_clipboard_counts(self):
        self.assertEqual(self.failures("expect(await navigator.clipboard.readText()).toBe(LONG_TEXT);"), [])

    def test_a_clipboard_spy_call_argument_compared_to_the_prompt_counts(self):
        self.assertEqual(self.failures(
            'const copied = vi.spyOn(navigator.clipboard, "writeText");',
            "expect(copied.mock.calls[0][0]).toBe(LONG_TEXT);",
        ), [])

    def test_a_spy_installed_under_another_name_with_a_bare_called_check_does_not_count(self):
        self.assertEqual(self.failures(
            "const spy = vi.fn();",
            "Object.assign(navigator, { clipboard: { writeText: spy } });",
            "expect(spy).toHaveBeenCalled();",
        ), ["constraint:C3: no added web test asserts what Copy writes"])


class HiddenTailTests(unittest.TestCase):
    """C3 wants the text past the cut asserted absent while collapsed and present
    after, so the absent and present assertions must name the same value."""
    COPY = "expect(writeText).toHaveBeenCalledWith(LONG_TEXT);"
    PRESENT = "constraint:C3: no added web test asserts that hidden prompt text is present"

    def failures(self, *lines):
        return oracle().tests_assert_hidden_text_and_copy({"web/src/chat.test.tsx": [self.COPY, *lines]})

    def test_an_unrelated_present_assertion_does_not_count(self):
        self.assertEqual(self.failures("expect(bubble).not.toHaveTextContent(TAIL);",
                                       "expect(bubble).toHaveTextContent(SHORT_TEXT);"), [self.PRESENT])

    def test_the_copied_payload_holding_the_tail_is_not_the_rendered_text(self):
        self.assertEqual(self.failures(
            "const written: string[] = [];",
            "vi.stubGlobal(\"navigator\", { clipboard: { writeText: vi.fn((text: string) => { written.push(text); }) } });",
            "expect(bubble).not.toHaveTextContent(TAIL);",
            "expect(written[0]).toContain(TAIL);",
        ), [self.PRESENT])

    def test_the_tail_absent_from_the_copied_payload_is_not_hidden_text(self):
        self.assertEqual(self.failures(
            "const written: string[] = [];",
            "vi.stubGlobal(\"navigator\", { clipboard: { writeText: vi.fn((text: string) => { written.push(text); }) } });",
            "expect(written).not.toContain(TAIL);",
            "expect(bubble).toHaveTextContent(TAIL);",
        ), ["constraint:C3: no added web test asserts that hidden prompt text is absent", self.PRESENT])

    def test_a_multiline_assertion_on_the_copied_payload_is_not_the_rendered_text(self):
        stub = ["const written: string[] = [];",
                "vi.stubGlobal(\"navigator\", { clipboard: { writeText: vi.fn((text: string) => { written.push(text); }) } });",
                'it("copies", () => {', "  expect(bubble).not.toHaveTextContent(TAIL);"]
        for copied in (["  expect(written[0])", "    .toContain(TAIL);"], ["  expect(", "    written[0],", "  ).toContain(TAIL);"]):
            with self.subTest(copied):
                self.assertEqual(self.failures(*stub, *copied, "});"), [self.PRESENT])

    def test_a_variable_declared_after_a_semicolonless_spy_is_not_a_clipboard_capture(self):
        self.assertEqual(self.failures("const writeText = vi.fn()", "const bubble = renderPrompt()",
                                       "expect(bubble).not.toHaveTextContent(TAIL)", "expect(bubble).toHaveTextContent(TAIL)"), [])

    def test_a_payload_captured_in_each_stub_form_is_not_the_rendered_text(self):
        for stub, name in (("writeText: vi.fn((text) => written.push(text)) } })", "written"),
                           ("writeText: async function (text) { copied = text } } })", "copied"),
                           ("writeText(text) { written.push(text) } } })", "written")):
            with self.subTest(stub):
                self.assertEqual(self.failures("vi.stubGlobal(\"navigator\", { clipboard: {", stub,
                                               "expect(bubble).not.toHaveTextContent(TAIL)", f"expect({name}).toContain(TAIL)"),
                                 [self.PRESENT])

    def test_an_open_paren_inside_a_string_does_not_join_the_next_assertions(self):
        self.assertEqual(self.failures('expect(bubble).not.toHaveTextContent("tail (end")', 'expect(bubble).toHaveTextContent("tail (end")',
                                       "expect(writeText).toHaveBeenCalledWith(LONG_TEXT)"), [])

    def test_assertions_without_semicolons_still_count(self):
        self.assertEqual(self.failures('it("hides", () => {', "  expect(bubble).not.toHaveTextContent(TAIL)",
                                       "  expect(bubble).toHaveTextContent(TAIL)", "})"), [])

    def test_multiline_assertions_compare_their_values(self):
        absent = ["expect(bubble).not.toHaveTextContent(", "  TAIL,", ");"]
        self.assertEqual(self.failures(*absent, "expect(bubble).toHaveTextContent(", "  SHORT_TEXT,", ");"), [self.PRESENT])
        self.assertEqual(self.failures(*absent, "expect(bubble).toHaveTextContent(", "  TAIL", ");"), [])

    def test_the_same_value_absent_then_present_counts_across_assertion_forms(self):
        for absent, present in (("expect(bubble).not.toHaveTextContent(TAIL);", "expect(bubble).toHaveTextContent( TAIL );"),
                                ("expect(screen.queryByText(TAIL)).toBeNull();", "expect(screen.getByText(TAIL)).toBeTruthy();"),
                                ("expect(bubble).not.toHaveTextContent(TAIL);", "expect(await screen.findByText(TAIL)).toBeInTheDocument();"),
                                ("expect(bubble.textContent).not.toContain(TAIL);", "expect(bubble.textContent).toContain(TAIL);"),
                                ('expect(bubble).not.toHaveTextContent("the end");', "expect(bubble).toHaveTextContent('the end');"),
                                ("expect(bubble).not.toHaveTextContent(/it's the end/);", "expect(bubble).toHaveTextContent(/it's the end/);"),
                                (r'expect(bubble).not.toHaveTextContent("say \"hi\" now");', """expect(bubble).toHaveTextContent('say "hi" now');""")):
            with self.subTest(absent):
                self.assertEqual(self.failures(absent, present), [])


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

    def test_a_record_whose_prose_is_short_prefers_more_words_to_a_longer_label(self):
        self.assertEqual(self.prose({"kind": "unsupported-platform", "summary": "Install loops."}), ["Install loops."])

    def test_a_record_whose_prose_is_short_keeps_its_longest_string(self):
        self.assertEqual(self.prose({"kind": "embedded", "severity": "high", "summary": "Embedded mode loops."}),
                         ["Embedded mode loops."])


class LiveEntryPinTests(unittest.TestCase):
    """C6: the agent's own tests still pass once the edited catalog entry is restored."""
    ENTRY = "plugin-catalog/hindsight.yaml"
    DIFF = (f"diff --git a/{ENTRY} b/{ENTRY}\n--- a/{ENTRY}\n+++ b/{ENTRY}\n@@ -1 +1 @@\n-sha: old\n+sha: new\n"
            "diff --git a/tests/hermes_cli/test_own.py b/tests/hermes_cli/test_own.py\nnew file mode 100644\n"
            "--- /dev/null\n+++ b/tests/hermes_cli/test_own.py\n@@ -0,0 +1 @@\n+def test_a(): pass\n")

    def failures(self, edited, restored):
        module = oracle()
        with tempfile.TemporaryDirectory() as directory, \
                mock.patch.object(module, "project_test_results", side_effect=[edited, restored]):
            (Path(directory) / "plugin-catalog").mkdir()
            (Path(directory) / self.ENTRY).write_text("sha: old\n")
            return module.own_tests_pin_the_live_entry(Workspace(Path(directory), self.DIFF, None))

    def test_a_test_that_skips_once_the_entry_is_restored_fails(self):
        self.assertEqual(self.failures({"tests.hermes_cli.test_own::test_a": "passed"},
                                       {"tests.hermes_cli.test_own::test_a": "skipped"}),
                         [f"constraint:C6: tests.hermes_cli.test_own::test_a skipped with {self.ENTRY} restored"])

    def test_a_failure_under_a_label_the_edited_run_lacks_fails(self):
        self.assertEqual(self.failures({"tests.hermes_cli.test_own::test_a[new]": "passed"},
                                       {"tests.hermes_cli.test_own::test_a[old]": "failed"}),
                         [f"constraint:C6: tests.hermes_cli.test_own::test_a[old] failed with {self.ENTRY} restored"])

    def test_a_collection_error_once_the_entry_is_restored_fails(self):
        self.assertEqual(self.failures({"tests.hermes_cli.test_own::test_a": "passed"},
                                       {"tests.hermes_cli.test_own": "failed"}),
                         [f"constraint:C6: tests.hermes_cli.test_own failed with {self.ENTRY} restored"])

    def test_a_test_that_skips_or_fails_either_way_does_not_pin_the_entry(self):
        both = {"tests.hermes_cli.test_own::test_windows": "skipped", "tests.hermes_cli.test_own::test_broken": "failed"}
        self.assertEqual(self.failures(both, both), [])


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

    def test_an_unparseable_file_earns_no_credit_from_a_docstring(self):
        mark = 'def test_x(:\n    """@pytest.mark.platforms("windows")"""'
        self.assertEqual(self.run_static("tests_never_patch_the_host", self.PY, mark), [self.NO_MARK])
        self.assertEqual(self.run_static("adds_minimal_fixture", self.PY, f'def test_x(:\n    """{self.FIXTURE}"""'), self.K4)

    def test_hidden_text_and_copy_assertions_in_js_comments_do_not_count(self):
        content = ("// expect(writeText).toHaveBeenCalledWith(LONG_TEXT);\n"
                   "/* expect(bubble).not.toHaveTextContent(TAIL);\n   expect(bubble).toHaveTextContent(TAIL); */")
        self.assertEqual(self.run_static("tests_assert_hidden_text_and_copy", self.TS, content), [
            "constraint:C3: no added web test asserts what Copy writes",
            "constraint:C3: no added web test asserts that hidden prompt text is absent",
            "constraint:C3: no added web test asserts that hidden prompt text is present",
        ])

    def test_hidden_text_and_copy_assertions_in_code_still_count(self):
        content = ("expect(writeText).toHaveBeenCalledWith(LONG_TEXT);\n"
                   "expect(bubble).not.toHaveTextContent(TAIL);\nexpect(bubble).toHaveTextContent(TAIL);")
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


    def test_an_early_windows_skip_alone_leaves_the_helper_stopping_its_own_desktop(self):
        def keep_the_posix_only_spare(diff):
            return re.sub(r"(?ms)^@@ -428,13 .*?(?=^@@ -1249,)", "", diff, count=1)

        self.assertEqual(self.grade_sample("good", keep_the_posix_only_spare)[0], [
            "functional: tests/hermes_cli/test_desktop_update_tail.py"
            "::test_windows_stop_spares_its_own_desktop_and_stops_an_unrelated_one failed",
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
            "::test_live_catalog_hindsight_declares_known_issues failed with plugin-catalog/hindsight.yaml restored",
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
            "constraint:C3: no added web test asserts that hidden prompt text is present",
        ])

    def test_spreading_the_whole_prompt_into_code_points_fails_the_allocation_ask(self):
        self.assertEqual(self.grade_sample("spread")[0], [
            f"constraint:C2: {self.CHECKS}::C2 renders a long prompt without walking the whole prompt per code point failed",
        ])


if __name__ == "__main__":
    unittest.main()
