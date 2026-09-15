#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Iterable


CONFIG_PATH = Path("evals/direct-skills-experiment.json")
RECEIPT_NAME = "integrated-lane-receipt.json"
PAIRED_VARIANTS = ("with_skill", "old_skill")


class LaneError(ValueError):
    pass


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise LaneError(f"cannot read JSON from {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise LaneError(f"expected a JSON object in {path}")
    return value


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def _validate_regular_tree(root: Path, boundary: Path) -> None:
    if root.is_symlink():
        raise LaneError(f"symlinks are not allowed in lane sources: {root}")
    resolved_root = root.resolve()
    if not _is_within(resolved_root, boundary.resolve()):
        raise LaneError(f"path escapes source repository: {root}")
    if not resolved_root.is_dir():
        raise LaneError(f"missing source directory: {root}")
    for parent, directory_names, file_names in os.walk(resolved_root, followlinks=False):
        parent_path = Path(parent)
        for name in [*directory_names, *file_names]:
            path = parent_path / name
            if path.is_symlink():
                raise LaneError(f"symlinks are not allowed in lane sources: {path}")
            if path.is_file() or path.is_dir():
                continue
            raise LaneError(f"non-regular lane source is not allowed: {path}")


def _inventory(root: Path) -> dict[str, str]:
    files: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise LaneError(f"symlinks are not allowed in a materialized lane: {path}")
        if path.is_file():
            files[path.relative_to(root).as_posix()] = _sha256(path)
    return files


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _git_head(repo: Path) -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise LaneError(f"cannot identify source repository revision: {result.stderr.strip()}")
    return result.stdout.strip()


def _lane_contract(repo: Path) -> tuple[dict[str, Any], dict[str, Any], list[str]]:
    contract = _read_json(repo / CONFIG_PATH)
    targets = contract.get("targets")
    baseline = contract.get("baseline")
    lanes = contract.get("lanes")
    if not isinstance(targets, list) or not all(isinstance(name, str) and name for name in targets):
        raise LaneError("experiment targets must be a non-empty string list")
    if not isinstance(baseline, dict) or not isinstance(lanes, dict):
        raise LaneError("experiment baseline and lanes must be objects")
    integrated = lanes.get("integrated")
    if not isinstance(integrated, dict):
        raise LaneError("experiment must define the integrated lane")
    roster = integrated.get("upstream_skill_roster")
    mapping = integrated.get("local_cli_port_map")
    additions = integrated.get("port_additions_absent_upstream")
    if not isinstance(roster, list) or not all(isinstance(name, str) and name for name in roster):
        raise LaneError("integrated upstream roster must be a string list")
    if roster != sorted(set(roster)):
        raise LaneError("integrated upstream roster must be sorted and unique")
    if not isinstance(mapping, dict) or not all(
        isinstance(key, str) and isinstance(value, str) and key and value
        for key, value in mapping.items()
    ):
        raise LaneError("integrated local port map must map non-empty strings")
    if set(mapping) - set(roster):
        raise LaneError("integrated local port map contains a name outside the upstream roster")
    if not isinstance(additions, list) or additions != sorted(set(additions)):
        raise LaneError("integrated port additions must be a sorted unique list")
    names = [*targets, *roster, *mapping, *mapping.values(), *additions]
    if any(Path(name).name != name or name in {".", ".."} for name in names):
        raise LaneError("skill roster names must be single safe path components")
    if not set(targets).issubset(additions):
        raise LaneError("every target must be declared as an absent-upstream port addition")
    if sorted(baseline.get("target_skills_absent", [])) != sorted(targets):
        raise LaneError("baseline target absence does not match experiment targets")
    pinned = (repo / ".github" / "upstream-sha").read_text(encoding="utf-8").strip()
    if baseline.get("commit") != pinned:
        raise LaneError("baseline commit does not match .github/upstream-sha")
    local_roster = [mapping.get(name, name) for name in roster]
    if len(local_roster) != len(set(local_roster)):
        raise LaneError("integrated port mapping aliases two upstream skills to one local skill")
    if set(local_roster) & set(additions):
        raise LaneError("integrated baseline leaks an absent-upstream port addition")
    _validate_regular_tree(repo / "skills", repo)
    actual = {path.parent.name for path in (repo / "skills").glob("*/SKILL.md")}
    expected = set(local_roster) | set(additions)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise LaneError(f"local skill roster mismatch; missing={missing}; extra={extra}")
    return contract, integrated, local_roster


def _copy_skill(repo: Path, destination: Path, name: str) -> None:
    source = repo / "skills" / name
    _validate_regular_tree(source, repo)
    shutil.copytree(source, destination / "skills" / name)


def _tracked_suite_files(repo: Path, suite_relative: Path) -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "-z", "--", suite_relative.as_posix()],
        cwd=repo,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise LaneError(f"cannot list tracked eval files: {result.stderr.decode(errors='replace').strip()}")
    files: list[Path] = []
    for raw in result.stdout.split(b"\0"):
        if not raw:
            continue
        relative = Path(os.fsdecode(raw))
        try:
            suite_file = relative.relative_to(suite_relative)
        except ValueError as exc:
            raise LaneError(f"tracked eval path escapes its suite: {relative}") from exc
        source = repo / relative
        if source.is_symlink() or not source.is_file():
            raise LaneError(f"tracked eval source must be a regular file: {source}")
        files.append(suite_file)
    if not files:
        raise LaneError(f"eval suite has no tracked files: {suite_relative}")
    return sorted(files)


