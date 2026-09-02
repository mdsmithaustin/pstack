import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).parent / "check-models-config.py"
EXAMPLE = Path(__file__).parent.parent / "examples" / "pstack-models.md"

_spec = importlib.util.spec_from_file_location("check_models_config", SCRIPT)
cmc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cmc)

GRAMMAR_EXAMPLE = """---
description: pstack per-role model choices (overrides skill defaults)
---
# comment lines start with #
feature, refactoring: sonnet
bug-fix: opus@xhigh
arena runners: fable@xhigh, opus, sonnet, haiku
swarm workers: inherit-parent

## codex
feature, refactoring: gpt-5.6-terra@high
bug-fix: gpt-5.6-sol@xhigh
arena runners: gpt-5.6-sol@max, gpt-5.6-sol@xhigh, gpt-5.6-terra@high, gpt-5.6-luna@high
"""


def errors_of(findings):
    return [f for f in findings if f[1] == "error"]


def notices_of(findings):
    return [f for f in findings if f[1] == "notice"]


class ShippedShape(unittest.TestCase):
    def test_lints_clean(self):
        text = EXAMPLE.read_text(encoding="utf-8")
        _, findings = cmc.parse(text)
        self.assertEqual(errors_of(findings), [])


class GrammarExample(unittest.TestCase):
    def test_lints_clean_and_parses(self):
        sections, findings = cmc.parse(GRAMMAR_EXAMPLE)
        self.assertEqual(errors_of(findings), [])
        self.assertEqual(sections[""]["bug-fix"], [("opus", "xhigh")])
        self.assertEqual(
            sections["codex"]["arena runners"],
            [
                ("gpt-5.6-sol", "max"),
                ("gpt-5.6-sol", "xhigh"),
                ("gpt-5.6-terra", "high"),
                ("gpt-5.6-luna", "high"),
            ],
        )

    def test_max_and_ultra_produce_notices_not_errors(self):
        _, findings = cmc.parse(GRAMMAR_EXAMPLE)
        self.assertTrue(any("max" in n[2] for n in notices_of(findings)))


class ErrorRules(unittest.TestCase):
    def test_unknown_role(self):
        _, findings = cmc.parse("frobnicate: sonnet\n")
        errs = errors_of(findings)
        self.assertEqual(len(errs), 1)
        self.assertIn("unknown role", errs[0][2])

    def test_duplicate_role_in_section(self):
        _, findings = cmc.parse("bug-fix: sonnet\nbug-fix: opus\n")
        errs = errors_of(findings)
        self.assertEqual(len(errs), 1)
        self.assertIn("bound twice", errs[0][2])

    def test_unknown_effort(self):
        _, findings = cmc.parse("bug-fix: opus@ludicrous\n")
        errs = errors_of(findings)
        self.assertEqual(len(errs), 1)
        self.assertIn("unknown effort", errs[0][2])

    def test_list_on_single_value_role(self):
        _, findings = cmc.parse("bug-fix: opus, sonnet\n")
        errs = errors_of(findings)
        self.assertEqual(len(errs), 1)
        self.assertIn("given a list", errs[0][2])

    def test_unknown_section_header(self):
        _, findings = cmc.parse("## nonesuch\nbug-fix: opus\n")
        errs = errors_of(findings)
        self.assertEqual(len(errs), 1)
        self.assertIn("unknown section header", errs[0][2])

    def test_duplicate_section(self):
        text = "## codex\nbug-fix: opus\n## codex\nfeature: sonnet\n"
        _, findings = cmc.parse(text)
        errs = errors_of(findings)
        self.assertEqual(len(errs), 1)
        self.assertIn("duplicate section", errs[0][2])

    def test_unclosed_frontmatter(self):
        text = "---\ndescription: x\nbug-fix: opus\n"
        _, findings = cmc.parse(text)
        errs = errors_of(findings)
        self.assertEqual(len(errs), 1)
        self.assertIn("unclosed frontmatter", errs[0][2])

    def test_empty_entry(self):
        _, findings = cmc.parse("bug-fix: opus,,\n")
        errs = errors_of(findings)
        self.assertTrue(any("empty entry" in e[2] for e in errs))

    def test_minimal_is_not_an_effort(self):
        sections, findings = cmc.parse("bug-fix: gpt-5.6-terra@minimal\n")
        errs = errors_of(findings)
        self.assertEqual(len(errs), 1)
        self.assertIn("unknown effort", errs[0][2])
        self.assertNotIn("bug-fix", sections[""])

    def test_invalid_entries_are_omitted_from_sections(self):
        sections, findings = cmc.parse("arena runners: gpt-5.6-terra@ultra, sonnet@high\n")
        self.assertEqual(len(errors_of(findings)), 1)
        self.assertEqual(sections[""]["arena runners"], [("sonnet", "high")])

    def test_ultra_on_gpt56_terra(self):
        _, findings = cmc.parse("bug-fix: gpt-5.6-terra@ultra\n")
        errs = errors_of(findings)
        self.assertEqual(len(errs), 1)
        self.assertIn("not supported", errs[0][2])

    def test_ultra_allowed_on_gpt56_sol(self):
        _, findings = cmc.parse("bug-fix: gpt-5.6-sol@ultra\n")
        self.assertEqual(errors_of(findings), [])
        self.assertTrue(any("ultra" in n[2] for n in notices_of(findings)))


class ReflectShorthand(unittest.TestCase):
    def test_expands_bare_labels(self):
        sections, findings = cmc.parse("reflect judgment, divergent, synthesizer: fable\n")
        self.assertEqual(errors_of(findings), [])
        self.assertEqual(sections[""]["reflect judgment"], [("fable", None)])
        self.assertEqual(sections[""]["reflect divergent"], [("fable", None)])
        self.assertEqual(sections[""]["reflect synthesizer"], [("fable", None)])


class CliExitCodes(unittest.TestCase):
    def _run(self, text):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "pstack-models.md"
            path.write_text(text, encoding="utf-8")
            return subprocess.run(
                [sys.executable, str(SCRIPT), str(path)],
                capture_output=True,
                text=True,
            )

    def test_valid_file_exits_zero(self):
        result = self._run(GRAMMAR_EXAMPLE)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_invalid_file_exits_one(self):
        result = self._run("frobnicate: sonnet\n")
        self.assertEqual(result.returncode, 1)
        self.assertIn("error", result.stdout)

    def test_example_file_exits_zero(self):
        result = subprocess.run(
            [sys.executable, str(SCRIPT), str(EXAMPLE)],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
