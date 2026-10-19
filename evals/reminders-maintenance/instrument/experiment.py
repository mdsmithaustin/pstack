#!/usr/bin/env python3
from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import importlib.metadata
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path

from artifact_contracts import CompleteArtifactSet, observe_artifact_set
from skill_benchmark import parse_trace_jsonl_text, prepared_task_rows, run_cost_facts, validate_manifest
from workspace_contracts import (
    Added, CapturedChanges, InBlob, InPatch, RegularFile, WorkspaceChangesState,
    blob_path, git_patch_entry, load_workspace_changes, workspace_changes_state,
)

from codex_project import extract_project

HERE = Path(__file__).resolve().parent
HARNESS_REVISION = "9190e1c2e4a2fe8e0dbcc73f932e7e995158f7fb"
TREATMENTS = ("current", "workflow", "principle")
INSTRUCTION = (
    "Use poteto-mode. Work directly in project/. Implement the request yourself "
    "using the local project and provided skills. Edit only application files in project/. "
    "Target Python 3.12 or newer using its standard library. "
    "Do not spawn or message downstream agents. Return concise usage and design notes."
)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")
    temporary.replace(path)


def read_json(path: Path) -> dict:
    return json.loads(path.read_text())


def tree_inventory(root: Path) -> dict[str, dict]:
    result = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink() or not (path.is_file() or path.is_dir()):
            raise ValueError(f"application and suite trees must contain regular files: {path}")
        if path.is_file():
            data = path.read_bytes()
            if len(data) > 1 << 20:
                raise ValueError(f"file exceeds the capture limit: {path}")
            result[path.relative_to(root).as_posix()] = {
                "sha256": digest(data), "size": len(data), "executable": bool(path.stat().st_mode & 0o111),
            }
    return result


def archive_project(project: Path, archive: Path) -> None:
    inventory = {name: value for name, value in tree_inventory(project).items()
                 if "__pycache__" not in Path(name).parts and not name.endswith((".pyc", ".pyo"))}
    if not inventory or "app.py" not in inventory:
        raise ValueError(f"application fixture must contain app.py: {project}")
    archive.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as target:
        for name, state in inventory.items():
            member = zipfile.ZipInfo(name, date_time=(2020, 1, 1, 0, 0, 0))
            member.external_attr = (0o100755 if state["executable"] else 0o100644) << 16
            target.writestr(member, (project / name).read_bytes())


@dataclass(frozen=True)
class Plan:
    root: Path
    config: dict

    @classmethod
    def load(cls, path: Path) -> Plan:
        config = read_json(path)
        root = Path(config["experiment_root"]).resolve()
        repository = HERE.parents[2]
        if root == repository or repository in root.parents:
            raise ValueError("experiment_root must be outside the source repository")
        if set(config["treatments"]) != set(TREATMENTS):
            raise ValueError("provide exactly current, workflow, and principle treatments")
        repeats = config.get("repeats", 2)
        if type(repeats) is not int or repeats < 1:
            raise ValueError("repeats must be a positive integer")
        ids = [case["id"] for case in config["cases"]]
        if not ids or len(ids) != len(set(ids)):
            raise ValueError("provide unique case ids")
        for name in ids:
            if not name or any(character not in "abcdefghijklmnopqrstuvwxyz0123456789-_" for character in name):
                raise ValueError("case ids must use lowercase letters, numbers, hyphens, and underscores")
        for key in ("models", "maintenance_models"):
            models = config.get(key)
            if models is None and key == "maintenance_models":
                continue
            if (not isinstance(models, list) or not models or len(models) != len(set(models))
                    or any(not isinstance(model, str) or not model or "/" in model or "\\" in model
                           or model in (".", "..") for model in models)):
                raise ValueError(f"{key} must be a nonempty list of unique path-safe model ids")
        return cls(root, config)


