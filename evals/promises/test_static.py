import hashlib
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GUIDE = ROOT / "docs" / "guide"
SKILLS = ROOT / "skills"
POTETO = SKILLS / "poteto-mode" / "SKILL.md"
PLAYBOOKS = SKILLS / "poteto-mode" / "playbooks"

PLAYBOOK_FILES = [
    "authoring-a-skill",
    "autonomous-run",
    "autopilot-full",
    "autopilot-stack",
    "babysit",
    "bug-fix",
    "code-review",
    "eval",
    "feature",
    "hillclimb",
    "investigation",
    "multi-phase-plan",
    "opening-a-pr",
    "orchestrate",
    "pause-safely",
    "perf-issue",
    "prototype",
    "refactoring",
    "research",
    "runtime-forensics",
    "session-pickup",
    "shipping",
    "trace-forensics",
    "visual-parity",
    "worktree-cleanup",
]

PRINCIPLE_RULES = {
    "principle-laziness-protocol": "Bias toward deletion and the smallest change that solves the problem.",
    "principle-foundational-thinking": "choosing core types and data structures",
    "principle-redesign-from-first-principles": "foundational assumption from day one",
    "principle-attack-the-premise": "question the premise",
    "principle-subtract-before-you-add": "then build on the simpler base",
    "principle-minimize-reader-load": "collapse one-caller wrappers",
    "principle-outcome-oriented-execution": "Converge on the target architecture",
    "principle-experience-first": "Choose user delight over implementation convenience",
    "principle-exhaust-the-design-space": "Build 2-3 competing prototypes",
    "principle-build-the-lever": "The tool is the artifact a reviewer can rerun.",
    "principle-model-the-domain": "Encode the domain in a structure instead of scattered conditionals.",
    "principle-boundary-discipline": "trust internal types",
    "principle-type-system-discipline": "Make illegal states unrepresentable",
    "principle-make-operations-idempotent": "Converge to the same end state",
    "principle-migrate-callers-then-delete-legacy-apis": "delete the old API in the same wave",
    "principle-separate-before-serializing-shared-state": "Eliminate the sharing first",
    "principle-prove-it-works": "Verify against the real artifact",
    "principle-fix-root-causes": "reproduce first",
    "principle-sequence-verifiable-units": "check each before the next",
    "principle-test-behavior-not-implementation": "every imported function returns undefined",
    "principle-guard-the-context-window": "Route bulk to subagents",
    "principle-never-block-on-the-human": "Proceed, present the result",
    "principle-encode-lessons-in-structure": "Encode the rule as a lint, metadata flag, runtime check, or script",
}

GUIDE_SLASH_SKILLS = {
    "how", "why", "poteto-teach", "recall", "architect", "arena", "swarm", "interrogate",
    "poteto-tdd", "unslop", "no-comments", "blast-radius", "create-verification-skill",
    "maintain-verification-skill", "documentation-impact", "show-me-your-work", "figure-it-out",
    "automate-me", "reflect", "technical-writing", "bro", "setup-pstack", "poteto-mode",
}
GUIDE_LINKED_SKILLS = GUIDE_SLASH_SKILLS | {"typescript-best-practices"} | {
    "principle-laziness-protocol", "principle-foundational-thinking",
    "principle-redesign-from-first-principles", "principle-attack-the-premise",
    "principle-subtract-before-you-add", "principle-minimize-reader-load",
    "principle-outcome-oriented-execution", "principle-experience-first",
    "principle-exhaust-the-design-space", "principle-build-the-lever", "principle-model-the-domain",
    "principle-boundary-discipline", "principle-type-system-discipline",
    "principle-make-operations-idempotent", "principle-migrate-callers-then-delete-legacy-apis",
    "principle-separate-before-serializing-shared-state", "principle-prove-it-works",
    "principle-fix-root-causes", "principle-sequence-verifiable-units",
    "principle-test-behavior-not-implementation", "principle-guard-the-context-window",
    "principle-never-block-on-the-human", "principle-encode-lessons-in-structure",
}
GUIDE_SLASH_NON_SKILLS = {"loop": "loop-is-harness-facility-not-pstack", "deslop": "deslop-available-for-code"}

