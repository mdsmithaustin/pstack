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

    CAPTURE_FORMS = (
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
        ('vi.spyOn(navigator.clipboard, "writeText")\n  .mockImplementation(async (t) => { written = t })', "expect(written).toBe(LONG_TEXT)"),
        ("Object.assign(navigator.clipboard, {\n  writeText: (t) =>\n    written.push(t),\n})", "expect(written).toEqual([LONG_TEXT])"),
        ("Object.assign(navigator.clipboard, {\n  writeText:\n    vi.fn((t) => { written = t }),\n})", "expect(written).toBe(LONG_TEXT)"),
        ("Object.assign(navigator.clipboard, {\r\n  writeText: (t) =>\r\n    written.push(t),\r\n})", "expect(written).toEqual([LONG_TEXT])"),
        ("Object.assign(navigator, { clipboard: { writeText: vi.fn<\n(text: string) => Promise<void>\n>(async (t) => { written = t }) } });",
         "expect(written).toBe(LONG_TEXT);"),
        ("it('copies', () => {\n  expect(screen.getByText(/don't/i)).toBeInTheDocument()\n"
         "  Object.assign(navigator, { clipboard: { writeText: vi.fn((t) => { written = t }) } })",
         "  expect(written).toBe(LONG_TEXT)\n})\nit('collapses', () => {})"),
        ("", "expect((navigator.clipboard.writeText as jest.Mock).mock.calls[0][0]).toBe(LONG_TEXT);"),
        ("", "expect(vi.mocked(navigator.clipboard.writeText).mock.lastCall).toEqual([LONG_TEXT]);"),
        ("", "expect(jest.mocked(writeText).mock.calls[0]).toEqual([LONG_TEXT]);"),
    )

    def test_each_payload_check_trunk_credits_counts(self):
        for stub, compared in self.CAPTURE_FORMS:
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

    def test_a_variable_assigned_after_a_semicolonless_spy_is_not_a_clipboard_capture(self):
        for after in (["const writeText = vi.fn()", "const bubble = renderPrompt()"],
                      ["const writeText = vi.fn()", "bubble = renderPrompt()"],
                      ["const writeText = vi.fn()", "beforeEach(() => {", "  bubble = renderPrompt()", "})"],
                      ['vi.stubGlobal("navigator", { clipboard: { writeText } })', "beforeEach(() => {", "  bubble = renderPrompt()", "})"],
                      ['const writeText = vi.fn(() => log(":-("))', "bubble = renderPrompt()"],
                      ['it("writeText receives the full prompt", () => {', "  bubble = renderPrompt()"]):
            with self.subTest(after):
                self.assertEqual(self.failures(*after, "expect(bubble).not.toHaveTextContent(TAIL)", "expect(bubble).toHaveTextContent(TAIL)"), [])

    def test_rendered_text_kept_in_a_variable_after_a_semicolonless_stub_counts(self):
        stub = ["const writeText = vi.fn()", "Object.assign(navigator, { clipboard: { writeText } })", "render(<PromptBubble text={LONG_TEXT} />)"]
        for absent, present in (("expect(text).not.toContain(TAIL)", "expect(bubble).toHaveTextContent(TAIL)"),
                                ("expect(bubble).not.toHaveTextContent(TAIL)", "expect(text).toContain(TAIL)")):
            with self.subTest(absent=absent):
                self.assertEqual(self.failures(*stub, "const text = bubble.textContent", absent, present), [])

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

    def test_a_present_constant_built_from_the_absent_value_counts(self):
        for definitions in (["const LONG_TEXT = `${HEAD}${TAIL}`;"], ["const LONG_TEXT = HEAD + TAIL;"],
                            ['const LONG_TEXT: string = "chunk ".repeat(900) + TAIL;'],
                            ['const TAIL = "the ending";', 'const LONG_TEXT = "r ".repeat(2500) + "the ending";']):
            for present in ("expect(container).toHaveTextContent(LONG_TEXT);", "expect(container.textContent).toBe(LONG_TEXT);"):
                with self.subTest(definitions=definitions, present=present):
                    self.assertEqual(self.failures(*definitions, "expect(container).not.toHaveTextContent(TAIL);", present), [])

    def test_a_present_value_tied_to_the_absent_one_counts(self):
        long_from_tail = 'const LONG_TEXT = "a".repeat(9000) + TAIL;'
        for row, lines in (("inline concatenation", ["expect(bubble).not.toHaveTextContent(TAIL);",
                                                     "expect(bubble).toHaveTextContent(HEAD + TAIL);"]),
                           ("inline template", ["expect(bubble).not.toHaveTextContent(TAIL);",
                                                "expect(bubble).toHaveTextContent(`${HEAD}${TAIL}`);"]),
                           ("tail sliced from the present value", ["const TAIL = LONG_TEXT.slice(-40);",
                                                                   "expect(bubble).not.toHaveTextContent(TAIL);",
                                                                   "expect(bubble).toHaveTextContent(LONG_TEXT);"]),
                           ("definition continued on the next line", ['const LONG_TEXT = "chunk ".repeat(2500) +', "  TAIL;",
                                                                      "expect(bubble).not.toHaveTextContent(TAIL);",
                                                                      "expect(bubble).toHaveTextContent(LONG_TEXT);"]),
                           ("absent literal of a constant the present one holds", ['const TAIL = "UNIQUE_TAIL";', long_from_tail,
                                                                                    'expect(bubble).not.toHaveTextContent("UNIQUE_TAIL");',
                                                                                    "expect(bubble).toHaveTextContent(LONG_TEXT);"]),
                           ("absent cut inline from the present value", ["expect(bubble).not.toHaveTextContent(LONG_TEXT.slice(-40));",
                                                                          "expect(bubble).toHaveTextContent(LONG_TEXT);"])):
            with self.subTest(row):
                self.assertEqual(self.failures(*lines), [])

    def test_a_definition_continued_as_javascript_continues_a_statement_counts(self):
        for row, definition in (("next line opens with an operator", ['const LONG_TEXT = "a".repeat(9000)', "  + TAIL"]),
                                ("next line opens with a method call", ['const LONG_TEXT = "a".repeat(9000)', "  .concat(TAIL)"]),
                                ("line ends with an arrow", ["const LONG_TEXT = () =>", "  TAIL"]),
                                ("line ends with a division", ["const LONG_TEXT = 1 /", "  TAIL"]),
                                ("template literal across lines", ["const LONG_TEXT = `a", "${TAIL}`"])):
            with self.subTest(row):
                self.assertEqual(self.failures(*definition, "expect(bubble).not.toHaveTextContent(TAIL)",
                                               "expect(bubble).toHaveTextContent(LONG_TEXT)"), [])

    def test_a_present_value_that_reaches_the_absent_one_through_names_counts(self):
        absent = "expect(bubble).not.toHaveTextContent(TAIL)"
        for row, lines in (("present wrapped in a method call", ["const LONG_TEXT = HEAD + TAIL", absent, "expect(bubble).toHaveTextContent(LONG_TEXT.trim())"]),
                           ("present wrapped in a function call", ["const LONG_TEXT = HEAD + TAIL", absent, "expect(bubble).toHaveTextContent(String(LONG_TEXT))"]),
                           ("present text compared with a wrapped value", ["const LONG_TEXT = HEAD + TAIL", absent, "expect(bubble.textContent).toBe(LONG_TEXT.trim())"]),
                           ("definition two names away", ["const makeLong = () => HEAD + TAIL", "const LONG_TEXT = makeLong()", absent,
                                                          "expect(bubble).toHaveTextContent(LONG_TEXT)"]),
                           ("let assigned in a hook", ["let LONG_TEXT: string", "beforeEach(() => {", "  LONG_TEXT = HEAD + TAIL", "})", absent,
                                                       "expect(bubble).toHaveTextContent(LONG_TEXT)"]),
                           ("declaration whose brackets close on a later line", ["const LONG_TEXT = Array.from({ length: 50 }, (_, i) => {",
                                                                                 "  return `chunk ${i}`", '}).join(" ") + TAIL', absent,
                                                                                 "expect(bubble).toHaveTextContent(LONG_TEXT)"]),
                           ("blank line where the pipeline blanked a comment", ['const LONG_TEXT = "x".repeat(500)', "   ", "  + TAIL", absent,
                                                                                "expect(bubble).toHaveTextContent(LONG_TEXT)"]),
                           ("present in parentheses", ["const LONG_TEXT = HEAD + TAIL", absent, "expect(bubble).toHaveTextContent((LONG_TEXT))"]),
                           ("present cast to a type", ["const LONG_TEXT = HEAD + TAIL", absent, "expect(bubble).toHaveTextContent(LONG_TEXT as string)"]),
                           ("present template holding the constant", ["const LONG_TEXT = HEAD + TAIL", absent, "expect(bubble).toHaveTextContent(`Prompt: ${LONG_TEXT}`)"]),
                           ("function declaration builds the present value", ["function makeLong() {", "  return HEAD + TAIL", "}",
                                                                              "const LONG_TEXT = makeLong()", absent,
                                                                              "expect(bubble).toHaveTextContent(LONG_TEXT)"])):
            with self.subTest(row):
                self.assertEqual(self.failures(*lines), [])

    def test_a_present_value_that_does_not_reach_the_absent_one_does_not_count(self):
        absent = "expect(bubble).not.toHaveTextContent(TAIL)"
        for row, lines in (("unrelated value wrapped in a call", ['const HEAD = "chunk ".repeat(900)', "const LONG_TEXT = HEAD + TAIL", absent,
                                                                  "expect(bubble).toHaveTextContent(HEAD.trim())"]),
                           ("open test body after a declaration", ['it("hides the tail", () => {', '  const HEAD = "chunk"', absent,
                                                                   "  expect(bubble).toHaveTextContent(HEAD)", "})"]),
                           ("button label that shares a constant's name", ['const prompt = "a".repeat(9000) + TAIL', absent,
                                                                           'expect(screen.getByText("Show full prompt")).toBeInTheDocument()'])):
            with self.subTest(row):
                self.assertEqual(self.failures(*lines), [self.PRESENT])

    def test_a_constant_declared_in_an_open_test_body_keeps_its_literal(self):
        self.assertEqual(self.failures('it("hides the tail", () => {', '  const TAIL = "tail marker"', "  expect(bubble).not.toHaveTextContent(TAIL)",
                                       '  expect(bubble).toHaveTextContent("tail marker")', "})"), [])

    def test_a_definition_in_any_statement_style_counts(self):
        absent, present = "expect(bubble).not.toHaveTextContent(TAIL);", "expect(bubble).toHaveTextContent(LONG_TEXT);"
        helper = ["  const head = \"x\".repeat(500);", "  return head + TAIL;"]
        array = ["Array.from({ length: 50 }, (_, i) => {", "    return `chunk ${i}`;", "  }).join(\" \") + TAIL;"]
        for row, lines in (("semicolon inside a string", ['const LONG_TEXT = "Hello; world ".repeat(500) + TAIL;']),
                           ("function of two statements", ["function makeLong() {", *helper, "}", "const LONG_TEXT = makeLong();"]),
                           ("arrow block of two statements", ["const makeLong = () => {", *helper, "};", "const LONG_TEXT = makeLong();"]),
                           ("callback ending in a semicolon", ["const LONG_TEXT = " + array[0], *array[1:]]),
                           ("immediately invoked arrow", ["const LONG_TEXT = (() => {", *helper, "})();"]),
                           ("hook of two statements", ["let LONG_TEXT: string;", "beforeEach(() => {", *helper[:1], "  LONG_TEXT = head + TAIL;", "});"]),
                           ("first statement of a test body", ['it("hides the tail", () => {', "  const LONG_TEXT = " + array[0], *array[1:]]),
                           ("first statement of a hook", ["let LONG_TEXT: string;", "beforeEach(() => {", "  LONG_TEXT = " + array[0], *array[1:]]),
                           ("exported declaration", ["export const LONG_TEXT = " + array[0], *array[1:]]),
                           ("async function", ["async function makeLong() {", *helper, "}", "const LONG_TEXT = await makeLong();"]),
                           ("compound assignment", ['let LONG_TEXT = "x".repeat(500);', "LONG_TEXT += TAIL;"])):
            with self.subTest(row):
                self.assertEqual(self.failures(*lines, absent, present), [])

    def test_a_literal_or_an_attribute_does_not_reach_the_absent_value(self):
        absent = "expect(bubble).not.toHaveTextContent(TAIL);"
        for row, lines in (("regex literal with a group", ['const prompt = "a" + TAIL;', absent, "expect(bubble).toHaveTextContent(/Show full (prompt|text)/);"]),
                           ("JSX attribute that shares a constant's name", ['const LONG_TEXT = "x".repeat(500) + TAIL;', 'const text = "Hello";',
                                                                             "render(<Bubble text={LONG_TEXT} />);", absent,
                                                                             "expect(bubble).toHaveTextContent(text);"])):
            with self.subTest(row):
                self.assertEqual(self.failures(*lines), [self.PRESENT])

    def test_literal_text_names_no_constants(self):
        absent, prompt = "expect(bubble).not.toHaveTextContent(TAIL)", 'const prompt = "a".repeat(13000) + TAIL'
        for row, lines in (("regex constant", [prompt, "const EXPAND = /show full prompt/i", absent, "expect(screen.getByText(EXPAND)).toBeInTheDocument()"]),
                           ("template constant", [prompt, "const EXPAND = `show full prompt`", absent, "expect(screen.getByText(EXPAND)).toBeInTheDocument()"]),
                           ("template label with a count", [prompt, absent, "expect(bubble).toHaveTextContent(`Show full prompt (${count} chars)`)"]),
                           ("flagless regex constant above a definition", ["const SHOW_LESS = /show less/", 'const TAIL = "tail marker"', absent,
                                                                            "expect(screen.getByText(SHOW_LESS)).toBeInTheDocument()"]),
                           ("block body statements", ["function setup() {", '  const label = "Show more"', "  render(<Bubble text={LONG_TEXT} />)", "}",
                                                      'const LONG_TEXT = "a".repeat(9) + TAIL', absent, "expect(screen.getByText(label)).toBeInTheDocument()"])):
            with self.subTest(row):
                self.assertEqual(self.failures(*lines), [self.PRESENT])

    def test_each_declarator_in_a_list_is_a_definition(self):
        absent, present = "expect(bubble).not.toHaveTextContent(TAIL)", "expect(bubble).toHaveTextContent(LONG_TEXT)"
        for row, lines in (("const list", ['const HEAD = "x".repeat(9), TAIL = "the end", LONG_TEXT = HEAD + TAIL']),
                           ("let list assigned in a hook", ["let TAIL, LONG_TEXT", "beforeEach(() => {", '  TAIL = "the end"', '  LONG_TEXT = "x".repeat(9) + TAIL', "})"]),
                           ("let list with a value", ['let HEAD = "x".repeat(9), LONG_TEXT', "beforeEach(() => {", "  LONG_TEXT = HEAD + TAIL", "})"])):
            with self.subTest(row):
                self.assertEqual(self.failures(*lines, absent, present), [])

    def test_an_escape_past_the_last_code_point_is_kept_as_written(self):
        self.assertEqual(self.failures('const TAIL = "\\u{110000}";', "expect(container).not.toHaveTextContent(TAIL);",
                                       "expect(container).toHaveTextContent(TAIL);"), [])

    def test_a_name_defined_twice_keeps_both_definitions(self):
        for second in ('const LONG_TEXT = "short";', 'const TAIL = "unrelated";'):
            with self.subTest(second):
                self.assertEqual(self.failures('it("hides the tail", () => {', "  const LONG_TEXT = HEAD + TAIL;",
                                               "  expect(bubble).not.toHaveTextContent(TAIL);", "  expect(bubble).toHaveTextContent(LONG_TEXT);",
                                               "});", 'it("renders a short prompt", () => {', f"  {second}", "});"), [])

    def test_a_joined_line_keeps_each_definition_its_own(self):
        absent = "expect(bubble).not.toHaveTextContent(TAIL)"
        for row, lines, expected in (
                ("regex literal above a string constant", ["const RE = /chunk/", 'const TAIL = "tail marker"', absent,
                                                           'expect(bubble).toHaveTextContent("tail marker")'], []),
                ("declaration word inside a string", ["const RE = /chunk/", 'const TAIL = "let it end"', absent,
                                                      'expect(bubble).toHaveTextContent("let it end")'], []),
                ("stray backtick in a comment", ["// a ` stray", 'const HEAD = "chunk"', absent,
                                                 "expect(bubble).toHaveTextContent(HEAD)"], [self.PRESENT])):
            with self.subTest(row):
                self.assertEqual(self.failures(*lines), expected)

    def test_a_present_constant_not_built_from_the_absent_value_does_not_count(self):
        self.assertEqual(self.failures('const HEAD = "chunk ".repeat(900);', "const LONG_TEXT = HEAD + TAIL;",
                                       "expect(container).not.toHaveTextContent(TAIL);", "expect(container).toHaveTextContent(HEAD);"),
                         [self.PRESENT])

    def test_a_constant_and_its_literal_name_the_same_value(self):
        for absent, present in (("TAIL", '"the end of it"'), ('"the end of it"', "TAIL"), ("/the end of it/", '"the end of it"'),
                                ("new RegExp(TAIL)", "TAIL"), ("TAIL", "expect.stringContaining(TAIL)"), ("TAIL", "`${TAIL}`")):
            with self.subTest(absent=absent, present=present):
                self.assertEqual(self.failures('const TAIL = "the end of it";', f"expect(container).not.toHaveTextContent({absent});",
                                               f"expect(container).toHaveTextContent({present});"), [])

    def test_a_constant_and_a_literal_that_spell_the_same_text_with_escapes_match(self):
        for constant, literal in ((r'"\x41\u0042\u{43}"', '"ABC"'), (r"'it\'s'", '"it\'s"'), (r'"tab\there"', r"'tab\u0009here'"),
                                  (r'"caf\u00e9"', '"café"')):
            with self.subTest(constant):
                self.assertEqual(self.failures(f"const TAIL = {constant};", "expect(container).not.toHaveTextContent(TAIL);",
                                               f"expect(container).toHaveTextContent({literal});"), [])

    def test_a_bare_query_after_a_clipboard_assertion_is_the_rendered_text(self):
        for query in ("screen.getByText(TAIL);", "await screen.findByText(TAIL)"):
            with self.subTest(query):
                self.assertEqual(self.failures("expect(bubble).not.toHaveTextContent(TAIL);", "fireEvent.click(expand);",
                                               "expect(writeText).toHaveBeenCalledWith(LONG_TEXT);", query), [])

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
