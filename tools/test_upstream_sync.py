from __future__ import annotations

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
        self.root = Path(self.directory.name)
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
        self.origin = self.root / "origin"
        self.git("init", "--template=", "-q", "-b", "main", str(self.origin))
        (self.origin / ".github").mkdir()
        (self.origin / ".github" / "upstream-sha").write_text(self.recorded + "\n")
        (self.origin / "PORTING.md").write_text("Fixture porting contract.\n")
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
                print("0")
            else:
                print("fixture has no published PR", file=sys.stderr)
                sys.exit(1)
        """)
        self.executable("claude", """
            import os
            import sys
            from pathlib import Path

            root = Path(os.environ["PSTACK_TEST_ROOT"])
            (root / "agent-cwd").write_text(str(Path.cwd()))
            (root / "received-prompt").write_text(sys.stdin.read())
            Path("local-work.txt").write_text("Keep this sync work.\\n")
            print("Publication blocked by the configured gate.")
            sys.exit(17 if os.environ["PSTACK_TEST_MODE"] == "failed" else 0)
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

    def test_failed_agent_keeps_clone_and_work(self) -> None:
        result = self.run_sync(PSTACK_TEST_MODE="failed")
        self.assertEqual(result.returncode, 17)
        clone = Path((self.root / "agent-cwd").read_text())
        self.assertTrue(clone.is_relative_to(self.state), str(clone))
        self.assertEqual((clone / "local-work.txt").read_text(), "Keep this sync work.\n")


if __name__ == "__main__":
    unittest.main()
