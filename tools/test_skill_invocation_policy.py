import importlib.util
import re
import unittest
from pathlib import Path

SKILLS = Path(__file__).resolve().parents[1] / "skills"
FRONTMATTER = re.compile(r"\A---\n(.*?)\n---\n", re.S)
FLAG = re.compile(r"^disable-model-invocation\s*:", re.M)

_spec = importlib.util.spec_from_file_location("skill_listing", SKILLS / "setup-pstack/scripts/skill-listing.py")
skill_listing = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(skill_listing)


class SkillInvocationPolicy(unittest.TestCase):
    def test_no_skill_sets_disable_model_invocation(self):
        flagged = [p.parent.name for p in sorted(SKILLS.glob("*/SKILL.md"))
                   if FLAG.search(FRONTMATTER.match(p.read_text(encoding="utf-8")).group(1))]
        self.assertEqual(flagged, [], "the Skill tool refuses these skills by name; gate them with agents/openai.yaml")

    def test_listing_inventory_names_every_skill(self):
        shipped = sorted(p.parent.name for p in SKILLS.glob("*/SKILL.md"))
        self.assertEqual(sorted(skill_listing.PSTACK_SKILLS), shipped,
                         "PSTACK_SKILLS in skills/setup-pstack/scripts/skill-listing.py must name exactly the skills/ directories")


if __name__ == "__main__":
    unittest.main()
