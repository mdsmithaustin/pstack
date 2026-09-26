import contextlib
import difflib
import importlib.util
import io
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("canon_screen", ROOT / "screen.py")
screen = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(screen)
sys.path.insert(0, str(ROOT / "oracles"))

import workspace  # noqa: E402
from shared import OracleError, apply_diff, workspace_diff  # noqa: E402

UPSTREAM = {
    "app/orders.py": "def place(order):\n    return order\n",
    "app/legacy.py": "OLD = 1\n",
    "README.md": "# Shop\n",
    "skills/tools/SKILL.md": "# Tools\n",
}
CONTEXT = b"# Orders\n\nAmendment: a change to a placed order.\n"
GOOD_DIFF = """diff --git a/app/amend_log.md b/app/amend_log.md
new file mode 100644
--- /dev/null
+++ b/app/amend_log.md
@@ -0,0 +1 @@
+Amendments change a placed order.
diff --git a/app/legacy.py b/app/legacy.py
deleted file mode 100644
--- a/app/legacy.py
+++ /dev/null
@@ -1 +0,0 @@
-OLD = 1
diff --git a/app/orders.py b/app/orders.py
--- a/app/orders.py
+++ b/app/orders.py
@@ -1,2 +1,5 @@
 def place(order):
     return order
+
+def amend(order, quantity):
+    return {**order, "quantity": quantity}
"""
BAD_DIFF = """diff --git a/README.md b/README.md
--- a/README.md
+++ b/README.md
@@ -1 +1,2 @@
 # Shop
+Orders can change.
"""
ORACLE = '''from shared import apply_diff


def check_amend(answer, workspace):
    tree = apply_diff(workspace.checkout, workspace.diff)
    failures = []
    if b"def amend" not in (tree.get("app/orders.py") or b""):
        failures.append("app/orders.py defines no amend")
    if "app/legacy.py" not in tree or tree["app/legacy.py"] is not None:
        failures.append("app/legacy.py is still there")
    if not tree.get("app/amend_log.md"):
        failures.append("no app/amend_log.md")
    return failures


CHECKS = {"orders-amend": check_amend}
'''
FAILURES_OF_BAD = ["app/orders.py defines no amend", "app/legacy.py is still there", "no app/amend_log.md"]


def git(cwd, *args):
    env = {**os.environ, **workspace.GIT_ENV, "GIT_AUTHOR_NAME": "Shop", "GIT_AUTHOR_EMAIL": "shop@example.com",
           "GIT_COMMITTER_NAME": "Shop", "GIT_COMMITTER_EMAIL": "shop@example.com",
           "GIT_AUTHOR_DATE": "2026-01-01T00:00:00Z", "GIT_COMMITTER_DATE": "2026-01-01T00:00:00Z"}
    return subprocess.run(["git", *args], cwd=cwd, env=env, capture_output=True, text=True, check=True).stdout


class ShopRepo(unittest.TestCase):
    """A tiny upstream repo with a pinned commit in a mirror under a private cache."""

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.base = Path(directory.name)
        upstream = self.base / "upstream"
        for path, text in UPSTREAM.items():
            (upstream / path).parent.mkdir(parents=True, exist_ok=True)
            (upstream / path).write_text(text)
        git(upstream, "init", "-q")
        git(upstream, "add", "-A")
        git(upstream, "commit", "-q", "-m", "Shop")
        self.commit = git(upstream, "rev-parse", "HEAD").strip()
        environment = {"CANON_CACHE": str(self.base / "cache")}
        if not (screen.skill_ci() / "runner.lock").is_file():
            # A build stamps each manifest with the harness that skill-ci's
            # runner.lock pins, and CI has no skill-ci checkout.
            (self.base / "skill-ci").mkdir()
            (self.base / "skill-ci" / "runner.lock").write_text("git+https://example.invalid/harness.git@abc123\n")
            environment["SKILL_CI"] = str(self.base / "skill-ci")
        patch = mock.patch.dict(os.environ, environment)
        patch.start()
        self.addCleanup(patch.stop)
        self.mirror = workspace.fetch("shop", self.commit, upstream)
        self.spec = workspace.Spec("shop", self.commit, {"CONTEXT.md": CONTEXT})

    def harness_workspace(self, name, skill_text):
        root = self.base / name
        (root / "skills" / "pstack" / "poteto-mode").mkdir(parents=True)
        (root / "skills" / "pstack" / "poteto-mode" / "SKILL.md").write_text(skill_text)
        return root


