#!/usr/bin/env python3
"""Both lints must fire on planted defects and stay quiet on valid input."""
from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
CONTENT = TOOLS / "check-skill-content.py"
FRONTMATTER = TOOLS / "check-skill-frontmatter.py"


def run(script: Path, root: Path) -> tuple[int, str]:
    p = subprocess.run([sys.executable, str(script), str(root)], capture_output=True, text=True)
    return p.returncode, p.stdout


class Tree(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "skills"
        self.root.mkdir()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def skill(self, name: str, frontmatter: str, body: str = "Body.") -> Path:
        d = self.root / name
        d.mkdir(parents=True, exist_ok=True)
        (d / "SKILL.md").write_text(f"---\n{frontmatter}\n---\n\n{body}\n", encoding="utf-8")
        return d


class ContentLint(Tree):
    def setUp(self) -> None:
        super().setUp()
        real = self.skill("real-skill", 'name: real-skill\ndescription: "d"')
        (real / "refs").mkdir()
        (real / "refs" / "my notes.md").write_text("x", encoding="utf-8")

    def body(self, body: str) -> tuple[int, str]:
        self.skill("a", 'name: a\ndescription: "d"', body)
        return run(CONTENT, self.root)

    def test_clean_tree_passes(self) -> None:
        self.assertEqual(run(CONTENT, self.root), (0, ""))

    def test_dotdot_link_broken_fires(self) -> None:
        code, out = self.body("See [x](../gone/n.md).")
        self.assertEqual(code, 1)
        self.assertIn("relative-link", out)

    def test_bare_relative_link_broken_fires(self) -> None:
        code, out = self.body("See [x](references/gone.md).")
        self.assertEqual(code, 1, "a link with no ./ prefix is still a relative link")
        self.assertIn("references/gone.md", out)

    def test_inline_code_path_broken_fires(self) -> None:
        code, out = self.body("Read `../gone/setup.md` first.")
        self.assertEqual(code, 1)

    def test_broken_non_md_inline_path_fires(self) -> None:
        code, out = self.body("Run `../real-skill/gone.sh` first.")
        self.assertEqual(code, 1, "inline code paths are checked whatever the extension")
        self.assertIn("relative-link", out)

    def test_resolving_link_passes(self) -> None:
        self.assertEqual(self.body("See `../real-skill/SKILL.md`.")[0], 0)

    def test_url_encoded_target_that_exists_passes(self) -> None:
        self.assertEqual(self.body("See [x](../real-skill/refs/my%20notes.md).")[0], 0)

    def test_link_inside_a_fence_is_ignored(self) -> None:
        self.assertEqual(self.body("```markdown\n[x](../nope/gone.md)\n```")[0], 0)

    def test_placeholder_path_is_ignored(self) -> None:
        self.assertEqual(self.body("Use `../<suite>/notes.md` here.")[0], 0)

    def test_absolute_url_is_ignored(self) -> None:
        self.assertEqual(self.body("See [x](https://example.com/a.md).")[0], 0)

    def test_unknown_skill_reference_fires(self) -> None:
        code, out = self.body("Use the **fake-skill** skill.")
        self.assertEqual(code, 1)
        self.assertIn("sibling-skill", out)

    def test_principle_name_fires_without_the_word_skill(self) -> None:
        code, out = self.body("- **L** (**principle-nope**). Bias to deletion.")
        self.assertEqual(code, 1, "a principle- name is checked even with no 'skill' on the line")
        self.assertIn("principle-nope", out)

    def test_known_skill_reference_passes(self) -> None:
        self.assertEqual(self.body("Use the **real-skill** skill.")[0], 0)

    def test_bold_prose_is_not_a_skill_reference(self) -> None:
        self.assertEqual(self.body("- **promoted**: it cleared every gate.")[0], 0)

    def test_bold_inside_a_fence_is_ignored(self) -> None:
        self.assertEqual(self.body("```\nuse the **fake-skill** skill\n```")[0], 0)

    def test_bold_inside_inline_code_is_ignored(self) -> None:
        self.assertEqual(self.body("Write `**fake-skill** skill` here.")[0], 0)


class FenceHandling(Tree):
    def setUp(self) -> None:
        super().setUp()
        self.skill("real-skill", 'name: real-skill\ndescription: "d"')

    def body(self, body: str) -> tuple[int, str]:
        self.skill("a", 'name: a\ndescription: "d"', body)
        return run(CONTENT, self.root)

    def test_scripts_parse(self) -> None:
        for script in (CONTENT, FRONTMATTER):
            compile(script.read_text(encoding="utf-8"), str(script), "exec")

    def test_four_backtick_fence_survives_an_inner_fence(self) -> None:
        code, out = self.body("````\n```\nSee [x](../gone/n.md).\n```\n````")
        self.assertEqual(code, 0, out)

    def test_tilde_fence_is_skipped(self) -> None:
        self.assertEqual(self.body("~~~\n[x](../gone/n.md)\n~~~")[0], 0)

    def test_fence_with_info_string_is_skipped(self) -> None:
        self.assertEqual(self.body("```markdown\n[x](../gone/n.md)\n```")[0], 0)

    def test_a_line_with_an_info_string_does_not_close_a_fence(self) -> None:
        code, out = self.body("```markdown\n```json\nSee [x](../gone/n.md).\n```")
        self.assertEqual(code, 0, "only a bare fence closes one, so the link stays inside the block")

    def test_content_after_a_closed_fence_is_checked(self) -> None:
        self.assertEqual(self.body("```\nx\n```\n\nSee [x](../gone/n.md).")[0], 1)

    def test_unclosed_fence_is_reported(self) -> None:
        code, out = self.body("```\nx\n\nSee [x](../gone/n.md).")
        self.assertEqual(code, 1, "an unclosed fence hides the rest of the file")
        self.assertIn("unclosed-fence", out)

    def test_indented_code_block_is_skipped(self) -> None:
        self.assertEqual(self.body("Example:\n\n    See [x](../gone/n.md).")[0], 0)

    def test_link_with_a_title_attribute_is_checked(self) -> None:
        code, out = self.body('See [x](../gone/n.md "Title").')
        self.assertEqual(code, 1, "a title attribute does not make the target unreachable")
        self.assertIn("../gone/n.md", out)


class FrontmatterLint(Tree):
    def check(self, frontmatter: str) -> tuple[int, str]:
        self.skill("a", frontmatter)
        return run(FRONTMATTER, self.root)

    def test_valid_passes(self) -> None:
        self.assertEqual(self.check('name: a\ndescription: "d"')[0], 0)

    def test_nested_mapping_passes(self) -> None:
        self.assertEqual(self.check('name: a\ndescription: "d"\nmetadata:\n  type: project')[0], 0)

    def test_sequence_at_column_zero_passes(self) -> None:
        self.assertEqual(self.check('name: a\ndescription: "d"\nallowed-tools:\n- Read')[0], 0)

    def test_comment_line_passes(self) -> None:
        self.assertEqual(self.check('name: a\ndescription: "d"\n# a note')[0], 0)

    def test_space_before_colon_passes(self) -> None:
        self.assertEqual(self.check('name : a\ndescription: "d"')[0], 0)

    def test_trailing_space_after_quoted_value_passes(self) -> None:
        self.assertEqual(self.check('name: a\ndescription: "d" ')[0], 0)

    def test_duplicate_key_fires(self) -> None:
        code, out = self.check('name: a\ndescription: "d"\nname: a')
        self.assertEqual(code, 1)
        self.assertIn("duplicate key", out)

    def test_duplicate_key_with_space_before_colon_fires(self) -> None:
        code, out = self.check('name: a\ndescription: "d"\nname : a')
        self.assertEqual(code, 1, "extraction accepts this form, so duplicate detection must too")
        self.assertIn("duplicate key", out)

    def test_tab_fires(self) -> None:
        code, out = self.check('name: a\ndescription:\t"d"')
        self.assertEqual(code, 1)
        self.assertIn("tab character", out)

    def test_wrong_name_fires(self) -> None:
        self.assertEqual(self.check('name: zzz\ndescription: "d"')[0], 1)

    def test_empty_description_fires(self) -> None:
        self.assertEqual(self.check("name: a\ndescription:")[0], 1)


if __name__ == "__main__":
    unittest.main()