def manifest_rows(directory: Path, suite: Path, cases: list[dict], models: list[str], repeats: int,
                  stage: str, name: str) -> tuple[dict, list[dict], list[dict]]:
    skills = sorted(path for path in suite.glob("*/SKILL.md"))
    if not skills:
        raise ValueError(f"treatment suite contains no per-skill SKILL.md files: {suite}")
    manifest = {
        "version": 2, "skill_name": "application-guidance",
        "skill_paths": [os.path.relpath(path, directory) for path in skills],
        "variants": ["with_skill", "without_skill"], "cases": [],
    }
    for case in cases:
        manifest["cases"].append({
            "id": case["id"], "kind": "task", "split": "tune",
            "prompt": INSTRUCTION + "\n\n" + Path(case["prompt_path"]).read_text(),
            "files": [os.path.relpath(case["archive_path"], directory)],
            "expected_behavior": ["The captured application satisfies the private acceptance checks."],
            "assertions": [{
                "name": "application-acceptance", "type": "script", "severity": "gate",
                "oracle": "strong", "command": [
                    sys.executable, "instrument/experiment.py", "check", "--run", "{output_dir}",
                    "--oracle", os.path.relpath(case["oracle_path"], directory), "--stage", stage,
                ], "timeout_s": 120,
            }],
        })
    path = directory / name
    write_json(path, manifest)
    validated = validate_manifest(path)
    rows = prepared_task_rows(path, validated, models=models, runs_per_variant=repeats)
    return manifest, [row for row in rows if row["variant"] == "with_skill"], [
        row for row in rows if row["variant"] != "with_skill"]


def prepare(plan: Plan) -> dict:
    package = importlib.metadata.distribution("skill-eval-harness-ext")
    provenance = json.loads(package.read_text("direct_url.json") or "{}")
    if provenance.get("vcs_info", {}).get("commit_id") != HARNESS_REVISION:
        raise ValueError("the installed harness is not attested to the pinned revision")
    index_path = plan.root / "index.json"
    fingerprint = digest(json.dumps(plan.config, sort_keys=True).encode())
    if index_path.exists():
        index = read_json(index_path)
        if index["plan_sha256"] != fingerprint:
            raise ValueError("an existing experiment cannot be reused with a changed plan")
        verify_inputs(index)
        return index
    if plan.root.exists():
        existing = list(plan.root.iterdir())
        if existing and not (len(existing) == 1 and existing[0].name == "plan.json"
                             and read_json(existing[0]) == plan.config):
            raise ValueError("experiment_root is nonempty without a completed preparation record")
    plan.root.mkdir(parents=True, exist_ok=True)
    instrument = plan.root / "instrument"
    instrument.mkdir()
    for name in ("experiment.py", "codex_project.py", "claude_project.py"):
        shutil.copy2(HERE / name, instrument / name)
    cases = {}
    for case in plan.config["cases"]:
        destination = plan.root / "fixtures" / case["id"]
        destination.mkdir(parents=True)
        archive = destination / "project.zip"
        archive_project(Path(case["project_dir"]), archive)
        copied = {**case, "archive_path": str(archive)}
        for key in ("initial_prompt_path", "maintenance_prompt_path", "oracle_path"):
            source = Path(case[key])
            target = destination / source.name
            shutil.copyfile(source, target)
            copied[key] = str(target)
        for asset in case.get("oracle_assets", []):
            source = Path(asset)
            target = destination / source.name
            if target.exists():
                raise ValueError(f"oracle asset conflicts with another input: {source.name}")
            shutil.copyfile(source, target)
        cases[case["id"]] = copied
    suites = {}
    for treatment, source in plan.config["treatments"].items():
        destination = plan.root / "snapshots" / treatment / "skills"
        tree_inventory(Path(source))
        shutil.copytree(source, destination)
        suites[treatment] = str(destination)
    records, omissions = [], []
    for treatment in TREATMENTS:
        case_rows = [{**case, "prompt_path": case["initial_prompt_path"]} for case in cases.values()]
        _, selected, omitted = manifest_rows(plan.root, Path(suites[treatment]), case_rows,
                                             plan.config["models"], plan.config.get("repeats", 2), "design",
                                             f"{treatment}-manifest.json")
        omissions.extend({"treatment": treatment, "reason": "external nonempty treatment only", "task": row} for row in omitted)
        for row in selected:
            number = len(records) + 1
            directory = plan.root / "artifacts" / f"artifact-{number:04d}"
            directory.mkdir(parents=True)
            task = directory / "design.jsonl"
            task.write_text(json.dumps(row) + "\n")
            records.append({
                "id": f"artifact-{number:04d}", "treatment": treatment,
                "case_id": row["case_id"], "model": row["model"], "run_number": row["run_number"],
                "directory": str(directory), "design_task": str(task), "design_identity": row,
                "baseline_archive": cases[row["case_id"]]["archive_path"],
                "capture_baseline": "project_absent_before_wrapper_extraction",
            })
    index = {
        "schema_version": 1, "harness_revision": HARNESS_REVISION, "harness_version": package.version,
        "plan_sha256": fingerprint,
        "design": "external_three_treatment", "paired_lift": None, "cases": cases,
        "suites": suites, "records": records, "omitted_tasks": omissions,
        "judge_dimensions": "pending", "human_dimensions": "pending",
        "input_inventory": tree_inventory(plan.root),
    }
    write_json(index_path, index)
    return index