def _tracked_suite_inventory(repo: Path, suite_relative: Path) -> dict[str, str]:
    return {
        path.as_posix(): _sha256(repo / suite_relative / path)
        for path in _tracked_suite_files(repo, suite_relative)
    }


def _copy_tracked_suite(repo: Path, suite_relative: Path, destination: Path) -> None:
    for relative in _tracked_suite_files(repo, suite_relative):
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(repo / suite_relative / relative, target)


def _materialize_at(
    repo: Path,
    target_skill: str,
    output: Path,
    contract: dict[str, Any],
    integrated: dict[str, Any],
    baseline_skills: list[str],
) -> dict[str, Any]:
    targets = list(contract["targets"])
    if target_skill not in targets:
        raise LaneError(f"unsupported target skill: {target_skill}")
    if target_skill in baseline_skills:
        raise LaneError(f"target skill leaks into integrated baseline: {target_skill}")

    suite_relative = Path("evals") / target_skill
    output.mkdir(parents=True, exist_ok=True)
    control_root = output / "arms" / "control"
    treatment_root = output / "arms" / "treatment"
    for name in baseline_skills:
        _copy_skill(repo, control_root, name)
        _copy_skill(repo, treatment_root, name)
    _copy_skill(repo, treatment_root, target_skill)
    suite_destination = output / "evals" / target_skill
    _copy_tracked_suite(repo, suite_relative, suite_destination)

    manifest_path = suite_destination / "shared-benchmark.json"
    manifest = _read_json(manifest_path)
    control_paths = [f"arms/control/skills/{name}/SKILL.md" for name in baseline_skills]
    treatment_paths = [f"arms/treatment/skills/{target_skill}/SKILL.md"]
    treatment_paths.extend(f"arms/treatment/skills/{name}/SKILL.md" for name in baseline_skills)
    manifest["skill_paths"] = treatment_paths
    manifest["old_skill_paths"] = control_paths
    manifest["variants"] = ["with_skill", "without_skill"]
    manifest["optional_variants"] = ["old_skill"]
    _write_json(manifest_path, manifest)

    control_files = _inventory(control_root)
    treatment_files = _inventory(treatment_root)
    treatment_without_target = {
        path: digest
        for path, digest in treatment_files.items()
        if not path.startswith(f"skills/{target_skill}/")
    }
    if control_files != treatment_without_target:
        raise LaneError("non-target arm mismatch after materialization")
    source_skill_inventory = {
        name: _inventory(repo / "skills" / name)
        for name in [*baseline_skills, target_skill]
    }
    receipt: dict[str, Any] = {
        "version": 1,
        "lane": "integrated",
        "target_skill": target_skill,
        "manifest": manifest_path.relative_to(output).as_posix(),
        "source": {
            "repository_root": str(repo),
            "git_head": _git_head(repo),
            "experiment_config": CONFIG_PATH.as_posix(),
            "experiment_config_sha256": _sha256(repo / CONFIG_PATH),
            "upstream": {
                "repository": contract["baseline"]["repository"],
                "commit": contract["baseline"]["commit"],
                "subdirectory": contract["baseline"]["subdirectory"],
            },
            "upstream_skill_roster": integrated["upstream_skill_roster"],
            "local_cli_port_map": integrated["local_cli_port_map"],
            "skills": source_skill_inventory,
            "eval_suite": _tracked_suite_inventory(repo, suite_relative),
        },
        "arms": {
            "control": {
                "variant": "old_skill",
                "skill_paths": control_paths,
                "files": control_files,
            },
            "treatment": {
                "variant": "with_skill",
                "skill_paths": treatment_paths,
                "files": treatment_files,
            },
        },
    }
    receipt["files"] = _inventory(output)
    _write_json(output / RECEIPT_NAME, receipt)
    return receipt


