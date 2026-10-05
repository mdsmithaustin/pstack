#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SKILLS = ROOT / "skills"
RESOLVER = SKILLS / "setup-pstack/scripts/check-models-config.py"
SHIPPED_DEFAULTS = SKILLS / "setup-pstack/examples/pstack-models.md"
SUBAGENTS = SKILLS / "pstack-harness/scripts/subagents.py"
LOG_SH = SKILLS / "show-me-your-work/scripts/log.sh"
AUDIT_SH = SKILLS / "poteto-mode/scripts/worktree-audit.sh"
WATCH_DIR = SKILLS / "poteto-mode/scripts/watch-pr"
MERGE_GATE = WATCH_DIR / "merge-gate"
WATCH_PR = WATCH_DIR / "watch-pr"

HARNESSES = ("claude-code", "codex", "hermes", "grok")
ORIGIN_URL = "https://github.com/octo/widgets.git"
REAL_GIT = shutil.which("git") or "git"
INHERIT = "inherit-parent"


def scrubbed_env(home: Path, extra_path: Path | None = None) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith(("GH_", "GITHUB_", "PSTACK_", "FAKE_", "CODEX_"))}
    env.update(
        HOME=str(home),
        CODEX_HOME=str(home / ".codex"),
        XDG_CONFIG_HOME=str(home / ".config"),
        GIT_CONFIG_GLOBAL=str(home / ".gitconfig"),
        GIT_CONFIG_NOSYSTEM="1",
        GIT_AUTHOR_NAME="pstack-test",
        GIT_AUTHOR_EMAIL="pstack-test@example.com",
        GIT_COMMITTER_NAME="pstack-test",
        GIT_COMMITTER_EMAIL="pstack-test@example.com",
    )
    if extra_path is not None:
        env["PATH"] = f"{extra_path}{os.pathsep}{env.get('PATH', '')}"
    return env


