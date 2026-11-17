#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import subprocess
import textwrap
import tomllib
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = (ROOT / ".github" / "workflows" / "lint.yml").read_text(encoding="utf-8")
SHARED_WORKFLOW = (ROOT / ".github" / "workflows" / "skill-checks.yml").read_text(encoding="utf-8")
PIN = tomllib.loads((ROOT / ".skill-ci.toml").read_text(encoding="utf-8"))
RULESET = json.loads((ROOT / ".github" / "rulesets" / "copilot-code-review.json").read_text(encoding="utf-8"))


def workflow_job_models(workflow: str) -> dict:
    def scalar(value: str) -> str:
        value = re.sub(r"\s+#.*$", "", value).strip()
        if value.startswith(('"', "'")):
            value = value[1:-1]
        if value.startswith("${{") and value.endswith("}}"):
            value = value[3:-2].strip()
        return value

    jobs_block = re.search(r"(?ms)^jobs:\s*\n(.*?)(?=^\S|\Z)", workflow).group(1)
    models = {}
    for job, body in re.findall(r"(?ms)^  ([\w-]+):[^\S\n]*\n(.*?)(?=^  \S|\Z)", jobs_block):
        fields = {}
        for key, first, continuation in re.findall(
            r"(?m)^    ([\w-]+):([^\n]*)(\n(?:(?:[ ]{5,}[^\n]*|)\n)*)", body
        ):
            fields[key] = (scalar(first), continuation)
        first, continuation = fields.get("needs", ("", ""))
        if first.startswith("["):
            value = first + " ".join(scalar(line) for line in continuation.splitlines())
            needs = [scalar(item) for item in value[1:-1].split(",") if item.strip()]
        elif first:
            needs = [first]
        else:
            needs = [scalar(item) for item in re.findall(r"(?m)^\s+- (.+)$", continuation)]
        results = re.findall(r"(?m)^          RESULTS:([^\n]*)$", body)
        scripts = [textwrap.dedent(block) for block in re.findall(
            r"(?m)^        run: \|[+-]?[^\S\n]*\n((?:[ ]{10}[^\n]*\n|\n)+)", body
        )]
        models[job] = {
            "needs": needs,
            "if": fields.get("if", ("", ""))[0],
            "results": scalar(results[0]) if len(results) == 1 else None,
            "scripts": scripts,
        }
    return models


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
                "invocation_policy": "openai-yaml",
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

    def test_required_skills_gate_waits_for_every_skills_job(self) -> None:
        jobs = workflow_job_models(WORKFLOW)
        parts = {job for job in jobs if job.startswith("skills-")}
        self.assertGreaterEqual(len(parts), 2)
        gate = jobs["skills"]
        self.assertEqual(set(gate["needs"]), parts)
        self.assertEqual(gate["if"], "always()")

    def test_required_skills_gate_accepts_only_successful_results(self) -> None:
        jobs = workflow_job_models(WORKFLOW)
        gate = jobs["skills"]
        self.assertEqual(gate["results"], "toJSON(needs)")
        self.assertEqual(len(gate["scripts"]), 1)
        script = gate["scripts"][0]
        commands = [shlex.split(line, comments=True) for line in script.splitlines()]
        filters = [command[i + 2] for command in commands
                   for i, token in enumerate(command[:-2])
                   if token == "jq" and command[i + 1] == "-e"]
        self.assertEqual(len(filters), 1, "expected one jq exit-status filter")
        jq = shutil.which("jq")
        if jq is None:
            self.skipTest("jq is absent from PATH; cannot execute the skills gate")
        successful = {job: {"result": "success"} for job in gate["needs"]}
        cases = [("all successful", successful, 0), ("empty", {}, 1)]
        for job in successful:
            for result in ("failure", "skipped", "cancelled"):
                cases.append((f"{job}: {result}",
                              {**successful, job: {"result": result}}, 1))
        for name, results, expected in cases:
            with self.subTest(case=name):
                payload = json.dumps(results)
                filtered = subprocess.run(
                    [jq, "-e", filters[0]], input=payload,
                    capture_output=True, text=True, timeout=10,
                )
                self.assertEqual(filtered.returncode, expected, filtered.stderr)
                executed = subprocess.run(
                    ["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", script],
                    env={**os.environ, "RESULTS": payload},
                    capture_output=True, text=True, timeout=10,
                )
                self.assertEqual(executed.returncode, expected, executed.stderr)

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
        hook = json.loads((ROOT / "lefthook.yml").read_text(encoding="utf-8"))
        commit = hook["pre-commit"]["commands"]
        push = hook["pre-push"]["commands"]
        self.assertEqual(commit["cross-suite-references"]["run"],
                         "{python} tools/check-cross-suite-references.py --foreign-file tools/cross-suite-foreign.txt skills")
        self.assertEqual(commit["personal-paths"]["run"],
                         "{python} tools/check-personal-paths.py --source index")
        self.assertEqual(push["personal-paths"]["run"],
                         "{python} tools/check-personal-paths.py --source pre-push")
        self.assertTrue(push["personal-paths"]["use_stdin"])
        self.assertEqual(hook["templates"]["python"],
                         '\"$(git rev-parse --path-format=absolute --git-common-dir)/../.venv/bin/python\"')
        self.assertEqual(commit["skill-ci-check-fast"]["run"], "skill-ci check --fast")
        self.assertEqual(push["skill-ci-check"]["run"], "skill-ci check")


if __name__ == "__main__":
    unittest.main()