def verify_inputs(index: dict) -> None:
    root = Path(next(iter(index["suites"].values()))).parents[2]
    for name, expected in index["input_inventory"].items():
        path = root / name
        if path.is_symlink() or not path.is_file() or digest(path.read_bytes()) != expected["sha256"]:
            raise ValueError(f"immutable experiment input changed: {name}")
    for name in ("experiment.py", "codex_project.py", "claude_project.py"):
        if digest((HERE / name).read_bytes()) != index["input_inventory"][f"instrument/{name}"]["sha256"]:
            raise ValueError(f"controller differs from frozen instrumentation: {name}")


def reconstruct(run: Path, output: Path) -> dict:
    artifact = observe_artifact_set(run, declared_contract_version=1)
    if not isinstance(artifact, CompleteArtifactSet):
        raise ValueError(f"complete committed artifact required: {artifact}")
    if workspace_changes_state(run, artifact) is not WorkspaceChangesState.CAPTURED:
        raise ValueError("complete workspace capture required")
    capture = load_workspace_changes(run)
    if not isinstance(capture, CapturedChanges):
        raise ValueError("captured workspace required")
    for change in capture.changes:
        if (not change.path.startswith("project/") or not isinstance(change, Added)
                or not isinstance(change.after, RegularFile)
                or not isinstance(change.evidence, (InPatch, InBlob)) or change.after.size > 1 << 20):
            raise ValueError(f"protocol failure, unexpected workspace change: {change.path}")
    if not capture.changes:
        raise ValueError("no final application files captured")
    if output.exists():
        raise ValueError("reconstruction destination already exists")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="application-replay-", dir=output.parent) as temporary:
        replay = Path(temporary)
        patch_path = run / "candidate.patch"
        expected_patch = ""
        if capture.patch_sha256 is not None:
            subprocess.run(["git", "apply", "--whitespace=nowarn", str(patch_path.resolve())],
                           cwd=replay, capture_output=True, check=True, timeout=10)
        for change in capture.changes:
            target = replay / change.path
            state = change.after
            if isinstance(change.evidence, InBlob):
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes((run / blob_path(state.sha256)).read_bytes())
                target.chmod(0o755 if state.executable else 0o644)
            if target.is_symlink() or not target.is_file():
                raise ValueError(f"replayed file must be regular: {change.path}")
            data = target.read_bytes()
            if digest(data) != state.sha256 or len(data) != state.size:
                raise ValueError(f"replayed file digest disagrees: {change.path}")
            if bool(target.stat().st_mode & 0o111) != state.executable:
                raise ValueError(f"replayed executable state disagrees: {change.path}")
            if isinstance(change.evidence, InPatch):
                expected_patch += git_patch_entry(change.path, None, state, b"", data)
        if capture.patch_sha256 is not None and patch_path.read_text() != expected_patch:
            raise ValueError("patch disagrees with canonical captured project additions")
        inventory = tree_inventory(replay / "project")
        if set(inventory) != {change.path.removeprefix("project/") for change in capture.changes}:
            raise ValueError("replay produced undeclared application files")
        shutil.move(replay / "project", output)
    return inventory