class MaterializeTests(ShopRepo):
    def test_both_arms_get_the_same_tree_with_the_overlay_applied(self):
        current = self.harness_workspace("current", "# Poteto mode\n")
        amended = self.harness_workspace("amended", "# Poteto mode\nOne more rule.\n")

        trees = [workspace.materialize(root, self.mirror, self.commit, self.spec.overlay) for root in (current, amended)]

        self.assertEqual(trees[0], trees[1])
        self.assertEqual(trees[0], workspace.reference_checkout(self.spec)[1])
        for root in (current, amended):
            self.assertEqual((root / "CONTEXT.md").read_bytes(), CONTEXT)
            self.assertEqual((root / "app" / "orders.py").read_text(), UPSTREAM["app/orders.py"])
            self.assertEqual(git(root, "status", "--porcelain"), "?? CONTEXT.md\n")

    def test_repo_file_where_a_mounted_file_sits_is_refused(self):
        root = self.harness_workspace("clash", "# Poteto mode\n")
        (root / "README.md").write_text("mounted\n")

        with self.assertRaisesRegex(workspace.WorkspaceError, r"would overwrite mounted files: \['README.md'\]"):
            workspace.materialize(root, self.mirror, self.commit, {})


class ApplyDiffTests(unittest.TestCase):
    def setUp(self):
        self.base = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.base)
        self.checkout = self.base / "checkout"
        (self.checkout / "app").mkdir(parents=True)
        (self.checkout / "app" / "orders.py").write_text("OLD = 1\n")
        self.secret = self.base / "host-secret.txt"
        self.secret.write_text("SECRET-HOST-CONTENT\n")

    def test_diff_that_adds_a_symlink_to_a_host_file_is_refused(self):
        plain = ("diff --git a/leak.txt b/leak.txt\nnew file mode 100644\n--- /dev/null\n+++ b/leak.txt\n"
                 "@@ -0,0 +1 @@\n+not a link\n")
        link = ("diff --git a/leak.txt b/leak.txt\nnew file mode 120000\n--- /dev/null\n+++ b/leak.txt\n"
                f"@@ -0,0 +1 @@\n+{self.secret}\n\\ No newline at end of file\n")

        self.assertEqual(apply_diff(self.checkout, plain), {"leak.txt": b"not a link\n"})
        with self.assertRaisesRegex(OracleError, r"^workspace diff leaves a symlink at leak.txt$"):
            apply_diff(self.checkout, link)

    def test_diff_that_edits_a_symlink_in_the_checkout_is_refused(self):
        (self.checkout / "app" / "alias.py").symlink_to("orders.py")
        edit = ("diff --git a/app/{0} b/app/{0}\n--- a/app/{0}\n+++ b/app/{0}\n"
                "@@ -1 +1 @@\n-OLD = 1\n+NEW = 2\n")

        self.assertEqual(apply_diff(self.checkout, edit.format("orders.py")), {"app/orders.py": b"NEW = 2\n"})
        with self.assertRaisesRegex(OracleError, r"^workspace diff touches a symlink in the checkout: app/alias.py$"):
            apply_diff(self.checkout, edit.format("alias.py"))

    def test_path_that_resolves_outside_the_checkout_is_refused(self):
        (self.checkout / "docs").symlink_to(self.base)
        edit = ("diff --git a/docs/host-secret.txt b/docs/host-secret.txt\n--- a/docs/host-secret.txt\n"
                "+++ b/docs/host-secret.txt\n@@ -1 +1 @@\n-SECRET-HOST-CONTENT\n+changed\n")

        with self.assertRaisesRegex(OracleError, r"^workspace diff path resolves outside the checkout: docs/host-secret.txt$"):
            apply_diff(self.checkout, edit)


API_KEY = "sk-" + "canon" * 5
OAUTH = '{"claudeAi' + 'Oauth": {"accessToken": "' + "t" * 24 + '"}}'


