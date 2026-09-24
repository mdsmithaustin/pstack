import contextlib
import importlib.util
import io
import json
import os
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
        environment = mock.patch.dict(os.environ, {"CANON_CACHE": str(self.base / "cache")})
        environment.start()
        self.addCleanup(environment.stop)
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

    def test_untouched_workspace_harvests_an_empty_diff(self):
        root = self.harness_workspace("idle", "# Poteto mode\n")
        tree = workspace.materialize(root, self.mirror, self.commit, self.spec.overlay)

        self.assertEqual(workspace.harvest(root, tree), b"")
        self.assertEqual(apply_diff(root, ""), {})

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


class MountClashTests(unittest.TestCase):
    def setUp(self):
        self.rule = screen.load_rule("preparatory-refactor")
        self.skills = {"poteto-mode/SKILL.md": b"", "principle-laziness-protocol/SKILL.md": b""}

    def test_repo_that_tracks_the_skill_root_is_refused(self):
        self.assertEqual(screen.mount_clashes({"skills/pstack/README.md"}, self.rule, "poteto-mode", self.skills), ["skills/pstack"])

    def test_repo_skill_named_like_a_mounted_skill_is_refused_under_its_discovery_dir(self):
        tracked = {".claude/skills/poteto-mode/SKILL.md", ".claude/skills/run-load-test/SKILL.md"}

        self.assertEqual(screen.mount_clashes(tracked, self.rule, "poteto-mode", self.skills), [".claude/skills/poteto-mode"])

    def test_repo_skills_beside_the_mounted_tree_are_fine(self):
        tracked = {"skills/tools/SKILL.md", ".claude/skills/run-load-test/SKILL.md"}

        self.assertEqual(screen.mount_clashes(tracked, self.rule, "poteto-mode", self.skills), [])


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


if __name__ == "__main__":
    unittest.main()