def acceptance(project: Path, oracle: Path, stage: str, image: str | None = None,
               prior: Path | None = None) -> dict:
    if image is None:
        command = [sys.executable, "-B", str(oracle.resolve()), str(project.resolve()), "--stage", stage]
        if prior is not None:
            command.extend(["--prior-project", str(prior.resolve())])
    else:
        if "@sha256:" not in image:
            raise ValueError("acceptance image must be pinned by digest")
        command = ["docker", "run", "--rm", "--network", "none", "--read-only", "--cap-drop", "ALL",
                   "--security-opt", "no-new-privileges", "--pids-limit", "64", "--memory", "512m", "--cpus", "1",
                   "--tmpfs", "/tmp:rw,nosuid,nodev,size=64m",
                   "--mount", f"type=bind,src={project.resolve()},dst=/project,readonly",
                   "--mount", f"type=bind,src={oracle.resolve().parent},dst=/oracle,readonly"]
        if prior is not None:
            command.extend(["--mount", f"type=bind,src={prior.resolve()},dst=/prior,readonly"])
        command.extend([image, "python", "-B", "/oracle/" + oracle.name, "/project", "--stage", stage])
        if prior is not None:
            command.extend(["--prior-project", "/prior"])
    result = subprocess.run(command, capture_output=True, text=True, timeout=120,
                            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
    return {"returncode": result.returncode, "stdout": result.stdout, "stderr": result.stderr,
            "passed": result.returncode == 0}


def maintenance_task(plan: Plan, index: dict, record: dict) -> Path:
    directory = Path(record["directory"])
    design_directory = Path(record.get("design_directory", record["directory"]))
    project = design_directory / "design-project"
    if not project.exists():
        raise ValueError("design emitted no verified application tree")
    if not (project / "app.py").is_file():
        raise ValueError("design artifact is not runnable through app.py")
    design_record = read_json(design_directory / "design-record.json")
    if tree_inventory(project) != design_record.get("artifact_inventory"):
        raise ValueError("frozen design artifact changed before maintenance")
    if not isinstance(observe_artifact_set(Path(design_record["run_dir"]), declared_contract_version=1), CompleteArtifactSet):
        raise ValueError("design capture changed before maintenance")
    manifest_dir = directory / "maintenance-input"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    archive = manifest_dir / "project.zip"
    if not archive.exists():
        archive_project(project, archive)
    case = index["cases"][record["case_id"]]
    _, selected, omitted = manifest_rows(plan.root, Path(index["suites"]["current"]), [{
        **case, "prompt_path": case["maintenance_prompt_path"], "archive_path": str(archive),
    }], [record["model"]], 1, "maintenance", f"{record['id']}-{record['model']}-maintenance-manifest.json")
    task = directory / "maintenance.jsonl"
    if task.exists() and task.read_text() != json.dumps(selected[0]) + "\n":
        raise ValueError("maintenance task identity changed")
    task.write_text(json.dumps(selected[0]) + "\n")
    write_json(directory / "maintenance-identity.json", {
        "source_design_artifact": record["id"], "source_treatment": record["treatment"],
        "design_model": record.get("design_model", record["model"]), "maintenance_model": record["model"],
        "parent_run_number": record["run_number"],
        "guidance": "current", "task": selected[0], "omitted_tasks": omitted,
        "baseline_archive_sha256": digest(archive.read_bytes()), "baseline_inventory": tree_inventory(project),
    })
    return task


def execute_one(plan: Plan, index: dict, record: dict, stage: str) -> dict:
    directory = Path(record["directory"])
    status_path = directory / f"{stage}-record.json"
    if status_path.exists():
        status = read_json(status_path)
        run = Path(status["run_dir"])
        artifact = observe_artifact_set(run, declared_contract_version=1)
        if not isinstance(artifact, CompleteArtifactSet):
            raise ValueError(f"saved attempt artifacts changed: {run}")
        project = directory / f"{stage}-project"
        if "artifact_inventory" in status and tree_inventory(project) != status["artifact_inventory"]:
            raise ValueError(f"frozen application artifact changed: {project}")
        return status
    started = directory / f"{stage}-started.json"
    task = Path(record["design_task"]) if stage == "design" else maintenance_task(plan, index, record)
    row = json.loads(task.read_text())
    runs = directory / f"{stage}-runs"
    run = runs / row["run_dir"]
    if started.exists() and not run.exists():
        raise ValueError(f"interrupted attempt has no artifact, inspect before retrying: {started}")
    instrument = plan.root / "instrument"
    wrapper = shlex.join([sys.executable, str(instrument / "codex_project.py"),
                          plan.config.get("real_codex") or shutil.which("codex") or "codex",
                          "--sandbox", "workspace-write", "--disable", "multi_agent"])
    backend = plan.config.get("backends", {}).get(record["model"], "codex")
    if backend not in ("codex", "claude"):
        raise ValueError(f"unsupported native backend: {backend}")
    command = [plan.config.get("harness_bin") or str(Path(sys.executable).with_name("skill-benchmark")), "run-agent", "--agent", backend,
               "--tasks", str(task), "--runs", str(runs),
               "--timeout", str(plan.config.get("timeout", 600))]
    environment = dict(os.environ)
    if backend == "codex":
        command.extend(["--codex-cmd", plan.config.get("codex_cmd", wrapper)])
    else:
        environment["MODULE_CHOICE_CLAUDE"] = plan.config.get("real_claude") or shutil.which("claude") or "claude"
        command.extend(["--claude-bin", str(instrument / "claude_project.py")])
    if plan.config.get("effort"):
        command.extend(["--effort", plan.config["effort"]])
    if not started.exists():
        write_json(started, {"argv": command, "task": row, "stage": stage})
        with (directory / f"{stage}-harness.stdout").open("w") as stdout, (directory / f"{stage}-harness.stderr").open("w") as stderr:
            result = subprocess.run(command, stdout=stdout, stderr=stderr, check=False, env=environment)
        native_returncode = result.returncode
    else:
        native_returncode = None
    status = {"artifact_id": record["id"], "stage": stage, "run_dir": str(run),
              "harness_returncode": native_returncode, "task": row, "quality": "pending",
              "requested_model": record["model"], "design_model": record.get("design_model", record["model"])}
    try:
        project = directory / f"{stage}-project"
        with tempfile.TemporaryDirectory(prefix="verify-application-", dir=directory) as temporary:
            replay = Path(temporary) / "project"
            inventory = reconstruct(run, replay)
            if project.exists():
                if tree_inventory(project) != inventory:
                    raise ValueError("saved application tree differs from committed capture")
            else:
                shutil.move(replay, project)
        status["artifact_inventory"] = inventory
        status["protocol"] = "pass"
        case = index["cases"][record["case_id"]]
        baseline_archive = Path(record["baseline_archive"]) if stage == "design" else directory / "maintenance-input/project.zip"
        with tempfile.TemporaryDirectory(prefix="application-baseline-") as temporary:
            baseline = Path(temporary) / "project"
            extract_project(baseline_archive, baseline)
            before = tree_inventory(baseline)
        status["application_changes"] = {
            "created": sorted(set(inventory) - set(before)), "deleted": sorted(set(before) - set(inventory)),
            "modified": sorted(name for name in set(before) & set(inventory) if before[name] != inventory[name]),
        }
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        status["protocol"] = "fail"
        status["error"] = str(error)
    if status["protocol"] == "pass":
        try:
            prior = None
            if stage == "maintenance" and case.get("cross_version"):
                design_directory = Path(record.get("design_directory", record["directory"]))
                if read_json(design_directory / "design-record.json").get("acceptance", {}).get("passed"):
                    prior = design_directory / "design-project"
                    status["cross_version"] = "included_in_acceptance"
                else:
                    status["cross_version"] = "unmeasured_design_failed"
            status["acceptance"] = acceptance(project, Path(case["oracle_path"]), stage,
                                               plan.config.get("oracle_image"), prior)
        except (OSError, ValueError, subprocess.SubprocessError) as error:
            status["acceptance"] = {"passed": False, "error": str(error)}
    write_json(status_path, status)
    return status


def stage_records(plan: Plan, index: dict, stage: str) -> list[dict]:
    if stage == "design":
        return index["records"]
    records = []
    for record in index["records"]:
        models = plan.config.get("maintenance_by_design_model", {}).get(
            record["model"], plan.config.get("maintenance_models", [record["model"]]))
        for model in models:
            if not model or "/" in model or "\\" in model or model in (".", ".."):
                raise ValueError("maintenance models must be path-safe model ids")
            directory = Path(record["directory"]) / "maintenance" / model
            directory.mkdir(parents=True, exist_ok=True)
            records.append({**record, "design_directory": record["directory"],
                            "design_model": record["model"], "directory": str(directory), "model": model})
    return records


def execute(plan: Plan, stage: str, jobs: int, models: list[str] | None = None,
            repetitions: int | None = None) -> list[dict]:
    index = prepare(plan)
    verify_inputs(index)
    records = [record for record in stage_records(plan, index, stage)
               if (models is None or record["model"] in models)
               and (repetitions is None or record["run_number"] <= repetitions)]
    if not records:
        raise ValueError("execution filters selected no artifacts")
    with concurrent.futures.ThreadPoolExecutor(max_workers=jobs) as pool:
        futures = {pool.submit(execute_one, plan, index, record, stage): record for record in records}
        results = []
        for future in concurrent.futures.as_completed(futures):
            record = futures[future]
            try:
                result = future.result()
            except (OSError, ValueError, subprocess.SubprocessError) as error:
                result = {"artifact_id": record["id"], "stage": stage, "requested_model": record["model"],
                          "design_model": record.get("design_model", record["model"]),
                          "execution": "blocked", "error": str(error)}
                write_json(Path(record["directory"]) / f"{stage}-blocked.json", result)
            results.append(result)
            print(json.dumps({key: result.get(key) for key in ("artifact_id", "stage", "protocol", "execution", "error")}), flush=True)
    return sorted(results, key=lambda result: (result["artifact_id"], result.get("requested_model", "")))


def summarize(plan: Plan) -> dict:
    index = prepare(plan)
    attempts = []
    blocked = []
    for stage in ("design", "maintenance"):
        for record in stage_records(plan, index, stage):
            directory = Path(record["directory"])
            started = directory / f"{stage}-started.json"
            if not started.exists():
                blocked_path = directory / f"{stage}-blocked.json"
                if blocked_path.exists():
                    blocked.append(read_json(blocked_path))
                continue
            identity = read_json(started)
            run = directory / f"{stage}-runs" / identity["task"]["run_dir"]
            artifact = observe_artifact_set(run, declared_contract_version=1)
            committed = isinstance(artifact, CompleteArtifactSet)
            metrics = read_json(run / "metrics.json") if committed else {}
            metadata = read_json(run / "metadata.json") if committed else {}
            facts = run_cost_facts({**metadata, **metrics})
            attempt = {"artifact_id": record["id"], "treatment": record["treatment"], "stage": stage,
                       "requested_model": record["model"], "case_id": record["case_id"],
                       "design_model": record.get("design_model", record["model"]),
                       "artifact_state": artifact.state.value,
                       "backend": plan.config.get("backends", {}).get(record["model"], "codex"),
                       "run_number": record["run_number"], "run_dir": str(run),
                       "input_tokens": facts["input_tokens"], "output_tokens": facts["output_tokens"],
                       "total_tokens": facts["total_tokens"], "observed_usd": facts["cost_usd"],
                       "observed_subtotal_usd": metrics.get("observed_subtotal_usd", metadata.get("observed_subtotal_usd")),
                       "cost_source": facts["cost_source"], "elapsed_ms": metrics.get("elapsed_ms", metadata.get("elapsed_ms")),
                       "served_model": metadata.get("served_model"), "served_models": metadata.get("served_models"),
                       "served_model_availability": "reported" if metadata.get("served_model") else "unreported",
                       "telemetry": metrics.get("telemetry"), "native_metadata": metadata,
                       "evidence_files": [str(run / name) for name in ("metadata.json", "metrics.json", "events.json", "workspace-changes.json", "artifact-commit.json")],
                       "api_equivalent_estimate_usd": None}
            price = plan.config.get("price_table", {}).get(record["model"])
            incoming, outgoing = facts["input_tokens"], facts["output_tokens"]
            trace = run / "trace.jsonl"
            native_usage = None
            if committed and trace.exists():
                native_events, errors = parse_trace_jsonl_text(trace.read_text(), strict=False)
                terminal = "result" if attempt["backend"] == "claude" else "turn.completed"
                usages = [event.get("usage") for event in native_events if event.get("type") == terminal]
                if not errors and len(usages) == 1 and isinstance(usages[0], dict):
                    native_usage = usages[0]
            attempt["native_usage"] = native_usage
            if price and native_usage is not None:
                if attempt["backend"] == "codex":
                    cached = native_usage.get("cached_input_tokens")
                    written = 0
                    uncached = incoming - cached if incoming is not None and cached is not None else None
                else:
                    cached = native_usage.get("cache_read_input_tokens")
                    written = native_usage.get("cache_creation_input_tokens")
                    uncached = native_usage.get("input_tokens")
                counts = (uncached, cached, written, outgoing)
                write_price = price.get("cache_write", price.get("cache_creation"))
                if all(type(value) is int and value >= 0 for value in counts) and (written == 0 or write_price is not None):
                    attempt["api_equivalent_estimate_usd"] = (
                        uncached * price["input"] + cached * price["cached_input"]
                        + written * (write_price or 0) + outgoing * price["output"]
                    ) / 1_000_000
            attempt["evidence_files"].append(str(trace))
            attempt["estimate_availability"] = "estimated" if attempt["api_equivalent_estimate_usd"] is not None else "unknown_tokens_or_price"
            status = directory / f"{stage}-record.json"
            attempt["result"] = read_json(status) if status.exists() else {"execution": "incomplete"}
            attempts.append(attempt)
    summary = {"design": "external_three_treatment", "paired_lift": None, "attempts": attempts,
               "blocked_cells": blocked,
               "attempt_count": len(attempts), "unknown_token_attempts": sum(a["total_tokens"] is None for a in attempts),
               "observed_usd_known_subtotal": sum(a["observed_usd"] or 0 for a in attempts),
               "observed_usd_unknown_attempts": sum(a["observed_usd"] is None for a in attempts),
               "judge_dimensions": "pending", "human_dimensions": "pending"}
    write_json(plan.root / "summary.json", summary)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("prepare", "execute", "summarize"):
        command = commands.add_parser(name)
        command.add_argument("--plan", type=Path, required=True)
        if name == "execute":
            command.add_argument("--stage", choices=("design", "maintenance"), required=True)
            command.add_argument("--jobs", type=int, default=3)
            command.add_argument("--models", help="comma-separated stage models for a smaller first screen")
            command.add_argument("--repetitions", type=int, help="run only the first N planned repetitions")
    replay = commands.add_parser("reconstruct")
    replay.add_argument("--run", type=Path, required=True)
    replay.add_argument("--output", type=Path, required=True)
    check = commands.add_parser("check")
    check.add_argument("--run", type=Path, required=True)
    check.add_argument("--oracle", type=Path, required=True)
    check.add_argument("--stage", choices=("design", "maintenance"), required=True)
    check.add_argument("--oracle-image", required=True)
    check.add_argument("--prior-project", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "reconstruct":
            print(json.dumps(reconstruct(args.run, args.output)))
        elif args.command == "check":
            with tempfile.TemporaryDirectory(prefix="application-check-") as temporary:
                project = Path(temporary) / "project"
                reconstruct(args.run, project)
                result = acceptance(project, args.oracle, args.stage,
                                    args.oracle_image, args.prior_project)
                print(json.dumps(result))
                return int(not result["passed"])
        else:
            plan = Plan.load(args.plan)
            if args.command == "prepare":
                result = prepare(plan)
                print(json.dumps({"prepared": len(result["records"]), "omitted": len(result["omitted_tasks"])}))
            elif args.command == "execute":
                if args.jobs < 1:
                    raise ValueError("jobs must be positive")
                if args.repetitions is not None and args.repetitions < 1:
                    raise ValueError("repetitions must be positive")
                results = execute(plan, args.stage, args.jobs,
                                  args.models.split(",") if args.models else None, args.repetitions)
                return int(any(result.get("protocol") != "pass" or not result.get("acceptance", {}).get("passed") for result in results))
            else:
                result = summarize(plan)
                print(json.dumps({"attempts": result["attempt_count"], "summary": str(plan.root / "summary.json")}))
        return 0
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print(str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
