import importlib.util
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("skill_references", ROOT / "tools" / "skill-references.py")
skill_references = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(skill_references)


def tracked_repo(tmp, files):
    root = Path(tmp)
    for rel, text in files.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text)
    subprocess.run(["git", "init", "-q", tmp], check=True)
    subprocess.run(["git", "-C", tmp, "add", "."], check=True)
    return root


class SkillReferenceSpelling(unittest.TestCase):
    def test_model_facing_text_never_spells_a_skill_with_a_slash_or_dollar(self):
        self.assertEqual(skill_references.violations(), [],
                         'write "Use the **name** skill." as its own sentence or step; a passage that quotes the '
                         "user or text shown to the user goes in USER_FACING in tools/skill-references.py")

    def test_every_exempt_passage_still_matches(self):
        self.assertEqual(skill_references.stale_exemptions(), [],
                         "remove USER_FACING or MODE_REMINDERS passages in tools/skill-references.py that no "
                         "longer hold a /name or $name spelling")

    def test_a_skill_may_spell_itself_only_on_its_description_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = tracked_repo(tmp, {
                "skills/demo/SKILL.md": "---\ndescription: Use for /demo.\n---\nThen run /demo.\n",
                "skills/other/SKILL.md": "---\ndescription: Use for /other.\n---\n",
            })
            self.assertEqual(skill_references.violations(root), ["skills/demo/SKILL.md:4: /demo"])

    def test_a_body_line_that_starts_with_description_is_not_exempt(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = tracked_repo(tmp, {
                "skills/demo/SKILL.md": "---\ndescription: Use for /demo.\n---\ndescription: then run /demo again\n",
            })
            self.assertEqual(skill_references.violations(root), ["skills/demo/SKILL.md:4: /demo"])

    def test_a_folded_description_may_spell_its_own_skill_on_any_continuation_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = tracked_repo(tmp, {
                "skills/demo/SKILL.md": "---\nname: demo\ndescription: >-\n  Build a page.\n  Use for /demo, not /other.\nicon: x\n---\nBody.\n",
                "skills/other/SKILL.md": "---\ndescription: Use for /other.\n---\n",
            })
            self.assertEqual(skill_references.violations(root), ["skills/demo/SKILL.md:5: /other"])

    def test_a_key_after_a_folded_description_is_not_part_of_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = tracked_repo(tmp, {
                "skills/demo/SKILL.md": "---\ndescription: >-\n  Build a page.\nreminder: apply /demo.\n---\n",
            })
            self.assertEqual(skill_references.violations(root), ["skills/demo/SKILL.md:4: /demo"])

    def test_a_description_line_may_not_spell_another_skill(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = tracked_repo(tmp, {
                "skills/demo/SKILL.md": "---\ndescription: Use for /demo, then /other.\n---\n",
                "skills/other/SKILL.md": "---\ndescription: Use for /other.\n---\n",
            })
            self.assertEqual(skill_references.violations(root), ["skills/demo/SKILL.md:2: /other"])

    def test_an_exempt_passage_missing_from_its_file_is_stale(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = tracked_repo(tmp, {
                "skills/demo/SKILL.md": "Say /demo to start.\n",
                "skills/other/SKILL.md": "Nothing here.\n",
            })
            table = {"skills/demo/SKILL.md": ["Say /demo to start.", "Say /demo to pause."],
                     "skills/other/SKILL.md": ["Run /other."]}
            with mock.patch.object(skill_references, "EXEMPT", table):
                self.assertEqual(skill_references.stale_exemptions(root),
                                 ["skills/demo/SKILL.md: Say /demo to pause.", "skills/other/SKILL.md: Run /other."])

    def test_the_scan_skips_untracked_markdown(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "skills/demo/node_modules").mkdir(parents=True)
            (root / "skills/demo/SKILL.md").write_text("Then run /demo.\n")
            (root / "skills/demo/node_modules/README.md").write_text("Run /demo here too.\n")
            subprocess.run(["git", "init", "-q", tmp], check=True)
            subprocess.run(["git", "-C", tmp, "add", "skills/demo/SKILL.md"], check=True)
            self.assertEqual(skill_references.sigils(root),
                             [("skills/demo/SKILL.md", 1, "/demo", "Then run /demo.", False)])

    def test_the_scan_skips_a_tracked_file_deleted_from_disk(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "skills/demo").mkdir(parents=True)
            (root / "skills/demo/SKILL.md").write_text("Then run /demo.\n")
            (root / "skills/demo/notes.md").write_text("Run /demo here too.\n")
            subprocess.run(["git", "init", "-q", tmp], check=True)
            subprocess.run(["git", "-C", tmp, "add", "skills"], check=True)
            (root / "skills/demo/notes.md").unlink()
            self.assertEqual(skill_references.sigils(root),
                             [("skills/demo/SKILL.md", 1, "/demo", "Then run /demo.", False)])

    def test_the_scan_finds_a_slash_and_a_dollar_spelling(self):
        names = skill_references.skill_names(ROOT)
        sigil = skill_references.sigil_pattern("deslop")
        self.assertIn("deslop", names)
        self.assertEqual([m.group(0) for m in sigil.finditer("Run `/deslop`, then $deslop, not skills/deslop/x.")],
                         ["/deslop", "$deslop"])


if __name__ == "__main__":
    unittest.main()
