#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import tomllib
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = (ROOT / ".github" / "workflows" / "lint.yml").read_text(encoding="utf-8")
SHARED_WORKFLOW = (ROOT / ".github" / "workflows" / "skill-checks.yml").read_text(encoding="utf-8")
PIN = tomllib.loads((ROOT / ".skill-ci.toml").read_text(encoding="utf-8"))
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
        self.assertIn('bun-version: "1.4.0"', WORKFLOW)
        self.assertIn("bun install --frozen-lockfile", WORKFLOW)
        self.assertIn("bun run test", WORKFLOW)
        self.assertIn("bun run typecheck", WORKFLOW)

    def test_skill_checks_run_the_version_the_pin_names(self) -> None:
        self.assertIn("permissions:\n  contents: read", SHARED_WORKFLOW)
        self.assertNotRegex(SHARED_WORKFLOW, r"(?m)^\s+uses: mdsmithaustin/skill-ci/")
        self.assertIn('uv tool run --from "git+$SKILL_CI_SOURCE" skill-ci check', SHARED_WORKFLOW)
        self.assertRegex(PIN["version"], r"^v\d+\.\d+\.\d+$")
        self.assertEqual(
            PIN,
            {
                "version": PIN["version"],
                "skills_dir": "skills",
                "evals_dir": "evals",
                "trigger_cases": "tools/skill-trigger-cases.json",
                "pii_scope": "repository",
                "content_conventions_file": "tools/skill-content-conventions.json",
            },
        )

    def test_only_lint_reports_the_required_skills_context(self) -> None:
        reporting = []
        for path in sorted((ROOT / ".github" / "workflows").glob("*.y*ml")):
            workflow = re.sub(
                r'''("(?:\\.|[^"\\])*"|'(?:''|[^'])*')| #[^\n]*''',
                lambda match: match.group(1) or "",
                path.read_text(encoding="utf-8"),
            )
            jobs = re.search(r"(?ms)^jobs:\n(.*?)(?=^\S|\Z)", workflow).group(1)
            for job_id, body in re.findall(r"(?ms)^  ([\w-]+):\s*\n(.*?)(?=^  \S|\Z)", jobs):
                name = re.search(r"(?m)^    name:\s*['\"]?(.*?)['\"]?\s*$", body)
                job_name = name.group(1) if name else None
                if "skills" in (job_id, job_name):
                    reporting.append((path.name, job_id, job_name))
        self.assertEqual(reporting, [("lint.yml", "skills", None)])

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

    def test_hook_keeps_the_fast_contract(self) -> None:
        hook = (ROOT / "lefthook.yml").read_text(encoding="utf-8")
        python_runs = re.findall(r"^\s+run: (.*python.*)$", hook, re.MULTILINE)
        self.assertEqual(python_runs, ["'{python} tools/check-cross-suite-references.py --foreign-file tools/cross-suite-foreign.txt skills'"])
        self.assertIn("""python: '"$(git rev-parse --path-format=absolute --git-common-dir)/../.venv/bin/python"'""", hook)
        self.assertIn("    skill-ci-check-fast:\n      run: skill-ci check --fast\n", hook)
        self.assertIn("pre-push:\n  commands:\n    skill-ci-check:\n      run: skill-ci check\n", hook)


if __name__ == "__main__":
    unittest.main()
