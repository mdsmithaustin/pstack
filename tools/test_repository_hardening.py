#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = (ROOT / ".github" / "workflows" / "lint.yml").read_text(encoding="utf-8")
RULESET = json.loads((ROOT / ".github" / "rulesets" / "copilot-code-review.json").read_text(encoding="utf-8"))


class RepositoryHardening(unittest.TestCase):
    def test_skills_job_has_read_only_pinned_tooling_and_required_checks(self) -> None:
        self.assertIn("permissions:\n  contents: read", WORKFLOW)
        self.assertIn("  skills:\n", WORKFLOW)
        self.assertNotIn("setup-node", WORKFLOW)
        action_references = re.findall(r"^\s*- uses: (\S+)", WORKFLOW, re.MULTILINE)
        self.assertGreaterEqual(len(action_references), 3)
        for action_reference in action_references:
            self.assertRegex(action_reference, r"^[^@\s]+@[0-9a-f]{40}$")
        self.assertIn('python-version: "3.12"', WORKFLOW)
        self.assertIn("pip install --require-hashes -r tools/requirements.txt", WORKFLOW)
        self.assertIn("check-skill-frontmatter.py skills --triggers tools/skill-trigger-cases.json", WORKFLOW)
        self.assertIn('bun-version: "1.4.0"', WORKFLOW)
        self.assertIn("bun install --frozen-lockfile", WORKFLOW)
        self.assertIn("bun run test", WORKFLOW)
        self.assertIn("bun run typecheck", WORKFLOW)

    def test_ruleset_has_required_branch_protections(self) -> None:
        self.assertEqual(RULESET["enforcement"], "active")
        self.assertEqual(RULESET["conditions"]["ref_name"]["include"], ["~DEFAULT_BRANCH"])
        rules = {rule["type"]: rule.get("parameters", {}) for rule in RULESET["rules"]}
        self.assertIn("copilot_code_review", rules)
        pull_request = rules["pull_request"]
        self.assertEqual(pull_request["required_approving_review_count"], 0)
        self.assertTrue(pull_request["required_review_thread_resolution"])
        self.assertTrue(pull_request["dismiss_stale_reviews_on_push"])
        self.assertFalse(pull_request["require_extra_approval_for_unattributed_changes"])
        self.assertEqual(pull_request["required_reviewers"], [])
        self.assertEqual(set(pull_request["allowed_merge_methods"]), {"merge", "squash", "rebase"})
        status = rules["required_status_checks"]
        self.assertTrue(status["strict_required_status_checks_policy"])
        self.assertIn({"context": "skills", "integration_id": 15368}, status["required_status_checks"])
        self.assertIn("deletion", rules)
        self.assertIn("non_fast_forward", rules)

    def test_hook_and_manifest_keep_the_fast_and_frozen_contract(self) -> None:
        hook = (ROOT / "lefthook.yml").read_text(encoding="utf-8")
        python_runs = re.findall(r"^\s+run: (.*python.*)$", hook, re.MULTILINE)
        self.assertEqual(len(python_runs), 4)
        self.assertTrue(all(command.startswith(".venv/bin/python ") for command in python_runs))
        self.assertIn(".venv/bin/python tools/check-skill-frontmatter.py skills --triggers tools/skill-trigger-cases.json", hook)
        self.assertIn(".venv/bin/python tools/check-skill-content.py skills", hook)
        self.assertIn(".venv/bin/python tools/check-cross-suite-references.py", hook)
        self.assertIn(".venv/bin/python tools/check-pii.py --staged", hook)
        manifest = json.loads((ROOT / "skills" / "poteto-mode" / "scripts" / "package.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["devDependencies"]["bun-types"], "1.3.14")
        self.assertEqual(manifest["devDependencies"]["typescript"], "7.0.2")


if __name__ == "__main__":
    unittest.main()