class CredentialScanTests(unittest.TestCase):
    def setUp(self):
        self.work = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.work)

    def write(self, path, text):
        (self.work / path).parent.mkdir(parents=True, exist_ok=True)
        (self.work / path).write_text(text)

    def test_credential_files_and_tokens_are_found_and_ordinary_mentions_are_not(self):
        self.write("runs/orders-amend/with_skill/run-1/stream.jsonl", '{"text": "oauth flow, sk-short, task-' + "x" * 30 + '"}\n')
        self.write("harvest/orders-amend/with_skill/run-1/transcripts/codex/auth.json", "{}\n")
        self.write("harvest/orders-amend/with_skill/run-1/transcripts/claude/s1.jsonl", f'{{"key": "{API_KEY}"}}\n')
        self.write("harvest/orders-amend/with_skill/run-2/raw-stream.jsonl", OAUTH + "\n")

        self.assertEqual(workspace.credential_findings(self.work), [
            ("harvest/orders-amend/with_skill/run-1/transcripts/claude/s1.jsonl", "API key"),
            ("harvest/orders-amend/with_skill/run-1/transcripts/codex/auth.json", "credential file"),
            ("harvest/orders-amend/with_skill/run-2/raw-stream.jsonl", "OAuth token"),
        ])

    def run_arm(self, leak):
        rule, case = mock.Mock(id="orders-workspace"), mock.Mock(id="orders-amend")
        calls = []

        def harness(*arguments, env=None):
            calls.append(arguments[0])
            if arguments[0] == "run-agent":
                self.write("out/codex/orders-workspace/orders-amend/amended/runs/orders-amend/with_skill/run-1/stream.jsonl",
                           f'{{"text": "{leak}"}}\n')

        with mock.patch.object(screen, "harness", harness), mock.patch.object(screen, "with_skill_rows"):
            try:
                screen.run_arm("codex", self.work / "out", rule, case, "amended", {"timeout_s": 60}, [], {}, "gpt-6-sol", 1, None)
            except screen.ScreenError as exc:
                return calls, str(exc)
        return calls, None

    def test_a_run_whose_output_holds_a_token_fails_before_grading(self):
        self.assertEqual(self.run_arm("done"), (["prepare", "run-agent", "grade"], None))

        work = self.work / "out" / "codex" / "orders-workspace" / "orders-amend" / "amended"
        shutil.rmtree(self.work / "out")
        self.assertEqual(self.run_arm(API_KEY), (["prepare", "run-agent"],
                         f"{work}: credential material in the run output: "
                         "runs/orders-amend/with_skill/run-1/stream.jsonl (API key)"))


class HarvestTests(ShopRepo):
    def test_diff_carries_edits_deletions_and_new_files_but_not_mounted_skills(self):
        root = self.harness_workspace("run", "# Poteto mode\n")
        tree = workspace.materialize(root, self.mirror, self.commit, self.spec.overlay)
        (root / "app" / "orders.py").write_text("def place(order):\n    return order\n\ndef amend(order):\n    return order\n")
        (root / "app" / "legacy.py").unlink()
        (root / "app" / "amend_log.md").write_text("Amendments change a placed order.\n")
        (root / "skills" / "pstack" / "poteto-mode" / "notes.md").write_text("scratch\n")
        workspace.expose(root, ".agents/skills")

        diff = workspace.harvest(root, tree).decode()

        checkout = workspace.reference_checkout(self.spec)[0]
        self.assertEqual(apply_diff(checkout, diff), {
            "app/amend_log.md": b"Amendments change a placed order.\n",
            "app/legacy.py": None,
            "app/orders.py": b"def place(order):\n    return order\n\ndef amend(order):\n    return order\n",
        })

    def test_an_untouched_workspace_harvests_an_empty_diff_and_one_edit_harvests_only_that_edit(self):
        root = self.harness_workspace("idle", "# Poteto mode\n")
        tree = workspace.materialize(root, self.mirror, self.commit, self.spec.overlay)

        untouched = workspace.harvest(root, tree)
        (root / "README.md").write_text("# Shop\nOrders can change.\n")

        self.assertEqual((untouched, apply_diff(root, "")), (b"", {}))
        self.assertEqual(workspace.harvest(root, tree).decode(), "diff --git a/README.md b/README.md\nindex a00621b..c08b66c 100644\n"
                         "--- a/README.md\n+++ b/README.md\n@@ -1 +1,2 @@\n # Shop\n+Orders can change.\n")

    def test_run_dir_finds_its_diff_in_the_parallel_harvest_tree(self):
        work = self.base / "work"
        (work / "runs" / "orders-amend" / "with_skill").mkdir(parents=True)
        (work / "harvest" / "orders-amend" / "with_skill").mkdir(parents=True)
        (work / "harvest" / "orders-amend" / "with_skill" / "workspace.diff").write_text(BAD_DIFF)

        self.assertEqual(workspace_diff(work / "runs" / "orders-amend" / "with_skill"), BAD_DIFF)
        with self.assertRaisesRegex(OracleError, "no workspace diff was harvested"):
            workspace_diff(work / "runs" / "other" / "with_skill")


