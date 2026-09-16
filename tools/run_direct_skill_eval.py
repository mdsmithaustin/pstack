from __future__ import annotations

import argparse
import shlex
import subprocess
from pathlib import Path

from direct_skill_lanes import LaneError, _strict_json_loads, verify_materialized_lane


def adapter_arguments(agent: str, skill_ci: Path) -> list[str]:
    if agent == "claude":
        return ["--claude-bin", str(skill_ci / "tools" / "claude-project-only")]
    if agent == "codex":
        command = skill_ci / "tools" / "codex-project-only"
        return [
            "--codex-cmd",
            shlex.join([
                str(command),
                "exec",
                "--json",
                "--skip-git-repo-check",
                "--sandbox",
                "read-only",
            ]),
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
    judge_backend: str | None,
    judge_model: str | None,
    output: Path,
    runs: int,
    judge_runs: int,
    timeout: int,
    lane: str = "isolated",
    helper: Path | None = None,
) -> list[list[str]]:
    if lane == "isolated" and (judge_backend is None or judge_model is None):
        raise ValueError("the isolated lane requires a judge backend and model")
    if lane == "isolated" and agent == judge_backend:
        raise ValueError("answer and judge backends must be from different model families")
    manifest = repo / "evals" / skill / "shared-benchmark.json"
    runner = skill_ci / "tools" / "run_runner.py"
    if not manifest.is_file():
        raise ValueError(f"missing manifest: {manifest}")
    if not runner.is_file():
        raise ValueError(f"missing pinned runner: {runner}")
    if lane not in {"isolated", "integrated"}:
        raise ValueError(f"unsupported lane: {lane}")
    if lane == "integrated":
        try:
            manifest_data = _strict_json_loads(manifest.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise ValueError(f"cannot read integrated manifest: {exc}") from exc
        if (
            not isinstance(manifest_data, dict)
            or manifest_data.get("optional_variants") != ["old_skill"]
            or not manifest_data.get("old_skill_paths")
            or not manifest_data.get("skill_paths")
        ):
            raise ValueError("integrated manifest must define with_skill and old_skill path sets")
        if helper is None or not helper.is_file():
            raise ValueError(f"missing integrated lane helper: {helper}")
    prefix = ["uv", "run", "--no-project", "python", str(runner), "skill-benchmark"]
    tasks = output / "tasks.jsonl"
    answer_runs = output / "answers"
    judge_results = output / "judge.jsonl"
    benchmark = output / "benchmark.json"
    validation = [*prefix, "validate", "--strict-leakage"]
    if split == "holdback":
        validation.append("--strict-holdback")
    validation.append(str(manifest))
    prepare_tasks = output / ("tasks.all.jsonl" if lane == "integrated" else "tasks.jsonl")
    prepare = [
        *prefix,
        "prepare",
        str(manifest),
        "--split",
        split,
        "--runs-per-variant",
        str(runs),
        "--out",
        str(prepare_tasks),
    ]
    if lane == "integrated":
        prepare.append("--include-old-skill")
    shared = [
        validation,
        [
            *prefix,
            "audit-manifest",
            "--fail-on-blockers",
            "--strict-judge",
            str(manifest),
        ],
        prepare,
    ]
    run_agent = [
        "uv",
        "run",
        "--no-project",
        "python",
        str(repo / "tools" / "direct_skill_runner.py"),
        "--skill-ci",
        str(skill_ci),
        "--backend",
        agent,
        "--",
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
    ]
    if lane == "integrated":
        return [
            *shared,
            [
                "python3",
                str(helper),
                "filter-tasks",
                "--input",
                str(prepare_tasks),
                "--out",
                str(tasks),
            ],
            run_agent,
            [
                *prefix,
                "grade",
                str(manifest),
                "--runs",
                str(answer_runs),
                "--split",
                split,
                "--variant",
                "with_skill",
                "--variant",
                "old_skill",
                "--allow-scripts",
                "--out",
                str(output / "grade.json"),
            ],
            [
                "python3",
                str(helper),
                "check-exposure",
                "--runs",
                str(answer_runs),
                "--manifest",
                str(manifest),
                "--skill",
                skill,
                "--split",
                split,
                "--out",
                str(output / "exposure.json"),
            ],
            [
                *prefix,
                "compare-tasks",
                str(manifest),
                "--runs",
                str(answer_runs),
                "--split",
                split,
                "--primary",
                "with_skill",
                "--baseline",
                "old_skill",
                "--out",
                str(output / "compare-tasks.jsonl"),
                "--truth-out",
                str(output / "compare-truth.json"),
            ],
        ]
    return [
        *shared,
        run_agent,
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
            str(judge_model),
            "--judge-runs",
            str(judge_runs),
            *adapter_arguments(str(judge_backend), skill_ci),
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


def execute_plan(
    commands: list[list[str]],
    *,
    cwd: Path,
    integrated_repo: Path | None = None,
    source_repo: Path | None = None,
    skill: str | None = None,
) -> None:
    integrated_values = (integrated_repo, source_repo, skill)
    verification = (
        (source_repo, integrated_repo, skill)
        if source_repo is not None and integrated_repo is not None and skill is not None
        else None
    )
    if any(value is not None for value in integrated_values) and verification is None:
        raise ValueError("integrated post-model verification needs both repositories and the target skill")
    model_stage_complete = False
    for command in commands:
        if model_stage_complete and verification is not None:
            source, integrated, target = verification
            verify_materialized_lane(source, integrated, target)
        subprocess.run(command, cwd=cwd, check=True)
        if "run-agent" in command:
            model_stage_complete = True


def main() -> int:
    source_repo = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(description="Run one direct-skill answer and cross-family judge arm.")
    parser.add_argument("--repo", type=Path, default=source_repo)
    parser.add_argument("--lane", choices=("isolated", "integrated"), default="isolated")
    parser.add_argument("--shadow-repo", type=Path)
    parser.add_argument("--skill-ci", type=Path, default=source_repo.parent / "skill-ci")
    parser.add_argument("--skill", required=True)
    parser.add_argument("--split", choices=("tune", "holdback"), default="tune")
    parser.add_argument("--agent", choices=("claude", "codex"), required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--judge-backend", choices=("claude", "codex"))
    parser.add_argument("--judge-model")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--judge-runs", type=int, default=3)
    parser.add_argument("--timeout", type=int, default=240)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    repo = args.repo.resolve()
    skill_ci = args.skill_ci.resolve()
    if args.out.is_symlink():
        parser.error("output must not be a symlink")
    output = args.out.resolve()
    if args.runs < 1 or args.judge_runs < 1 or args.timeout < 1:
        parser.error("runs, judge-runs, and timeout must be positive")
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        parser.error(f"output must be a new or empty directory: {output}")
    eval_repo = repo
    if args.lane == "integrated":
        if args.shadow_repo is None:
            parser.error("--shadow-repo is required for the integrated lane")
        eval_repo = args.shadow_repo.resolve()
        try:
            verify_materialized_lane(repo, eval_repo, args.skill)
        except LaneError as exc:
            parser.error(str(exc))
        try:
            output.relative_to(eval_repo)
        except ValueError:
            pass
        else:
            parser.error("integrated output must be outside the immutable shadow repository")
    try:
        commands = command_plan(
            repo=eval_repo,
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
            lane=args.lane,
            helper=eval_repo / "tools" / "direct_skill_lanes.py",
        )
    except ValueError as exc:
        parser.error(str(exc))
    if args.dry_run:
        for command in commands:
            print(shlex.join(command))
        if args.lane == "integrated":
            print("Pairwise judging remains external. Judge compare-tasks.jsonl blind, then import verdicts with compare-results.")
        return 0
    output.mkdir(parents=True, exist_ok=True)
    try:
        execute_plan(
            commands,
            cwd=eval_repo,
            integrated_repo=eval_repo if args.lane == "integrated" else None,
            source_repo=repo if args.lane == "integrated" else None,
            skill=args.skill if args.lane == "integrated" else None,
        )
    except (LaneError, ValueError) as exc:
        parser.error(str(exc))
    if args.lane == "integrated":
        print("Pairwise judging remains external. Judge compare-tasks.jsonl blind, then import verdicts with compare-results.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
