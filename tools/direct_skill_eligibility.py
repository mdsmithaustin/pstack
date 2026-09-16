from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from pathlib import Path, PurePosixPath
from typing import Any, Iterable

from direct_skill_lanes import LaneError, exposure_report


PAIRED_VARIANTS = ("with_skill", "old_skill")
ISSUE_CATEGORIES = {
    "candidate_failure",
    "missing_measurement",
    "infrastructure_failure",
}
SHA256 = re.compile(r"sha256:[0-9a-f]{64}")
PLAIN_SHA256 = re.compile(r"[0-9a-f]{64}")
REQUIRED_RUN_FILES = {
    "output.md",
    "events.json",
    "metrics.json",
    "metadata.json",
}
DEFAULT_MINIMUM_CALIBRATION_LABELS = 5
DEFAULT_MINIMUM_ACCURACY = 0.8
DEFAULT_MINIMUM_ORDER_SWAP_PAIRS = 4
DEFAULT_MINIMUM_ORDER_SWAP_CONSISTENCY = 0.9
OBSERVATION_FIELDS = (
    "observation_complete",
    "trace_observation_complete",
    "process_observation_complete",
    "provider_response_complete",
    "operation_observation_complete",
)


class EligibilityError(ValueError):
    pass


def _reject_constant(value: str) -> None:
    raise EligibilityError(f"non-finite numeric constant {value!r}")


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise EligibilityError(f"duplicate object key {key!r}")
        value[key] = item
    return value


def _ensure_finite(value: Any) -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise EligibilityError("non-finite numeric value")
    if isinstance(value, dict):
        for item in value.values():
            _ensure_finite(item)
    elif isinstance(value, list):
        for item in value:
            _ensure_finite(item)


def _read_json(path: Path) -> Any:
    if path.is_symlink() or not path.is_file():
        raise EligibilityError(f"not a regular file: {path}")
    try:
        value = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_pairs,
            parse_constant=_reject_constant,
        )
        _ensure_finite(value)
    except (
        OSError,
        UnicodeError,
        json.JSONDecodeError,
        EligibilityError,
        RecursionError,
    ) as exc:
        raise EligibilityError(f"cannot read JSON {path}: {exc}") from exc
    return value


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if path.is_symlink() or not path.is_file():
        raise EligibilityError(f"not a regular file: {path}")
    rows: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as exc:
        raise EligibilityError(f"cannot read JSON Lines {path}: {exc}") from exc
    for number, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            row = json.loads(
                line,
                object_pairs_hook=_pairs,
                parse_constant=_reject_constant,
            )
            _ensure_finite(row)
        except (json.JSONDecodeError, EligibilityError, RecursionError) as exc:
            raise EligibilityError(f"invalid JSON Lines row {number} in {path}: {exc}") from exc
        if not isinstance(row, dict):
            raise EligibilityError(f"JSON Lines row {number} in {path} is not an object")
        rows.append(row)
    return rows


def _sha256(path: Path) -> str:
    if path.is_symlink() or not path.is_file():
        raise EligibilityError(f"not a regular file: {path}")
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