AGENT = """import os, pathlib, sys
if not pathlib.Path(".agents/skills/poteto-mode/SKILL.md").is_file():
    sys.exit(5)
pathlib.Path("prompt-seen.txt").write_bytes(sys.stdin.buffer.read())
pathlib.Path("app/orders.py").write_text("changed\\n")
"""


class WrapTests(ShopRepo):
    def run_wrap(self, tree):
        root = self.harness_workspace("wrapped", "# Poteto mode\n")
        arm = self.base / "arm"
        (arm / "overlay").mkdir(parents=True)
        (arm / "overlay" / "CONTEXT.md").write_bytes(CONTEXT)
        (arm / "workspace.json").write_text(json.dumps({"repo": "shop", "commit": self.commit, "mirror": str(self.mirror), "tree": tree}))
        (self.base / "agent.py").write_text(AGENT)
        environment = {"CANON_WORKSPACE": str(arm), "CANON_HARVEST": str(self.base / "harvest")}
        previous = Path.cwd()
        os.chdir(root)
        try:
            with mock.patch.dict(os.environ, environment), contextlib.redirect_stderr(io.StringIO()):
                code = workspace.wrap(["--token", "$poteto-mode", "--discovery", ".agents/skills", "--", sys.executable, str(self.base / "agent.py")],
                                      stdin=io.BytesIO(b"Add amendments."))
        finally:
            os.chdir(previous)
        slot = self.base / "harvest" / "0001"
        return code, root, json.loads((slot / "workspace.json").read_text()), slot

    def test_wrapper_builds_the_checkout_runs_the_agent_and_harvests_its_diff(self):
        tree = workspace.reference_checkout(self.spec)[1]

        code, root, record, slot = self.run_wrap(tree)

        self.assertEqual((code, record["tree"], record["agent_rc"]), (0, tree, 0))
        self.assertEqual((root / "prompt-seen.txt").read_text(), "$poteto-mode Add amendments.")
        self.assertEqual(sorted(apply_diff(workspace.reference_checkout(self.spec)[0], (slot / "workspace.diff").read_text())),
                         ["app/orders.py", "prompt-seen.txt"])

    def test_wrapper_refuses_a_workspace_that_is_not_the_recorded_tree(self):
        code, root, record, slot = self.run_wrap("0" * 40)

        self.assertEqual(code, workspace.REFUSED)
        self.assertIn("is not the recorded", record["error"])
        self.assertFalse((root / "prompt-seen.txt").exists())
        self.assertFalse((slot / "workspace.diff").exists())


ARGV_AGENT = """#!/usr/bin/env python3
import json, pathlib, sys
pathlib.Path("argv.json").write_text(json.dumps(sys.argv[1:]))
"""
CLAUDE_READ_ONLY_SHELL = [
    "--allowedTools",
    "Bash(git log:*)", "Bash(git show:*)", "Bash(git grep:*)", "Bash(git diff:*)", "Bash(git status:*)",
    "Bash(rg:*)", "Bash(grep:*)", "Bash(ls:*)", "Bash(find:*)", "Bash(wc:*)", "Bash(head:*)", "Bash(sed -n:*)",
    "--disallowedTools",
    "Bash(find * -exec*)", "Bash(find * -ok*)", "Bash(find * -delete*)",
    "Bash(rg * --pre*)", "Bash(git grep * -O*)", "Bash(git grep * --open-files-in-pager*)",
]


