#!/usr/bin/env python3
from __future__ import annotations

import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

IGNORED = (
    "evals/runs/transcript.jsonl",
    "evals/unslop/runs/transcript.jsonl",
    "skills/unslop/evals/runs/transcript.jsonl",
    "skills/unslop/evals/runs/nested/judge-transcripts/run-1/prompt.md",
    "eval-runs/transcript.jsonl",
    "skills/unslop/evals/eval-runs/transcript.jsonl",
    "review-inbox/harvest.md",
    "skills/unslop/evals/review-inbox/harvest.md",
)

TRACKABLE = (
    "evals/unslop/shared-benchmark.json",
    "evals/unslop/oracles/check_edited.py",
    "evals/shared-benchmark.json",
    "skills/unslop/SKILL.md",
)


def ignored(path: str) -> bool:
    return subprocess.run(
        ["git", "check-ignore", "-q", "--no-index", path],
        cwd=ROOT, capture_output=True,
    ).returncode == 0


class EvalArtifactsStayOutOfGit(unittest.TestCase):
    def test_run_transcripts_are_ignored_at_every_depth(self) -> None:
        for path in IGNORED:
            with self.subTest(path=path):
                self.assertTrue(ignored(path), f"{path} would be committable")

    def test_manifests_and_oracles_stay_trackable(self) -> None:
        for path in TRACKABLE:
            with self.subTest(path=path):
                self.assertFalse(ignored(path), f"{path} cannot be committed")


if __name__ == "__main__":
    unittest.main()
