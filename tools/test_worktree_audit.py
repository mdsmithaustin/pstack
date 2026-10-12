#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "skills/poteto-mode/scripts/worktree-audit.sh"


def _have(cmd: str) -> bool:
    return shutil.which(cmd) is not None


@unittest.skipUnless(_have("rg"), "worktree-audit.sh shells out to rg to read transcripts")
@unittest.skipUnless(_have("jq"), "worktree-audit.sh shells out to jq to read PR state")
class WorktreeAuditTranscriptSlugTest(unittest.TestCase):
    def test_last_chat_found_for_repo_path_with_dot_and_underscore(self):
        with tempfile.TemporaryDirectory(prefix="pstack-worktree-audit-") as tmp_raw:
            tmp = Path(tmp_raw).resolve()
            home = tmp / "home"
            home.mkdir()
            repo = tmp / "my_repo.v2"
            repo.mkdir()

            env = dict(os.environ)
            env["HOME"] = str(home)
            env["GIT_AUTHOR_NAME"] = "pstack-test"
            env["GIT_AUTHOR_EMAIL"] = "pstack-test@example.com"
            env["GIT_COMMITTER_NAME"] = "pstack-test"
            env["GIT_COMMITTER_EMAIL"] = "pstack-test@example.com"

            def git(*args: str, cwd: Path = repo) -> None:
                subprocess.run(
                    ["git", *args], cwd=cwd, env=env, check=True,
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                )

            git("init", "-q", "-b", "main")
            (repo / "README.md").write_text("repro\n", encoding="utf-8")
            git("add", "README.md")
            git("commit", "-q", "-m", "init")

            origin = tmp / "origin.git"
            git("init", "-q", "--bare", str(origin))
            git("remote", "add", "origin", str(origin))
            git("push", "-q", "origin", "main")
            git("fetch", "-q", "origin")

            worktree = tmp / "my_repo.v2-wt"
            git("worktree", "add", "-q", "-b", "wt-branch", str(worktree))

            main_wt = subprocess.run(
                ["git", "rev-parse", "--show-toplevel"], cwd=repo, env=env,
                check=True, stdout=subprocess.PIPE, text=True,
            ).stdout.strip()

            slug = re.sub(r"[^a-zA-Z0-9]", "-", main_wt)
            project_dir = home / ".claude" / "projects" / slug
            project_dir.mkdir(parents=True)
            transcript = project_dir / "s.jsonl"
            transcript.write_text(json.dumps({"cwd": f"{worktree}/"}) + "\n", encoding="utf-8")

            result = subprocess.run(
                ["bash", str(SCRIPT)], cwd=repo, env=env,
                check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            )

            lines = [line for line in result.stdout.splitlines() if line.strip()]
            base, header, *rows = lines
            self.assertEqual(base, "# base: origin/main")
            self.assertEqual(header.split("\t")[6:8], ["LAST_CHAT", "BUCKET"])
            row = next(r for r in rows if r.endswith(str(worktree)))
            fields = row.split("\t")
            self.assertEqual(fields[6], date.today().strftime("%Y-%m-%d"))
            self.assertEqual(fields[7], "verify-recent-chat")



class WorktreeAuditBaseTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="pstack-worktree-audit-base-")
        self.tmp = Path(self._tmp.name).resolve()
        self.env = dict(os.environ, HOME=str(self.tmp / "home"),
                        GIT_AUTHOR_NAME="pstack-test", GIT_AUTHOR_EMAIL="pstack-test@example.com",
                        GIT_COMMITTER_NAME="pstack-test", GIT_COMMITTER_EMAIL="pstack-test@example.com")
        (self.tmp / "home").mkdir()
        self.repo = self.tmp / "repo"
        self.repo.mkdir()

    def tearDown(self):
        self._tmp.cleanup()

    def git(self, *args: str) -> None:
        subprocess.run(["git", *args], cwd=self.repo, env=self.env, check=True,
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    def audit(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(["bash", str(SCRIPT), *args], cwd=self.repo, env=self.env,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    def init(self, branch: str) -> None:
        self.git("init", "-q", "-b", branch)
        (self.repo / "README.md").write_text("repro\n", encoding="utf-8")
        self.git("add", "README.md")
        self.git("commit", "-q", "-m", "init")

    def test_no_remote_base_exits_1(self):
        self.init("main")
        result = self.audit()
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("no base ref", result.stderr)

    def test_unknown_option_exits_2(self):
        self.init("main")
        self.assertEqual(self.audit("--bogus").returncode, 2)

    @unittest.skipUnless(_have("rg") and _have("jq"), "worktree-audit.sh shells out to rg and jq")
    def test_master_default_branch_reports_merged(self):
        self.init("master")
        origin = self.tmp / "origin.git"
        self.git("init", "-q", "--bare", str(origin))
        self.git("remote", "add", "origin", str(origin))
        worktree = self.tmp / "wt"
        self.git("worktree", "add", "-q", "-b", "done", str(worktree))
        self.git("push", "-q", "origin", "master")
        self.git("fetch", "-q", "origin")
        result = self.audit()
        self.assertEqual(result.returncode, 0, result.stderr)
        lines = [line for line in result.stdout.splitlines() if line.strip()]
        self.assertEqual(lines[0], "# base: origin/master")
        row = next(r for r in lines[2:] if r.endswith(str(worktree)))
        self.assertEqual(row.split("\t")[2], "YES")


@unittest.skipUnless(_have("rg") and _have("jq"), "worktree-audit.sh shells out to rg and jq")
class WorktreeAuditKeptPathsTest(WorktreeAuditBaseTest):
    def test_trails_and_notes_hold_while_build_caches_stay_safe(self):
        self.init("master")
        (self.repo / ".gitignore").write_text(".audit/\nnode_modules/\n", encoding="utf-8")
        self.git("add", ".gitignore")
        self.git("commit", "-q", "-m", "ignore")
        origin = self.tmp / "origin.git"
        self.git("init", "-q", "--bare", str(origin))
        self.git("remote", "add", "origin", str(origin))
        self.git("push", "-q", "origin", "master")
        self.git("fetch", "-q", "origin")

        def add(name: str) -> Path:
            path = self.tmp / name
            self.git("worktree", "add", "-q", "-b", name.replace(" ", "-"), str(path), "master")
            return path

        trail = add("wt-trail")
        (trail / ".audit").mkdir()
        (trail / ".audit" / "decisions.tsv").write_text("ts\tphase\n", encoding="utf-8")
        notes = add("wt-notes")
        (notes / "notes.md").write_text("findings\n", encoding="utf-8")
        cache = add("wt-cache")
        (cache / "node_modules").mkdir()
        (cache / "node_modules" / "dep.js").write_text("x\n", encoding="utf-8")
        spaced = add("wt with space")

        result = self.audit()
        self.assertEqual(result.returncode, 0, result.stderr)
        lines = [line for line in result.stdout.splitlines() if line.strip()]
        self.assertEqual(lines[0], "# base: origin/master")
        rows = {Path(f[8]).name: (f[3], f[7]) for f in (line.split("\t") for line in lines[2:] if not line.startswith("#"))}
        self.assertEqual(rows, {
            "wt-trail": ("kept:1", "hold-kept"),
            "wt-notes": ("kept:1", "hold-kept"),
            "wt-cache": ("clean", "safe"),
            "wt with space": ("clean", "safe"),
        }, result.stdout)
        kept = sorted(line for line in lines if line.startswith("# kept: "))
        self.assertEqual(kept, [f"# kept: {notes}/notes.md", f"# kept: {trail}/.audit/"], result.stdout)
        self.assertEqual((trail / ".audit" / "decisions.tsv").read_text(encoding="utf-8"), "ts\tphase\n")
        self.assertTrue(spaced.is_dir())


if __name__ == "__main__":
    unittest.main()
