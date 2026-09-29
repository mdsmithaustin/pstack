#!/usr/bin/env python3
"""Repro for the Claude Code transcript slug bug in worktree-audit.sh.

Claude Code names a project's transcript directory by replacing every
non-alphanumeric character of the resolved cwd with "-". The script's slug
line only replaces "/", so a repo path containing "." or "_" (like
my_repo.v2) looks in the wrong directory and never finds a recent chat.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
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
            header, *rows = lines
            self.assertEqual(header.split("\t")[6:8], ["LAST_CHAT", "BUCKET"])
            row = next(r for r in rows if r.endswith(str(worktree)))
            fields = row.split("\t")
            self.assertEqual(fields[6], date.today().strftime("%Y-%m-%d"))
            self.assertEqual(fields[7], "verify-recent-chat")


if __name__ == "__main__":
    unittest.main()