def materialize_integrated_lane(repo: Path, target_skill: str, output: Path) -> dict[str, Any]:
    repo = repo.resolve()
    if output.is_symlink():
        raise LaneError(f"integrated lane output cannot be a symlink: {output}")
    output = output.resolve()
    if _is_within(output, repo):
        raise LaneError(f"integrated lane output must be outside the source repository: {output}")
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise LaneError(f"integrated lane output must be a new or empty directory: {output}")
    contract, integrated, baseline_skills = _lane_contract(repo)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=f".{output.name}.", dir=output.parent) as staging_name:
        staging = Path(staging_name)
        receipt = _materialize_at(
            repo,
            target_skill,
            staging,
            contract,
            integrated,
            baseline_skills,
        )
        if output.exists():
            output.rmdir()
        os.replace(staging, output)
    return receipt


def verify_materialized_lane(repo: Path, shadow_repo: Path, target_skill: str) -> dict[str, Any]:
    repo = repo.resolve()
    if shadow_repo.is_symlink():
        raise LaneError("integrated shadow repository cannot be a symlink")
    shadow_repo = shadow_repo.resolve()
    if _is_within(shadow_repo, repo):
        raise LaneError("integrated shadow repository must be outside the source repository")
    receipt = _read_json(shadow_repo / RECEIPT_NAME)
    if receipt.get("lane") != "integrated" or receipt.get("target_skill") != target_skill:
        raise LaneError("integrated lane receipt identity mismatch")
    contract, integrated, baseline_skills = _lane_contract(repo)
    source = receipt.get("source")
    if not isinstance(source, dict):
        raise LaneError("integrated lane receipt has no source identity")
    expected_upstream = {
        "repository": contract["baseline"]["repository"],
        "commit": contract["baseline"]["commit"],
        "subdirectory": contract["baseline"]["subdirectory"],
    }
    if source.get("upstream") != expected_upstream:
        raise LaneError("integrated lane receipt upstream identity mismatch")
    if source.get("upstream_skill_roster") != integrated["upstream_skill_roster"]:
        raise LaneError("integrated lane receipt roster mismatch")
    if source.get("local_cli_port_map") != integrated["local_cli_port_map"]:
        raise LaneError("integrated lane receipt port map mismatch")
    if source.get("repository_root") != str(repo) or source.get("git_head") != _git_head(repo):
        raise LaneError("integrated lane source repository identity changed after materialization")
    if source.get("experiment_config_sha256") != _sha256(repo / CONFIG_PATH):
        raise LaneError("integrated lane source config changed after materialization")
    expected_source_skills = {
        name: _inventory(repo / "skills" / name)
        for name in [*baseline_skills, target_skill]
    }
    if source.get("skills") != expected_source_skills:
        raise LaneError("integrated lane source skill inventory changed after materialization")
    if source.get("eval_suite") != _tracked_suite_inventory(repo, Path("evals") / target_skill):
        raise LaneError("integrated lane source eval inventory changed after materialization")

    expected_files = receipt.get("files")
    if not isinstance(expected_files, dict):
        raise LaneError("integrated lane receipt has no file inventory")
    actual_files = _inventory(shadow_repo)
    actual_files.pop(RECEIPT_NAME, None)
    if actual_files != expected_files:
        raise LaneError("integrated lane file inventory does not match its receipt")

    arms = receipt.get("arms")
    if not isinstance(arms, dict) or not isinstance(arms.get("control"), dict) or not isinstance(arms.get("treatment"), dict):
        raise LaneError("integrated lane receipt has invalid arms")
    control = arms["control"]
    treatment = arms["treatment"]
    if control.get("skill_paths") != [f"arms/control/skills/{name}/SKILL.md" for name in baseline_skills]:
        raise LaneError("integrated control roster mismatch")
    expected_treatment = [f"arms/treatment/skills/{target_skill}/SKILL.md"]
    expected_treatment.extend(f"arms/treatment/skills/{name}/SKILL.md" for name in baseline_skills)
    if treatment.get("skill_paths") != expected_treatment:
        raise LaneError("integrated treatment roster mismatch")
    control_files = control.get("files")
    treatment_files = treatment.get("files")
    if not isinstance(control_files, dict) or not isinstance(treatment_files, dict):
        raise LaneError("integrated lane arm inventory is invalid")
    target_prefix = f"skills/{target_skill}/"
    if any(path.startswith(target_prefix) for path in control_files):
        raise LaneError("integrated control contains the target skill")
    if control_files != {
        path: digest for path, digest in treatment_files.items() if not path.startswith(target_prefix)
    }:
        raise LaneError("integrated lane has a non-target arm mismatch")
    expected_control_files = {
        f"skills/{name}/{path}": digest
        for name in baseline_skills
        for path, digest in expected_source_skills[name].items()
    }
    expected_treatment_files = {
        **expected_control_files,
        **{
            f"skills/{target_skill}/{path}": digest
            for path, digest in expected_source_skills[target_skill].items()
        },
    }
    if control_files != expected_control_files or treatment_files != expected_treatment_files:
        raise LaneError("integrated arm inventory does not match the source skill inventory")

    manifest_relative = Path(str(receipt.get("manifest", "")))
    if manifest_relative.is_absolute() or ".." in manifest_relative.parts:
        raise LaneError("integrated lane receipt manifest path escapes the shadow repository")
    manifest_path = shadow_repo / manifest_relative
    manifest = _read_json(manifest_path)
    if manifest.get("skill_paths") != treatment.get("skill_paths"):
        raise LaneError("integrated manifest treatment paths do not match receipt")
    if manifest.get("old_skill_paths") != control.get("skill_paths"):
        raise LaneError("integrated manifest control paths do not match receipt")
    if manifest.get("optional_variants") != ["old_skill"]:
        raise LaneError("integrated manifest does not enable the old_skill control")
    return receipt


