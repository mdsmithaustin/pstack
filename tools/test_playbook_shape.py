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
    r"p&&/^[^ 0-9]/{exit} p"
)

SENTINEL = "Read this playbook in full."
REPLY = "**Reply:**"
STEP = re.compile(r"[0-9]+\. ")
HEADING = re.compile(r"#")
STOP = re.compile(r"[^ 0-9]")


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
        if in_steps and STOP.match(line):
            return printed, lines[index:]
        if in_steps:
            printed.append(line)
    return printed, []


def is_index_shaped(printed):
    return any(line.startswith(SENTINEL) for line in printed)


def first_shape_violation(text):
    """Return a description of why the playbook breaks the rule, or None."""
    printed, rest = extract(text)
    if is_index_shaped(printed):
        return None
    if not any(STEP.match(line) for line in printed):
        return "no numbered step 1"
    for line in rest:
        if line.strip() and not line.startswith(REPLY):
            return f"first offending line after the extractor stops: {line!r}"
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

    def test_digit_led_line_after_step_one_continues(self):
        text = "1. a\n2026 note\n10. ten\n"
        self.assertEqual(extract(text), (["1. a", "2026 note", "10. ten"], []))

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
                violation = first_shape_violation(path.read_text(encoding="utf-8"))
                self.assertIsNone(violation, f"{path}: {violation}")

    def test_sentinel_exemption_is_not_vacuous(self):
        shaped = [
            path.name
            for path in PLAYBOOKS
            if is_index_shaped(extract(path.read_text(encoding="utf-8"))[0])
        ]
        self.assertLessEqual(
            len(shaped), 3, f"index-shaped playbooks should be a short list: {shaped}"
        )
        self.assertLess(
            len(shaped), len(PLAYBOOKS), "every playbook is exempt, so the rule checks nothing"
        )


if __name__ == "__main__":
    unittest.main()
