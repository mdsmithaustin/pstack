import re
import shutil
import subprocess
import textwrap
import unittest
from pathlib import Path


PLAYBOOKS = sorted(
    (Path(__file__).resolve().parents[1] / "skills/poteto-mode/playbooks").glob("*.md")
)

# Leads open a worklist by running this over a playbook. extract() mirrors it.
AWK_PROGRAM = (
    r"/^[0-9]+\. /{p=1} "
    r"!p && !/^#/ && NF {print; next} "
    r"p && /^[^ ]/ && !/^[0-9]+\. /{exit} p"
)

SENTINEL = "Read this playbook in full."
INDEX_SHAPED = frozenset({"multi-phase-plan.md", "opening-a-pr.md", "orchestrate.md"})
REPLY = "**Reply:**"
STEP = re.compile(r"[0-9]+\. ")
HEADING = re.compile(r"#")
NON_SPACE_LEAD = re.compile(r"[^ ]")


def extract(text):
    """Return (printed_lines, rest_lines) as the awk extractor splits them.

    rest_lines runs from the stop line to the end of the text.
    """
    lines = text.split("\n")
    if lines[-1] == "":
        lines.pop()
    printed = []
    in_steps = False
    for index, line in enumerate(lines):
        if STEP.match(line):
            in_steps = True
        if not in_steps and not HEADING.match(line) and line.strip(" \t"):
            printed.append(line)
            continue
        if in_steps and NON_SPACE_LEAD.match(line) and not STEP.match(line):
            return printed, lines[index:]
        if in_steps:
            printed.append(line)
    return printed, []


def is_index_shaped(printed):
    return any(line.startswith(SENTINEL) for line in printed)


def first_shape_violation(name, text):
    """Return a description of why the playbook breaks the rule, or None."""
    printed, rest = extract(text)
    if is_index_shaped(printed):
        if name in INDEX_SHAPED:
            return None
        return f"index-shaped playbook is not in INDEX_SHAPED: {name!r}"
    if not any(line.startswith("1. ") for line in printed):
        return "no numbered step 1"
    for line in rest:
        if line.strip() and not line.startswith(REPLY):
            return f"first offending line after the extractor stops: {line!r}"
    if not any(line.startswith(REPLY) for line in rest):
        return f"no {REPLY} line after the steps"
    return None


class Extract(unittest.TestCase):
    def test_lead_prose_steps_sub_item_trailing_paragraph_and_reply(self):
        text = textwrap.dedent("""\
            # Title

            Lead prose.
            More lead.

            1. First step.
               - sub item
            2. Second step.

            Trailing paragraph.
            **Reply:** done
            """)
        self.assertEqual(
            extract(text),
            (
                [
                    "Lead prose.",
                    "More lead.",
                    "1. First step.",
                    "   - sub item",
                    "2. Second step.",
                    "",
                ],
                ["Trailing paragraph.", "**Reply:** done"],
            ),
        )

    def test_file_without_numbered_steps_prints_all_prose(self):
        text = "# Heading\n\nLine a\n## Sub\n   \nLine b\n"
        self.assertEqual(extract(text), (["Line a", "Line b"], []))

    def test_column_zero_bullet_inside_step_block_stops_it(self):
        text = "1. a\n   cont\n- b\n2. c\n"
        self.assertEqual(extract(text), (["1. a", "   cont"], ["- b", "2. c"]))

    def test_heading_after_step_one_stops_it(self):
        text = "1. a\n\n# Later\ntext\n"
        self.assertEqual(extract(text), (["1. a", ""], ["# Later", "text"]))

    def test_digit_led_non_step_line_stops_the_block(self):
        text = "1. a\n2026 note\n10. ten\n"
        self.assertEqual(extract(text), (["1. a"], ["2026 note", "10. ten"]))

    def test_two_digit_step_directly_after_steps_continues(self):
        text = "1. a\n10. ten\n"
        self.assertEqual(extract(text), (["1. a", "10. ten"], []))

    def test_matches_real_awk_on_every_playbook(self):
        awk = shutil.which("awk")
        if awk is None:
            self.skipTest("awk is not installed")
        self.assertTrue(PLAYBOOKS, "no playbooks found")
        for path in PLAYBOOKS:
            with self.subTest(playbook=path.name):
                text = path.read_text(encoding="utf-8")
                awk_out = subprocess.run(
                    [awk, AWK_PROGRAM, str(path)],
                    capture_output=True,
                    text=True,
                    check=True,
                ).stdout
                printed, _ = extract(text)
                self.assertEqual(printed, awk_out.split("\n")[:-1])


class PlaybookShape(unittest.TestCase):
    def test_nothing_after_the_extractor_stops_except_reply(self):
        self.assertTrue(PLAYBOOKS, "no playbooks found")
        for path in PLAYBOOKS:
            with self.subTest(playbook=path.name):
                violation = first_shape_violation(path.name, path.read_text(encoding="utf-8"))
                self.assertIsNone(violation, f"{path}: {violation}")

    def test_index_shaped_playbooks_are_exactly_the_named_set(self):
        shaped = {
            path.name
            for path in PLAYBOOKS
            if is_index_shaped(extract(path.read_text(encoding="utf-8"))[0])
        }
        self.assertEqual(shaped, INDEX_SHAPED)


class FirstShapeViolation(unittest.TestCase):
    def test_step_numbered_two_is_not_step_one(self):
        self.assertEqual(
            first_shape_violation("a.md", "2. a\n**Reply:** done\n"),
            "no numbered step 1",
        )

    def test_step_numbered_ten_is_not_step_one(self):
        self.assertEqual(
            first_shape_violation("a.md", "10. a\n**Reply:** done\n"),
            "no numbered step 1",
        )

    def test_steps_that_reach_end_of_file_have_no_reply(self):
        self.assertEqual(
            first_shape_violation("a.md", "1. a\n2. b\n"),
            "no **Reply:** line after the steps",
        )

    def test_reply_after_steps_passes(self):
        self.assertIsNone(first_shape_violation("a.md", "1. a\n\n**Reply:** done\n"))

    def test_stray_line_before_reply_still_fails(self):
        self.assertEqual(
            first_shape_violation("a.md", "1. a\n\nstray\n**Reply:** done\n"),
            "first offending line after the extractor stops: 'stray'",
        )

    def test_digit_led_paragraph_after_steps_is_the_first_offender(self):
        self.assertEqual(
            first_shape_violation("a.md", "1. a\n2026 note\n**Reply:** done\n"),
            "first offending line after the extractor stops: '2026 note'",
        )

    def test_sentinel_in_an_unlisted_playbook_fails(self):
        self.assertEqual(
            first_shape_violation("other.md", "Read this playbook in full.\n"),
            "index-shaped playbook is not in INDEX_SHAPED: 'other.md'",
        )

    def test_sentinel_in_a_listed_playbook_passes(self):
        self.assertIsNone(
            first_shape_violation("orchestrate.md", "Read this playbook in full.\n")
        )


if __name__ == "__main__":
    unittest.main()
