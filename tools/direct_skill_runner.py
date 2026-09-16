#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import sys
from importlib import metadata
from pathlib import Path
from typing import Any, Sequence


RUNNER_PREFIX = "git+https://github.com/mdsmithaustin/skill-eval-harness.git@"
LOCK_PATTERN = re.compile(re.escape(RUNNER_PREFIX) + r"([0-9a-fA-F]{40})\Z")
RECEIPT_KEY = "pstack_workspace_receipt"
RUNNER_SPEC_ENV = "PSTACK_PINNED_RUNNER_SPEC"
RUNNER_DISTRIBUTION = "skill-eval-harness"
RUNNER_REPOSITORY = "https://github.com/mdsmithaustin/skill-eval-harness.git"


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


def _runner_install_root(expected_spec: str) -> Path:
    match = LOCK_PATTERN.fullmatch(expected_spec)
    if match is None:
        raise RunnerError("internal runner handoff does not contain a valid pin")
    expected_commit = match.group(1).lower()
    try:
        distribution = metadata.distribution(RUNNER_DISTRIBUTION)
        direct_url_text = distribution.read_text("direct_url.json")
        direct_url = json.loads(direct_url_text or "")
        if not isinstance(direct_url, dict):
            raise ValueError("direct_url.json must contain an object")
        distribution_root = Path(distribution.locate_file("")).resolve(strict=True)
        prefix = Path(sys.prefix).resolve(strict=True)
        distribution_root.relative_to(prefix)
        Path(sys.executable).absolute().relative_to(Path(sys.prefix).absolute())
    except (
        AttributeError,
        json.JSONDecodeError,
        metadata.PackageNotFoundError,
        OSError,
        TypeError,
        ValueError,
    ) as exc:
        raise RunnerError(f"cannot attest pinned runner provenance: {exc}") from exc
    if sys.flags.isolated != 1 or Path(sys.prefix).resolve() == Path(sys.base_prefix).resolve():
        raise RunnerError("pinned runner must use isolated Python in a virtual environment")
    vcs = direct_url.get("vcs_info") if isinstance(direct_url, dict) else None
    if (
        direct_url.get("url") != RUNNER_REPOSITORY
        or not isinstance(vcs, dict)
        or vcs.get("vcs") != "git"
        or str(vcs.get("commit_id", "")).lower() != expected_commit
        or str(vcs.get("requested_revision", "")).lower() != expected_commit
    ):
        raise RunnerError("installed runner provenance does not match runner.lock")
    return distribution_root


def verify_runner_provenance(module: Any, expected_spec: str) -> None:
    distribution_root = _runner_install_root(expected_spec)
    try:
        Path(module.__file__).resolve(strict=True).relative_to(distribution_root)
    except (AttributeError, OSError, TypeError, ValueError) as exc:
        raise RunnerError(f"runner module is outside the pinned installation: {exc}") from exc


def run_inside(
    backend: str,
    runner_arguments: Sequence[str],
    expected_spec: str,
) -> int:
    distribution_root = _runner_install_root(expected_spec)
    import skill_benchmark

    try:
        Path(skill_benchmark.__file__).resolve(strict=True).relative_to(distribution_root)
    except (AttributeError, OSError, TypeError, ValueError) as exc:
        raise RunnerError(f"runner module is outside the pinned installation: {exc}") from exc
    decorate_backend(skill_benchmark, backend)
    sys.argv = ["skill-benchmark", *runner_arguments]
    return int(skill_benchmark.main())


def parse_arguments(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the pinned direct-skill answer backend with workspace evidence."
    )
    parser.add_argument("--skill-ci", type=Path)
    parser.add_argument("--backend", choices=("claude", "codex"), required=True)
    parser.add_argument("runner_arguments", nargs=argparse.REMAINDER)
    values = parser.parse_args(argv)
    if values.runner_arguments[:1] == ["--"]:
        values.runner_arguments = values.runner_arguments[1:]
    if not values.runner_arguments or values.runner_arguments[0] != "run-agent":
        parser.error("expected run-agent followed by pinned runner arguments")
    return values


def main(argv: Sequence[str] | None = None) -> int:
    values = parse_arguments(argv)
    expected_spec = os.environ.pop(RUNNER_SPEC_ENV, None)
    if expected_spec is not None:
        return run_inside(values.backend, values.runner_arguments, expected_spec)
    if values.skill_ci is None:
        raise RunnerError("--skill-ci is required outside the pinned runner")
    expected_spec = runner_spec(values.skill_ci)
    command = pinned_runner_argv(
        Path(__file__),
        values.skill_ci,
        values.backend,
        values.runner_arguments,
    )
    try:
        os.environ[RUNNER_SPEC_ENV] = expected_spec
        os.execvp(command[0], command)
    except FileNotFoundError as exc:
        raise SystemExit("uv is required to run the pinned evaluator") from exc


if __name__ == "__main__":
    raise SystemExit(main())
