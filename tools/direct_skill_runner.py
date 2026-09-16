#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import os
import re
import shutil
import stat
import sys
from pathlib import Path
from typing import Any, Sequence


RUNNER_PREFIX = "git+https://github.com/mdsmithaustin/skill-eval-harness.git@"
LOCK_PATTERN = re.compile(re.escape(RUNNER_PREFIX) + r"([0-9a-fA-F]{40})\Z")
RECEIPT_KEY = "pstack_workspace_receipt"


class RunnerError(ValueError):
    pass


def runner_spec(skill_ci: Path) -> str:
    lock = skill_ci / "runner.lock"
    try:
        entries = [
            line.strip()
            for line in lock.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]
    except (OSError, UnicodeError) as exc:
        raise RunnerError(f"cannot read pinned runner lock {lock}: {exc}") from exc
    if len(entries) != 1 or LOCK_PATTERN.fullmatch(entries[0]) is None:
        raise RunnerError("runner.lock must pin skill-eval-harness to one full commit")
    return entries[0]


def pinned_runner_argv(
    script: Path,
    skill_ci: Path,
    backend: str,
    runner_arguments: Sequence[str],
) -> list[str]:
    return [
        "uv",
        "tool",
        "run",
        "--isolated",
        "--from",
        runner_spec(skill_ci),
        "python",
        "-I",
        str(script.resolve()),
        "--inside-pinned-runner",
        "--backend",
        backend,
        "--",
        *runner_arguments,
    ]


def _tree_state(workspace: Path) -> dict[str, Any]:
    files: dict[str, str] = {}
    for root_name in ("inputs", "skills"):
        root = workspace / root_name
        if not root.exists():
            continue
        if root.is_symlink() or not root.is_dir():
            raise RunnerError(f"workspace mount is not a regular directory: {root_name}")
        for path in sorted(root.rglob("*")):
            if path.is_symlink():
                raise RunnerError(
                    f"workspace mount contains a symlink: {path.relative_to(workspace)}"
                )
            if path.is_dir():
                continue
            metadata = path.stat()
            if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
                raise RunnerError(
                    f"workspace mount contains a non-regular file: {path.relative_to(workspace)}"
                )
            relative = path.relative_to(workspace).as_posix()
            files[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    digest = hashlib.sha256()
    for relative, file_digest in sorted(files.items()):
        digest.update(relative.encode("utf-8") + b"\0")
        digest.update(file_digest.encode("ascii") + b"\0")
    return {"sha256": digest.hexdigest(), "files": files}


def workspace_receipt(workspace: Path, before: dict[str, Any]) -> dict[str, Any]:
    after = _tree_state(workspace)
    root = workspace.resolve(strict=True)
    python = shutil.which("python3")
    if python is None:
        raise RunnerError("python3 is unavailable in the answer runner environment")
    python_path = Path(python).resolve(strict=True)
    return {
        "schema_version": 2,
        "mounts": sorted(before["files"]),
        "pre_sha256": before["sha256"],
        "post_sha256": after["sha256"],
        "workspace_root_sha256": hashlib.sha256(
            root.as_posix().encode("utf-8")
        ).hexdigest(),
        "python_path_sha256": hashlib.sha256(
            python_path.as_posix().encode("utf-8")
        ).hexdigest(),
    }


def decorate_backend(module: Any, backend_name: str) -> None:
    try:
        delegate = module.AGENT_BACKENDS[backend_name]
    except (AttributeError, KeyError) as exc:
        raise RunnerError(f"unsupported runner backend: {backend_name}") from exc

    class WorkspaceReceiptBackend:
        name = backend_name

        def invoke_answer(self, request: Any, **options: Any) -> Any:
            before = _tree_state(Path(request.workspace))
            outcome = delegate.invoke_answer(request, **options)
            try:
                receipt = workspace_receipt(Path(request.workspace), before)
            except RunnerError as exc:
                python = shutil.which("python3")
                receipt = {
                    "schema_version": 2,
                    "mounts": sorted(before["files"]),
                    "pre_sha256": before["sha256"],
                    "workspace_root_sha256": hashlib.sha256(
                        Path(request.workspace)
                        .resolve(strict=True)
                        .as_posix()
                        .encode("utf-8")
                    ).hexdigest(),
                    "python_path_sha256": (
                        hashlib.sha256(
                            Path(python)
                            .resolve(strict=True)
                            .as_posix()
                            .encode("utf-8")
                        ).hexdigest()
                        if python is not None
                        else None
                    ),
                    "error": str(exc),
                }
            context = module.outcome_context(outcome)
            return module.outcome_with_context(
                outcome,
                context.enriched(metadata={RECEIPT_KEY: receipt}),
            )

    module.AGENT_BACKENDS[backend_name] = WorkspaceReceiptBackend()


def run_inside(backend: str, runner_arguments: Sequence[str]) -> int:
    import skill_benchmark

    decorate_backend(skill_benchmark, backend)
    sys.argv = ["skill-benchmark", *runner_arguments]
    return int(skill_benchmark.main())


def parse_arguments(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the pinned direct-skill answer backend with workspace evidence."
    )
    parser.add_argument("--inside-pinned-runner", action="store_true")
    parser.add_argument("--skill-ci", type=Path)
    parser.add_argument("--backend", choices=("claude", "codex"), required=True)
    parser.add_argument("runner_arguments", nargs=argparse.REMAINDER)
    values = parser.parse_args(argv)
    if values.runner_arguments[:1] == ["--"]:
        values.runner_arguments = values.runner_arguments[1:]
    if not values.runner_arguments or values.runner_arguments[0] != "run-agent":
        parser.error("expected run-agent followed by pinned runner arguments")
    if not values.inside_pinned_runner and values.skill_ci is None:
        parser.error("--skill-ci is required outside the pinned runner")
    return values


def main(argv: Sequence[str] | None = None) -> int:
    values = parse_arguments(argv)
    if values.inside_pinned_runner:
        return run_inside(values.backend, values.runner_arguments)
    command = pinned_runner_argv(
        Path(__file__),
        values.skill_ci,
        values.backend,
        values.runner_arguments,
    )
    try:
        os.execvp(command[0], command)
    except FileNotFoundError as exc:
        raise SystemExit("uv is required to run the pinned evaluator") from exc


if __name__ == "__main__":
    raise SystemExit(main())