class Sandbox(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="pstack-promise-")
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name).resolve()
        self.home = self.tmp / "home"
        self.project = self.tmp / "project"
        self.home.mkdir()
        self.project.mkdir()
        self.env = scrubbed_env(self.home)

    def run_cmd(self, argv, cwd=None, env=None, expect=None, input=None):
        result = subprocess.run(
            [str(a) for a in argv], cwd=cwd or self.project, env=env or self.env,
            capture_output=True, text=True, input=input, timeout=180,
        )
        if expect is not None:
            self.assertEqual(result.returncode, expect, f"{argv}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}")
        return result

    def git(self, *args, cwd=None, env=None):
        result = subprocess.run(
            [REAL_GIT, *args], cwd=cwd or self.project, env=env or self.env,
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(result.returncode, 0, f"git {args}\n{result.stderr}")
        return result.stdout


class ResolverSandbox(Sandbox):
    def write_user(self, text: str) -> Path:
        path = self.home / ".agents" / "pstack-models.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def write_workspace(self, text: str) -> Path:
        path = self.project / ".agents" / "pstack-models.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def resolve(self, harness: str, *roles: str) -> list[dict]:
        result = self.run_cmd(
            [sys.executable, RESOLVER, "--resolve", "--harness", harness, "--project", self.project, *roles],
            expect=0,
        )
        self.assertEqual(result.stderr, "")
        return [json.loads(line) for line in result.stdout.splitlines()]


def arm(role, n, model, effort, source, **extra):
    return {"role": role, "arm": n, "model": model, "effort": effort, "source": source, **extra}


def shipped_entries(role: str, harness: str) -> list[str]:
    section = ""
    sections: dict[str, dict[str, list[str]]] = {"": {}}
    for raw in SHIPPED_DEFAULTS.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line.startswith("## "):
            section = line[3:].strip()
            sections.setdefault(section, {})
        elif line and not line.startswith("#") and ":" in line and line != "---":
            names, entries = line.split(":", 1)
            for name in (n.strip() for n in names.split(",")):
                sections[section][name] = [e.strip() for e in entries.split(",")]
    for scope in (harness, ""):
        if role in sections.get(scope, {}):
            return sections[scope][role]
    raise AssertionError(f"{role} not in {SHIPPED_DEFAULTS}")



FAKE_GH = r'''#!__PY__
import json, os, sys

argv = sys.argv[1:]
state_path = os.environ["FAKE_GH_STATE"]
with open(state_path, encoding="utf-8") as stream:
    state = json.load(stream)
with open(os.environ["FAKE_GH_CALLS"], "a", encoding="utf-8") as stream:
    stream.write(json.dumps(argv) + "\n")


def out(value, code=0):
    print(json.dumps(value))
    sys.exit(code)


def opt(name):
    return argv[argv.index(name) + 1] if name in argv else None


def save():
    with open(state_path, "w", encoding="utf-8") as stream:
        json.dump(state, stream)


pr = state.get("pr", {})
head = pr.get("headRefOid")
if argv[:2] == ["pr", "view"]:
    fields = opt("--json")
    if fields.startswith("state,mergedAt"):
        if state.get("merged"):
            out({"state": "MERGED", "mergedAt": "2026-01-02T03:04:05Z", "mergeCommit": {"oid": "c" * 40}})
        out({"state": "OPEN", "mergedAt": None, "mergeCommit": None})
    if fields.startswith("number,url"):
        out({"number": pr["number"], "url": "https://github.com/octo/widgets/pull/%d" % pr["number"]})
    out({k: pr[k] for k in fields.split(",")})
if argv[:2] == ["pr", "checks"]:
    failing = any(c["bucket"] == "fail" for c in state["checks"])
    out(state["checks"], 1 if failing else 0)
if argv[:2] == ["pr", "list"]:
    out(state.get("prs", []))
if argv[:2] == ["pr", "merge"]:
    state["merged"] = True
    save()
    sys.exit(0)
if argv[:2] == ["pr", "comment"]:
    sys.exit(0)
if argv[:2] == ["api", "graphql"]:
    query = next(a[len("query="):] for a in argv if a.startswith("query="))
    author = {"login": state["author"]}
    if "query ReviewThreads" in query:
        out({"data": {"repository": {"pullRequest": {
            "headRefOid": head, "author": author,
            "reviewThreads": {"nodes": state["threads"]},
            "reviewRequests": {"nodes": state["review_requests"]},
            "reviews": {"nodes": state["reviews"]},
            "comments": {"nodes": state["comments"]},
        }}}})
    if "query PrCommitStatuses" in query:
        out({"data": {"repository": {"pullRequest": {"commits": {"nodes": [
            {"commit": {"oid": head, "statusCheckRollup": {"state": state["rollup"]}}}
        ]}}}}})
    if "query PrCheckRollup" in query:
        out({"data": {"repository": {"pullRequest": {"commits": {"nodes": [
            {"commit": {"statusCheckRollup": {"contexts": {"pageInfo": {"hasNextPage": False, "endCursor": None}, "nodes": []}}}}
        ]}}}}})
    if "query MergeGateConversation" in query:
        out({"data": {"repository": {"pullRequest": {
            "author": author,
            "reviewThreads": {"totalCount": len(state["threads"])},
            "reviewRequests": {"totalCount": len(state["review_requests"])},
            "reviews": {"totalCount": len(state["reviews"])},
            "comments": {"totalCount": len(state["comments"]), "nodes": state["comments"]},
        }}}})
sys.stderr.write("fake gh: unsupported call %r\n" % (argv,))
sys.exit(99)
'''

FAKE_GIT = r'''#!__PY__
import os, sys

args = sys.argv[1:]
if args[:2] == ["fetch", "origin"]:
    args[1] = os.environ["FAKE_GIT_ORIGIN"]
os.execv(os.environ["FAKE_REAL_GIT"], [os.environ["FAKE_REAL_GIT"], *args])
'''


def install_fake_binaries(bin_dir: Path, redirect_fetch: bool) -> None:
    bin_dir.mkdir(parents=True, exist_ok=True)
    for name, body in (("gh", FAKE_GH), ("git", FAKE_GIT))[: 2 if redirect_fetch else 1]:
        path = bin_dir / name
        path.write_text(body.replace("__PY__", sys.executable), encoding="utf-8")
        path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


BOT = "copilot-pull-request-reviewer"
REVIEW_URL = "https://github.com/octo/widgets/pull/7#pullrequestreview-111"
COPILOT_FINDING_BODY = """<!-- ccr-overview-v2 -->
## Pull request overview

**Findings:** 1

<details><summary><strong>Open (1)</strong></summary>

- Missing nil check before the write (previously missed)

</details>
"""


class FakeGhSandbox(Sandbox):
    redirect_fetch = False

    def setUp(self):
        super().setUp()
        self.bin = self.tmp / "bin"
        install_fake_binaries(self.bin, self.redirect_fetch)
        self.state_path = self.tmp / "gh-state.json"
        self.calls_path = self.tmp / "gh-calls.jsonl"
        self.calls_path.write_text("")
        self.env = scrubbed_env(self.home, self.bin)
        self.env.update(FAKE_GH_STATE=str(self.state_path), FAKE_GH_CALLS=str(self.calls_path), FAKE_REAL_GIT=REAL_GIT)
        self.state: dict = {}

    def flush(self):
        self.state_path.write_text(json.dumps(self.state))

    def calls(self):
        return [json.loads(line) for line in self.calls_path.read_text().splitlines()]


class GitHubSandbox(FakeGhSandbox):
    redirect_fetch = True

    def setUp(self):
        super().setUp()
        bare = self.tmp / "origin.git"
        self.git("init", "-q", "--bare", "-b", "main", str(bare), cwd=self.tmp)
        self.git("config", "uploadpack.allowAnySHA1InWant", "true", cwd=bare)
        seed = self.tmp / "seed"
        self.git("clone", "-q", str(bare), str(seed), cwd=self.tmp)
        (seed / "a.txt").write_text("one\ntwo\nthree\n")
        self.git("add", "a.txt", cwd=seed)
        self.git("commit", "-q", "-m", "base", cwd=seed)
        self.git("push", "-q", "origin", "HEAD:main", cwd=seed)
        self.git("checkout", "-q", "-b", "feature", cwd=seed)
        (seed / "a.txt").write_text("one\nTWO\nthree\nfour\n")
        self.git("commit", "-q", "-am", "change", cwd=seed)
        self.git("push", "-q", "origin", "feature", cwd=seed)
        self.head = self.git("rev-parse", "HEAD", cwd=seed).strip()
        base = self.git("rev-parse", "main", cwd=seed).strip()
        diff = self.git("diff", f"{base}...{self.head}", cwd=seed)
        self.patch_id = subprocess.run(
            [REAL_GIT, "patch-id", "--stable"], input=diff, capture_output=True, text=True, check=True,
        ).stdout.split()[0]
        self.checkout = self.tmp / "checkout"
        self.git("init", "-q", "-b", "main", str(self.checkout), cwd=self.tmp)
        self.git("remote", "add", "origin", ORIGIN_URL, cwd=self.checkout)
        self.env["FAKE_GIT_ORIGIN"] = str(bare)
        self.state = self.green_state()

    def comment(self, body, login="alice", association="OWNER", kind="User", n=1, at="2026-01-01T00:00:%02dZ"):
        return {
            "body": body, "url": f"https://github.com/octo/widgets/pull/7#issuecomment-{n}",
            "createdAt": at % n, "authorAssociation": association,
            "author": {"login": login, "__typename": kind},
        }

    def verdict_comment(self, head=None, patch_id=None, verdict="PASS", docs="pass", n=1):
        body = f"Verdict: {verdict}\nHead: {head or self.head}\nPatch-id: {patch_id or self.patch_id}\nDocs: {docs}\n\nChecked.\n"
        return self.comment(body, n=n)

    def green_state(self):
        return {
            "author": "alice",
            "pr": {
                "number": 7, "mergeable": "MERGEABLE", "mergeStateStatus": "CLEAN", "reviewDecision": "",
                "headRefOid": self.head, "headRefName": "feature", "baseRefName": "main",
                "state": "OPEN", "mergedAt": None, "isDraft": False,
            },
            "checks": [{"name": "build", "state": "SUCCESS", "bucket": "pass", "description": "", "link": "https://ci/1", "workflow": "ci"}],
            "rollup": "SUCCESS",
            "threads": [],
            "reviews": [],
            "review_requests": [],
            "comments": [self.verdict_comment()],
        }

    def bot_review(self, body=COPILOT_FINDING_BODY, url=REVIEW_URL):
        return {
            "body": body, "state": "COMMENTED", "url": url, "commit": {"oid": self.head},
            "author": {"login": BOT, "__typename": "Bot"},
        }

    def unresolved_thread(self):
        return {
            "id": "T1", "isResolved": False,
            "comments": {"nodes": [{
                "body": "Please handle the empty case.", "createdAt": "2026-01-01T00:00:00Z",
                "path": "a.txt", "line": 2, "author": {"login": "reviewer", "__typename": "User"},
            }]},
        }

    def failing_check(self):
        return {"name": "unit", "state": "FAILURE", "bucket": "fail", "description": "", "link": "https://ci/2", "workflow": "ci"}

    def merge_calls(self):
        return [c for c in self.calls() if c[:2] == ["pr", "merge"]]

    def merge_gate(self, *extra, merge=True):
        self.flush()
        body = self.tmp / "body.txt"
        body.write_text("Squash body\n")
        args = ["--pr", "7"] + (["--subject", "Land the widget", "--body-file", str(body)] if merge else ["--check"])
        return self.run_cmd([MERGE_GATE, *args, *extra], cwd=self.checkout)

    def gate_report(self, result):
        record = json.loads(result.stdout.strip().splitlines()[-1])
        return record, {g["gate"]: g["ok"] for g in record["report"]["gates"]}

    def watch(self):
        self.flush()
        result = self.run_cmd([WATCH_PR, "--pr", "7", "--interval", "1", "--timeout", "30"], cwd=self.checkout)
        return result, json.loads(result.stdout.strip().splitlines()[-1])




class ModelsResolverPromises(ResolverSandbox):
    def test_arena_panel_from_config(self):
        self.write_user("arena runners: haiku, sonnet\narena cross-judge pool: opus\n")
        self.assertEqual(
            self.resolve("claude-code", "arena runners", "arena cross-judge pool"),
            [
                arm("arena runners", 1, "haiku", INHERIT, "user flat"),
                arm("arena runners", 2, "sonnet", INHERIT, "user flat"),
                arm("arena cross-judge pool", 1, "opus", INHERIT, "user flat"),
            ],
        )
        self.write_user("arena runners: fable, opus, sonnet, haiku\narena cross-judge pool: sonnet, opus\n")
        panel = self.resolve("claude-code", "arena runners", "arena cross-judge pool")
        self.assertEqual(
            [(a["role"], a["arm"], a["model"]) for a in panel],
            [("arena runners", 1, "fable"), ("arena runners", 2, "opus"), ("arena runners", 3, "sonnet"),
             ("arena runners", 4, "haiku"), ("arena cross-judge pool", 1, "sonnet"), ("arena cross-judge pool", 2, "opus")],
        )
        arena = (SKILLS / "arena/SKILL.md").read_text(encoding="utf-8")
        self.assertIn("Use the `arena runners` role, one arm per entry.", arena)
        self.assertIn("choose one arm of the `arena cross-judge pool` role", arena)

    def test_config_read_at_next_run(self):
        self.write_user("feature: sonnet\n")
        self.assertEqual(self.resolve("claude-code", "feature"), [arm("feature", 1, "sonnet", INHERIT, "user flat")])
        self.write_user("feature: opus@high\n")
        self.assertEqual(self.resolve("claude-code", "feature"), [arm("feature", 1, "opus", "high", "user flat")])
        self.write_workspace("feature: haiku\n")
        self.assertEqual(self.resolve("claude-code", "feature"), [arm("feature", 1, "haiku", INHERIT, "workspace flat")])
        (self.project / ".agents" / "pstack-models.md").unlink()
        self.assertEqual(self.resolve("claude-code", "feature"), [arm("feature", 1, "opus", "high", "user flat")])
        guide = (SKILLS / "pstack-harness/SKILL.md").read_text(encoding="utf-8")
        self.assertIn("Do not read the config files to pick values.", guide)

    def test_inherit_parent_omits_model_field(self):
        for harness in HARNESSES:
            for value in ("inherit-parent", "auto"):
                with self.subTest(harness=harness, value=value):
                    self.write_user(f"feature: {value}\nbug-fix: {value}@high\n")
                    self.assertEqual(
                        self.resolve(harness, "feature", "bug-fix"),
                        [arm("feature", 1, INHERIT, INHERIT, "user flat"), arm("bug-fix", 1, INHERIT, "high", "user flat")],
                    )
            with self.subTest(harness=harness, role="default ships inherit-parent"):
                (self.home / ".agents" / "pstack-models.md").unlink()
                self.assertEqual(self.resolve(harness, "default"), [arm("default", 1, INHERIT, INHERIT, "skill default")])
        harness_skill = (SKILLS / "pstack-harness/SKILL.md").read_text(encoding="utf-8")
        self.assertIn("`inherit-parent` in a field means omit that field.", harness_skill)

    def test_models_config_grammar_model_at_effort(self):
        self.write_user("feature: sonnet@high\nbug-fix: opus\nhillclimb: haiku@low\n")
        self.assertEqual(
            self.resolve("claude-code", "feature", "bug-fix", "hillclimb"),
            [
                arm("feature", 1, "sonnet", "high", "user flat"),
                arm("bug-fix", 1, "opus", INHERIT, "user flat"),
                arm("hillclimb", 1, "haiku", "low", "user flat"),
            ],
        )
        self.write_user("## codex\nfeature: gpt-6-sol@xhigh\n")
        self.assertEqual(self.resolve("codex", "feature"), [arm("feature", 1, "gpt-6-sol", "xhigh", "user ## codex")])
        self.write_user("feature: sonnet@bogus\n")
        refused = self.run_cmd(
            [sys.executable, RESOLVER, "--resolve", "--harness", "claude-code", "--project", self.project, "feature"], expect=1,
        )
        self.assertEqual(refused.stdout, "")
        self.assertIn("unknown effort 'bogus'", refused.stderr)

    def test_models_config_harness_sections(self):
        self.write_user("feature: haiku\nbug-fix: sonnet\n\n## codex\nfeature: gpt-6-luna@low\n")
        self.assertEqual(
            self.resolve("claude-code", "feature", "bug-fix"),
            [arm("feature", 1, "haiku", INHERIT, "user flat"), arm("bug-fix", 1, "sonnet", INHERIT, "user flat")],
        )
        codex = self.resolve("codex", "feature", "bug-fix")
        self.assertEqual(codex[0], arm("feature", 1, "gpt-6-luna", "low", "user ## codex"))
        self.assertEqual(codex[1]["source"], "user flat")
        self.assertEqual(self.resolve("grok", "feature")[0]["source"], "user flat")
        self.assertEqual(self.resolve("hermes", "feature")[0]["source"], "user flat")

    def test_panel_list_sets_arm_count(self):
        for harness in HARNESSES:
            with self.subTest(harness=harness, source="user list"):
                self.write_user("interrogate reviewers: opus, sonnet, haiku, auto, fable\n")
                arms = self.resolve(harness, "interrogate reviewers")
                self.assertEqual([a["arm"] for a in arms], [1, 2, 3, 4, 5])
                self.assertEqual({a["role"] for a in arms}, {"interrogate reviewers"})
                self.assertEqual({a["source"] for a in arms}, {"user flat"})
                self.write_user("interrogate reviewers: opus, sonnet\n")
                self.assertEqual([a["arm"] for a in self.resolve(harness, "interrogate reviewers")], [1, 2])
            with self.subTest(harness=harness, source="shipped default"):
                (self.home / ".agents" / "pstack-models.md").unlink()
                shipped = shipped_entries("arena runners", harness)
                arms = self.resolve(harness, "arena runners")
                self.assertEqual([a["arm"] for a in arms], list(range(1, len(shipped) + 1)))
                self.assertGreater(len(arms), 1)
        self.write_user("feature: sonnet, opus\n")
        bad = self.run_cmd(
            [sys.executable, RESOLVER, "--resolve", "--harness", "claude-code", "--project", self.project, "feature"], expect=1,
        )
        self.assertIn("single-value role 'feature' given a list", bad.stderr)

    def test_resolver_falls_back_to_shipped_default(self):
        for harness in ("claude-code", "codex"):
            with self.subTest(harness=harness):
                shipped = shipped_entries("hardest tasks", harness)
                self.assertEqual(len(shipped), 1)
                model, _, effort = shipped[0].partition("@")
                self.write_user("hardest tasks: haiku\nfeature: haiku\n")
                overridden = self.resolve(harness, "hardest tasks")[0]
                self.assertEqual(overridden["source"], "user flat")
                self.assertNotEqual(overridden["model"], model)
                self.write_user("feature: haiku\n")
                restored = self.resolve(harness, "hardest tasks")
                self.assertEqual(len(restored), 1)
                self.assertEqual(restored[0]["model"], model)
                self.assertEqual(restored[0]["source"], "skill default ## codex" if harness == "codex" else "skill default")
                if effort:
                    self.assertEqual(restored[0]["effort"], effort)
        (self.home / ".agents" / "pstack-models.md").unlink()
        self.assertEqual(self.resolve("claude-code", "hardest tasks")[0]["source"], "skill default")

    def test_resolver_resolves_roles(self):
        self.write_workspace("feature: haiku\n")
        self.write_user("feature: opus\nbug-fix: opus@xhigh\nswarm workers: sonnet\n")
        self.assertEqual(
            self.resolve("claude-code", "feature", "bug-fix", "swarm workers"),
            [
                arm("feature", 1, "haiku", INHERIT, "workspace flat"),
                arm("bug-fix", 1, "opus", "xhigh", "user flat"),
                arm("swarm workers", 1, "sonnet", INHERIT, "user flat"),
            ],
        )
        self.write_workspace("## codex\nfeature: gpt-6-sol@high\n")
        raw = self.run_cmd(
            [sys.executable, RESOLVER, "--resolve", "--harness", "codex", "--project", self.project, "feature", "bug-fix"], expect=0,
        )
        lines = raw.stdout.splitlines()
        self.assertEqual(len(lines), 2)
        self.assertEqual(
            [json.loads(line) for line in lines],
            [
                arm("feature", 1, "gpt-6-sol", "high", "workspace ## codex"),
                arm("bug-fix", 1, "gpt-6-sol", "xhigh", "user flat", notes=["opus translated to gpt-6-sol"]),
            ],
        )
        everything = self.run_cmd([sys.executable, RESOLVER, "--resolve", "--harness", "claude-code", "--project", self.project], expect=0)
        roles = [json.loads(line)["role"] for line in everything.stdout.splitlines()]
        self.assertEqual(roles, sorted(roles))
        self.assertIn("trail reviewer", roles)
        self.assertEqual(roles.count("arena runners"), 3)


class DecisionLogPromises(Sandbox):
    def test_decision_log_tsv_columns_and_path(self):
        header = "ts\tphase\tdecision\twhy\tevidence\tresult"
        self.assertEqual((SKILLS / "show-me-your-work/references/decision-log-template.tsv").read_text().rstrip("\n"), header)
        self.run_cmd(["bash", LOG_SH, "decisions.tsv", "frame", "counted the work", "wanted the size first", "commit 3a9f1c2", "found 5 gaps"], expect=0)
        self.run_cmd(["bash", LOG_SH, "decisions.tsv", "widget", "moved\tthe styles", "kept it small", "pixel-diff 0", "tests pass"], expect=0)
        lines = (self.project / "decisions.tsv").read_text().splitlines()
        self.assertEqual(lines[0], header)
        self.assertEqual(len(lines), 3)
        first = lines[1].split("\t")
        self.assertRegex(first[0], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")
        self.assertEqual(first[1:], ["frame", "counted the work", "wanted the size first", "commit 3a9f1c2", "found 5 gaps"])
        self.assertEqual(lines[2].split("\t")[1:], ["widget", "moved the styles", "kept it small", "pixel-diff 0", "tests pass"])
        self.run_cmd(["bash", LOG_SH, ".audit/refactor-auth.tsv", "start", "began", "new run", "agent a1", "open"], expect=0)
        audit = (self.project / ".audit" / "refactor-auth.tsv").read_text().splitlines()
        self.assertEqual(audit[0], header)
        self.assertEqual(audit[1].split("\t")[1:], ["start", "began", "new run", "agent a1", "open"])
        skill = (SKILLS / "show-me-your-work/SKILL.md").read_text(encoding="utf-8")
        self.assertIn("`decisions.tsv` in the work dir, or `.audit/<task-slug>.tsv`", skill)
        self.assertEqual(self.run_cmd(["bash", LOG_SH, "decisions.tsv", "only", "three"], expect=1).stdout, "")


def copy_skills_only(destination: Path) -> Path:
    shutil.copytree(SKILLS, destination / "skills", ignore=shutil.ignore_patterns("node_modules", "__pycache__"))
    return destination / "skills"


class PersonaInstallerPromises(Sandbox):
    def subagents(self, script, *args, expect=None, cwd=None):
        return self.run_cmd([sys.executable, script, *args], cwd=cwd, expect=expect)

    def test_installer_delivers_personas_payload(self):
        installed = copy_skills_only(self.tmp / "installed")
        script = installed / "pstack-harness/scripts/subagents.py"
        self.assertFalse((installed.parent / "agents").exists())
        report = json.loads(self.subagents(script, "check", expect=0, cwd=self.tmp).stdout)
        self.assertEqual(report["payload"], "ready")
        self.assertEqual(report["native_activation"], "unverified")
        self.assertEqual(
            sorted((row["id"], row["native_file"]) for row in report["roles"]),
            [("comment-sicko", "not-requested"), ("poteto-agent", "not-requested")],
        )
        (installed / "pstack-harness/references/subagents/roles.json").unlink()
        broken = self.subagents(script, "check", expect=1, cwd=self.tmp)
        self.assertEqual(json.loads(broken.stdout)["payload"], "invalid")

    def test_installer_refuses_user_managed_files(self):
        agents = self.project / ".claude" / "agents"
        agents.mkdir(parents=True)
        mine = agents / "poteto-agent.md"
        mine.write_text("# my own agent\n")
        outside = self.tmp / "elsewhere.md"
        outside.write_text("untouched\n")
        (agents / "comment-sicko.md").symlink_to(outside)
        refused = self.subagents(SUBAGENTS, "install", "--harness", "claude-code", "--project", self.project, expect=1)
        rows = {row["id"]: row["native_file"] for row in json.loads(refused.stdout)["roles"]}
        self.assertEqual(rows, {"poteto-agent": "conflict", "comment-sicko": "conflict"})
        self.assertEqual(mine.read_text(), "# my own agent\n")
        self.assertEqual(outside.read_text(), "untouched\n")
        self.assertTrue((agents / "comment-sicko.md").is_symlink())
        mine.unlink()
        (agents / "comment-sicko.md").unlink()
        self.subagents(SUBAGENTS, "install", "--harness", "claude-code", "--project", self.project, expect=0)
        edited = agents / "poteto-agent.md"
        marker_line = edited.read_text().splitlines()[-1]
        self.assertTrue(marker_line.startswith("<!-- pstack-generated:v1:poteto-agent:"))
        edited.write_text(edited.read_text().replace("Poteto subagent", "My subagent"))
        self.assertIn(marker_line, edited.read_text())
        after_edit = edited.read_bytes()
        refused = self.subagents(SUBAGENTS, "install", "--harness", "claude-code", "--project", self.project, expect=1)
        rows = {row["id"]: row["native_file"] for row in json.loads(refused.stdout)["roles"]}
        self.assertEqual(rows["poteto-agent"], "conflict")
        self.assertEqual(edited.read_bytes(), after_edit)

    def test_native_registration_project_or_user_scope(self):
        project_root = self.tmp / "some-project"
        user_root = self.tmp / "some-user-home"
        project_root.mkdir()
        user_root.mkdir()
        cases = (
            ("claude-code", "--project", project_root, ".claude/agents", ".md"),
            ("codex", "--project", project_root, ".codex/agents", ".toml"),
            ("claude-code", "--user", user_root, ".claude/agents", ".md"),
            ("codex", "--user", user_root, ".codex/agents", ".toml"),
        )
        for harness, scope, root, directory, suffix in cases:
            with self.subTest(harness=harness, scope=scope):
                report = json.loads(self.subagents(SUBAGENTS, "install", "--harness", harness, scope, root, expect=0).stdout)
                self.assertEqual({row["native_file"] for row in report["roles"]}, {"current"})
                for persona in ("poteto-agent", "comment-sicko"):
                    written = root / directory / (persona + suffix)
                    self.assertTrue(written.is_file(), written)
                    declared = f'name = "{persona}"' if suffix == ".toml" else f"name: {persona}"
                    self.assertIn(declared, written.read_text())
        self.assertEqual(list(self.home.rglob("*.md")), [])
        both = self.subagents(SUBAGENTS, "install", "--harness", "codex", "--project", project_root, "--user", user_root, expect=2)
        self.assertEqual(both.stdout, "")

    def test_persona_briefing_to_generic_delegate(self):
        installed = copy_skills_only(self.tmp / "installed")
        script = installed / "pstack-harness/scripts/subagents.py"
        brief = self.subagents(script, "brief", "poteto-agent", expect=0, cwd=self.tmp)
        self.assertEqual(brief.stderr, "")
        text = brief.stdout
        self.assertTrue(text.startswith("Pstack installed skill paths\n"))
        self.assertIn("Put the exact line `persona: poteto-agent` on its own line in your first reply.\n", text)
        body = (ROOT / "agents/poteto-agent.md").read_text().split("---\n", 2)[2]
        self.assertTrue(text.endswith(body), "the brief ends with the complete persona body")
        listed = re.findall(r'^- ([a-z-]+): "([^"]+)"$', text, re.M)
        self.assertIn("poteto-mode", [name for name, _ in listed])
        for name, path in listed:
            self.assertEqual(Path(path), installed / name / "SKILL.md")
            self.assertTrue(Path(path).is_file(), path)
        self.assertNotIn(str(ROOT), text)
        self.assertEqual(self.subagents(script, "brief", "poteto-agent", cwd=self.tmp).stdout, text)
        unknown = self.subagents(script, "brief", "nobody", expect=2, cwd=self.tmp)
        self.assertEqual(unknown.stdout, "")

    def test_setup_detects_stale_personas(self):
        import hashlib

        self.subagents(SUBAGENTS, "install", "--harness", "claude-code", "--project", self.project, expect=0)
        path = self.project / ".claude" / "agents" / "poteto-agent.md"
        current = path.read_bytes()
        prefix = current[: current.rindex(b"<!-- pstack-generated")]
        older = prefix.replace(b"Read the `poteto-mode` skill", b"Read the poteto-mode skill, older wording")
        self.assertNotEqual(older, prefix)
        digest = hashlib.sha256(older).hexdigest()
        path.write_bytes(older + f"<!-- pstack-generated:v1:poteto-agent:{digest} -->\n".encode())
        checked = self.subagents(SUBAGENTS, "check", "--harness", "claude-code", "--project", self.project, expect=1)
        report = json.loads(checked.stdout)
        self.assertEqual({row["id"]: row["native_file"] for row in report["roles"]}, {"poteto-agent": "outdated-generated", "comment-sicko": "current"})
        refreshed = self.subagents(SUBAGENTS, "install", "--harness", "claude-code", "--project", self.project, expect=0)
        by_id = {row["id"]: (row["action"], row["native_file"]) for row in json.loads(refreshed.stdout)["roles"]}
        self.assertEqual(by_id, {"poteto-agent": ("installed", "current"), "comment-sicko": ("unchanged", "current")})
        self.assertEqual(path.read_bytes(), current)
        setup = (SKILLS / "setup-pstack/SKILL.md").read_text(encoding="utf-8")
        self.assertIn("Offer the reference's `install` for that CLI and scope when a row reports `outdated-generated`.", setup)


@unittest.skipUnless(shutil.which("bun"), "merge-gate and watch-pr run on bun")
class MergeGatePromises(GitHubSandbox):
    def reset(self):
        self.state = self.green_state()
        self.calls_path.write_text("")

    def failed_gates(self, result):
        record, ok = self.gate_report(result)
        return record["kind"], [gate for gate, passed in ok.items() if not passed]

    def test_merge_gate_refuses_until_gates_hold(self):
        result = self.merge_gate()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        record, ok = self.gate_report(result)
        self.assertEqual(record["kind"], "MERGED")
        self.assertEqual(set(ok.values()), {True})
        self.assertEqual(record["receipt"]["head"], self.head)
        self.assertEqual(record["receipt"]["patchId"], self.patch_id)
        self.assertEqual(
            self.merge_calls(),
            [["pr", "merge", "7", "--repo", "octo/widgets", "--squash", "--match-head-commit", self.head,
              "--subject", "Land the widget", "--body-file", str(self.tmp / "body.txt")]],
        )

        def failing_check(state):
            state["checks"].append(self.failing_check())
            state["rollup"] = "FAILURE"

        refusals = {
            "the PR patch changed after the verdict": (
                lambda st: st.update(comments=[self.verdict_comment(patch_id="0" * 40)]), ["patch-id"]),
            "the verdict covers another head and patch": (
                lambda st: st.update(comments=[self.verdict_comment(head="1" * 40, patch_id="0" * 40)]), ["head", "patch-id"]),
            "a check failed": (failing_check, ["checks"]),
            "a bot review body is unacknowledged": (
                lambda st: st.update(reviews=[self.bot_review()]), ["review-bodies"]),
            "a review thread is unresolved": (
                lambda st: st.update(threads=[self.unresolved_thread()]), ["threads"]),
            "the PR is not mergeable": (
                lambda st: st["pr"].update(mergeable="CONFLICTING", mergeStateStatus="DIRTY"), ["mergeability"]),
            "no verdict was posted": (lambda st: st.update(comments=[]), ["verdict", "head", "patch-id"]),
        }
        for label, (break_it, failed) in refusals.items():
            with self.subTest(label):
                self.reset()
                break_it(self.state)
                result = self.merge_gate()
                self.assertEqual(result.returncode, 10, result.stdout + result.stderr)
                self.assertEqual(self.failed_gates(result), ("REFUSED", failed))
                self.assertEqual(self.merge_calls(), [])

        holds = {
            "a rebased head with an unchanged patch": lambda st: st.update(comments=[self.verdict_comment(head="1" * 40)]),
            "a bot review acknowledged by the author's PR comment": lambda st: st.update(
                reviews=[self.bot_review()],
                comments=[self.verdict_comment(), self.comment(f"False positive, the guard sits upstream: {REVIEW_URL}", n=2)],
            ),
        }
        for label, adjust in holds.items():
            with self.subTest(label):
                self.reset()
                adjust(self.state)
                result = self.merge_gate()
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual(len(self.merge_calls()), 1)

    def test_merge_gate_lists_every_failed_gate(self):
        self.state["comments"] = []
        self.state["pr"].update(mergeable="CONFLICTING", mergeStateStatus="DIRTY", isDraft=True)
        self.state["checks"].append(self.failing_check())
        self.state["rollup"] = "FAILURE"
        self.state["reviews"] = [self.bot_review()]
        self.state["threads"] = [self.unresolved_thread()]
        result = self.merge_gate()
        self.assertEqual(result.returncode, 10, result.stdout + result.stderr)
        every_gate = ["verdict", "head", "patch-id", "checks", "review-bodies", "threads", "mergeability", "draft"]
        self.assertEqual(self.failed_gates(result), ("REFUSED", every_gate))
        self.assertEqual(self.merge_calls(), [])
        pretty = self.merge_gate("--pretty")
        self.assertEqual(pretty.returncode, 10)
        failed_lines = [line.split(":")[0] for line in pretty.stdout.splitlines() if line.startswith("FAIL ")]
        self.assertEqual(failed_lines, [f"FAIL {gate}" for gate in every_gate])


@unittest.skipUnless(shutil.which("bun"), "merge-gate and watch-pr run on bun")
class BabysitWatcherPromises(GitHubSandbox):
    def test_babysit_body_only_finding_acknowledged_in_pr_comment(self):
        self.state["reviews"] = [self.bot_review()]
        result, verdict = self.watch()
        self.assertEqual(result.returncode, 8, result.stdout + result.stderr)
        self.assertEqual(verdict["blocker"]["kind"], "review-findings")
        self.assertEqual([r["url"] for r in verdict["blocker"]["reviews"]], [REVIEW_URL])

        not_acknowledgments = {
            "an author comment that never links the review": self.comment("Looks fine to me.", login="alice", association="NONE", n=2),
            "a link from a stranger": self.comment(f"See {REVIEW_URL}", login="mallory", association="NONE", n=2),
            "a link from a bot": self.comment(f"See {REVIEW_URL}", login="helper-bot", association="MEMBER", kind="Bot", n=2),
            "a link to a longer review id": self.comment(f"See {REVIEW_URL}9", login="alice", association="NONE", n=2),
        }
        for label, comment in not_acknowledgments.items():
            with self.subTest(label):
                self.state["comments"] = [comment]
                result, verdict = self.watch()
                self.assertEqual(result.returncode, 8, result.stdout + result.stderr)
                self.assertEqual(verdict["blocker"]["kind"], "review-findings")

        for label, comment in {
            "the PR author": self.comment(f"Disproved, the guard is in `write()`: {REVIEW_URL}", login="alice", association="NONE", n=2),
            "a maintainer": self.comment(f"Disproved: {REVIEW_URL}", login="maint", association="MEMBER", n=2),
        }.items():
            with self.subTest(label):
                self.state["comments"] = [comment]
                result, verdict = self.watch()
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual(verdict["kind"], "READY")


@unittest.skipUnless(shutil.which("rg") and shutil.which("jq"), "worktree-audit.sh shells out to rg and jq")
class WorktreeAuditPromises(FakeGhSandbox):
    def test_worktree_cleanup_classifies_worktrees(self):
        repo = self.tmp / "audit-repo"
        bare = self.tmp / "audit-origin.git"
        self.git("init", "-q", "--bare", "-b", "main", str(bare), cwd=self.tmp)
        self.git("clone", "-q", str(bare), str(repo), cwd=self.tmp)
        (repo / "README.md").write_text("base\n")
        self.git("add", "README.md", cwd=repo)
        self.git("commit", "-q", "-m", "base", cwd=repo)
        self.git("push", "-q", "origin", "HEAD:main", cwd=repo)
        self.git("fetch", "-q", "origin", "main", cwd=repo)

        def add(name, branch):
            path = self.tmp / name
            self.git("worktree", "add", "-q", "-b", branch, str(path), "main", cwd=repo)
            return path

        add("wt-merged", "merged-br")
        wip = add("wt-wip", "wip-br")
        (wip / "README.md").write_text("edited, not committed\n")
        for index in range(4096):
            (wip / f"generated-{index:04d}.tmp").touch()
        (add("wt-scratch", "scratch-br") / "notes.tmp").write_text("scratch\n")
        for name, branch in (("wt-unmerged", "unmerged-br"), ("wt-openpr", "openpr-br")):
            path = add(name, branch)
            (path / "work.txt").write_text(name)
            self.git("add", "work.txt", cwd=path)
            self.git("commit", "-q", "-m", name, cwd=path)
        chat = add("wt-chat", "chat-br")
        top = self.git("rev-parse", "--show-toplevel", cwd=repo).strip()
        transcripts = self.home / ".claude" / "projects" / re.sub(r"[^a-zA-Z0-9]", "-", top)
        transcripts.mkdir(parents=True)
        (transcripts / "session.jsonl").write_text(json.dumps({"cwd": f"{chat}/"}) + "\n")

        self.state = {"prs": [{"number": 9, "state": "OPEN", "headRefName": "openpr-br"}]}
        self.flush()
        listing_before = self.git("worktree", "list", "--porcelain", cwd=repo)
        branches_before = self.git("branch", "--list", cwd=repo)
        result = self.run_cmd(["bash", AUDIT_SH], cwd=repo, expect=0)
        lines = result.stdout.splitlines()
        self.assertEqual(lines[0].split("\t"), ["SIZE", "AGE", "MERGED", "DIRTY", "REMOTE", "PR", "LAST_CHAT", "BUCKET", "WORKTREE"])
        rows = {Path(f[8]).name: f for f in (line.split("\t") for line in lines[1:])}
        today = date.today().strftime("%Y-%m-%d")
        got = {name: tuple(f[2:8]) for name, f in rows.items()}
        self.assertEqual(
            got,
            {
                "wt-merged": ("YES", "clean", "no-remote", "-", "-", "safe"),
                "wt-wip": ("YES", "wip:1", "no-remote", "-", "-", "hold-wip"),
                "wt-scratch": ("YES", "scratch:1", "no-remote", "-", "-", "safe"),
                "wt-unmerged": ("no", "clean", "no-remote", "-", "-", "review"),
                "wt-openpr": ("no", "clean", "no-remote", "#9/OPEN", "-", "hold-open-pr"),
                "wt-chat": ("YES", "clean", "no-remote", "-", today, "verify-recent-chat"),
            },
            result.stdout,
        )

        from datetime import datetime, timedelta, timezone

        transcript = transcripts / "session.jsonl"
        newest = transcripts / "newest.jsonl"
        newest.write_text(json.dumps({"cwd": f"{chat}/"}) + "\n")
        os.utime(transcript, (946684800, 946684800))
        os.utime(newest, (946778400, 946778400))
        local_env = dict(self.env, TZ="EST5")
        result = self.run_cmd(["bash", AUDIT_SH], cwd=repo, env=local_env, expect=0)
        row = next(line.split("\t") for line in result.stdout.splitlines()[1:] if line.endswith(str(chat)))
        self.assertEqual(row[6:8], ["2000-01-01", "safe"])

        now = int(datetime.now().timestamp())
        for age, bucket in ((4.5, "verify-recent-chat"), (5, "safe")):
            with self.subTest(chat_age_days=age):
                timestamp = now - int(age * 86400)
                os.utime(newest, (timestamp, timestamp))
                result = self.run_cmd(["bash", AUDIT_SH], cwd=repo, env=local_env, expect=0)
                row = next(line.split("\t") for line in result.stdout.splitlines()[1:] if line.endswith(str(chat)))
                local_date = datetime.fromtimestamp(timestamp, timezone(timedelta(hours=-5))).strftime("%Y-%m-%d")
                self.assertEqual(row[6:8], [local_date, bucket])

        self.assertEqual(self.git("worktree", "list", "--porcelain", cwd=repo), listing_before)
        self.assertEqual(self.git("branch", "--list", cwd=repo), branches_before)
        self.assertEqual((self.tmp / "wt-wip" / "README.md").read_text(), "edited, not committed\n")
        self.assertEqual((self.tmp / "wt-scratch" / "notes.tmp").read_text(), "scratch\n")
        for name in rows:
            self.assertTrue((self.tmp / name).is_dir(), f"{name} was deleted")

        failing_python = self.bin / "python3"
        failing_python.write_text("#!/bin/sh\necho 'timestamp interpreter failed' >&2\nexit 17\n")
        failing_python.chmod(0o755)
        result = self.run_cmd(["bash", AUDIT_SH], cwd=repo, expect=17)
        self.assertIn("timestamp interpreter failed", result.stderr)


if __name__ == "__main__":
    unittest.main()
