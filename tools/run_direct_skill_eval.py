from __future__ import annotations

import argparse
import shlex
import subprocess
from pathlib import Path


def adapter_arguments(agent: str, skill_ci: Path) -> list[str]:
    if agent == "claude":
        return ["--claude-bin", str(skill_ci / "tools" / "claude-project-only")]
    if agent == "codex":
        command = skill_ci / "tools" / "codex-project-only"
        return [
            "--codex-cmd",
            f"{command} exec --json --skip-git-repo-check --sandbox read-only",
        ]
    raise ValueError(f"unsupported agent: {agent}")


def command_plan(
    *,
    repo: Path,
    skill_ci: Path,
    skill: str,
    split: str,
    agent: str,
    model: str,
    judge_backend: str,
    judge_model: str,
    output: Path,
    runs: int,
    judge_runs: int,
    timeout: int,
) -> list[list[str]]:
    if agent == judge_backend:
        raise ValueError("answer and judge backends must be from different model families")
    manifest = repo / "evals" / skill / "shared-benchmark.json"
    runner = skill_ci / "tools" / "run_runner.py"
    if not manifest.is_file():
        raise ValueError(f"missing manifest: {manifest}")
    if not runner.is_file():
        raise ValueError(f"missing pinned runner: {runner}")
    prefix = ["uv", "run", "--no-project", "python", str(runner), "skill-benchmark"]
    tasks = output / "tasks.jsonl"
    answer_runs = output / "answers"
    judge_results = output / "judge.jsonl"
    benchmark = output / "benchmark.json"
    validation = [*prefix, "validate", "--strict-leakage"]
    if split == "holdback":
        validation.append("--strict-holdback")
    validation.append(str(manifest))
    return [
        validation,
        [
            *prefix,
            "audit-manifest",
            "--fail-on-blockers",
            "--strict-judge",
            str(manifest),
        ],
        [
            *prefix,
            "prepare",
            str(manifest),
            "--split",
            split,
            "--runs-per-variant",
            str(runs),
            "--out",
            str(tasks),
        ],
        [
            *prefix,
            "run-agent",
            "--agent",
            agent,
            "--model",
            model,
            *adapter_arguments(agent, skill_ci),
            "--tasks",
            str(tasks),
            "--runs",
            str(answer_runs),
            "--timeout",
            str(timeout),
        ],
        [
            *prefix,
            "grade",
            str(manifest),
            "--runs",
            str(answer_runs),
            "--split",
            split,
            "--allow-scripts",
            "--out",
            str(output / "grade.json"),
        ],
        [
            *prefix,
            "judge",
            str(manifest),
            "--runs",
            str(answer_runs),
            "--split",
            split,
            "--judge-backend",
            judge_backend,
            "--judge-model",
            judge_model,
            "--judge-runs",
            str(judge_runs),
            *adapter_arguments(judge_backend, skill_ci),
            "--transcripts",
            str(output / "judge-transcripts"),
            "--out",
            str(judge_results),
        ],
        [
            *prefix,
            "benchmark",
            str(manifest),
            "--runs",
            str(answer_runs),
            "--split",
            split,
            "--allow-scripts",
            "--judge-results",
            str(judge_results),
            "--out",
            str(benchmark),
        ],
        [
            *prefix,
            "report",
            "--benchmark",
            str(benchmark),
            "--format",
            "github",
            "--out",
            str(output / "report.md"),
        ],
    ]


def main() -> int:
    source_repo = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(description="Run one direct-skill answer and cross-family judge arm.")
    parser.add_argument("--repo", type=Path, default=source_repo)
    parser.add_argument("--skill-ci", type=Path, default=source_repo.parent / "skill-ci")
    parser.add_argument("--skill", required=True)
    parser.add_argument("--split", choices=("tune", "holdback"), default="tune")
    parser.add_argument("--agent", choices=("claude", "codex"), required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--judge-backend", choices=("claude", "codex"), required=True)
    parser.add_argument("--judge-model", required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--judge-runs", type=int, default=3)
    parser.add_argument("--timeout", type=int, default=240)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    repo = args.repo.resolve()
    skill_ci = args.skill_ci.resolve()
    output = args.out.resolve()
    if args.runs < 1 or args.judge_runs < 1 or args.timeout < 1:
        parser.error("runs, judge-runs, and timeout must be positive")
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        parser.error(f"output must be a new or empty directory: {output}")
    try:
        commands = command_plan(
            repo=repo,
            skill_ci=skill_ci,
            skill=args.skill,
            split=args.split,
            agent=args.agent,
            model=args.model,
            judge_backend=args.judge_backend,
            judge_model=args.judge_model,
            output=output,
            runs=args.runs,
            judge_runs=args.judge_runs,
            timeout=args.timeout,
        )
    except ValueError as exc:
        parser.error(str(exc))
    if args.dry_run:
        for command in commands:
            print(shlex.join(command))
        return 0
    output.mkdir(parents=True, exist_ok=True)
    for command in commands:
        subprocess.run(command, cwd=repo, check=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