def _canonical_sha256(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def _issue(category: str, code: str, detail: str, *, run: str | None = None) -> dict[str, str]:
    if category not in ISSUE_CATEGORIES:
        raise AssertionError(f"unknown issue category {category!r}")
    issue = {"category": category, "code": code, "detail": detail}
    if run is not None:
        issue["run"] = run
    return issue


def _report(
    issues: list[dict[str, str]],
    evidence_digests: dict[str, Any],
    counts: dict[str, int],
) -> dict[str, Any]:
    by_category = {category: 0 for category in sorted(ISSUE_CATEGORIES)}
    for issue in issues:
        by_category[issue["category"]] += 1
    return {
        "status": "eligible" if not issues else "ineligible",
        "headline_eligible": not issues,
        "issues": issues,
        "evidence_digests": evidence_digests,
        "counts": {**counts, **by_category},
    }


def _validate_artifact_commit(run_dir: Path, issues: list[dict[str, str]], run: str) -> str | None:
    commit_path = run_dir / "artifact-commit.json"
    try:
        commit = _read_json(commit_path)
    except EligibilityError as exc:
        issues.append(_issue("infrastructure_failure", "artifact_commit_missing", str(exc), run=run))
        return None
    if not isinstance(commit, dict) or commit.get("schema_version") != 1:
        issues.append(_issue(
            "infrastructure_failure",
            "artifact_commit_schema",
            "artifact-commit.json must use schema version 1",
            run=run,
        ))
        return _sha256(commit_path)
    required = commit.get("required_files")
    inventory = commit.get("inventory_sha256")
    required_names = set(required) if isinstance(required, list) and all(
        isinstance(name, str) for name in required
    ) else set()
    if (
        not isinstance(required, list)
        or not all(isinstance(name, str) and name for name in required)
        or len(required) != len(set(required))
        or not REQUIRED_RUN_FILES.issubset(set(required))
    ):
        issues.append(_issue(
            "infrastructure_failure",
            "artifact_required_files",
            f"artifact commit must require {sorted(REQUIRED_RUN_FILES)}",
            run=run,
        ))
    if not isinstance(inventory, dict):
        issues.append(_issue(
            "infrastructure_failure",
            "artifact_inventory",
            "artifact commit inventory must be an object",
            run=run,
        ))
        return _sha256(commit_path)
    for name, expected in inventory.items():
        if (
            not isinstance(name, str)
            or not name
            or PurePosixPath(name).is_absolute()
            or len(PurePosixPath(name).parts) != 1
        ):
            issues.append(_issue(
                "infrastructure_failure",
                "artifact_path_invalid",
                f"artifact commit has an unsafe inventory path {name!r}",
                run=run,
            ))
            continue
        artifact = run_dir / name
        if not isinstance(expected, str) or PLAIN_SHA256.fullmatch(expected) is None:
            issues.append(_issue(
                "infrastructure_failure",
                "artifact_digest_missing",
                f"artifact commit has no valid digest for {name}",
                run=run,
            ))
            continue
        try:
            observed = _sha256(artifact).removeprefix("sha256:")
        except EligibilityError as exc:
            issues.append(_issue("infrastructure_failure", "artifact_missing", str(exc), run=run))
            continue
        if observed != expected:
            issues.append(_issue(
                "infrastructure_failure",
                "artifact_digest_mismatch",
                f"artifact commit digest does not match {name}",
                run=run,
            ))
    for name in required_names - set(inventory):
        issues.append(_issue(
            "infrastructure_failure",
            "artifact_digest_missing",
            f"artifact commit has no valid digest for {name}",
            run=run,
        ))
    return _sha256(commit_path)


def _validate_telemetry(
    metadata: dict[str, Any],
    identity: dict[str, Any],
    issues: list[dict[str, str]],
    run: str,
) -> None:
    telemetry = metadata.get("telemetry")
    if metadata.get("telemetry_schema_version") != 3 or not isinstance(telemetry, dict):
        issues.append(_issue(
            "infrastructure_failure",
            "telemetry_schema",
            "metadata must contain telemetry schema version 3",
            run=run,
        ))
        return
    basis = telemetry.get("basis")
    expected_basis = {
        "population": "answer",
        "model": identity["model"],
        "case_id": identity["case_id"],
        "run_number": identity["run_number"],
        "skill_tree_hash": identity["planned_skill_tree_hash"],
    }
    if not isinstance(basis, dict) or any(basis.get(key) != value for key, value in expected_basis.items()):
        issues.append(_issue(
            "infrastructure_failure",
            "telemetry_basis_mismatch",
            "telemetry basis does not match the answer design",
            run=run,
        ))
    measurements = telemetry.get("measurements")
    if not isinstance(measurements, dict):
        issues.append(_issue(
            "infrastructure_failure",
            "telemetry_measurements",
            "telemetry measurements are missing",
            run=run,
        ))
        return
    for name in ("input_tokens", "output_tokens", "total_tokens"):
        measurement = measurements.get(name)
        value = measurement.get("value") if isinstance(measurement, dict) else None
        if (
            not isinstance(measurement, dict)
            or measurement.get("availability") != "available"
            or isinstance(value, bool)
            or not isinstance(value, int)
            or value < 0
        ):
            issues.append(_issue(
                "infrastructure_failure",
                "telemetry_measurement_incomplete",
                f"telemetry has no complete {name} measurement",
                run=run,
            ))


def validate_answer_runs(
    *,
    runs: Path,
    manifest: Path,
    target_skill: str,
    split: str,
    model: str,
    repetitions: int,
    expected_case_ids: Iterable[str],
) -> dict[str, Any]:
    issues: list[dict[str, str]] = []
    evidence: dict[str, Any] = {}
    requested_cases = list(expected_case_ids)
    valid_cases = [
        case_id for case_id in requested_cases
        if isinstance(case_id, str) and case_id
    ]
    expected_cases = set(valid_cases)
    expected_coordinates = {
        (case_id, variant, run_number)
        for case_id in expected_cases
        for variant in PAIRED_VARIANTS
        for run_number in range(1, repetitions + 1)
    }
    counts = {
        "cases": len(expected_cases),
        "expected_runs": len(expected_coordinates),
        "observed_runs": 0,
        "repetitions": repetitions,
        "exposure_runs": 0,
    }
    if repetitions < 3:
        issues.append(_issue(
            "missing_measurement",
            "insufficient_repetitions",
            "headline evidence requires at least 3 repetitions",
        ))
    if not model:
        issues.append(_issue("missing_measurement", "model_missing", "one requested model is required"))
    if not expected_cases or len(valid_cases) != len(requested_cases):
        issues.append(_issue(
            "missing_measurement",
            "case_population_invalid",
            "expected behavior case ids must be non-empty strings",
        ))
    if len(valid_cases) != len(expected_cases):
        issues.append(_issue(
            "missing_measurement",
            "duplicate_case_selection",
            "expected behavior case ids must be unique",
        ))
    design_path = runs / "answer-design.json"
    try:
        design = _read_json(design_path)
        evidence["answer_design"] = _sha256(design_path)
        evidence["manifest"] = _sha256(manifest)
    except EligibilityError as exc:
        issues.append(_issue("infrastructure_failure", "answer_design_unreadable", str(exc)))
        return _report(issues, evidence, counts)
    if not isinstance(design, dict) or design.get("schema_version") != 2 or design.get("population") != "answer":
        issues.append(_issue(
            "missing_measurement",
            "answer_design_schema",
            "answer-design.json must use answer schema version 2",
        ))
        identities: list[Any] = []
    else:
        identities = design.get("identities") if isinstance(design.get("identities"), list) else []
        payload = {
            key: design.get(key)
            for key in ("schema_version", "population", "eval_contract_sha256", "identities")
        }
        if design.get("design_sha256") != _canonical_sha256(payload):
            issues.append(_issue(
                "infrastructure_failure",
                "answer_design_digest",
                "answer design digest does not match its contents",
            ))
    coordinates: dict[tuple[str, str, int], dict[str, Any]] = {}
    for position, identity in enumerate(identities, 1):
        if not isinstance(identity, dict):
            issues.append(_issue(
                "infrastructure_failure",
                "answer_identity_schema",
                f"answer design identity {position} is not an object",
            ))
            continue
        case_id = identity.get("case_id")
        variant = identity.get("variant")
        run_number = identity.get("run_number")
        if (
            not isinstance(case_id, str)
            or not case_id
            or not isinstance(variant, str)
            or not variant
            or isinstance(run_number, bool)
            or not isinstance(run_number, int)
            or run_number < 1
        ):
            issues.append(_issue(
                "infrastructure_failure",
                "answer_identity_schema",
                f"answer design identity {position} has an invalid coordinate",
            ))
            continue
        coordinate = (case_id, variant, run_number)
        if coordinate in coordinates:
            issues.append(_issue(
                "missing_measurement",
                "duplicate_run",
                f"duplicate answer coordinate {coordinate!r}",
            ))
            continue
        coordinates[coordinate] = identity
    observed_coordinates = set(coordinates)
    counts["observed_runs"] = len(observed_coordinates)
    missing = sorted(expected_coordinates - observed_coordinates)
    extra = sorted(observed_coordinates - expected_coordinates, key=str)
    if missing:
        issues.append(_issue("missing_measurement", "missing_runs", f"missing run coordinates {missing!r}"))
    if extra:
        issues.append(_issue("missing_measurement", "unexpected_runs", f"unexpected run coordinates {extra!r}"))
    raw_models = [row.get("model") for row in coordinates.values()]
    if any(not isinstance(value, str) or not value for value in raw_models):
        issues.append(_issue(
            "infrastructure_failure",
            "model_identity_invalid",
            "every answer design identity must name a non-empty model",
        ))
    observed_models = {value for value in raw_models if isinstance(value, str) and value}
    if observed_models != {model}:
        issues.append(_issue(
            "missing_measurement",
            "model_population",
            f"answer design models {sorted(observed_models, key=str)!r} do not equal requested model {model!r}",
        ))
    artifact_digests: dict[str, str] = {}
    for coordinate in sorted(expected_coordinates & observed_coordinates):
        identity = coordinates[coordinate]
        run = identity.get("run_dir")
        if not isinstance(run, str) or not run:
            issues.append(_issue(
                "infrastructure_failure",
                "run_directory_invalid",
                f"answer coordinate {coordinate!r} has no run directory",
            ))
            continue
        relative = PurePosixPath(run)
        if relative.is_absolute() or any(part in {"", ".", ".."} for part in relative.parts):
            issues.append(_issue(
                "infrastructure_failure",
                "run_directory_invalid",
                f"run directory is not a safe relative path: {run!r}",
                run=run,
            ))
            continue
        run_dir = runs.joinpath(*relative.parts)
        ancestors = [runs.joinpath(*relative.parts[:index]) for index in range(1, len(relative.parts) + 1)]
        if any(path.is_symlink() for path in ancestors) or not run_dir.is_dir():
            issues.append(_issue(
                "infrastructure_failure",
                "run_directory_missing",
                f"run directory is absent or not regular: {run_dir}",
                run=run,
            ))
            continue
        digest = _validate_artifact_commit(run_dir, issues, run)
        if digest is not None:
            artifact_digests[run] = digest
        output_path = run_dir / "output.md"
        try:
            output = output_path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            issues.append(_issue(
                "infrastructure_failure", "candidate_output_unreadable", str(exc), run=run
            ))
        else:
            if not output.strip():
                issues.append(_issue(
                    "candidate_failure",
                    "candidate_output_missing",
                    "candidate output is blank",
                    run=run,
                ))
        metadata_path = run_dir / "metadata.json"
        try:
            metadata = _read_json(metadata_path)
        except EligibilityError as exc:
            issues.append(_issue("infrastructure_failure", "metadata_unreadable", str(exc), run=run))
            continue
        if not isinstance(metadata, dict):
            issues.append(_issue(
                "infrastructure_failure", "metadata_schema", "metadata must be an object", run=run
            ))
            continue
        expected_attestation = {
            "population": "answer",
            "case_id": identity.get("case_id"),
            "run_number": identity.get("run_number"),
            "variant": identity.get("variant"),
            "answer_design_sha256": design.get("design_sha256"),
            "answer_task_sha256": identity.get("task_sha256"),
            "answer_instruction_sha256": identity.get("instruction_sha256"),
            "skill_tree_hash": identity.get("planned_skill_tree_hash"),
            "fixture_tree_hash": identity.get("fixture_tree_hash"),
            "model": identity.get("model"),
        }
        mismatched = [key for key, value in expected_attestation.items() if metadata.get(key) != value]
        if mismatched:
            issues.append(_issue(
                "infrastructure_failure",
                "metadata_attestation_mismatch",
                f"metadata attestation mismatch in {mismatched!r}",
                run=run,
            ))
        incomplete = [field for field in OBSERVATION_FIELDS if metadata.get(field) is not True]
        if incomplete:
            issues.append(_issue(
                "infrastructure_failure",
                "invocation_observation_incomplete",
                f"invocation observation is incomplete in {incomplete!r}",
                run=run,
            ))
        _validate_telemetry(metadata, identity, issues, run)
        returncode = metadata.get("returncode")
        timed_out = metadata.get("timed_out")
        state = metadata.get("invocation_state")
        lifecycle_valid = (
            isinstance(state, str)
            and state
            and isinstance(timed_out, bool)
            and isinstance(returncode, int)
            and not isinstance(returncode, bool)
        )
        if not lifecycle_valid or (state != "complete" and not timed_out):
            issues.append(_issue(
                "infrastructure_failure",
                "candidate_invocation_invalid",
                f"candidate invocation lifecycle is malformed: state={state!r}, timed_out={timed_out!r}, returncode={returncode!r}",
                run=run,
            ))
        elif timed_out or returncode != 0:
            issues.append(_issue(
                "candidate_failure",
                "candidate_invocation_failed",
                f"candidate invocation state={state!r}, timed_out={timed_out!r}, returncode={returncode!r}",
                run=run,
            ))
    evidence["artifact_commits"] = artifact_digests
    try:
        exposure = exposure_report(runs, manifest, target_skill, split)
    except (LaneError, OSError, ValueError, RecursionError) as exc:
        issues.append(_issue("infrastructure_failure", "exposure_invalid", str(exc)))
    else:
        evidence["exposure_report"] = _canonical_sha256(exposure)
        counts["exposure_runs"] = len(exposure.get("runs", []))
        if not exposure.get("eligible"):
            issues.append(_issue(
                "missing_measurement",
                "exposure_ineligible",
                "target-skill exposure did not match the selected behavior cases",
            ))
    return _report(issues, evidence, counts)


def _task_ids(rows: list[dict[str, Any]], label: str) -> tuple[dict[str, dict[str, Any]], list[dict[str, str]]]:
    indexed: dict[str, dict[str, Any]] = {}
    issues: list[dict[str, str]] = []
    for position, row in enumerate(rows, 1):
        task_id = row.get("comparison_task_id", row.get("id"))
        if not isinstance(task_id, str) or not task_id:
            issues.append(_issue(
                "infrastructure_failure",
                f"{label}_id_missing",
                f"{label} row {position} has no comparison task id",
            ))
            continue
        if task_id in indexed:
            issues.append(_issue(
                "missing_measurement",
                f"duplicate_{label}",
                f"{label} contains duplicate task id {task_id!r}",
            ))
            continue
        indexed[task_id] = row
    return indexed, issues


def _comparison_task_digest(task: dict[str, Any]) -> str:
    identity = {
        "schema_version": task["schema_version"],
        "comparison_task_id": task["comparison_task_id"],
        "case_id": task["case_id"],
        "model": task.get("model"),
        "run_number": task["run_number"],
        "answer_design_sha256": task["answer_design_sha256"],
        "blind_nonce": task["blind_nonce"],
        "prompt": task["prompt"],
        "expectations": task["expectations"],
        "rubric": task["rubric"],
        "output_a_sha256": task["output_a_sha256"],
        "output_b_sha256": task["output_b_sha256"],
        "result_schema": task["result_schema"],
    }
    return _canonical_sha256(identity)


def validate_judge_receipt(
    *,
    receipt_path: Path,
    compare_tasks_path: Path,
    results_path: Path,
    prompt_path: Path,
    rubric_path: Path,
    calibration_set_path: Path,
    calibration_results_path: Path,
    order_swap_results_path: Path,
    answer_family: str,
    answer_model: str,
    minimum_calibration_labels: int = DEFAULT_MINIMUM_CALIBRATION_LABELS,
    minimum_accuracy: float = DEFAULT_MINIMUM_ACCURACY,
    minimum_order_swap_pairs: int = DEFAULT_MINIMUM_ORDER_SWAP_PAIRS,
    minimum_order_swap_consistency: float = DEFAULT_MINIMUM_ORDER_SWAP_CONSISTENCY,
) -> dict[str, Any]:
    issues: list[dict[str, str]] = []
    evidence: dict[str, Any] = {}
    counts = {
        "expected_verdicts": 0,
        "observed_verdicts": 0,
        "calibration_labels": 0,
        "order_swap_pairs": 0,
    }
    if (
        isinstance(minimum_calibration_labels, bool)
        or not isinstance(minimum_calibration_labels, int)
        or minimum_calibration_labels < 1
        or isinstance(minimum_accuracy, bool)
        or not isinstance(minimum_accuracy, (int, float))
        or not math.isfinite(minimum_accuracy)
        or not 0 < minimum_accuracy <= 1
        or isinstance(minimum_order_swap_pairs, bool)
        or not isinstance(minimum_order_swap_pairs, int)
        or minimum_order_swap_pairs < 1
        or isinstance(minimum_order_swap_consistency, bool)
        or not isinstance(minimum_order_swap_consistency, (int, float))
        or not math.isfinite(minimum_order_swap_consistency)
        or not 0 < minimum_order_swap_consistency <= 1
    ):
        issues.append(_issue(
            "infrastructure_failure",
            "eligibility_policy_invalid",
            "judge eligibility policy thresholds must be positive and bounded",
        ))
    paths = {
        "receipt": receipt_path,
        "compare_tasks": compare_tasks_path,
        "results": results_path,
        "prompt": prompt_path,
        "rubric": rubric_path,
        "calibration_set": calibration_set_path,
        "calibration_results": calibration_results_path,
        "order_swap_results": order_swap_results_path,
    }
    try:
        receipt = _read_json(receipt_path)
        tasks = _read_jsonl(compare_tasks_path)
        results = _read_jsonl(results_path)
        calibration_rows = _read_jsonl(calibration_set_path)
        calibration_results = _read_jsonl(calibration_results_path)
        order_swap_results = _read_jsonl(order_swap_results_path)
        evidence = {name: _sha256(path) for name, path in paths.items()}
    except EligibilityError as exc:
        issues.append(_issue("infrastructure_failure", "judge_evidence_unreadable", str(exc)))
        return _report(issues, evidence, counts)
    if not isinstance(receipt, dict) or receipt.get("schema_version") != 1:
        issues.append(_issue(
            "infrastructure_failure",
            "judge_receipt_schema",
            "judge receipt must use schema version 1",
        ))
        return _report(issues, evidence, counts)
    receipt_answer = receipt.get("answer")
    judge = receipt.get("judge")
    if receipt_answer != {"family": answer_family, "model": answer_model}:
        issues.append(_issue(
            "missing_measurement",
            "answer_identity_mismatch",
            "judge receipt does not bind the requested answer family and model",
        ))
    if (
        not isinstance(judge, dict)
        or not isinstance(judge.get("family"), str)
        or not judge.get("family")
        or not isinstance(judge.get("model"), str)
        or not judge.get("model")
    ):
        issues.append(_issue(
            "missing_measurement", "judge_identity_missing", "judge family and model are required"
        ))
    elif judge["family"] == answer_family:
        issues.append(_issue(
            "missing_measurement",
            "judge_not_cross_family",
            "judge family must differ from the answer family",
        ))
    receipt_digests = receipt.get("evidence_sha256")
    if not isinstance(receipt_digests, dict):
        issues.append(_issue(
            "infrastructure_failure",
            "judge_digest_schema",
            "judge receipt evidence_sha256 must be an object",
        ))
    else:
        for name in (
            "compare_tasks",
            "results",
            "prompt",
            "rubric",
            "calibration_set",
            "calibration_results",
            "order_swap_results",
        ):
            expected = evidence[name]
            observed = receipt_digests.get(name)
            if not isinstance(observed, str) or SHA256.fullmatch(observed) is None or observed != expected:
                issues.append(_issue(
                    "missing_measurement",
                    "judge_digest_mismatch",
                    f"judge receipt digest does not match {name}",
                ))
    task_index, task_issues = _task_ids(tasks, "task")
    result_index, result_issues = _task_ids(results, "result")
    issues.extend(task_issues)
    issues.extend(result_issues)
    counts["expected_verdicts"] = len(task_index)
    counts["observed_verdicts"] = len(result_index)
    if not task_index:
        issues.append(_issue(
            "missing_measurement",
            "comparison_population_empty",
            "comparison tasks must contain at least one pairwise verdict",
        ))
    if set(task_index) != set(result_index):
        missing = sorted(set(task_index) - set(result_index))
        extra = sorted(set(result_index) - set(task_index))
        issues.append(_issue(
            "missing_measurement",
            "verdict_coverage",
            f"verdict coverage differs from comparison tasks; missing={missing!r}; extra={extra!r}",
        ))
    for task_id in sorted(set(task_index) & set(result_index)):
        task = task_index[task_id]
        result = result_index[task_id]
        invalid_task_fields = [
            name for name in (
                "comparison_task_sha256",
                "answer_design_sha256",
                "comparison_design_sha256",
            )
            if not isinstance(task.get(name), str) or SHA256.fullmatch(task[name]) is None
        ]
        if invalid_task_fields:
            issues.append(_issue(
                "infrastructure_failure",
                "comparison_task_invalid",
                f"comparison task {task_id!r} has invalid digests {invalid_task_fields!r}",
            ))
        try:
            observed_task_digest = _comparison_task_digest(task)
        except KeyError as exc:
            issues.append(_issue(
                "infrastructure_failure",
                "comparison_task_invalid",
                f"comparison task {task_id!r} is missing identity field {exc.args[0]!r}",
            ))
        else:
            if task.get("comparison_task_sha256") != observed_task_digest:
                issues.append(_issue(
                    "missing_measurement",
                    "stale_comparison_task",
                    f"comparison task {task_id!r} does not match its identity digest",
                ))
        if result.get("comparison_task_sha256") != task.get("comparison_task_sha256"):
            issues.append(_issue(
                "missing_measurement",
                "stale_task_digest",
                f"verdict {task_id!r} does not bind its comparison task",
            ))
        if result.get("answer_design_sha256") != task.get("answer_design_sha256"):
            issues.append(_issue(
                "missing_measurement",
                "stale_answer_design",
                f"verdict {task_id!r} does not bind its answer design",
            ))
        if result.get("comparison_design_sha256") != task.get("comparison_design_sha256"):
            issues.append(_issue(
                "missing_measurement",
                "stale_comparison_design",
                f"verdict {task_id!r} does not bind its comparison design",
            ))
        if (
            result.get("schema_version") != 1
            or result.get("observation_complete") is not True
            or type(result.get("returncode")) is not int
            or result.get("returncode") != 0
            or result.get("winner") not in {"A", "B", "TIE"}
        ):
            issues.append(_issue(
                "infrastructure_failure",
                "verdict_invalid",
                f"verdict {task_id!r} has an invalid lifecycle or winner",
            ))
    coverage = receipt.get("verdict_coverage")
    expected_coverage = {
        "expected": len(task_index),
        "observed": len(result_index),
        "complete": set(task_index) == set(result_index),
    }
    if coverage != expected_coverage:
        issues.append(_issue(
            "missing_measurement",
            "receipt_verdict_coverage",
            "judge receipt verdict coverage does not match the evidence files",
        ))
    calibration = receipt.get("calibration")
    calibration_labels: dict[str, tuple[str, bool]] = {}
    for position, row in enumerate(calibration_rows, 1):
        calibration_id = row.get("id")
        expected_winner = row.get("expected_winner")
        critical = row.get("critical", False)
        if (
            not isinstance(calibration_id, str)
            or not calibration_id
            or calibration_id in calibration_labels
            or expected_winner not in {"A", "B", "TIE"}
            or not isinstance(critical, bool)
        ):
            issues.append(_issue(
                "infrastructure_failure",
                "calibration_set_invalid",
                f"calibration row {position} has an invalid id, label, or critical flag",
            ))
            continue
        calibration_labels[calibration_id] = (expected_winner, critical)
    calibration_predictions: dict[str, str] = {}
    for position, row in enumerate(calibration_results, 1):
        calibration_id = row.get("id")
        winner = row.get("winner")
        if (
            not isinstance(calibration_id, str)
            or not calibration_id
            or calibration_id in calibration_predictions
            or winner not in {"A", "B", "TIE"}
            or row.get("observation_complete") is not True
            or type(row.get("returncode")) is not int
            or row.get("returncode") != 0
        ):
            issues.append(_issue(
                "infrastructure_failure",
                "calibration_result_invalid",
                f"calibration result row {position} has an invalid lifecycle, id, or winner",
            ))
            continue
        calibration_predictions[calibration_id] = winner
    if set(calibration_predictions) != set(calibration_labels):
        issues.append(_issue(
            "missing_measurement",
            "calibration_coverage",
            "calibration predictions do not cover the labeled set exactly",
        ))
    calibration_correct = sum(
        calibration_predictions.get(calibration_id) == expected
        for calibration_id, (expected, _) in calibration_labels.items()
    )
    critical_total = sum(critical for _, critical in calibration_labels.values())
    critical_passed = sum(
        critical and calibration_predictions.get(calibration_id) == expected
        for calibration_id, (expected, critical) in calibration_labels.items()
    )
    if not isinstance(calibration, dict):
        issues.append(_issue(
            "missing_measurement", "calibration_missing", "judge calibration is required"
        ))
    else:
        labeled = len(calibration_labels)
        correct = calibration_correct
        accuracy = calibration.get("accuracy")
        threshold = calibration.get("minimum_accuracy")
        counts["calibration_labels"] = labeled
        valid_counts = (
            labeled >= minimum_calibration_labels
            and calibration.get("labeled_count") == labeled
            and calibration.get("correct_count") == correct
            and isinstance(accuracy, (int, float))
            and not isinstance(accuracy, bool)
            and accuracy == correct / labeled
            and isinstance(threshold, (int, float))
            and not isinstance(threshold, bool)
            and minimum_accuracy <= threshold <= 1
            and accuracy >= threshold
        )
        critical_ok = (
            critical_total > 0
            and calibration.get("critical_controls_total") == critical_total
            and calibration.get("critical_controls_passed") == critical_passed
            and critical_passed == critical_total
        )
        if not valid_counts or not critical_ok:
            issues.append(_issue(
                "missing_measurement",
                "calibration_failed",
                "judge calibration must meet its threshold and pass every critical control",
            ))
    order_swap = receipt.get("order_swap")
    swap_ids: set[str] = set()
    swap_consistent = 0
    inverse = {"A": "B", "B": "A", "TIE": "TIE"}
    for position, row in enumerate(order_swap_results, 1):
        pair_id = row.get("pair_id")
        original = row.get("original_winner")
        swapped = row.get("swapped_winner")
        if (
            not isinstance(pair_id, str)
            or not pair_id
            or pair_id in swap_ids
            or original not in inverse
            or swapped not in inverse
            or row.get("original_observation_complete") is not True
            or row.get("swapped_observation_complete") is not True
            or type(row.get("original_returncode")) is not int
            or row.get("original_returncode") != 0
            or type(row.get("swapped_returncode")) is not int
            or row.get("swapped_returncode") != 0
        ):
            issues.append(_issue(
                "infrastructure_failure",
                "order_swap_result_invalid",
                f"order-swap row {position} has an invalid lifecycle, id, or winner",
            ))
            continue
        swap_ids.add(pair_id)
        swap_consistent += int(inverse[original] == swapped)
    if not isinstance(order_swap, dict):
        issues.append(_issue(
            "missing_measurement", "order_swap_missing", "order-swap calibration is required"
        ))
    else:
        pair_count = len(swap_ids)
        consistent = swap_consistent
        consistency = order_swap.get("consistency")
        threshold = order_swap.get("minimum_consistency")
        counts["order_swap_pairs"] = pair_count
        valid_swap = (
            pair_count >= minimum_order_swap_pairs
            and order_swap.get("pair_count") == pair_count
            and order_swap.get("consistent_count") == consistent
            and isinstance(consistency, (int, float))
            and not isinstance(consistency, bool)
            and consistency == consistent / pair_count
            and isinstance(threshold, (int, float))
            and not isinstance(threshold, bool)
            and minimum_order_swap_consistency <= threshold <= 1
            and consistency >= threshold
        )
        if not valid_swap:
            issues.append(_issue(
                "missing_measurement",
                "order_swap_failed",
                "order-swap consistency must meet its declared threshold",
            ))
    return _report(issues, evidence, counts)


def _write_report(report: dict[str, Any], output: Path | None) -> None:
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if output is None:
        print(rendered, end="")
    else:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate direct-skill headline evidence eligibility.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    answer = subparsers.add_parser("answer-runs")
    answer.add_argument("--runs", type=Path, required=True)
    answer.add_argument("--manifest", type=Path, required=True)
    answer.add_argument("--skill", required=True)
    answer.add_argument("--split", required=True)
    answer.add_argument("--model", required=True)
    answer.add_argument("--repetitions", type=int, required=True)
    answer.add_argument("--case", action="append", required=True, dest="cases")
    answer.add_argument("--out", type=Path)

    judge = subparsers.add_parser("judge-receipt")
    judge.add_argument("--receipt", type=Path, required=True)
    judge.add_argument("--compare-tasks", type=Path, required=True)
    judge.add_argument("--results", type=Path, required=True)
    judge.add_argument("--prompt", type=Path, required=True)
    judge.add_argument("--rubric", type=Path, required=True)
    judge.add_argument("--calibration-set", type=Path, required=True)
    judge.add_argument("--calibration-results", type=Path, required=True)
    judge.add_argument("--order-swap-results", type=Path, required=True)
    judge.add_argument("--answer-family", required=True)
    judge.add_argument("--answer-model", required=True)
    judge.add_argument(
        "--minimum-calibration-labels",
        type=int,
        default=DEFAULT_MINIMUM_CALIBRATION_LABELS,
    )
    judge.add_argument("--minimum-accuracy", type=float, default=DEFAULT_MINIMUM_ACCURACY)
    judge.add_argument(
        "--minimum-order-swap-pairs",
        type=int,
        default=DEFAULT_MINIMUM_ORDER_SWAP_PAIRS,
    )
    judge.add_argument(
        "--minimum-order-swap-consistency",
        type=float,
        default=DEFAULT_MINIMUM_ORDER_SWAP_CONSISTENCY,
    )
    judge.add_argument("--out", type=Path)

    args = parser.parse_args()
    if args.command == "answer-runs":
        report = validate_answer_runs(
            runs=args.runs,
            manifest=args.manifest,
            target_skill=args.skill,
            split=args.split,
            model=args.model,
            repetitions=args.repetitions,
            expected_case_ids=args.cases,
        )
    else:
        report = validate_judge_receipt(
            receipt_path=args.receipt,
            compare_tasks_path=args.compare_tasks,
            results_path=args.results,
            prompt_path=args.prompt,
            rubric_path=args.rubric,
            calibration_set_path=args.calibration_set,
            calibration_results_path=args.calibration_results,
            order_swap_results_path=args.order_swap_results,
            answer_family=args.answer_family,
            answer_model=args.answer_model,
            minimum_calibration_labels=args.minimum_calibration_labels,
            minimum_accuracy=args.minimum_accuracy,
            minimum_order_swap_pairs=args.minimum_order_swap_pairs,
            minimum_order_swap_consistency=args.minimum_order_swap_consistency,
        )
    _write_report(report, args.out)
    return 0 if report["headline_eligible"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
