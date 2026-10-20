from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
RUNNER = ROOT / "tools" / "upstream-sync.sh"


class UpstreamSync(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name).resolve()
        self.home = self.root / "home"
        self.bin = self.home / ".local" / "bin"
        self.bin.mkdir(parents=True)
        self.state = self.home / ".local" / "state" / "pstack-sync"
        self.env = {
            **os.environ,
            "HOME": str(self.home),
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": str(self.root / "gitconfig"),
            "GIT_AUTHOR_NAME": "Sync fixture",
            "GIT_AUTHOR_EMAIL": "sync-fixture",
            "GIT_COMMITTER_NAME": "Sync fixture",
            "GIT_COMMITTER_EMAIL": "sync-fixture",
            "PSTACK_TEST_ROOT": str(self.root),
            "PSTACK_TEST_MODE": "blocked",
        }
        self.upstream = self.root / "upstream"
        self.git("init", "--template=", "-q", "-b", "main", str(self.upstream))
        (self.upstream / "pstack").mkdir()
        (self.upstream / "pstack" / "SKILL.md").write_text("old\n")
        self.git("add", ".", cwd=self.upstream)
        self.git("commit", "-qm", "Initial upstream", cwd=self.upstream)
        self.recorded = self.git("rev-parse", "HEAD", cwd=self.upstream)
        (self.upstream / "pstack" / "SKILL.md").write_text("new\n")
        self.git("commit", "-qam", "New upstream", cwd=self.upstream)
        self.latest = self.git("rev-parse", "HEAD", cwd=self.upstream)
        self.env["PSTACK_TEST_LATEST"] = self.latest
        self.origin = self.root / "origin"
        self.git("init", "--template=", "-q", "-b", "main", str(self.origin))
        (self.origin / ".github").mkdir()
        (self.origin / ".github" / "upstream-sha").write_text(self.recorded + "\n")
        (self.origin / "PORTING.md").write_text("Fixture porting contract.\n")
        ledger = self.origin / "evals" / "promises" / "ledger.json"
        ledger.parent.mkdir(parents=True)
        ledger.write_text(json.dumps({"promises": {
            "architect-checkpoint-opt-in": {
                "check": "live", "owners": ["skills/architect/SKILL.md"],
            },
            "static-contract": {
                "check": "static", "owners": ["skills/static-check/SKILL.md"],
            },
        }}))
        owner = self.origin / "skills" / "architect" / "SKILL.md"
        owner.parent.mkdir(parents=True)
        owner.write_text("Original live promise owner.\n")
        static_owner = self.origin / "skills" / "static-check" / "SKILL.md"
        static_owner.parent.mkdir(parents=True)
        static_owner.write_text("Original static promise owner.\n")
        report = self.origin / "evals" / "promises" / "results" / "earlier.md"
        report.parent.mkdir()
        report.write_text("Earlier live results.\n")
        self.git("add", ".", cwd=self.origin)
        self.git("commit", "-qm", "Initial port", cwd=self.origin)
        self.git("config", "--global", f"url.{self.origin}.insteadOf",
                 "https://github.com/mdsmithaustin/pstack.git")
        self.git("config", "--global", f"url.{self.upstream}.insteadOf",
                 "https://github.com/cursor/plugins.git")
        self.executable("gh", """
            import json
            import os
            import sys
            from pathlib import Path

            root = Path(os.environ["PSTACK_TEST_ROOT"])
            if sys.argv[1:3] == ["pr", "list"]:
                print(os.environ.get("PSTACK_TEST_OPEN_PR", "0"))
            elif sys.argv[1:2] == ["api"]:
                case = os.environ.get("PSTACK_TEST_PR_CASE", "valid")
                if case == "unavailable":
                    sys.exit(1)
                if case == "malformed":
                    print("invalid JSON")
                    sys.exit(0)
                pulls = json.loads((root / "pulls.json").read_text())
                if pulls:
                    pr = pulls[0]
                    if case == "wrong_base_repo":
                        pr["base"]["repo"]["full_name"] = "other/repo"
                    elif case == "wrong_head_repo":
                        pr["head"]["repo"]["full_name"] = "other/repo"
                    elif case == "wrong_base":
                        pr["base"]["ref"] = "other"
                    elif case == "wrong_branch":
                        pr["head"]["ref"] = "other"
                    elif case == "stale_head":
                        pr["head"]["sha"] = "0" * 40
                    elif case == "ready":
                        pr["draft"] = False
                    elif case == "closed":
                        pr["state"] = "closed"
                    elif case == "missing":
                        pulls = []
                    elif case == "ambiguous":
                        pulls.append(pr)
                print(json.dumps(pulls))
            else:
                print("fixture has no published PR", file=sys.stderr)
                sys.exit(1)
        """)
        self.executable("claude", """
            import json
            import os
            import re
            import subprocess
            import sys
            from pathlib import Path

            root = Path(os.environ["PSTACK_TEST_ROOT"])
            (root / "agent-cwd").write_text(str(Path.cwd()))
            with (root / "agent-calls").open("a") as calls:
                calls.write("called\\n")
            prompt = sys.stdin.read()
            (root / "received-prompt").write_text(prompt)
            Path("local-work.txt").write_text("Keep this sync work.\\n")
            mode = os.environ["PSTACK_TEST_MODE"]
            if mode in ("blocked", "failed"):
                print("Publication blocked by the configured gate.")
                sys.exit(17 if mode == "failed" else 0)

            branch = re.search(r"Use branch (\\S+)", prompt).group(1).rstrip(".")
            subprocess.run(["git", "checkout", "-qb", branch], check=True)
            if mode != "stale_recorded":
                Path(".github/upstream-sha").write_text(os.environ["PSTACK_TEST_LATEST"] + "\\n")
            for name, contents in json.loads(os.environ.get("PSTACK_TEST_FILES", "{}")).items():
                path = Path(name)
                if contents is None:
                    path.unlink()
                else:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(contents)
            if os.environ.get("PSTACK_TEST_CHMOD_REPORT"):
                Path("evals/promises/results/earlier.md").chmod(0o755)
            subprocess.run(["git", "add", "-A"], check=True)
            subprocess.run(["git", "commit", "-qm", "Sync fixture"], check=True)
            if os.environ.get("PSTACK_TEST_MOVE_BASE_REF"):
                subprocess.run(["git", "branch", "-f", "main", "HEAD"], check=True)
            subprocess.run(["git", "push", "-qu", "origin", branch], check=True)
            head = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
            pulls = [{
                "base": {"repo": {"full_name": "mdsmithaustin/pstack"}, "ref": "main"},
                "head": {"repo": {"full_name": "mdsmithaustin/pstack"}, "ref": branch, "sha": head},
                "draft": True,
                "state": "open",
                "html_url": "https://github.com/mdsmithaustin/pstack/pull/123",
            }]
            (root / "pulls.json").write_text(json.dumps(pulls if mode != "commit_only" else []))
            if mode == "dirty":
                Path("unfinished.txt").write_text("Still working.\\n")
            elif mode == "wrong_branch":
                subprocess.run(["git", "checkout", "-qb", "other"], check=True)
            print("Draft PR published.")
        """)

    def git(self, *args: str, cwd: Path | None = None) -> str:
        return subprocess.run(
            ["git", *args], cwd=cwd, env=self.env, check=True,
            text=True, capture_output=True,
        ).stdout.strip()

    def executable(self, name: str, source: str) -> None:
        path = self.bin / name
        path.write_text(f"#!{sys.executable}\n" + textwrap.dedent(source))
        path.chmod(0o755)

    def run_sync(self, **changes: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["/bin/bash", str(RUNNER)], cwd=self.root,
            env={**self.env, **changes}, capture_output=True, text=True,
        )

    def test_blocked_agent_exit_zero_is_not_success(self) -> None:
        result = self.run_sync()
        self.assertNotEqual(result.returncode, 0, "blocked publication must fail")
        clone = Path((self.root / "agent-cwd").read_text())
        self.assertEqual((clone / "local-work.txt").read_text(), "Keep this sync work.\n")
        self.assertFalse((clone.parent / "complete").exists())

    def test_failed_agent_keeps_clone_and_work(self) -> None:
        result = self.run_sync(PSTACK_TEST_MODE="failed")
        self.assertEqual(result.returncode, 17)
        clone = Path((self.root / "agent-cwd").read_text())
        self.assertTrue(clone.is_relative_to(self.state), str(clone))
        self.assertEqual((clone / "local-work.txt").read_text(), "Keep this sync work.\n")

    def test_published_draft_matches_committed_sha_and_keeps_attempt(self) -> None:
        result = self.run_sync(PSTACK_TEST_MODE="published")
        self.assertEqual(result.returncode, 0, result.stderr)
        clone = Path((self.root / "agent-cwd").read_text())
        self.assertEqual((clone / ".github/upstream-sha").read_text(), self.latest + "\n")
        self.assertEqual(self.git("show", "HEAD:.github/upstream-sha", cwd=clone), self.latest)
        self.assertEqual(self.git("status", "--porcelain", cwd=clone), "")
        self.assertEqual((clone.parent / "complete").read_text(),
                         "https://github.com/mdsmithaustin/pstack/pull/123\n")
        self.assertEqual((clone.parent / "upstream-sha").read_text(), self.latest + "\n")
        self.assertEqual((clone.parent / "base-sha").read_text(),
                         self.git("rev-parse", "HEAD", cwd=self.origin) + "\n")
        self.assertEqual((clone / "skills/architect/SKILL.md").read_text(),
                         "Original live promise owner.\n")
        self.assertEqual((clone.parent / "claude.log").read_text(), "Draft PR published.\n")

    def test_changed_static_owner_completes_without_new_results(self) -> None:
        result = self.run_sync(
            PSTACK_TEST_MODE="published",
            PSTACK_TEST_FILES=json.dumps({"skills/static-check/SKILL.md": "Changed static owner.\n"}),
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        clone = Path((self.root / "agent-cwd").read_text())
        self.assertEqual(self.git("show", "HEAD:skills/static-check/SKILL.md", cwd=clone),
                         "Changed static owner.")
        self.assertEqual((clone.parent / "complete").read_text(),
                         "https://github.com/mdsmithaustin/pstack/pull/123\n")

    def test_changed_live_owner_requires_committed_results(self) -> None:
        result = self.run_sync(
            PSTACK_TEST_MODE="published",
            PSTACK_TEST_FILES=json.dumps({"skills/architect/SKILL.md": "Changed owner.\n"}),
            PSTACK_TEST_MOVE_BASE_REF="1",
        )
        self.assertNotEqual(result.returncode, 0)
        clone = Path((self.root / "agent-cwd").read_text())
        self.assertTrue(clone.is_dir())
        self.assertEqual((clone / "skills/architect/SKILL.md").read_text(), "Changed owner.\n")
        self.assertFalse((clone.parent / "complete").exists())
        self.assertEqual((clone.parent / "base-sha").read_text(),
                         self.git("rev-parse", "HEAD", cwd=self.origin) + "\n")
        self.assertEqual(self.git("rev-parse", "main", cwd=clone),
                         self.git("rev-parse", "HEAD", cwd=clone))
        log = (self.state / "sync.log").read_text()
        self.assertIn("architect-checkpoint-opt-in", log)
        self.assertIn("skills/architect/SKILL.md", log)
        self.assertIn("committed results Markdown", log)
        retry = self.run_sync(PSTACK_TEST_MODE="published")
        self.assertNotEqual(retry.returncode, 0)
        self.assertEqual((self.root / "agent-calls").read_text(), "called\n")

    def test_added_or_updated_committed_results_allow_live_owner_change(self) -> None:
        for report in ("new.md", "earlier.md"):
            with self.subTest(report=report):
                result = self.run_sync(
                    PSTACK_TEST_MODE="published", PSTACK_SYNC_STATE_DIR=str(self.root / report),
                    PSTACK_TEST_FILES=json.dumps({
                        "skills/architect/SKILL.md": "Changed owner.\n",
                        f"evals/promises/results/{report}": "Current results.\n",
                    }),
                )
                self.assertEqual(result.returncode, 0)
                clone = Path((self.root / "agent-cwd").read_text())
                self.assertTrue((clone.parent / "complete").is_file())

    def test_invalid_results_do_not_satisfy_live_evidence(self) -> None:
        reports = {
            "empty": {"evals/promises/results/new.md": " \n\t"},
            "unrelated": {"docs/results.md": "Current results.\n",
                          "evals/promises/results/new.txt": "Current results.\n"},
            "deleted": {"evals/promises/results/earlier.md": None},
            "mode_only": {},
        }
        for case, files in reports.items():
            with self.subTest(case=case):
                result = self.run_sync(
                    PSTACK_TEST_MODE="published", PSTACK_SYNC_STATE_DIR=str(self.root / case),
                    PSTACK_TEST_CHMOD_REPORT="1" if case == "mode_only" else "",
                    PSTACK_TEST_FILES=json.dumps({"skills/architect/SKILL.md": "Changed owner.\n", **files}),
                )
                self.assertNotEqual(result.returncode, 0)
                clone = Path((self.root / "agent-cwd").read_text())
                self.assertFalse((clone.parent / "complete").exists())
                self.assertIn("committed results Markdown", (clone.parent.parent / "sync.log").read_text())

    def test_added_and_deleted_live_owners_require_results(self) -> None:
        cases = {
            "added": {
                "evals/promises/ledger.json": json.dumps({"promises": {
                    "new-live-promise": {"check": "live", "owners": ["skills/new/SKILL.md"]},
                }}),
                "skills/new/SKILL.md": "New live owner.\n",
            },
            "deleted": {
                "evals/promises/ledger.json": json.dumps({"promises": {}}),
                "skills/architect/SKILL.md": None,
            },
        }
        for case, files in cases.items():
            with self.subTest(case=case):
                result = self.run_sync(
                    PSTACK_TEST_MODE="published", PSTACK_SYNC_STATE_DIR=str(self.root / case),
                    PSTACK_TEST_FILES=json.dumps(files),
                )
                self.assertNotEqual(result.returncode, 0)
                clone = Path((self.root / "agent-cwd").read_text())
                self.assertFalse((clone.parent / "complete").exists())
                self.assertIn("committed results Markdown", (clone.parent.parent / "sync.log").read_text())

    def test_missing_or_malformed_committed_ledger_refuses_completion(self) -> None:
        for case, contents in (("missing", None), ("malformed", "not JSON"),
                               ("wrong_shape", '{"promises": []}')):
            with self.subTest(case=case):
                result = self.run_sync(
                    PSTACK_TEST_MODE="published", PSTACK_SYNC_STATE_DIR=str(self.root / case),
                    PSTACK_TEST_FILES=json.dumps({"evals/promises/ledger.json": contents}),
                )
                self.assertNotEqual(result.returncode, 0)
                clone = Path((self.root / "agent-cwd").read_text())
                self.assertFalse((clone.parent / "complete").exists())
                self.assertIn("cannot verify committed promise ledger",
                              (clone.parent.parent / "sync.log").read_text())

    def test_invalid_base_ledger_cannot_be_repaired_to_bypass_guard(self) -> None:
        ledger = self.origin / "evals" / "promises" / "ledger.json"
        contents = ledger.read_text()
        for case in ("missing", "malformed"):
            with self.subTest(case=case):
                if case == "missing":
                    ledger.unlink()
                else:
                    ledger.write_text("not JSON")
                self.git("add", "-A", cwd=self.origin)
                self.git("commit", "-qm", "Invalid baseline ledger", cwd=self.origin)
                result = self.run_sync(
                    PSTACK_TEST_MODE="published", PSTACK_SYNC_STATE_DIR=str(self.root / case),
                    PSTACK_TEST_FILES=json.dumps({"evals/promises/ledger.json": contents}),
                )
                self.assertNotEqual(result.returncode, 0)
                clone = Path((self.root / "agent-cwd").read_text())
                self.assertFalse((clone.parent / "complete").exists())
                self.assertIn("cannot verify committed promise ledger",
                              (clone.parent.parent / "sync.log").read_text())

    def test_incomplete_sync_is_rejected_even_when_agent_says_published(self) -> None:
        for mode in ("stale_recorded", "dirty", "wrong_branch", "commit_only"):
            with self.subTest(mode=mode):
                state = self.root / mode
                result = self.run_sync(PSTACK_TEST_MODE=mode, PSTACK_SYNC_STATE_DIR=str(state))
                self.assertNotEqual(result.returncode, 0)
                clone = Path((self.root / "agent-cwd").read_text())
                self.assertTrue(clone.is_dir())
                self.assertFalse((clone.parent / "complete").exists())

    def test_invalid_live_pr_is_rejected_and_retained(self) -> None:
        for case in ("wrong_base_repo", "wrong_head_repo", "wrong_base", "wrong_branch",
                     "stale_head", "ready", "closed", "missing", "ambiguous", "malformed",
                     "unavailable"):
            with self.subTest(case=case):
                state = self.root / case
                result = self.run_sync(PSTACK_TEST_MODE="published", PSTACK_TEST_PR_CASE=case,
                                       PSTACK_SYNC_STATE_DIR=str(state))
                self.assertNotEqual(result.returncode, 0)
                clone = Path((self.root / "agent-cwd").read_text())
                self.assertTrue(clone.is_dir())
                self.assertFalse((clone.parent / "complete").exists())

    def test_pending_attempt_blocks_another_paid_run(self) -> None:
        self.assertNotEqual(self.run_sync().returncode, 0)
        retained = Path((self.root / "agent-cwd").read_text())
        attempts = set(self.state.glob("attempt-*"))
        result = self.run_sync(PSTACK_TEST_MODE="published")
        self.assertEqual(result.returncode, 1)
        self.assertEqual((self.root / "agent-calls").read_text(), "called\n")
        self.assertIn("resolve it before another Claude run", (self.state / "sync.log").read_text())

        fresh, = set(self.state.glob("attempt-*")) - attempts
        self.assertFalse((fresh / "repo").exists())
        self.assertEqual((retained / "local-work.txt").read_text(), "Keep this sync work.\n")
        self.assertTrue((retained.parent / "prompt.txt").is_file())
        self.assertFalse((fresh / "complete").exists())

    def test_open_pr_skips_even_with_pending_attempt(self) -> None:
        self.assertNotEqual(self.run_sync().returncode, 0)
        retained = Path((self.root / "agent-cwd").read_text())
        attempts = set(self.state.glob("attempt-*"))
        result = self.run_sync(PSTACK_TEST_OPEN_PR="1")
        self.assertEqual(result.returncode, 0)
        self.assertEqual((self.root / "agent-calls").read_text(), "called\n")
        self.assertIn("skipping until it lands", (self.state / "sync.log").read_text())

        fresh, = set(self.state.glob("attempt-*")) - attempts
        self.assertFalse((fresh / "repo").exists())
        self.assertEqual((retained / "local-work.txt").read_text(), "Keep this sync work.\n")
        self.assertTrue((retained.parent / "prompt.txt").is_file())
        self.assertEqual((fresh / "complete").read_text(), "sync PR already open\n")

    def test_unchanged_upstream_skips_even_with_pending_attempt(self) -> None:
        self.assertNotEqual(self.run_sync().returncode, 0)
        retained = Path((self.root / "agent-cwd").read_text())
        attempts = set(self.state.glob("attempt-*"))
        (self.origin / ".github/upstream-sha").write_text(self.latest + "\n")
        self.git("commit", "-qam", "Record completed sync", cwd=self.origin)
        result = self.run_sync()
        self.assertEqual(result.returncode, 0)
        self.assertEqual((self.root / "agent-calls").read_text(), "called\n")
        self.assertIn("upstream unchanged", (self.state / "sync.log").read_text())

        fresh, = set(self.state.glob("attempt-*")) - attempts
        self.assertFalse((fresh / "repo").exists())
        self.assertEqual((retained / "local-work.txt").read_text(), "Keep this sync work.\n")
        self.assertTrue((retained.parent / "prompt.txt").is_file())
        self.assertEqual((fresh / "complete").read_text(), "upstream unchanged\n")

    def test_prompt_limits_authorization_to_draft_publication(self) -> None:
        result = self.run_sync(PSTACK_TEST_MODE="published")
        self.assertEqual(result.returncode, 0)
        prompt = (self.root / "received-prompt").read_text()
        branch = self.git("branch", "--show-current", cwd=Path((self.root / "agent-cwd").read_text()))
        self.assertIn(f"scheduled sync branch, {branch}, and create its draft PR", prompt)
        self.assertIn("user explicitly authorizes bypassing no-mistakes ONLY", prompt)
        self.assertIn("does not relax any local check", prompt)
        self.assertIn("not authorize marking a PR ready, merging, pushing to main, force-pushing", prompt)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--runner", type=Path, default=RUNNER)
    args, remaining = parser.parse_known_args()
    RUNNER = args.runner.resolve(strict=True)
    unittest.main(argv=[sys.argv[0], *remaining])
