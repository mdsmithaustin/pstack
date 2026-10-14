from __future__ import annotations

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent

GENERATED = (
    ".agents/skills/copied/SKILL.md",
    ".claude/skills/copied/SKILL.md",
    "skills-lock.json",
    ".gitnexus/index.json",
    ".audit/run/decisions.tsv",
    "decisions.tsv",
    "children.tsv",
    ".claude/scheduled_tasks.lock",
    ".claude/scheduled_tasks.json",
    ".claude/routines/.state/run.json",
    ".claude/worktrees/run/source.py",
    ".claude/checkpoints/checkpoint.json",
    ".claude/mailbox/message.json",
    ".claude/agent-registry.json",
    ".claude/agent-memory-local",
    ".claude/first-run",
    ".claude/assistant-daemon-state.json",
    "fixtures/project/.claude/mailbox/message.json",
)

MAINTAINED = (
    ".agents/pstack-models.md",
    ".agents/automations/benny.md",
    ".claude/settings.json",
    ".claude/agents/reviewer.md",
    ".skill-ci.toml",
    "docs/research/findings.md",
    "docs/research/decisions.tsv",
    "examples/children.tsv",
    "examples/skills-lock.json",
    "examples/.agents/skills/SKILL.md",
    "examples/.gitnexus/config.json",
    "agent/source.py",
    "skills/unslop/SKILL.md",
    "tools/check.py",
)


class GeneratedArtifactsStayOutOfGit(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.repo = Path(self.directory.name)
        subprocess.run(["git", "init", "--template=", "-q", str(self.repo)], check=True)
        shutil.copyfile(ROOT / ".gitignore", self.repo / ".gitignore")

    def test_generated_files_are_ignored_and_maintained_files_are_trackable(self) -> None:
        for paths, expected in ((GENERATED, 0), (MAINTAINED, 1)):
            for path in paths:
                with self.subTest(path=path):
                    target = self.repo / path
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text("fixture\n", encoding="utf-8")
                    result = subprocess.run(
                        ["git", "-c", "core.excludesFile=/dev/null", "check-ignore",
                         "--no-index", "-q", path],
                        cwd=self.repo, capture_output=True,
                    )
                    self.assertEqual(result.returncode, expected, result.stderr.decode())

        inventory = subprocess.run(
            ["git", "-c", "core.excludesFile=/dev/null", "ls-files", "--others",
             "--exclude-standard", "-z"],
            cwd=self.repo, check=True, capture_output=True, text=True,
        ).stdout.rstrip("\0").split("\0")
        self.assertEqual(sorted(inventory), sorted((".gitignore", *MAINTAINED)))

    def test_installed_skill_symlinks_are_ignored(self) -> None:
        for path in (".agents/skills", ".claude/skills"):
            with self.subTest(path=path):
                target = self.repo / path
                target.parent.mkdir(parents=True)
                target.symlink_to("../skills")
                result = subprocess.run(
                    ["git", "-c", "core.excludesFile=/dev/null", "check-ignore",
                     "--no-index", "-q", path],
                    cwd=self.repo, capture_output=True,
                )
                self.assertEqual(result.returncode, 0, result.stderr.decode())


if __name__ == "__main__":
    unittest.main()
