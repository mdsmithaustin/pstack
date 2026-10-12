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
        self.git("config", "status.showUntrackedFiles", "no")

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

    def merged_worktree(self, name: str) -> Path:
        self.init("main")
        (self.repo / ".gitignore").write_text(".audit/\n", encoding="utf-8")
        self.git("add", ".gitignore")
        self.git("commit", "-q", "-m", "ignore")
        origin = self.tmp / "origin.git"
        self.git("init", "-q", "--bare", str(origin))
        self.git("remote", "add", "origin", str(origin))
        self.git("push", "-q", "origin", "main")
        self.git("fetch", "-q", "origin")
        path = self.tmp / name
        self.git("worktree", "add", "-q", "-b", name, str(path), "main")
        return path

    def row(self, worktree: Path) -> tuple[str, str]:
        result = self.audit()
        self.assertEqual(result.returncode, 0, result.stderr)
        fields = next(line.split("\t") for line in result.stdout.splitlines() if line.endswith(f"\t{worktree}"))
        return fields[3], fields[7]

    def test_untracked_file_in_a_cache_named_dir_is_kept(self):
        worktree = self.merged_worktree("wt-dist")
        (worktree / "dist").mkdir()
        (worktree / "dist" / "important.txt").write_text("keep\n", encoding="utf-8")
        self.assertEqual(self.row(worktree), ("kept:1", "hold-kept"))

    def test_ignored_file_in_a_non_ignored_cache_named_dir_is_kept(self):
        worktree = self.merged_worktree("wt-ignored-dist")
        (self.repo / ".gitignore").write_text("*.log\n", encoding="utf-8")
        self.git("add", ".gitignore")
        self.git("commit", "-q", "-m", "ignore logs")
        self.git("-C", str(worktree), "merge", "-q", "--ff-only", "main")
        self.git("push", "-q", "origin", "main")
        (worktree / "dist").mkdir()
        (worktree / "dist" / "run.log").write_text("trail\n", encoding="utf-8")
        self.assertEqual(self.row(worktree), ("kept:1", "hold-kept"))

    def test_untracked_file_in_an_ignored_submodule_is_held(self):
        sub = self.tmp / "sub"
        sub.mkdir()
        for args in (("init", "-q", "-b", "main"), ("commit", "-q", "--allow-empty", "-m", "sub")):
            subprocess.run(["git", *args], cwd=sub, env=self.env, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.init("main")
        self.git("-c", "protocol.file.allow=always", "submodule", "add", "-q", str(sub), "sub")
        self.git("config", "-f", ".gitmodules", "submodule.sub.ignore", "all")
        self.git("add", ".gitmodules")
        self.git("commit", "-q", "-m", "submodule")
        origin = self.tmp / "origin.git"
        self.git("init", "-q", "--bare", str(origin))
        self.git("remote", "add", "origin", str(origin))
        self.git("push", "-q", "origin", "main")
        self.git("fetch", "-q", "origin")
        worktree = self.tmp / "wt-sub"
        self.git("worktree", "add", "-q", "-b", "wt-sub", str(worktree), "main")
        subprocess.run(["git", "-c", "protocol.file.allow=always", "submodule", "update", "-q", "--init"], cwd=worktree,
                       env=self.env, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        (worktree / "sub" / "notes.txt").write_text("trail\n", encoding="utf-8")
        self.assertEqual(self.row(worktree), ("wip:1,kept:1", "hold-wip"))

    def test_ignored_trail_in_a_clean_populated_submodule_is_kept(self):
        sub = self.tmp / "sub"
        sub.mkdir()
        subprocess.run(["git", "init", "-q", "-b", "main"], cwd=sub, env=self.env, check=True,
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        (sub / ".gitignore").write_text(".audit/\n", encoding="utf-8")
        for args in (("add", ".gitignore"), ("commit", "-q", "-m", "ignore trail")):
            subprocess.run(["git", *args], cwd=sub, env=self.env, check=True,
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.init("main")
        self.git("-c", "protocol.file.allow=always", "submodule", "add", "-q", str(sub), "sub")
        self.git("config", "-f", ".gitmodules", "submodule.sub.ignore", "all")
        self.git("add", ".gitmodules")
        self.git("commit", "-q", "-m", "submodule")
        origin = self.tmp / "origin.git"
        self.git("init", "-q", "--bare", str(origin))
        self.git("remote", "add", "origin", str(origin))
        self.git("push", "-q", "origin", "main")
        self.git("fetch", "-q", "origin")
        worktree = self.tmp / "wt-sub-trail"
        self.git("worktree", "add", "-q", "-b", "wt-sub-trail", str(worktree), "main")
        subprocess.run(["git", "-c", "protocol.file.allow=always", "submodule", "update", "-q", "--init"], cwd=worktree,
                       env=self.env, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        (worktree / "sub" / ".audit").mkdir()
        trail = worktree / "sub" / ".audit" / "d.tsv"
        trail.write_text("trail\n", encoding="utf-8")
        self.assertEqual(self.row(worktree), ("kept:1", "hold-kept"))
        result = self.audit()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(f"# kept: {worktree}/sub/", result.stdout.splitlines())
        self.assertEqual(trail.read_text(encoding="utf-8"), "trail\n")

    def test_ignored_trail_in_a_gitlink_without_gitmodules_is_kept(self):
        sub = self.tmp / "sub"
        sub.mkdir()
        subprocess.run(["git", "init", "-q", "-b", "main"], cwd=sub, env=self.env, check=True,
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        (sub / ".gitignore").write_text(".audit/\n", encoding="utf-8")
        for args in (("add", ".gitignore"), ("commit", "-q", "-m", "ignore trail")):
            subprocess.run(["git", *args], cwd=sub, env=self.env, check=True,
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        sub_head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=sub, env=self.env, check=True,
                                  stdout=subprocess.PIPE, text=True).stdout.strip()
        worktree = self.merged_worktree("wt-gitlink")
        self.git("update-index", "--add", "--cacheinfo", f"160000,{sub_head},sub")
        self.git("commit", "-q", "-m", "gitlink without gitmodules")
        self.git("-C", str(worktree), "merge", "-q", "--ff-only", "main")
        self.git("push", "-q", "origin", "main")
        self.git("clone", "-q", str(sub), str(worktree / "sub"))
        (worktree / "sub" / ".audit").mkdir()
        (worktree / "sub" / ".audit" / "d.tsv").write_text("trail\n", encoding="utf-8")
        self.assertEqual(self.row(worktree), ("kept:1", "hold-kept"))

    def test_untracked_nested_checkout_is_counted_once(self):
        worktree = self.merged_worktree("wt-scratch")
        scratch = worktree / "scratch"
        scratch.mkdir()
        subprocess.run(["git", "init", "-q", "-b", "main"], cwd=scratch, env=self.env, check=True,
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        (scratch / "notes.txt").write_text("trail\n", encoding="utf-8")
        result = self.audit()
        self.assertEqual(result.returncode, 0, result.stderr)
        lines = result.stdout.splitlines()
        fields = next(line.split("\t") for line in lines if line.endswith(f"\t{worktree}"))
        self.assertEqual((fields[3], fields[7]), ("kept:1", "hold-kept"))
        self.assertEqual(lines.count(f"# kept: {worktree}/scratch/"), 1, result.stdout)

    def test_untracked_parent_covers_a_nested_checkout(self):
        worktree = self.merged_worktree("wt-notes")
        nested = worktree / "notes" / "repo"
        nested.mkdir(parents=True)
        subprocess.run(["git", "init", "-q", "-b", "main"], cwd=nested, env=self.env, check=True,
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        (nested / "notes.txt").write_text("trail\n", encoding="utf-8")
        result = self.audit()
        self.assertEqual(result.returncode, 0, result.stderr)
        lines = result.stdout.splitlines()
        fields = next(line.split("\t") for line in lines if line.endswith(f"\t{worktree}"))
        self.assertEqual((fields[3], fields[7]), ("kept:1", "hold-kept"))
        self.assertEqual([line for line in lines if line.startswith("# kept: ")],
                         [f"# kept: {worktree}/notes/"], result.stdout)

    def test_ignored_build_cache_covers_a_nested_checkout(self):
        worktree = self.merged_worktree("wt-venv")
        (self.repo / ".gitignore").write_text(".audit/\n.venv/\n", encoding="utf-8")
        self.git("add", ".gitignore")
        self.git("commit", "-q", "-m", "ignore virtualenv")
        self.git("-C", str(worktree), "merge", "-q", "--ff-only", "main")
        self.git("push", "-q", "origin", "main")
        nested = worktree / ".venv" / "src" / "pkg"
        nested.mkdir(parents=True)
        subprocess.run(["git", "init", "-q", "-b", "main"], cwd=nested, env=self.env, check=True,
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        (nested / "package.py").write_text("pass\n", encoding="utf-8")
        self.assertEqual(self.row(worktree), ("clean", "safe"))

    def test_unreadable_status_is_never_safe(self):
        worktree = self.merged_worktree("wt-corrupt")
        (worktree / ".audit").mkdir()
        (worktree / ".audit" / "decisions.tsv").write_text("ts\n", encoding="utf-8")
        git_dir = subprocess.run(["git", "rev-parse", "--absolute-git-dir"], cwd=worktree, env=self.env,
                                 check=True, stdout=subprocess.PIPE, text=True).stdout.strip()
        Path(git_dir, "index").write_bytes(b"not an index")
        self.assertEqual(self.row(worktree), ("unreadable", "review"))


if __name__ == "__main__":
    unittest.main()
