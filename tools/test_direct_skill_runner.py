from __future__ import annotations

import tempfile
import unittest
from dataclasses import dataclass, replace
from pathlib import Path
from types import SimpleNamespace

from direct_skill_runner import (
    RECEIPT_KEY,
    decorate_backend,
    pinned_runner_argv,
    runner_spec,
)


@dataclass(frozen=True)
class FakeContext:
    metadata: dict[str, object]

    def enriched(self, *, metadata=None, environment=None):
        return replace(self, metadata={**self.metadata, **dict(metadata or {})})


@dataclass
class FakeOutcome:
    context: FakeContext


class FakeBackend:
    name = "codex"

    def __init__(self, *, mutate: bool = False) -> None:
        self.mutate = mutate

    def invoke_answer(self, request, **options):
        if self.mutate:
            (Path(request.workspace) / "inputs" / "driver.py").write_text(
                "changed", encoding="utf-8"
            )
        return FakeOutcome(FakeContext({"delegate": True}))


class FakeRunnerModule:
    def __init__(self, backend: FakeBackend) -> None:
        self.AGENT_BACKENDS = {"codex": backend}

    @staticmethod
    def outcome_context(outcome):
        return outcome.context

    @staticmethod
    def outcome_with_context(outcome, context):
        return FakeOutcome(context)


class DirectSkillRunnerTests(unittest.TestCase):
    def workspace(self, root: Path, payload: str = "original") -> Path:
        workspace = root / "workspace"
        (workspace / "inputs").mkdir(parents=True)
        (workspace / "skills" / "demo").mkdir(parents=True)
        (workspace / "inputs" / "driver.py").write_text(payload, encoding="utf-8")
        (workspace / "skills" / "demo" / "SKILL.md").write_text(
            "---\nname: demo\n---\n", encoding="utf-8"
        )
        return workspace

    def test_decorator_persists_path_free_workspace_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = self.workspace(Path(directory))
            module = FakeRunnerModule(FakeBackend())
            decorate_backend(module, "codex")

            outcome = module.AGENT_BACKENDS["codex"].invoke_answer(
                SimpleNamespace(workspace=workspace)
            )

            receipt = outcome.context.metadata[RECEIPT_KEY]
            self.assertEqual(receipt["schema_version"], 2)
            self.assertEqual(receipt["pre_sha256"], receipt["post_sha256"])
            self.assertRegex(receipt["workspace_root_sha256"], r"^[0-9a-f]{64}$")
            self.assertRegex(receipt["python_path_sha256"], r"^[0-9a-f]{64}$")
            self.assertEqual(
                receipt["mounts"],
                ["inputs/driver.py", "skills/demo/SKILL.md"],
            )
            self.assertNotIn(str(workspace), repr(receipt))
            self.assertTrue(outcome.context.metadata["delegate"])

    def test_decorator_records_mount_mutation_without_promoting_it(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = self.workspace(Path(directory))
            module = FakeRunnerModule(FakeBackend(mutate=True))
            decorate_backend(module, "codex")

            outcome = module.AGENT_BACKENDS["codex"].invoke_answer(
                SimpleNamespace(workspace=workspace)
            )

            receipt = outcome.context.metadata[RECEIPT_KEY]
            self.assertNotEqual(receipt["pre_sha256"], receipt["post_sha256"])

    def test_runner_argv_uses_the_exact_skill_ci_pin(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            skill_ci = root / "skill-ci"
            skill_ci.mkdir()
            commit = "c2a1735983fd7827491ad4d89f9bebe9e8e229a0"
            spec = f"git+https://github.com/mdsmithaustin/skill-eval-harness.git@{commit}"
            (skill_ci / "runner.lock").write_text(spec + "\n", encoding="utf-8")
            script = root / "direct skill runner.py"
            command = pinned_runner_argv(
                script,
                skill_ci,
                "codex",
                ["run-agent", "--agent", "codex"],
            )
            self.assertEqual(runner_spec(skill_ci), spec)
            self.assertEqual(command[command.index("--from") + 1], spec)
            self.assertIn(str(script.resolve()), command)
            self.assertEqual(command[-3:], ["run-agent", "--agent", "codex"])


if __name__ == "__main__":
    unittest.main()
