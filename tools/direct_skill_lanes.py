#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import shlex
import shutil
import stat
import subprocess
import tempfile
from pathlib import Path
from pathlib import PurePosixPath
from typing import Any, Iterable


CONFIG_PATH = Path("evals/direct-skills-experiment.json")
HELPER_PATH = Path("tools/direct_skill_lanes.py")
RECEIPT_NAME = "integrated-lane-receipt.json"
PAIRED_VARIANTS = ("with_skill", "old_skill")


class LaneError(ValueError):
    pass


def _strict_json_loads(text: str) -> Any:
    def object_from_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        output: dict[str, Any] = {}
        for key, value in pairs:
            if key in output:
                raise ValueError(f"duplicate object key: {key}")
            output[key] = value
        return output

    def reject_nonfinite(value: str) -> None:
        raise ValueError(f"non-finite numeric constant: {value}")

    value = json.loads(
        text,
        object_pairs_hook=object_from_pairs,
        parse_constant=reject_nonfinite,
    )

    def validate_persistable_value(item: Any, *, depth: int = 0) -> None:
        if depth > 100:
            raise ValueError("JSON value exceeds the maximum nesting depth")
        if isinstance(item, str):
            try:
                item.encode("utf-8", errors="strict")
            except UnicodeEncodeError as exc:
                raise ValueError("JSON value contains a surrogate code point") from exc
        if isinstance(item, float) and not math.isfinite(item):
            raise ValueError(f"non-finite numeric value: {item}")
        if isinstance(item, list):
            for child in item:
                validate_persistable_value(child, depth=depth + 1)
        if isinstance(item, dict):
            for key, child in item.items():
                validate_persistable_value(key, depth=depth)
                validate_persistable_value(child, depth=depth + 1)

    validate_persistable_value(value)
    return value


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _reject_symlink_chain(root: Path, relative: Path) -> None:
    if relative.is_absolute() or ".." in relative.parts:
        raise LaneError(f"lane source path must stay below its repository: {relative}")
    absolute_root = root.absolute()
    current_root = Path(absolute_root.anchor)
    for part in absolute_root.parts[1:]:
        current_root /= part
        if current_root.is_symlink():
            raise LaneError(f"lane source path contains a symlink: {current_root}")
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise LaneError(f"lane source path contains a symlink: {current}")


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = _strict_json_loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        raise LaneError(f"cannot read JSON from {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise LaneError(f"expected a JSON object in {path}")
    return value


def _load_eval_manifest(path: Path) -> dict[str, Any]:
    manifest = _read_json(path)
    dataset_files = manifest.pop("dataset_files", None)
    if dataset_files is None:
        return manifest
    if not isinstance(dataset_files, dict):
        raise LaneError("manifest dataset_files must map dataset ids to JSONL paths")
    datasets = dict(manifest.get("datasets") or {})
    for dataset_id, relative in dataset_files.items():
        rows_path = path.parent / str(relative)
        if not rows_path.is_file():
            raise LaneError(f"manifest dataset file does not exist: {rows_path}")
        rows: list[Any] = []
        for line_number, line in enumerate(rows_path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            try:
                rows.append(_strict_json_loads(line))
            except (json.JSONDecodeError, ValueError) as exc:
                raise LaneError(
                    f"manifest dataset line is invalid JSON: {rows_path}:{line_number}: {exc}"
                ) from exc
        datasets[str(dataset_id)] = rows
    manifest["datasets"] = datasets
    return manifest


def _read_regular_text_below(root: Path, relative: Path) -> str:
    if relative.is_absolute() or ".." in relative.parts:
        raise LaneError(f"lane artifact path must stay below its root: {relative}")
    absolute_root = root.absolute()
    root_parts = list(absolute_root.parts[1:])
    canonical_root = Path(absolute_root.anchor)
    if root_parts and (canonical_root / root_parts[0]).is_symlink():
        alias = canonical_root / root_parts.pop(0)
        resolved = alias.resolve(strict=True)
        if alias.lstat().st_uid != 0 or resolved.stat().st_uid != 0:
            raise LaneError(f"lane artifact path contains an untrusted symlink: {alias}")
        canonical_root = resolved
    for part in root_parts:
        canonical_root /= part
        if canonical_root.is_symlink():
            raise LaneError(f"lane artifact path contains a symlink: {canonical_root}")
    absolute_root = canonical_root
    parts = (*absolute_root.parts[1:], *relative.parts)
    descriptor = -1
    try:
        descriptor = os.open(absolute_root.anchor, os.O_RDONLY | os.O_DIRECTORY)
        for index, part in enumerate(parts):
            final = index == len(parts) - 1
            flags = os.O_RDONLY | os.O_NOFOLLOW
            flags |= os.O_NONBLOCK if final else os.O_DIRECTORY
            next_descriptor = os.open(part, flags, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = next_descriptor
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise LaneError(f"lane artifact is not a regular file: {root / relative}")
        if metadata.st_nlink != 1:
            raise LaneError(f"lane artifact must have exactly one hard link: {root / relative}")
        stream = os.fdopen(descriptor, "r", encoding="utf-8")
        descriptor = -1
        with stream:
            text = stream.read()
            if os.fstat(stream.fileno()).st_nlink != 1:
                raise LaneError(f"lane artifact must have exactly one hard link: {root / relative}")
            return text
    except (OSError, UnicodeError) as exc:
        raise LaneError(
            f"lane artifact path contains a symlink or unreadable component: "
            f"{root / relative}: {exc}"
        ) from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _read_json_below(root: Path, relative: Path, *, object_only: bool) -> Any:
    try:
        value = _strict_json_loads(_read_regular_text_below(root, relative))
    except (json.JSONDecodeError, ValueError) as exc:
        raise LaneError(f"cannot read JSON from {root / relative}: {exc}") from exc
    if object_only and not isinstance(value, dict):
        raise LaneError(f"expected a JSON object in {root / relative}")
    return value


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def _inventory(root: Path) -> dict[str, str]:
    if root.is_symlink() or not root.is_dir():
        raise LaneError(f"materialized lane root must be a regular directory: {root}")
    files: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise LaneError(f"symlinks are not allowed in a materialized lane: {path}")
        if path.is_dir():
            continue
        if not path.is_file():
            raise LaneError(f"special files are not allowed in a materialized lane: {path}")
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
    skills_root = repo / "skills"
    if skills_root.is_symlink() or not skills_root.is_dir():
        raise LaneError("skills source must be a regular directory")
    skill_files = list(skills_root.glob("*/SKILL.md"))
    if any(path.is_symlink() or not path.is_file() for path in skill_files):
        raise LaneError("each local skill must have a regular SKILL.md")
    actual = {path.parent.name for path in skill_files}
    expected = set(local_roster) | set(additions)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise LaneError(f"local skill roster mismatch; missing={missing}; extra={extra}")
    tracked = subprocess.run(
        ["git", "ls-files", "-z", "--", "skills/*/SKILL.md"],
        cwd=repo,
        capture_output=True,
        check=False,
    )
    if tracked.returncode != 0:
        raise LaneError(f"cannot list tracked skill manifests: {tracked.stderr.decode(errors='replace').strip()}")
    tracked_roster = {
        Path(os.fsdecode(path)).parent.name
        for path in tracked.stdout.split(b"\0")
        if path
    }
    if tracked_roster != expected:
        raise LaneError("tracked skill roster does not match the integrated lane contract")
    return contract, integrated, local_roster


def _tracked_tree_files(repo: Path, tree_relative: Path) -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "-z", "--", tree_relative.as_posix()],
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
            tree_file = relative.relative_to(tree_relative)
        except ValueError as exc:
            raise LaneError(f"tracked path escapes its tree: {relative}") from exc
        source = repo / relative
        _reject_symlink_chain(repo, relative)
        if source.is_symlink() or not source.is_file():
            raise LaneError(f"tracked lane source must be a regular file: {source}")
        files.append(tree_file)
    if not files:
        raise LaneError(f"lane source has no tracked files: {tree_relative}")
    return sorted(files)


def _tracked_tree_inventory(repo: Path, tree_relative: Path) -> dict[str, str]:
    return {
        path.as_posix(): _sha256(repo / tree_relative / path)
        for path in _tracked_tree_files(repo, tree_relative)
    }


def _copy_tracked_tree(repo: Path, tree_relative: Path, destination: Path) -> None:
    for relative in _tracked_tree_files(repo, tree_relative):
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(repo / tree_relative / relative, target)


def _copy_skill(repo: Path, destination: Path, name: str) -> None:
    _copy_tracked_tree(repo, Path("skills") / name, destination / "skills" / name)


def _tracked_file_digest(repo: Path, relative: Path) -> str:
    tracked = subprocess.run(
        ["git", "ls-files", "--error-unmatch", "--", relative.as_posix()],
        cwd=repo,
        capture_output=True,
        check=False,
    )
    source = repo / relative
    _reject_symlink_chain(repo, relative)
    if tracked.returncode != 0 or source.is_symlink() or not source.is_file():
        raise LaneError(f"lane helper must be a tracked regular file: {source}")
    return _sha256(source)


def _copy_tracked_file(repo: Path, relative: Path, destination: Path) -> str:
    digest = _tracked_file_digest(repo, relative)
    source = repo / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    return digest


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
    _copy_tracked_tree(repo, suite_relative, suite_destination)
    helper_digest = _copy_tracked_file(repo, HELPER_PATH, output / HELPER_PATH)

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
        name: _tracked_tree_inventory(repo, Path("skills") / name)
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
            "eval_suite": _tracked_tree_inventory(repo, suite_relative),
            "helpers": {HELPER_PATH.as_posix(): helper_digest},
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
        name: _tracked_tree_inventory(repo, Path("skills") / name)
        for name in [*baseline_skills, target_skill]
    }
    if source.get("skills") != expected_source_skills:
        raise LaneError("integrated lane source skill inventory changed after materialization")
    if source.get("eval_suite") != _tracked_tree_inventory(repo, Path("evals") / target_skill):
        raise LaneError("integrated lane source eval inventory changed after materialization")
    if source.get("helpers") != {HELPER_PATH.as_posix(): _tracked_file_digest(repo, HELPER_PATH)}:
        raise LaneError("integrated lane source helper changed after materialization")

    with tempfile.TemporaryDirectory(prefix="direct-skill-verify-") as expected_name:
        expected_receipt = _materialize_at(
            repo,
            target_skill,
            Path(expected_name),
            contract,
            integrated,
            baseline_skills,
        )
    expected_files = expected_receipt["files"]
    if receipt.get("files") != expected_files:
        raise LaneError("integrated lane receipt file inventory does not match its source")
    actual_files = _inventory(shadow_repo)
    actual_files.pop(RECEIPT_NAME, None)
    if actual_files != expected_files:
        raise LaneError("integrated lane file inventory does not match its source")

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


def _reader_command_names_target(command: str, target_skill: str, depth: int = 0) -> bool:
    if depth > 2:
        return False
    try:
        argv = shlex.split(command)
    except ValueError:
        return False
    if not argv or any(token in {"|", "||", "&&", ";"} for token in argv):
        return False
    while argv and ("=" in argv[0] and not argv[0].startswith(("/", "./", "../"))):
        argv.pop(0)
    if argv and Path(argv[0]).name == "env":
        argv.pop(0)
        while argv and (argv[0].startswith("-") or "=" in argv[0]):
            argv.pop(0)
    if not argv:
        return False
    executable = Path(argv[0]).name
    if executable in {"bash", "sh", "zsh"}:
        shell_args = argv[1:]
        options: list[str] = []
        while shell_args and shell_args[0].startswith("-"):
            options.append(shell_args.pop(0))
        if len(shell_args) != 1 or not any("c" in option.lstrip("-") for option in options):
            return False
        return _reader_command_names_target(shell_args[0], target_skill, depth + 1)
    if executable not in {"cat", "sed", "head", "tail"}:
        return False
    return any(
        PurePosixPath(argument.replace("\\", "/")).parts[-3:]
        == ("skills", target_skill, "SKILL.md")
        for argument in argv[1:]
    )


def _event_names_target(event: Any, target_skill: str) -> bool:
    if not isinstance(event, dict):
        return False
    if event.get("status") != "completed" or event.get("is_error") is True:
        return False
    if event.get("type") == "command":
        command = event.get("input_summary")
        output = event.get("output_summary")
        exit_code = event.get("exit_code")
        return (
            isinstance(command, str)
            and isinstance(output, str)
            and bool(output.strip())
            and (exit_code is None or (type(exit_code) is int and exit_code == 0))
            and _reader_command_names_target(command, target_skill)
        )
    if event.get("type") != "skill_load":
        return False
    name = event.get("name")
    if name not in (None, "Read", "read", "read_file", "Skill", "skill", "activate_skill"):
        return False
    otel = event.get("otel")
    value = otel.get("file.path") if isinstance(otel, dict) else None
    if not isinstance(value, str):
        value = event.get("input_summary")
    if not isinstance(value, str):
        return False
    if name in ("Skill", "skill", "activate_skill") and value == target_skill:
        return True
    parts = PurePosixPath(value.replace("\\", "/")).parts
    return parts[-3:] == ("skills", target_skill, "SKILL.md")


def _canonical_json_sha256(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def _apply_dataset_row(value: Any, row: dict[str, Any]) -> Any:
    if isinstance(value, str):
        output = value
        for key, cell in row.items():
            output = output.replace("{" + str(key) + "}", str(cell))
        return output
    if isinstance(value, list):
        return [_apply_dataset_row(item, row) for item in value]
    if isinstance(value, dict):
        return {key: _apply_dataset_row(item, row) for key, item in value.items()}
    return value


def _materialize_dataset_cases(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    cases = manifest.get("cases", [])
    if not isinstance(cases, list):
        raise LaneError("manifest cases must be a list")
    datasets = manifest.get("datasets") or {}
    output: list[dict[str, Any]] = []
    for case_index, case in enumerate(cases, 1):
        if not isinstance(case, dict) or not all(isinstance(key, str) for key in case):
            raise LaneError(f"manifest case {case_index} must be an object with string keys")
        dataset_id = case.get("template")
        if not dataset_id:
            output.append(dict(case))
            continue
        rows = datasets.get(str(dataset_id))
        if not isinstance(rows, list) or not rows:
            raise LaneError(f"manifest case template references an unknown dataset: {dataset_id}")
        for row_index, row in enumerate(rows, 1):
            if not isinstance(row, dict) or not all(isinstance(key, str) for key in row):
                raise LaneError(f"manifest dataset row {row_index} must be an object with string keys")
            materialized = {
                key: _apply_dataset_row(value, row)
                for key, value in case.items()
                if key != "template"
            }
            materialized["id"] = f"{case.get('id')}-{row.get('id', row_index)}"
            materialized["dataset"] = str(dataset_id)
            output.append(materialized)
    return output


def _eval_contract_sha256(manifest: dict[str, Any], manifest_path: Path, split: str) -> str:
    cases = [
        case for case in _materialize_dataset_cases(manifest)
        if case.get("split") == split
    ]
    referenced: set[str] = set()
    script_roots: set[Path] = set()
    manifest_dir = manifest_path.parent.resolve()
    for case in cases:
        prompt_ref = case.get("prompt_ref")
        if isinstance(prompt_ref, str) and prompt_ref:
            referenced.add(prompt_ref)
        referenced.update(str(value) for value in (case.get("files") or []))
        assertions = [*(case.get("assertions") or []), *[
            assertion
            for turn in (case.get("turns") or [])
            if isinstance(turn, dict)
            for assertion in (turn.get("assertions") or [])
        ]]
        for assertion in assertions:
            if not isinstance(assertion, dict):
                continue
            if assertion.get("type") == "golden_output":
                reference = assertion.get("reference", assertion.get("value"))
                if isinstance(reference, str) and reference:
                    referenced.add(reference)
            if assertion.get("type") != "script":
                continue
            command = assertion.get("command")
            parts = [command] if isinstance(command, str) else command
            if not isinstance(parts, list) or not all(isinstance(part, str) for part in parts):
                continue
            for part in parts:
                candidate = Path(part)
                if candidate.is_absolute() or ".." in candidate.parts:
                    continue
                resolved = (manifest_dir / candidate).resolve()
                if not resolved.is_file():
                    continue
                try:
                    relative = resolved.relative_to(manifest_dir)
                except ValueError as exc:
                    raise LaneError(f"eval contract path escapes manifest directory: {part}") from exc
                if len(relative.parts) == 1:
                    raise LaneError("script oracles must live in a dedicated subdirectory")
                referenced.add(relative.as_posix())
                script_roots.add(manifest_dir / relative.parts[0])
    files: list[dict[str, str]] = []
    for relative in sorted(referenced):
        candidate = (manifest_path.parent / relative).resolve()
        try:
            display = candidate.relative_to(manifest_dir).as_posix()
        except ValueError as exc:
            raise LaneError(f"eval contract path escapes manifest directory: {relative}") from exc
        if not candidate.is_file():
            files.append({"path": display, "availability": "missing"})
            continue
        files.append({
            "path": display,
            "sha256": hashlib.sha256(candidate.read_bytes()).hexdigest(),
        })
    oracle_trees: list[dict[str, str]] = []
    for root in sorted(script_roots):
        digest = hashlib.sha256()
        for candidate in sorted(root.rglob("*")):
            if candidate.is_symlink():
                raise LaneError(f"script oracle tree contains a symlink: {candidate}")
            if not candidate.is_file():
                continue
            relative = candidate.relative_to(root).as_posix()
            digest.update(relative.encode("utf-8") + b"\0")
            digest.update(candidate.read_bytes())
        oracle_trees.append({
            "path": root.relative_to(manifest_dir).as_posix(),
            "sha256": digest.hexdigest(),
        })
    return _canonical_json_sha256({
        "schema_version": 1,
        "manifest": manifest,
        "referenced_files": files,
        "script_oracle_trees": oracle_trees,
    })


def _expected_exposure_runs(
    runs: Path,
    expected_case_ids: set[str],
    expected_contract_digest: str,
) -> dict[str, dict[str, Any]]:
    design_path = Path("answer-design.json")
    design = _read_json_below(runs, design_path, object_only=True)
    identities = design.get("identities")
    if design.get("schema_version") != 2 or design.get("population") != "answer":
        raise LaneError("answer design has an unsupported identity")
    contract_digest = design.get("eval_contract_sha256")
    if not isinstance(contract_digest, str) or re.fullmatch(r"sha256:[0-9a-f]{64}", contract_digest) is None:
        raise LaneError("answer design has an invalid eval contract digest")
    if contract_digest != expected_contract_digest:
        raise LaneError("answer design does not match the selected manifest contract")
    if not isinstance(identities, list):
        raise LaneError("answer design identities must be a list")

    expected: dict[str, dict[str, Any]] = {}
    populations = {variant: set() for variant in PAIRED_VARIANTS}
    seen_coordinates: set[tuple[str, str | None, str, int]] = set()
    normalized_identities: list[dict[str, Any]] = []
    invariant_by_case: dict[str, tuple[str, str]] = {}
    treatment_by_coordinate: dict[tuple[str, str | None, str], tuple[str, str, str | None]] = {}
    for identity in identities:
        required_fields = {
            "case_id", "model", "variant", "run_number", "run_dir",
            "task_sha256", "case_input_sha256", "instruction_sha256",
            "planned_skill_tree_hash", "fixture_tree_hash",
        }
        if not isinstance(identity, dict) or set(identity) != required_fields:
            raise LaneError("answer design identity has an invalid shape")
        case_id = identity["case_id"]
        model = identity["model"]
        variant = identity["variant"]
        run_number = identity["run_number"]
        run_dir = identity["run_dir"]
        task_digest = identity["task_sha256"]
        case_digest = identity["case_input_sha256"]
        instruction_digest = identity["instruction_sha256"]
        skill_digest = identity["planned_skill_tree_hash"]
        fixture_digest = identity["fixture_tree_hash"]
        if not isinstance(case_id, str) or not case_id or case_id not in expected_case_ids:
            raise LaneError(f"answer design contains a case absent from the manifest: {case_id}")
        if variant not in PAIRED_VARIANTS:
            raise LaneError(f"answer design contains an unexpected variant: {variant}")
        if model is not None and (not isinstance(model, str) or not model):
            raise LaneError("answer design model must be null or a non-empty string")
        if isinstance(run_number, bool) or not isinstance(run_number, int) or run_number < 1:
            raise LaneError("answer design run number must be a positive integer")
        if not isinstance(run_dir, str) or not run_dir:
            raise LaneError("answer design run directory must be a non-empty string")
        if any(
            not isinstance(value, str) or re.fullmatch(r"sha256:[0-9a-f]{64}", value) is None
            for value in (task_digest, case_digest, instruction_digest)
        ):
            raise LaneError("answer design identity has an invalid task digest")
        if (
            skill_digest is not None
            and (not isinstance(skill_digest, str) or re.fullmatch(r"[0-9a-f]{64}", skill_digest) is None)
        ):
            raise LaneError("answer design identity has an invalid skill digest")
        if not isinstance(fixture_digest, str) or re.fullmatch(r"[0-9a-f]{64}", fixture_digest) is None:
            raise LaneError("answer design identity has an invalid fixture digest")
        run_path = PurePosixPath(run_dir)
        if (
            run_path.is_absolute()
            or not run_path.parts
            or run_path == PurePosixPath(".")
            or ".." in run_path.parts
            or "." in run_path.parts
        ):
            raise LaneError("answer design run directory must be a safe relative path")
        expected_parts = [str(case_id)]
        if model is not None:
            expected_parts.append(model)
        expected_parts.append(str(variant))
        if run_number > 1 or run_path.parts[-1].startswith("run-"):
            expected_parts.append(f"run-{run_number}")
        if run_path.parts != tuple(expected_parts):
            raise LaneError("answer design run directory disagrees with its coordinate")
        coordinate = (str(case_id), model, str(variant), run_number)
        if coordinate in seen_coordinates or run_dir in expected:
            raise LaneError(f"duplicate answer design run coordinate: {coordinate}")
        seen_coordinates.add(coordinate)
        pair_coordinate = (str(case_id), model, run_number)
        populations[str(variant)].add(pair_coordinate)
        expected[run_dir] = identity
        case_value = (case_digest, fixture_digest)
        previous_case = invariant_by_case.setdefault(case_id, case_value)
        if previous_case != case_value:
            raise LaneError(f"answer design case input or fixtures differ across coordinates: {case_id}")
        treatment_key = (case_id, model, variant)
        treatment_value = (task_digest, instruction_digest, skill_digest)
        previous_treatment = treatment_by_coordinate.setdefault(treatment_key, treatment_value)
        if previous_treatment != treatment_value:
            raise LaneError(f"answer design treatment differs across repetitions: {treatment_key}")
        normalized_identities.append(dict(identity))
    if not expected or populations["with_skill"] != populations["old_skill"]:
        raise LaneError("answer design population mismatch for with_skill and old_skill")
    observed_case_ids = {identity["case_id"] for identity in identities}
    if observed_case_ids != expected_case_ids:
        missing = sorted(expected_case_ids - observed_case_ids)
        extra = sorted(observed_case_ids - expected_case_ids)
        raise LaneError(f"answer design case population differs from the selected split; missing={missing}; extra={extra}")
    normalized_identities.sort(key=lambda row: (
        row["case_id"], str(row["model"] or ""), row["variant"], row["run_number"]
    ))
    payload = {
        "schema_version": 2,
        "population": "answer",
        "eval_contract_sha256": contract_digest,
        "identities": normalized_identities,
    }
    if design.get("design_sha256") != _canonical_json_sha256(payload):
        raise LaneError("answer design digest does not match its identities")
    return expected


def _case_requires_target_read(case: dict[str, Any]) -> bool:
    declared: list[bool] = []
    assertions = case.get("assertions")
    if assertions is None:
        assertions = []
    if not isinstance(assertions, list):
        raise LaneError(f"case {case.get('id')} assertions must be a list")
    turns = case.get("turns")
    if turns is None:
        turns = []
    if not isinstance(turns, list):
        raise LaneError(f"case {case.get('id')} turns must be a list")
    assertions = list(assertions)
    for turn_index, turn in enumerate(turns, 1):
        if not isinstance(turn, dict):
            raise LaneError(f"case {case.get('id')} turn {turn_index} must be an object")
        turn_assertions = turn.get("assertions")
        if turn_assertions is None:
            turn_assertions = []
        if not isinstance(turn_assertions, list):
            raise LaneError(
                f"case {case.get('id')} turn {turn_index} assertions must be a list"
            )
        assertions.extend(turn_assertions)
    for assertion in assertions:
        if not isinstance(assertion, dict) or assertion.get("type") != "skill_invoked":
            continue
        if "variants" in assertion and "only_variants" in assertion:
            raise LaneError(
                f"case {case.get('id')} skill_invoked assertion has conflicting variant filters"
            )
        for key in ("variants", "only_variants", "except_variants"):
            if key not in assertion:
                continue
            values = assertion[key]
            if (
                not isinstance(values, list)
                or not values
                or not all(isinstance(value, str) and value for value in values)
                or len(values) != len(set(values))
            ):
                raise LaneError(
                    f"case {case.get('id')} skill_invoked {key} must be a non-empty unique string list"
                )
        included = assertion.get("variants", assertion.get("only_variants"))
        excluded = assertion.get("except_variants")
        if isinstance(included, list) and isinstance(excluded, list) and set(included) & set(excluded):
            raise LaneError(
                f"case {case.get('id')} skill_invoked assertion includes and excludes the same variant"
            )
        if isinstance(included, list) and "with_skill" not in included:
            continue
        if isinstance(excluded, list) and "with_skill" in excluded:
            continue
        expected = assertion.get("expected", True)
        if not isinstance(expected, bool):
            raise LaneError(f"case {case.get('id')} has a non-boolean skill_invoked expectation")
        declared.append(expected)
    if len(set(declared)) > 1:
        raise LaneError(f"case {case.get('id')} has conflicting with_skill invocation expectations")
    if declared:
        return declared[0]
    return case.get("kind") != "trigger" or case.get("should_trigger") is True


def exposure_report(runs: Path, manifest_path: Path, target_skill: str, split: str) -> dict[str, Any]:
    manifest = _load_eval_manifest(manifest_path)
    cases = _materialize_dataset_cases(manifest)
    case_ids = [case.get("id") for case in cases]
    if (
        not all(isinstance(case_id, str) and case_id for case_id in case_ids)
        or len(case_ids) != len(set(case_ids))
    ):
        raise LaneError("manifest case ids must be non-empty and unique")
    selected_cases = [
        case for case in cases
        if isinstance(case, dict) and case.get("split") == split and case.get("kind") != "trigger"
    ]
    selected_case_ids = {case["id"] for case in selected_cases}
    if not selected_case_ids:
        raise LaneError(f"manifest has no answer cases in split {split!r}")
    expected_contract_digest = _eval_contract_sha256(manifest, manifest_path, split)
    expected_runs = _expected_exposure_runs(runs, selected_case_ids, expected_contract_digest)
    must_read = {
        case.get("id")
        for case in selected_cases
        if isinstance(case, dict)
        and isinstance(case.get("id"), str)
        and _case_requires_target_read(case)
    }
    event_files: dict[str, Path] = {}
    for events_path in sorted(runs.rglob("events.json")):
        relative = events_path.relative_to(runs)
        run_dir = relative.parent.as_posix()
        if run_dir in event_files:
            raise LaneError(f"duplicate exposure run directory: {run_dir}")
        event_files[run_dir] = events_path
    expected_paths = set(expected_runs)
    observed_paths = set(event_files)
    if expected_paths != observed_paths:
        missing = sorted(expected_paths - observed_paths)
        extra = sorted(observed_paths - expected_paths)
        raise LaneError(f"exposure run population differs from answer design; missing={missing}; extra={extra}")

    rows: list[dict[str, Any]] = []
    for run_dir in sorted(expected_runs):
        identity = expected_runs[run_dir]
        events_path = event_files[run_dir]
        payload = _read_json_below(runs, events_path.relative_to(runs), object_only=False)
        if (
            not isinstance(payload, dict)
            or type(payload.get("schema_version")) is not int
            or payload["schema_version"] != 2
            or not isinstance(payload.get("source"), str)
            or not payload["source"]
            or not isinstance(payload.get("events"), list)
            or not all(isinstance(event, dict) for event in payload["events"])
        ):
            raise LaneError(f"exposure events must use the harness event envelope: {events_path}")
        events = payload["events"]
        observed = any(_event_names_target(event, target_skill) for event in events)
        case_id = identity["case_id"]
        variant = identity["variant"]
        expected = variant == "with_skill" and case_id in must_read
        rows.append({
            "case_id": case_id,
            "variant": variant,
            "run": run_dir,
            "target_read_expected": expected,
            "target_read_observed": observed,
        })
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
    exposure.add_argument("--split", required=True)
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
        report = exposure_report(args.runs, args.manifest, args.skill, args.split)
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
