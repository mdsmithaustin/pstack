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
                         'write "Call the Skill tool with `name`." as its own sentence or step; a passage that quotes the '
                         "user or text shown to the user goes in USER_FACING in tools/skill-references.py")

    def test_model_facing_text_loads_a_skill_through_the_skill_tool(self):
        self.assertEqual(skill_references.legacy_loads(), [],
                         'write "Call the Skill tool with `name`." in place of "Use the **name** skill."')

    def test_a_use_the_load_is_legacy_and_a_bare_mention_is_not(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = tracked_repo(tmp, {
                "skills/demo/SKILL.md": "Use the **demo** skill.\nThen use the **demo** skill's Phase A.\n"
                                        "Call the Skill tool with `demo`.\nThe **demo** skill owns this.\n",
            })
            self.assertEqual(skill_references.legacy_loads(root),
                             ["skills/demo/SKILL.md:1: Use the **demo** skill",
                              "skills/demo/SKILL.md:2: use the **demo** skill"])

    def test_upstream_load_forms_are_legacy(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = tracked_repo(tmp, {
                "skills/principle-prove-it-works/SKILL.md": "Prove it.\n",
                "skills/demo/SKILL.md": "Run the **demo** skill over it.\n- Any code → the **demo** skill.\n"
                                        "Log it via the **demo** skill.\nCheck it, per the **demo** skill.\n"
                                        "Route through the **demo** skill.\nApply the **demo** skill.\n"
                                        "Verify it (the **principle-prove-it-works** skill).\n"
                                        "Verify it (**principle-prove-it-works**).\nThen run `demo` on it.\n"
                                        "Spawn per the Subagents section of the **demo** skill.\n"
                                        "See the **demo** and **principle-prove-it-works** skills.\nRead the\n**demo** skill.\n"
                                        "State it with the **demo** skill.\nRun Phase B of the **demo** skill.\n"
                                        "Shape them with the **principle-prove-it-works** principle skill.\n",
            })
            self.assertEqual([row.split(":")[1] for row in skill_references.legacy_loads(root)],
                             ["1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "12", "14", "15", "16"])

    def test_a_not_load_passage_is_exempt_only_where_it_stands(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = tracked_repo(tmp, {
                "skills/demo/SKILL.md": "Owners do a comment review with the **demo** skill.\nCheck it with the **demo** skill.\n",
            })
            with mock.patch.object(skill_references, "NOT_LOADS",
                                   {"skills/demo/SKILL.md": ["a comment review with the **demo** skill"]}):
                self.assertEqual(skill_references.legacy_loads(root), ["skills/demo/SKILL.md:2: with the **demo** skill"])

    def test_descriptions_index_labels_and_headings_are_not_loads(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = tracked_repo(tmp, {
                "skills/principle-prove-it-works/SKILL.md": "Prove it.\n",
                "skills/demo/SKILL.md": "The **demo** skill owns prose.\nA complement to the **demo** skill.\n"
                                        "- **Prove It Works** (**principle-prove-it-works**). After a task.\n"
                                        "## Proof (**principle-prove-it-works**)\nEvery owner uses the **demo** skill.\n",
            })
            self.assertEqual(skill_references.legacy_loads(root), [])

    def test_a_skill_tool_name_must_exist(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = tracked_repo(tmp, {
                "skills/demo/SKILL.md": "Call the Skill tool with `demo`.\ncall the Skill tool with `missing`, then go.\n",
            })
            self.assertEqual(skill_references.unresolved_names(root), ["skills/demo/SKILL.md:2: `missing`"])

    def test_model_facing_text_names_only_skills_that_exist(self):
        self.assertEqual(skill_references.unresolved_names(), [],
                         "write the skill's full directory name, such as **principle-prove-it-works**")

    def test_a_principle_named_without_its_prefix_is_unresolved(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = tracked_repo(tmp, {
                "skills/principle-prove-it-works/SKILL.md": "Prove it.\n",
                "skills/demo/SKILL.md": "Use the **prove-it-works** principle skill.\nPer (**prove-it-works**).\n"
                                        "Use the **principle-prove-it-works** skill.\n",
            })
            self.assertEqual(skill_references.unresolved_names(root),
                             ["skills/demo/SKILL.md:1: **prove-it-works**", "skills/demo/SKILL.md:2: **prove-it-works**"])

    def test_a_bold_name_before_skill_must_exist(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = tracked_repo(tmp, {
                "skills/demo/SKILL.md": "Use the **demo** skill.\nUse the **missing** skill.\n"
                                        "**Use** the skill.\nA **bold-phrase** here, then a skill.\n",
            })
            self.assertEqual(skill_references.unresolved_names(root), ["skills/demo/SKILL.md:2: **missing**"])

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
            with mock.patch.object(skill_references, "EXEMPT", table), mock.patch.object(skill_references, "NOT_LOADS", {}):
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