def _task_key(row: dict[str, Any]) -> tuple[Any, ...]:
    return row.get("case_id"), row.get("model"), row.get("run_number")


def filter_prepared_tasks(source: Path, destination: Path, variants: Iterable[str] = PAIRED_VARIANTS) -> dict[str, int]:
    variant_order = tuple(variants)
    if len(variant_order) != 2 or len(set(variant_order)) != 2:
        raise LaneError("task filtering requires two distinct variants")
    rows: list[dict[str, Any]] = []
    try:
        lines = source.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise LaneError(f"cannot read prepared tasks: {exc}") from exc
    for index, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise LaneError(f"prepared task line {index} is invalid JSON: {exc}") from exc
        if not isinstance(row, dict):
            raise LaneError(f"prepared task line {index} is not an object")
        if row.get("variant") in variant_order:
            rows.append(row)
    populations = {
        variant: {_task_key(row) for row in rows if row.get("variant") == variant}
        for variant in variant_order
    }
    if not populations[variant_order[0]] or populations[variant_order[0]] != populations[variant_order[1]]:
        raise LaneError(
            f"prepared task population mismatch for {variant_order[0]} and {variant_order[1]}"
        )
    expected_count = len(populations[variant_order[0]])
    counts = {variant: sum(row.get("variant") == variant for row in rows) for variant in variant_order}
    if any(count != expected_count for count in counts.values()):
        raise LaneError("prepared task population contains duplicate pair members")
    shared_fields = (
        "case_id",
        "split",
        "kind",
        "run_number",
        "skill_name",
        "repo_root",
        "input_files",
        "prompt",
        "tags",
        "eval_contract_sha256",
        "model",
        "turns",
    )
    by_variant = {
        variant: {_task_key(row): row for row in rows if row.get("variant") == variant}
        for variant in variant_order
    }
    for key in populations[variant_order[0]]:
        left = by_variant[variant_order[0]][key]
        right = by_variant[variant_order[1]][key]
        if any(left.get(field) != right.get(field) for field in shared_fields):
            raise LaneError(f"prepared task pair differs outside its skill arm at {key}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text("".join(json.dumps(row, separators=(",", ":")) + "\n" for row in rows), encoding="utf-8")
    return counts


def _event_names_target(event: Any, target_skill: str) -> bool:
    if not isinstance(event, dict):
        return False
    if event.get("status") not in (None, "completed", "success"):
        return False
    needle = f"/skills/{target_skill}/SKILL.md"
    for key in ("path", "command", "input_summary", "name"):
        value = event.get(key)
        if isinstance(value, str) and needle in value.replace("\\", "/"):
            return True
    return False


def exposure_report(runs: Path, manifest_path: Path, target_skill: str) -> dict[str, Any]:
    manifest = _read_json(manifest_path)
    cases = manifest.get("cases")
    if not isinstance(cases, list):
        raise LaneError("manifest cases must be a list")
    must_read = {
        case.get("id")
        for case in cases
        if isinstance(case, dict)
        and isinstance(case.get("id"), str)
        and (case.get("kind") != "trigger" or case.get("should_trigger") is True)
    }
    rows: list[dict[str, Any]] = []
    for events_path in sorted(runs.rglob("events.json")):
        relative = events_path.relative_to(runs)
        parts = relative.parts
        variant = next((value for value in PAIRED_VARIANTS if value in parts), None)
        if variant is None or not parts:
            continue
        case_id = parts[0]
        try:
            payload = json.loads(events_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise LaneError(f"cannot read exposure events from {events_path}: {exc}") from exc
        if not isinstance(payload, dict) or not isinstance(payload.get("events"), list):
            raise LaneError(f"exposure events must use the harness event envelope: {events_path}")
        events = payload["events"]
        observed = any(_event_names_target(event, target_skill) for event in events)
        expected = variant == "with_skill" and case_id in must_read
        pair_parts = tuple(part for part in relative.parent.parts if part != variant)
        rows.append({
            "case_id": case_id,
            "variant": variant,
            "run": relative.parent.as_posix(),
            "pair_key": "/".join(pair_parts),
            "target_read_expected": expected,
            "target_read_observed": observed,
        })
    if not rows:
        raise LaneError(f"no paired run events found under {runs}")
    populations = {
        variant: {row["pair_key"] for row in rows if row["variant"] == variant}
        for variant in PAIRED_VARIANTS
    }
    if not populations["with_skill"] or populations["with_skill"] != populations["old_skill"]:
        raise LaneError("exposure run population mismatch for with_skill and old_skill")
    missing = [row for row in rows if row["target_read_expected"] and not row["target_read_observed"]]
    unexpected = [
        row for row in rows
        if row["target_read_observed"] and (
            row["variant"] == "old_skill"
            or row["case_id"] not in must_read
        )
    ]
    return {
        "target_skill": target_skill,
        "eligible": not missing and not unexpected,
        "missing_target_reads": missing,
        "unexpected_target_reads": unexpected,
        "runs": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Materialize and verify direct-skill comparison lanes.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    materialize = subparsers.add_parser("materialize")
    materialize.add_argument("--repo", type=Path, required=True)
    materialize.add_argument("--skill", required=True)
    materialize.add_argument("--out", type=Path, required=True)

    verify = subparsers.add_parser("verify")
    verify.add_argument("--repo", type=Path, required=True)
    verify.add_argument("--skill", required=True)
    verify.add_argument("--shadow-repo", type=Path, required=True)

    filter_tasks = subparsers.add_parser("filter-tasks")
    filter_tasks.add_argument("--input", type=Path, required=True)
    filter_tasks.add_argument("--out", type=Path, required=True)

    exposure = subparsers.add_parser("check-exposure")
    exposure.add_argument("--runs", type=Path, required=True)
    exposure.add_argument("--manifest", type=Path, required=True)
    exposure.add_argument("--skill", required=True)
    exposure.add_argument("--out", type=Path, required=True)

    args = parser.parse_args()
    try:
        if args.command == "materialize":
            result = materialize_integrated_lane(args.repo, args.skill, args.out)
            print(args.out.resolve() / RECEIPT_NAME)
            return 0 if result else 1
        if args.command == "verify":
            verify_materialized_lane(args.repo, args.shadow_repo, args.skill)
            print(args.shadow_repo.resolve() / RECEIPT_NAME)
            return 0
        if args.command == "filter-tasks":
            counts = filter_prepared_tasks(args.input, args.out)
            print(json.dumps(counts, sort_keys=True))
            return 0
        report = exposure_report(args.runs, args.manifest, args.skill)
        _write_json(args.out, report)
        if not report["eligible"]:
            print(json.dumps({
                "missing_target_reads": len(report["missing_target_reads"]),
                "unexpected_target_reads": len(report["unexpected_target_reads"]),
            }, sort_keys=True))
            return 1
        print(args.out.resolve())
        return 0
    except (LaneError, OSError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    raise SystemExit(main())
