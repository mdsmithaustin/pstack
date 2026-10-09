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

# Skills that load from their description on every harness. Every other skill ships
# agents/openai.yaml with allow_implicit_invocation: false, which gates it on Codex and
# puts it in setup-pstack's Claude Code name-only listing.
AUTO_INVOCABLE = frozenset({
    "deslop", "documentation-impact", "how", "pstack-harness", "runtime-probes",
    "setup-pstack", "spec-probes", "unslop", "verify-commands", "why",
})


class SkillInvocationPolicy(unittest.TestCase):
    def test_no_skill_sets_disable_model_invocation(self):
        flagged = [p.parent.name for p in sorted(SKILLS.glob("*/SKILL.md"))
                   if FLAG.search(FRONTMATTER.match(p.read_text(encoding="utf-8")).group(1))]
        self.assertEqual(flagged, [], "the Skill tool refuses these skills by name; gate them with agents/openai.yaml")

    def test_every_skill_is_gated_or_listed_as_auto_invocable(self):
        open_skills = set(skill_listing.skill_dirs(SKILLS)) - set(skill_listing.managed_skills(SKILLS))
        self.assertEqual(sorted(open_skills - AUTO_INVOCABLE), [],
                         "add agents/openai.yaml with policy.allow_implicit_invocation: false, or add the skill to AUTO_INVOCABLE")
        self.assertEqual(sorted(AUTO_INVOCABLE - open_skills), [],
                         "AUTO_INVOCABLE names a skill that is gated or no longer exists")


if __name__ == "__main__":
    unittest.main()