class AgentFlagTests(ShopRepo):
    """The argv each agent receives through the wrapper screen.py writes."""

    def argv_seen(self, agent, in_workspace, entry="poteto-mode"):
        out = self.base / f"out-{agent}-{in_workspace}-{entry}"
        agent_path = self.base / "argv-agent"
        agent_path.write_text(ARGV_AGENT)
        agent_path.chmod(0o755)
        with mock.patch.object(screen, "skill_ci", return_value=self.base):
            (self.base / "tools").mkdir(exist_ok=True)
            for name in ("claude-project-only", "codex-project-only"):
                target = self.base / "tools" / name
                if not target.exists():
                    target.symlink_to(agent_path)
            backend = screen.backend_args(agent, out, entry, in_workspace)
        command = [backend[1]] if agent == "claude" else shlex.split(backend[1])
        root = self.harness_workspace(f"cwd-{agent}-{in_workspace}-{entry}", "# Poteto mode\n")
        arm = self.base / "arm"
        if in_workspace and not arm.exists():
            (arm / "overlay").mkdir(parents=True)
            tree = workspace.reference_checkout(workspace.Spec("shop", self.commit, {}))[1]
            (arm / "workspace.json").write_text(json.dumps({"repo": "shop", "commit": self.commit, "mirror": str(self.mirror), "tree": tree}))
        environment = {**os.environ, "CANON_WORKSPACE": str(arm), "CANON_HARVEST": str(self.base / "harvest")}
        subprocess.run([*command, "-p", "--model", "sonnet"], cwd=root, env=environment, input=b"Add amendments.", capture_output=True, check=True)
        return json.loads((root / "argv.json").read_text())

    def test_claude_in_a_workspace_may_run_read_only_shell_commands(self):
        self.assertEqual(self.argv_seen("claude", True), ["-p", "--model", "sonnet", *CLAUDE_READ_ONLY_SHELL])

    def test_claude_outside_a_workspace_gets_no_shell_rules(self):
        self.assertEqual(self.argv_seen("claude", False), ["-p", "--model", "sonnet"])
        self.assertEqual(self.argv_seen("claude", False, entry="skill"), ["-p", "--model", "sonnet"])

    def test_codex_in_a_workspace_gets_no_claude_rules(self):
        self.assertEqual(self.argv_seen("codex", True),
                         ["exec", "--json", "--skip-git-repo-check", "--sandbox", "workspace-write", "-p", "--model", "sonnet"])


class MountClashTests(unittest.TestCase):
    def setUp(self):
        self.rule = screen.load_rule("preparatory-refactor")
        self.skills = {"poteto-mode/SKILL.md": b"", "principle-laziness-protocol/SKILL.md": b""}

    def test_repo_that_tracks_the_skill_root_is_refused(self):
        self.assertEqual(screen.mount_clashes({"skills/pstack/README.md"}, self.rule, "poteto-mode", self.skills), ["skills/pstack"])

    def test_only_the_repo_skill_named_like_a_mounted_skill_is_refused_under_its_discovery_dir(self):
        tracked = {"skills/tools/SKILL.md", ".claude/skills/poteto-mode/SKILL.md", ".claude/skills/run-load-test/SKILL.md"}

        self.assertEqual(screen.mount_clashes(tracked, self.rule, "poteto-mode", self.skills), [".claude/skills/poteto-mode"])


class ShopRule(ShopRepo):
    """A rule in a private rules root whose one case works in the shop checkout."""

    def setUp(self):
        super().setUp()
        rules = self.base / "rules"
        rule = rules / "orders-workspace"
        case = rule / "cases" / "orders-amend"
        (case / "overlay").mkdir(parents=True)
        (case / "samples").mkdir()
        shutil.copyfile(ROOT / "rules" / "preparatory-refactor" / "rule.patch", rule / "rule.patch")
        (rule / "rule.json").write_text(json.dumps({"source": "shop fixture"}))
        (rule / "oracle.py").write_text(ORACLE)
        (case / "case.json").write_text(json.dumps({
            "kind": "positive", "domain": "orders",
            "expected_behavior": ["Adds amend to app/orders.py, drops app/legacy.py, and logs the amendment."],
            "workspace": {"repo": "shop", "commit": self.commit, "overlay": "overlay/"},
        }))
        (case / "prompt.md").write_text("Customers keep asking to change the quantity on an order after they place it. Add that to the orders code here.\n")
        (case / "overlay" / "CONTEXT.md").write_bytes(CONTEXT)
        for name, diff in (("good", GOOD_DIFF), ("bad", BAD_DIFF)):
            (case / "samples" / f"{name}.md").write_text("Done.\n")
            (case / "samples" / f"{name}.diff").write_text(diff)
        patches = [mock.patch.object(screen, "RULES", rules), mock.patch.dict(os.environ, {"CANON_RULES": str(rules)})]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)
        self.rule = screen.load_rule("orders-workspace")
        self.out = self.base / "out"


