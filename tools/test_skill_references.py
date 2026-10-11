import importlib.util
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("skill_references", ROOT / "tools" / "skill-references.py")
skill_references = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(skill_references)

USER_FACING_SKILLS = frozenset({"poteto-help"})
USER_FACING = {
    "skills/architect/SKILL.md": ["Use for /architect,", '"/architect with checkpoint,"'],
    "skills/arena/SKILL.md": ["Use for /arena,"],
    "skills/correct/SKILL.md": ["Use for /correct."],
    "skills/create-verification-skill/SKILL.md": ["Use for /create-verification-skill,",
                                                  "Point the user at `/maintain-verification-skill`"],
    "skills/deslop/SKILL.md": ["Use for /deslop,", "and on `/deslop`,"],
    "skills/figure-it-out/SKILL.md": ["Use for /figure-it-out or"],
    "skills/ketchup/SKILL.md": ["Use for /ketchup.", "the last message they wrote before `/ketchup`"],
    "skills/maintain-verification-skill/SKILL.md": ["Use for /maintain-verification-skill",
                                                    "point at `/create-verification-skill`"],
    "skills/poteto-mode/SKILL.md": ["Use for poteto, /poteto-mode,"],
    "skills/pstack-harness/SKILL.md": ["Run `/setup-pstack` to register it.\""],
    "skills/reflect/SKILL.md": ['the user says "reflect" or "/reflect"'],
    "skills/setup-pstack/SKILL.md": ["Use for /setup-pstack,", "4 of 4 `/poteto-mode` runs",
                                     "I can generate one with /create-verification-skill.\""],
    "skills/show-me-your-work/SKILL.md": ["Use for /show-me-your-work,"],
    "skills/swarm/SKILL.md": ["Use for /swarm,"],
    "skills/technical-writing/SKILL.md": ["Use for /technical-writing"],
}
# A mode's `reminder:` frontmatter reaches the model every turn while that mode is on. It names
# the mode already active, so it is model-facing text that loads nothing.
MODE_REMINDERS = {
    "skills/poteto-mode/SKILL.md": ["apply /poteto-mode."],
}
EXEMPT = {rel: USER_FACING.get(rel, []) + MODE_REMINDERS.get(rel, []) for rel in USER_FACING | MODE_REMINDERS}


def exempt(rel, spelling, line):
    if rel.split("/")[1] in USER_FACING_SKILLS:
        return True
    return any(spelling in passage and passage in line for passage in EXEMPT.get(rel, ()))


class SkillReferenceSpelling(unittest.TestCase):
    def test_model_facing_text_never_spells_a_skill_with_a_slash_or_dollar(self):
        found = [f"{rel}:{number}: {spelling}" for rel, number, spelling, line in skill_references.sigils()
                 if not exempt(rel, spelling, line)]
        self.assertEqual(found, [], 'write "Use the **name** skill." as its own sentence or step; a passage that '
                                    "quotes the user or text shown to the user goes in USER_FACING")

    def test_every_exempt_passage_still_matches(self):
        hits = skill_references.sigils()
        stale = [f"{rel}: {passage}" for rel, passages in EXEMPT.items() for passage in passages
                 if not any(r == rel and spelling in passage and passage in line for r, _, spelling, line in hits)]
        self.assertEqual(stale, [], "remove USER_FACING or MODE_REMINDERS passages that no longer hold a "
                                    "/name or $name spelling")

    def test_the_scan_skips_untracked_markdown(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "skills/demo/node_modules").mkdir(parents=True)
            (root / "skills/demo/SKILL.md").write_text("Then run /demo.\n")
            (root / "skills/demo/node_modules/README.md").write_text("Run /demo here too.\n")
            subprocess.run(["git", "init", "-q", tmp], check=True)
            subprocess.run(["git", "-C", tmp, "add", "skills/demo/SKILL.md"], check=True)
            self.assertEqual(skill_references.sigils(root),
                             [("skills/demo/SKILL.md", 1, "/demo", "Then run /demo.")])

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
                             [("skills/demo/SKILL.md", 1, "/demo", "Then run /demo.")])

    def test_the_scan_finds_a_slash_and_a_dollar_spelling(self):
        names = skill_references.skill_names(ROOT)
        sigil = skill_references.sigil_pattern("deslop")
        self.assertIn("deslop", names)
        self.assertEqual([m.group(0) for m in sigil.finditer("Run `/deslop`, then $deslop, not skills/deslop/x.")],
                         ["/deslop", "$deslop"])


if __name__ == "__main__":
    unittest.main()
