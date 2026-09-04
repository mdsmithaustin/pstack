#!/usr/bin/env python3
"""Both skill-content checks must fire on planted defects, not just pass on a clean tree."""
from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
CONTENT = TOOLS / "check-skill-content.py"
FRONTMATTER = TOOLS / "check-skill-frontmatter.py"


def write_skill(root: Path, name: str, frontmatter: str, body: str) -> None:
    d = root / name
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text(f"---\n{frontmatter}\n---\n\n{body}\n", encoding="utf-8")


def run(script: Path, root: Path) -> tuple[int, str]:
    p = subprocess.run(
        [sys.executable, str(script), str(root)], capture_output=True, text=True
    )
    return p.returncode, p.stdout


class SkillContentChecks(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "skills"
        self.root.mkdir()
        write_skill(self.root, "real-skill", 'name: real-skill\ndescription: "a real one"', "Body.")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_clean_tree_passes(self) -> None:
        code, out = run(CONTENT, self.root)
        self.assertEqual(code, 0, out)
        self.assertEqual(out.strip(), "")

    def test_broken_markdown_link_fires(self) -> None:
        write_skill(self.root, "a", 'name: a\ndescription: "d"', "See [notes](../gone/notes.md).")
        code, out = run(CONTENT, self.root)
        self.assertEqual(code, 1)
        self.assertIn("relative-link", out)
        self.assertIn("../gone/notes.md", out)

    def test_broken_inline_code_path_fires(self) -> None:
        write_skill(self.root, "a", 'name: a\ndescription: "d"', "Read `../gone/setup.md` first.")
        code, out = run(CONTENT, self.root)
        self.assertEqual(code, 1)
        self.assertIn("relative-link", out)

    def test_resolving_link_does_not_fire(self) -> None:
        write_skill(self.root, "a", 'name: a\ndescription: "d"', "See `../real-skill/SKILL.md`.")
        code, out = run(CONTENT, self.root)
        self.assertEqual(code, 0, out)

    def test_unknown_bolded_skill_fires(self) -> None:
        write_skill(self.root, "a", 'name: a\ndescription: "d"', "Use the **not-a-real-skill** skill.")
        code, out = run(CONTENT, self.root)
        self.assertEqual(code, 1)
        self.assertIn("sibling-skill", out)

    def test_known_bolded_skill_does_not_fire(self) -> None:
        write_skill(self.root, "a", 'name: a\ndescription: "d"', "Use the **real-skill** skill.")
        code, out = run(CONTENT, self.root)
        self.assertEqual(code, 0, out)

    def test_principle_name_fires_without_the_word_skill(self) -> None:
        write_skill(self.root, "a", 'name: a\ndescription: "d"', "- **Laziness** (**principle-nope**). Bias to deletion.")
        code, out = run(CONTENT, self.root)
        self.assertEqual(code, 1, "a principle- name must be checked even with no 'skill' on the line")
        self.assertIn("principle-nope", out)

    def test_bold_prose_is_not_treated_as_a_skill(self) -> None:
        write_skill(self.root, "a", 'name: a\ndescription: "d"', "- **promoted**: it cleared every gate.")
        code, out = run(CONTENT, self.root)
        self.assertEqual(code, 0, out)


class FrontmatterChecks(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "skills"
        self.root.mkdir()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_valid_frontmatter_passes(self) -> None:
        write_skill(self.root, "a", 'name: a\ndescription: "d"', "Body.")
        code, out = run(FRONTMATTER, self.root)
        self.assertEqual(code, 0, out)

    def test_nested_mapping_is_allowed(self) -> None:
        write_skill(self.root, "a", 'name: a\ndescription: "d"\nmetadata:\n  type: project', "Body.")
        code, out = run(FRONTMATTER, self.root)
        self.assertEqual(code, 0, out)

    def test_duplicate_key_fires(self) -> None:
        write_skill(self.root, "a", 'name: a\ndescription: "d"\nname: a', "Body.")
        code, out = run(FRONTMATTER, self.root)
        self.assertEqual(code, 1)
        self.assertIn("duplicate key", out)

    def test_tab_fires(self) -> None:
        write_skill(self.root, "a", 'name: a\ndescription:\t"d"', "Body.")
        code, out = run(FRONTMATTER, self.root)
        self.assertEqual(code, 1)
        self.assertIn("tab character", out)

    def test_unterminated_quote_fires(self) -> None:
        write_skill(self.root, "a", 'name: a\ndescription: "unclosed', "Body.")
        code, out = run(FRONTMATTER, self.root)
        self.assertEqual(code, 1)
        self.assertIn("not terminated", out)

    def test_shapeless_line_fires(self) -> None:
        write_skill(self.root, "a", 'name: a\ndescription: "d"\nthis is not a mapping', "Body.")
        code, out = run(FRONTMATTER, self.root)
        self.assertEqual(code, 1)
        self.assertIn("key-value shape", out)


if __name__ == "__main__":
    unittest.main()