class WorkspaceBuildTests(ShopRule):
    def build(self):
        with contextlib.redirect_stdout(io.StringIO()):
            return screen.build(self.out, [self.rule], "poteto-mode")["orders-workspace"]["cases"]["orders-amend"]

    def test_build_records_one_workspace_input_for_both_arms(self):
        built = self.build()

        checkout, tree = workspace.reference_checkout(workspace.parse_spec(self.rule.cases[0].root, self.rule.cases[0].workspace))
        record = built["workspace"]
        self.assertEqual((built["timeout_s"], record["tree"], record["checkout"]), (1800, tree, str(checkout)))
        self.assertEqual(sorted(record["arms"]), ["orders-amend/amended", "orders-amend/current"])
        self.assertEqual(len(set(record["arms"].values())), 1)
        for arm in screen.ARMS:
            root = self.out / "arms" / "orders-workspace" / "orders-amend" / arm
            self.assertEqual((root / "workspace" / "overlay" / "CONTEXT.md").read_bytes(), CONTEXT)
            self.assertEqual(json.loads((root / "rules" / "orders-workspace" / "cases" / "orders-amend" / "workspace.json").read_text())["checkout"], str(checkout))
            prompt = json.loads((root / screen.MANIFEST).read_text())["cases"][0]["prompt"]
            self.assertEqual(prompt, (self.rule.cases[0].root / "prompt.md").read_text().strip())

    def test_arms_with_different_workspace_inputs_are_refused(self):
        with self.assertRaisesRegex(screen.ScreenError, "arms hold different workspace inputs"):
            screen.workspace_record(self.spec, ("/checkout", "t"), {"c/current": "a", "c/amended": "b"})

    def test_sample_diffs_grade_as_the_samples_say(self):
        sys.path.insert(0, str(ROOT / "oracles"))
        import check
        from shared import Workspace

        checkout = workspace.reference_checkout(workspace.parse_spec(self.rule.cases[0].root, self.rule.cases[0].workspace))[0]
        with mock.patch.object(check, "RULES", screen.RULES):
            for sample, diff, expected in (("good.md", GOOD_DIFF, []), ("bad.md", BAD_DIFF, FAILURES_OF_BAD)):
                with self.subTest(sample=sample):
                    self.assertEqual(check.grade("orders-workspace", "orders-amend", sample, workspace=Workspace(checkout, diff)), expected)