ROUTER_ROUTES = {
    "Code or history question": "Investigation",
    "External or domain evidence": "Research",
    "Defect": "Bug fix",
    "New behavior": "Feature",
    "Structure only": "Refactoring",
    "Someone else's PR or diff": "Code review",
    "Measured slowness": "Perf issue",
    "Large work or no match": "figure-it-out",
}


def read(path):
    return path.read_text(encoding="utf-8")


def normalize(text):
    return " ".join(text.split())


def section(text, heading, next_level="## "):
    start = text.index(heading)
    rest = text[start + len(heading):]
    end = rest.find("\n" + next_level)
    return rest if end < 0 else rest[:end]


def poteto_playbook_bullets():
    body = section(read(POTETO), "\n## Playbooks\n")
    return re.findall(r"^- \*\*(.+?)\.\*\* .*?`playbooks/([a-z-]+)\.md`", body, flags=re.M)


def guide_text():
    return "\n".join(read(p) for p in sorted(GUIDE.glob("*.md")))


def first_mermaid_block(path):
    text = read(path)
    start = text.index("```mermaid")
    end = text.index("```", start + 10)
    return text[start:end]


class TestStaticPromises(unittest.TestCase):
    def test_twenty_five_playbooks(self):
        bullets = poteto_playbook_bullets()
        self.assertEqual(len(bullets), 25)
        self.assertEqual(sorted(f for _, f in bullets), PLAYBOOK_FILES)
        on_disk = sorted(p.stem for p in PLAYBOOKS.glob("*.md"))
        self.assertEqual(on_disk, PLAYBOOK_FILES)
        self.assertEqual(len(list(PLAYBOOKS.iterdir())), 25)

    def test_twenty_three_principle_skills(self):
        on_disk = sorted(p.parent.name for p in SKILLS.glob("principle-*/SKILL.md"))
        self.assertEqual(len(on_disk), 23)
        self.assertEqual(on_disk, sorted(PRINCIPLE_RULES))
        index = section(read(POTETO), "\n## Principles\n")
        listed = sorted(set(re.findall(r"\(\*\*(principle-[a-z-]+)\*\*\)", index)))
        self.assertEqual(listed, on_disk)

    def test_principle_leaf_summaries_match(self):
        page = read(GUIDE / "08-principles.md")
        links = re.findall(r"\[[^\]]+\]\(\.\./\.\./skills/(principle-[a-z-]+)/SKILL\.md\)", page)
        self.assertEqual(len(links), 23)
        self.assertEqual(sorted(links), sorted(PRINCIPLE_RULES))
        for name, rule in PRINCIPLE_RULES.items():
            leaf = SKILLS / name / "SKILL.md"
            self.assertTrue(leaf.is_file(), name)
            self.assertIn(rule, normalize(read(leaf)), name)

    def test_playbook_directory_complete(self):
        text = guide_text()
        self.assertIn("(../../skills/poteto-mode/playbooks/)", text)
        self.assertTrue(PLAYBOOKS.is_dir())
        linked = sorted(set(re.findall(r"skills/poteto-mode/playbooks/([a-z-]+)\.md", text)))
        self.assertEqual(
            linked,
            [
                "authoring-a-skill", "autonomous-run", "autopilot-full", "autopilot-stack", "babysit",
                "bug-fix", "code-review", "eval", "feature", "hillclimb", "opening-a-pr", "orchestrate",
                "perf-issue", "refactoring", "research", "session-pickup", "shipping", "worktree-cleanup",
            ],
        )
        for name in linked:
            self.assertTrue((PLAYBOOKS / f"{name}.md").is_file(), name)
        for name in PLAYBOOK_FILES:
            self.assertTrue((PLAYBOOKS / f"{name}.md").is_file(), name)

    def test_guide_named_skills_exist(self):
        text = guide_text()
        slashed = set(re.findall(r"`/([a-z][a-z0-9-]*)`", text))
        self.assertEqual(slashed - set(GUIDE_SLASH_NON_SKILLS), GUIDE_SLASH_SKILLS)
        linked = set(re.findall(r"\.\./\.\./skills/([a-z0-9-]+)/SKILL\.md", text))
        self.assertEqual(linked, GUIDE_LINKED_SKILLS)
        self.assertEqual(len(linked), 47)
        for name in GUIDE_LINKED_SKILLS:
            self.assertTrue((SKILLS / name / "SKILL.md").is_file(), name)
        for name in GUIDE_SLASH_NON_SKILLS:
            self.assertFalse((SKILLS / name).exists(), name)

    def test_router_diagram_routes_match_selector(self):
        block = first_mermaid_block(GUIDE / "02-poteto-mode.md")
        routes = dict(re.findall(r"D -->\|([^|]+)\| [A-Z]+\[([^\]]+)\]", block))
        self.assertEqual(routes, ROUTER_ROUTES)
        self.assertIn("B --> C[Read the Principles section]", block)
        skill = read(POTETO)
        self.assertIn("The Principles section below grounds every trigger.", skill)
        selector = {name for name, _ in poteto_playbook_bullets()}
        for target in ROUTER_ROUTES.values():
            if target == "figure-it-out":
                self.assertIn("Use **figure-it-out** whenever no bundled playbook fits.", skill)
            else:
                self.assertIn(target, selector)

    def test_feature_map_example_shipped(self):
        example = SKILLS / "create-verification-skill" / "references" / "feature-map-example"
        self.assertIn("[`references/feature-map-example/`](references/feature-map-example/)",
                      read(SKILLS / "create-verification-skill" / "SKILL.md"))
        readme = read(example / "README.md")
        features = sorted(p.name for p in example.glob("*.md") if p.name != "README.md")
        self.assertEqual(features, ["create-note.md", "search.md"])
        for name in features:
            self.assertIn(f"(./{name})", readme)
            headings = re.findall(r"^## (.+)$", read(example / name), flags=re.M)
            self.assertEqual(headings[0], "Sub-features", name)
            self.assertEqual(headings[1], "How to get to it (user POV)", name)
            self.assertTrue(headings[2].startswith("Driving it with "), name)
            self.assertEqual(headings[3], "Gotchas", name)
            self.assertEqual(len(headings), 4, name)

    def test_verification_skill_has_five_sections(self):
        text = read(SKILLS / "create-verification-skill" / "SKILL.md")
        generate = section(text, "\n## 2. Generate the skill\n")
        labels = re.findall(r"^- \*\*([A-Za-z]+):\*\*", generate, flags=re.M)
        self.assertEqual(labels, ["Launch", "Doctor", "Drive", "Evidence", "Cleanup", "Helpers"])
        self.assertIn("Write `.agents/skills/verify-<app>/SKILL.md`", text)
        self.assertIn("Create `.agents/skills/verify-<app>/features/README.md`", text)

    def test_loop_is_harness_facility_not_pstack(self):
        self.assertFalse((SKILLS / "loop").exists())
        self.assertIn("not a pstack skill", read(PLAYBOOKS / "autonomous-run.md"))

    def test_research_playbook_bundled(self):
        self.assertFalse((SKILLS / "research").exists())
        self.assertTrue((PLAYBOOKS / "research.md").is_file())
        self.assertIn("`playbooks/research.md`", read(POTETO))

    def test_comment_sicko_keep_list(self):
        agent = read(ROOT / "agents" / "comment-sicko.md")
        body = agent.split("---\n", 2)[2]
        roles = json.loads(read(SKILLS / "pstack-harness" / "references" / "subagents" / "roles.json"))
        role = next(r for r in roles["roles"] if r["id"] == "comment-sicko")
        self.assertEqual(role["body"], body)
        self.assertEqual(role["source_sha256"], hashlib.sha256(agent.encode("utf-8")).hexdigest())
        keeps = re.findall(r"^- (.+)$", section(agent, "Only these exceptions get to crawl away.\n", "\n"), flags=re.M)
        self.assertEqual(len(keeps), 5)


if __name__ == "__main__":
    unittest.main()