class RegradeTests(ShopRule):
    """A finished codex run of the shop rule, written by hand in the shape the
    harness leaves: grade.json per arm, runs/<case>/with_skill/run-N, harvest beside."""

    def finish(self, arm, runs):
        work = self.out / "codex" / "orders-workspace" / "orders-amend" / arm
        results = []
        for number, (harness_verdict, answer, diff) in enumerate(runs, 1):
            run_base = work / "runs" / "orders-amend" / "with_skill" / f"run-{number}"
            run_base.mkdir(parents=True)
            (run_base / "events.json").write_text(json.dumps({"events": [
                {"type": "file_read", "status": "completed", "input_summary": f"skills/pstack/{self.rule.target}"}]}))
            if answer is not None:
                (run_base / "output.md").write_text(answer)
            if diff is not None:
                harvest = work / "harvest" / "orders-amend" / "with_skill" / f"run-{number}"
                harvest.mkdir(parents=True)
                (harvest / "workspace.diff").write_text(diff)
            result = {"run_number": number, "run_base": str(run_base), "missing_output": answer is None, "execution_valid": answer is not None}
            if harness_verdict != "INVALID":
                evidence = "PASS\n" if harness_verdict == "PASS" else "".join(f"FAIL: {failure}\n" for failure in FAILURES_OF_BAD)
                result["assertions"] = [{"name": "rule-behavior", "passed": harness_verdict == "PASS", "evidence": evidence}]
            results.append(result)
        (work / "grade.json").write_text(json.dumps({"results": results}))
        return work / "grade.json"

    def test_invalid_run_whose_diff_passes_is_graded_pass_from_the_diff(self):
        with contextlib.redirect_stdout(io.StringIO()):
            screen.build(self.out, [self.rule], "poteto-mode")
        self.finish("current", [("FAIL", "Done.\n", BAD_DIFF), ("FAIL", "Done.\n", BAD_DIFF)])
        amended = self.finish("amended", [("INVALID", None, GOOD_DIFF), ("INVALID", None, None)])
        graded = amended.read_text()

        with contextlib.redirect_stdout(io.StringIO()) as printed:
            self.assertEqual(screen.main(["regrade", "--out", str(self.out)]), 0)

        compared = json.loads((self.out / "compare.json").read_text())
        self.assertEqual([(row["arm"], row["run"], row["verdict"], row.get("graded_from_diff")) for row in compared["runs"]], [
            ("amended", 1, "PASS", True),
            ("amended", 2, "INVALID", None),
            ("current", 1, "FAIL", None),
            ("current", 2, "FAIL", None),
        ])
        self.assertEqual([(pair["run"], pair["outcome"]) for pair in compared["pairs"]], [(1, "separates"), (2, "invalid")])
        self.assertEqual(compared["runs"][2]["reasons"], "; ".join(FAILURES_OF_BAD))
        self.assertEqual(json.loads(amended.with_name("regrade.json").read_text()),
                         {"results": [{"run": 1, "verdict": "PASS", "reasons": "", "graded_from_diff": True,
                                       "run_base": str(self.out / "codex" / "orders-workspace" / "orders-amend" / "amended" / "runs" / "orders-amend" / "with_skill" / "run-1")}]})
        self.assertEqual(amended.read_text(), graded)
        self.assertIn("amended: graded from the diff; the harness found no gradable answer", printed.getvalue())

    def test_pasted_project_cases_keep_the_harness_grade(self):
        with contextlib.redirect_stdout(io.StringIO()):
            screen.build(self.out, [self.rule], "poteto-mode")
        build_json = self.out / "arms" / "orders-workspace" / "build.json"
        built = json.loads(build_json.read_text())
        del built["cases"]["orders-amend"]["workspace"]
        build_json.write_text(json.dumps(built))
        current = self.finish("current", [("FAIL", "Done.\n", BAD_DIFF)])
        self.finish("amended", [("INVALID", None, GOOD_DIFF)])

        with contextlib.redirect_stdout(io.StringIO()):
            screen.regrade(self.out)

        compared = json.loads((self.out / "compare.json").read_text())
        self.assertEqual([(row["arm"], row["verdict"]) for row in compared["runs"]], [("amended", "INVALID"), ("current", "FAIL")])
        self.assertFalse(current.with_name("regrade.json").exists())


def harness_available():
    return (screen.skill_ci() / "runner.lock").is_file() and shutil.which("uv") is not None


@unittest.skipUnless(harness_available(), "needs a skill-ci checkout at $SKILL_CI and uv")
class OfflineWorkspaceRunTests(ShopRule):
    def test_stand_in_edits_the_checkout_and_the_rule_separates_on_the_harvested_diff(self):
        with mock.patch.dict(os.environ, {"CODEX_BIN": str(ROOT / "offline" / "codex")}), contextlib.redirect_stdout(io.StringIO()) as printed:
            screen.run("codex", self.out, [self.rule], "gpt-6-sol", 1, None, "poteto-mode")

        compared = json.loads((self.out / "compare.json").read_text())
        self.assertEqual([pair["outcome"] for pair in compared["pairs"]], ["separates"], printed.getvalue()[-2000:])
        self.assertEqual([row["verdict"] for row in compared["rules"]], ["separates"])
        harvest = self.out / "codex" / "orders-workspace" / "orders-amend"
        checkout = workspace.reference_checkout(workspace.parse_spec(self.rule.cases[0].root, self.rule.cases[0].workspace))[0]
        self.assertEqual(sorted(apply_diff(checkout, workspace_diff(harvest / "amended" / "runs" / "orders-amend" / "with_skill"))),
                         ["app/amend_log.md", "app/legacy.py", "app/orders.py"])
        self.assertEqual(sorted(apply_diff(checkout, workspace_diff(harvest / "current" / "runs" / "orders-amend" / "with_skill"))),
                         ["README.md"])


def unified(path, before, after):
    return "".join(difflib.unified_diff(before.splitlines(True), after.splitlines(True), f"a/{path}" if before else "/dev/null", f"b/{path}"))


LEAF_LINE = "When a placed order changes, record the change in app/amend_log.md.\n"
TRIGGER_LINE = "- Changing a placed order → record it in app/amend_log.md.\n"
NOTE = "Amendments keep a log beside the orders code.\n"


class ShopArmsRule(ShopRule):
    """A three-arm rule that takes its case from orders-workspace. Its arms
    patch real tracked skill files, so they are written against today's text."""

    def setUp(self):
        super().setUp()
        feature, index = (screen.tracked("skills")[path].decode() for path in ("poteto-mode/playbooks/feature.md", "poteto-mode/SKILL.md"))
        head, rest = feature.split("\n", 1)
        leaf = unified("poteto-mode/playbooks/feature.md", feature, f"{head}\n{LEAF_LINE}{rest}")
        trigger = leaf + unified("poteto-mode/SKILL.md", index, index + TRIGGER_LINE) + unified("poteto-mode/references/orders-amend.md", "", NOTE)
        rule = screen.RULES / "orders-arms"
        (rule / "arms").mkdir(parents=True)
        (rule / "rule.json").write_text(json.dumps({"cases_from": "orders-workspace", "arms": ["current", "leaf", "leaf+trigger"]}))
        (rule / "arms" / "leaf.patch").write_text(leaf)
        (rule / "arms" / "leaf+trigger.patch").write_text(trigger)
        self.rule = screen.load_rule("orders-arms")


@unittest.skipUnless(harness_available(), "needs a skill-ci checkout at $SKILL_CI and uv")
class OfflineArmsRunTests(ShopArmsRule):
    def test_each_treatment_arm_separates_from_current_and_the_two_tie(self):
        with mock.patch.dict(os.environ, {"CODEX_BIN": str(ROOT / "offline" / "codex")}), contextlib.redirect_stdout(io.StringIO()) as printed:
            screen.run("codex", self.out, [self.rule], "gpt-6-sol", 1, None, "poteto-mode")

        compared = json.loads((self.out / "compare.json").read_text())
        self.assertEqual([(pair["treatment"], pair["baseline"], pair["outcome"]) for pair in compared["pairs"]],
                         [("leaf", "current", "separates"), ("leaf+trigger", "current", "separates"), ("leaf+trigger", "leaf", "tie-pass")],
                         printed.getvalue()[-3000:])
        self.assertEqual([(row["arm"], row["verdict"]) for row in compared["rules"]], [("leaf", "separates"), ("leaf+trigger", "separates")])
        built = json.loads((self.out / "arms" / "orders-arms" / "build.json").read_text())
        self.assertEqual((built["arms"], built["patch_kind"], built["target"]), (["current", "leaf", "leaf+trigger"], "arms", "poteto-mode/playbooks/feature.md"))
        self.assertEqual(built["arm_changes"], {
            "current": [],
            "leaf": ["poteto-mode/playbooks/feature.md"],
            "leaf+trigger": ["poteto-mode/SKILL.md", "poteto-mode/playbooks/feature.md", "poteto-mode/references/orders-amend.md"],
        })
        self.assertEqual((self.out / "arms" / "orders-arms" / "orders-amend" / "leaf+trigger" / "pstack" / "poteto-mode" / "references" / "orders-amend.md").read_text(), NOTE)
        checkout = workspace.reference_checkout(workspace.parse_spec(self.rule.cases[0].root, self.rule.cases[0].workspace))[0]
        touched = {arm: sorted(apply_diff(checkout, workspace_diff(self.out / "codex" / "orders-arms" / "orders-amend" / arm / "runs" / "orders-amend" / "with_skill")))
                   for arm in self.rule.arm_names}
        self.assertEqual(touched, {"current": ["README.md"],
                                   "leaf": ["app/amend_log.md", "app/legacy.py", "app/orders.py"],
                                   "leaf+trigger": ["app/amend_log.md", "app/legacy.py", "app/orders.py"]})


if __name__ == "__main__":
    unittest.main()
