#!/usr/bin/env python3
"""Freeze and settle the bounded native, upstream, and current-port study."""
from __future__ import annotations

import argparse
import fcntl
from concurrent.futures import ThreadPoolExecutor
import hashlib
import io
import json
import math
from pathlib import Path, PurePosixPath
import random
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import uuid

EVALS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(EVALS))
from canon.application import ApplicationError, Request, Runtime, Snapshot, replay, run_application

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import upstream_personas

REPO = EVALS.parent
UPSTREAM = "1b6d44ff26d4e242f4e8f68c391e6d2f7ca16def"
CURRENT = "701c9a6f09ae3b0bd56a4962ff299c21accf8690"
IMAGE = "python:3.12-slim@sha256:229a2c5bfa27522db7815ea81f9bed70af17ccb9de9fc7ad142b1877b5830d36"
ARMS = ("native", "upstream", "current")
STAGES = ("initial", "maintenance")
DURATIONS = ("elapsed_s", "native_elapsed_s")
FORBIDDEN = re.compile(r"\b(eval|test|judge|experiment|rubric|score|compare|benchmark|candidate|arena)\b", re.I)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique_object)


def write_json(path: Path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def inventory(root: Path):
    result = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ValueError(f"symlink in frozen input: {path}")
        if path.is_file():
            data = path.read_bytes()
            result[path.relative_to(root).as_posix()] = {
                "sha256": digest(data), "bytes": len(data),
                "executable": bool(path.stat().st_mode & 0o111),
            }
        elif not path.is_dir():
            raise ValueError(f"unsupported frozen input: {path}")
    return result


def readonly(root: Path):
    for path in root.rglob("*"):
        path.chmod(0o555 if path.is_dir() or path.stat().st_mode & 0o111 else 0o444)
    root.chmod(0o555)


def relative(root: Path, raw: str) -> Path:
    path = PurePosixPath(raw)
    if not path.parts or path.is_absolute() or ".." in path.parts:
        raise ValueError(f"unsafe relative path: {raw}")
    target = root.joinpath(*path.parts)
    if not target.exists() or target.is_symlink():
        raise ValueError(f"missing or linked input: {raw}")
    return target


def export_tree(repo: Path, revision: str, prefix: str, destination: Path):
    archive = subprocess.run(
        ["git", "-C", str(repo), "archive", revision, prefix],
        check=True, capture_output=True,
    ).stdout
    destination.mkdir(parents=True)
    with tarfile.open(fileobj=io.BytesIO(archive)) as tree:
        for member in tree:
            if member.isdir():
                continue
            path = PurePosixPath(member.name)
            local = path.relative_to(prefix)
            if not member.isfile() or ".." in local.parts:
                raise ValueError(f"unsupported Git tree entry: {member.name}")
            target = destination.joinpath(*local.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(tree.extractfile(member).read())
            target.chmod(0o755 if member.mode & 0o111 else 0o644)


def adapt_upstream(skills: Path, agents: Path | None = None):
    edits = []
    for entry in sorted(skills.glob("*/SKILL.md")):
        original = entry.read_bytes()
        match = re.match(rb"\A---\r?\n(.*?)\r?\n---\r?\n", original, re.S)
        if not match:
            raise ValueError(f"skill has no frontmatter: {entry.name}")
        flag = re.compile(rb"^disable-model-invocation:\s*true\s*\r?\n", re.M)
        if not flag.search(match[1] + b"\n"):
            continue
        changed = original[:match.start(1)] + flag.sub(b"", match[1] + b"\n").rstrip(b"\n") + original[match.end(1):]
        entry.write_bytes(changed)
        policy = entry.parent / "agents/openai.yaml"
        if policy.exists():
            raise ValueError("upstream policy already exists; adaptation needs review")
        policy.parent.mkdir(exist_ok=True)
        policy.write_text("policy:\n  allow_implicit_invocation: false\n", encoding="utf-8")
        for path, before in ((entry, original), (policy, None)):
            after = path.read_bytes()
            edits.append({"path": path.relative_to(skills).as_posix(),
                          "kind": "invocation_policy",
                          "before_sha256": digest(before) if before is not None else None,
                          "after_sha256": digest(after),
                          "before": before.decode() if before is not None else None,
                          "after": after.decode(),
                          "reason": "Translate user-only invocation to native Codex policy."})
    if agents is not None:
        copied = skills / "pstack-harness/upstream-agents"
        copied.mkdir(parents=True)
        for name in ("poteto-agent", "comment-sicko"):
            source = agents / f"{name}.md"
            target = copied / source.name
            original = source.read_bytes()
            target.write_bytes(original)
            edits.append({"kind": "persona_source", "path": target.relative_to(skills).as_posix(),
                          "source": f"{UPSTREAM}:pstack/agents/{name}.md",
                          "before": original.decode(), "after": original.decode(),
                          "before_sha256": digest(original), "after_sha256": digest(original),
                          "reason": "Deliver the exact pinned upstream root persona."})
        adapter = skills / "pstack-harness/scripts/subagents.py"
        adapter.parent.mkdir()
        adapter.write_bytes(Path(upstream_personas.__file__).read_bytes())
        additions = [(adapter.relative_to(skills).as_posix(), adapter.read_bytes(), "registration_adapter")]
        additions.extend((f".codex/agents/{name}", content, "native_registration")
                         for name, content in upstream_personas.render(copied).items())
        for path, content, kind in additions:
            edits.append({"kind": kind, "path": path, "before": None, "after": content.decode(),
                          "before_sha256": None, "after_sha256": digest(content),
                          "reason": "Register upstream personas in native Codex format without adding skill workflow instructions."})
    return {"edits": edits, "delivery_prefix": upstream_personas.DELIVERY_PREFIX,
            "preserved": "All other upstream skill bytes, workflow text, tool and model fallback instructions, and exact root persona bodies.",
            "scope": "Cold-start relevance-driven skill discovery; no forced entry skill invocation."}


def parse_grade(stdout: bytes, returncode: int):
    if type(returncode) is not int:
        raise ValueError("oracle exit must be an integer")
    try:
        grade = json.loads(stdout, object_pairs_hook=unique_object)
    except (ValueError, UnicodeDecodeError) as exc:
        raise ValueError("oracle must return one JSON object") from exc
    if not isinstance(grade, dict) or set(grade) != {"passed", "assertions", "failures"}:
        raise ValueError("oracle requires passed, assertions, and failures only")
    if type(grade["passed"]) is not bool or type(grade["assertions"]) is not int or grade["assertions"] <= 0:
        raise ValueError("oracle requires a boolean result and positive integer assertions")
    if not isinstance(grade["failures"], list) or any(not isinstance(item, str) or not item for item in grade["failures"]):
        raise ValueError("oracle failures must be nonempty strings")
    if grade["passed"] != (not grade["failures"]):
        raise ValueError("oracle result conflicts with failures")
    if returncode != (0 if grade["passed"] else 1):
        raise ValueError("oracle exit disagrees with result")
    return grade


def grade_capture(oracle: Path, snapshot: Snapshot, stage: str, receipt: Path):
    receipt.mkdir(parents=True)
    started = time.monotonic()
    name = "pstack-check-" + uuid.uuid4().hex[:16]
    command = None
    try:
        with tempfile.TemporaryDirectory(prefix="parcel-") as temporary:
            project = replay(snapshot, Path(temporary) / "app")
            checks = Path(temporary) / "checks"
            checks.mkdir()
            shutil.copyfile(oracle, checks / "oracle.py")
            if (oracle.parent / "checks.json").exists():
                shutil.copyfile(oracle.parent / "checks.json", checks / "checks.json")
            command = ["docker", "run", "--detach", "--name", name,
                       "--network", "none", "--read-only", "--cap-drop", "ALL",
                       "--security-opt", "no-new-privileges", "--pids-limit", "128",
                       "--memory", "256m", "--cpus", "1", "--tmpfs", "/tmp:rw,nosuid,size=64m",
                       "--mount", f"type=bind,src={project},dst=/app,readonly",
                       "--mount", f"type=bind,src={checks},dst=/check,readonly",
                       IMAGE, "python", "-I", "-B", "/check/oracle.py",
                       "--project", "/app", "--stage", stage]
            launched = subprocess.run(command, capture_output=True, timeout=30, check=True)
            (receipt / "container.stdout").write_bytes(launched.stdout)
            waited = subprocess.run(["docker", "wait", name], capture_output=True, timeout=45, check=True)
            logs = subprocess.run(["docker", "logs", name], capture_output=True, timeout=10, check=True)
            (receipt / "oracle.stdout").write_bytes(logs.stdout)
            (receipt / "oracle.stderr").write_bytes(logs.stderr)
            returncode = int(waited.stdout.strip())
            grade = parse_grade(logs.stdout, returncode)
            outcome = {"state": "graded", **grade, "returncode": returncode}
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        outcome = {"state": "oracle_error", "passed": None, "error": str(exc)}
    finally:
        removed = subprocess.run(["docker", "rm", "-f", name], capture_output=True, timeout=15, check=False)
        (receipt / "cleanup.stderr").write_bytes(removed.stderr)
    outcome.update({"stage": stage, "capture_sha256": snapshot.sha256,
                    "oracle_sha256": digest(oracle.read_bytes()), "argv": command,
                    "elapsed_s": time.monotonic() - started})
    write_json(receipt / "receipt.json", outcome)
    return outcome


def calibration(root: Path, plan: dict, grader=grade_capture):
    rows = []
    for case in plan["cases"]:
        case_root = relative(root / "inputs", case["directory"])
        controls = [(control, path, stage, expected, None) for control, stage, expected in
                    (("initial", "initial", True), ("maintenance", "maintenance", True),
                     ("noop", "initial", False), ("noop", "maintenance", False),
                     ("targeted", "maintenance", False))
                    for path in [case["controls"][control]]]
        for defect in case.get("defects", []):
            if any(path == defect["path"] and stage == defect["stage"] for _, path, stage, _, _ in controls):
                controls = [(name, path, stage, expected, defect["failure"] if path == defect["path"] and stage == defect["stage"] else failure)
                            for name, path, stage, expected, failure in controls]
            else:
                controls.append((PurePosixPath(defect["path"]).name, defect["path"], defect["stage"], False, defect["failure"]))
        for control, path, stage, expected, failure in controls:
            key = f"{case['id']}-{control}-{stage}"
            snapshot = Snapshot.freeze(relative(case_root, path), root / "calibration" / key / "capture")
            grade = grader(relative(case_root, case["oracle"]), snapshot, stage, root / "calibration" / key / "grade")
            rows.append({"case": case["id"], "control": control, "stage": stage,
                         "expected": expected, "observed": grade,
                         "required_failure": failure,
                         "valid": grade["state"] == "graded" and grade["passed"] is expected and
                         (failure is None or any(item.startswith(failure + ":") for item in grade.get("failures", [])))})
    receipt = {"passed": bool(rows) and all(row["valid"] for row in rows), "checks": rows}
    write_json(root / "calibration.json", receipt)
    if not receipt["passed"]:
        raise ValueError("oracle calibration failed; no model slots may start")
    return receipt


def native_templates():
    process = subprocess.run(["sbx", "template", "ls", "--json"], capture_output=True,
                             check=True, timeout=15)
    listing = json.loads(process.stdout, object_pairs_hook=unique_object)
    rows = listing if isinstance(listing, list) else listing["images"]
    return {f"{row['repository'].rsplit('/', 1)[-1]}:{row['tag']}": row for row in rows}


def observe_runtime(runtime: dict, catalog):
    key = runtime["template"].rsplit("/", 1)[-1]
    observed = catalog().get(key)
    if observed is None or observed.get("id") != runtime["observed_template_id"]:
        raise ValueError("prepared native template identity changed or is unavailable")
    return observed


def prepare(root: Path, cases: Path, runtime_receipt: Path, *, model: str, effort: str,
            timeout_s: int = 240, seed: int = 73129, repo: Path = REPO, grader=grade_capture,
            template_catalog=native_templates):
    root = root.resolve()
    if root.is_relative_to(repo.resolve()) or root.exists():
        raise ValueError("study directory must be new and outside the repository")
    runtime = read_json(runtime_receipt)
    if not all(runtime.get(key) for key in ("template", "observed_template_id", "cli_version")):
        raise ValueError("runtime receipt lacks pinned template identity or CLI version")
    if any(runtime.get("capabilities", {}).get(key) is not True for key in ("skills", "multi_agent")):
        raise ValueError("runtime must establish native skill discovery and delegation")
    if timeout_s <= 0:
        raise ValueError("timeout must be positive")
    runtime_observation = observe_runtime(runtime, template_catalog)
    source_cases = sorted(cases.glob("*/case.json"))
    if len(source_cases) != 3:
        raise ValueError("comparison requires exactly three cases")
    root.mkdir(mode=0o700)
    inputs = root / "inputs"
    inputs.mkdir()
    shutil.copyfile(runtime_receipt, inputs / "runtime.json")
    write_json(inputs / "template-observation.json", runtime_observation)
    frozen_cases = []
    for manifest in source_cases:
        raw = read_json(manifest)
        if not re.fullmatch(r"[a-z][a-z0-9-]*", raw["id"]):
            raise ValueError("case id must be a simple project name")
        target = inputs / "cases" / raw["id"]
        inventory(manifest.parent)
        shutil.copytree(manifest.parent, target)
        project = relative(target, raw["project"])
        for item in [*project.rglob("*"), relative(target, raw["initial_request"]), relative(target, raw["maintenance_request"])]:
            exposed_name = item.relative_to(project).as_posix() if item.is_relative_to(project) else item.name
            if FORBIDDEN.search(exposed_name) or (item.is_file() and FORBIDDEN.search(item.read_text(encoding="utf-8"))):
                raise ValueError(f"candidate-facing material discloses study context: {exposed_name}")
        if set(raw["controls"]) != {"initial", "maintenance", "noop", "targeted"}:
            raise ValueError("case controls must name initial, maintenance, noop, and targeted")
        relative(target, raw["oracle"])
        for value in raw["controls"].values():
            relative(target, value)
        project_snapshot = Snapshot.freeze(project, inputs / "projects" / raw["id"])
        frozen_cases.append({**raw, "directory": target.relative_to(inputs).as_posix(),
                             "project_snapshot": {"directory": f"projects/{raw['id']}", "sha256": project_snapshot.sha256}})
    if len({case["id"] for case in frozen_cases}) != 3:
        raise ValueError("case ids must be unique")
    for arm, revision, prefix in (("upstream", UPSTREAM, "pstack/skills"), ("current", CURRENT, "skills")):
        export_tree(repo, revision, prefix, inputs / "guidance" / arm)
    export_tree(repo, UPSTREAM, "pstack/agents", inputs / "upstream-agents")
    write_json(inputs / "compatibility.json", adapt_upstream(inputs / "guidance/upstream", inputs / "upstream-agents"))
    guidance_snapshots = {}
    for arm in ("upstream", "current"):
        snapshot = Snapshot.freeze(inputs / "guidance" / arm, inputs / "guidance-snapshots" / arm)
        guidance_snapshots[arm] = {"directory": f"guidance-snapshots/{arm}", "sha256": snapshot.sha256}
    committed = subprocess.run(["git", "-C", str(repo), "ls-tree", "-r", CURRENT, "evals"],
                               check=True, capture_output=True, text=True).stdout
    corpus_objects = {}
    for line in committed.splitlines():
        metadata, path = line.split("\t", 1)
        corpus_objects.setdefault(metadata.split()[2], []).append(path)
    heldout = []
    for case in frozen_cases:
        private = relative(inputs, case["directory"])
        for stage in STAGES:
            prompt = relative(private, case[f"{stage}_request"])
            blob = subprocess.run(["git", "hash-object", "--stdin"], input=prompt.read_bytes(),
                                  check=True, capture_output=True).stdout.decode().strip()
            matches = corpus_objects.get(blob, [])
            heldout.append({"case": case["id"], "stage": stage, "sha256": digest(prompt.read_bytes()),
                            "committed_corpus_matches": matches})
            if matches:
                raise ValueError("held-out request already exists in committed public corpus")
    write_json(inputs / "heldout.json", {"revision": CURRENT, "scope": "Exact request bytes in committed evals files; conceptual task independence requires author review.", "requests": heldout})
    source_files = [Path(__file__).resolve(), Path(upstream_personas.__file__).resolve(),
                    EVALS / "canon/application.py", EVALS / "canon/sbx.json"]
    sources = {}
    for path in source_files:
        sources[str(path)] = digest(path.read_bytes())
        target = inputs / "source" / path.relative_to(EVALS)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
    blocks = [(case["id"], repetition) for case in frozen_cases for repetition in (1, 2)]
    rng = random.Random(seed)
    rng.shuffle(blocks)
    cells = []
    for case_id, repetition in blocks:
        arms = list(ARMS)
        rng.shuffle(arms)
        offset = len(cells)
        cells.extend({"id": f"p{offset + index + 1:02d}", "case": case_id,
                      "arm": arm, "repetition": repetition} for index, arm in enumerate(arms))
    plan = {"version": 1, "seed": seed, "runtime": {"template": runtime["template"],
            "model": model, "effort": effort, "timeout_s": timeout_s},
            "sources": sources, "pins": {"upstream": UPSTREAM, "current": CURRENT},
            "oracle_image": IMAGE, "cases": frozen_cases, "cells": cells, "guidance_snapshots": guidance_snapshots,
            "opportunities": 36,
            "limits": "Three held-out tasks, two repetitions per arm. Executable application acceptance only; requested README updates and broader task quality are unmeasured. Cold-start relevance-driven discovery without explicit workflow activation. No general causal claim."}
    write_json(inputs / "plan.json", plan)
    calibration(root, plan, grader)
    write_json(root / "seal.json", {"plan": plan, "inventory": inventory(inputs), "calibration_sha256": digest((root / "calibration.json").read_bytes())})
    readonly(inputs)
    (root / "seal.json").chmod(0o444)
    (root / "calibration.json").chmod(0o444)
    return plan


def verify_inputs(root: Path):
    seal = read_json(root / "seal.json")
    if inventory(root / "inputs") != seal["inventory"]:
        raise ValueError("frozen study input changed")
    if digest((root / "calibration.json").read_bytes()) != seal["calibration_sha256"]:
        raise ValueError("calibration receipt changed")
    plan = read_json(root / "inputs/plan.json")
    if not read_json(root / "calibration.json")["passed"]:
        raise ValueError("study is not calibrated")
    for raw, expected in plan["sources"].items():
        if digest(Path(raw).read_bytes()) != expected:
            raise ValueError(f"execution source changed: {raw}")
    return plan


def snapshot_at(root: Path, raw: dict):
    return Snapshot(relative(root, raw["directory"]), raw["sha256"])


def run_stage(root: Path, plan: dict, cell: dict, stage: str, *, execute=run_application,
              grader=grade_capture, template_catalog=native_templates):
    directory = root / "lineages" / cell["id"] / stage
    directory.mkdir(parents=True)
    case = next(case for case in plan["cases"] if case["id"] == cell["case"])
    private = relative(root / "inputs", case["directory"])
    outcome = {"state": "incomplete", "native_state": "unknown", "native_valid": False,
               "capture": None, "grade": None, "usage": None, "elapsed_s": None, "native_elapsed_s": None}
    write_json(directory / "claim.json", {"cell": cell["id"], "stage": stage})
    try:
        verified = verify_inputs(root)
        if verified != plan:
            raise ValueError("planned call differs from frozen plan")
        if stage == "maintenance":
            initial_path = directory.parent / "initial/outcome.json"
            initial = read_json(initial_path) if initial_path.exists() else {}
            if not initial.get("capture"):
                outcome.update(state="blocked", reason="initial capture missing or invalid")
                write_json(directory / "outcome.json", outcome)
                return outcome
            project = snapshot_at(root, initial["capture"])
        else:
            project = snapshot_at(root / "inputs", case["project_snapshot"])
        skills = None
        if cell["arm"] != "native":
            skills = snapshot_at(root / "inputs", plan["guidance_snapshots"][cell["arm"]])
        prompt = relative(private, case[f"{stage}_request"]).read_text(encoding="utf-8")
        write_json(directory / "claim.json", {"cell": cell["id"], "stage": stage,
                   "parent_sha256": project.sha256, "prompt_sha256": digest(prompt.encode()),
                   "guidance_sha256": skills.sha256 if skills else None})
        observed_runtime = observe_runtime(read_json(root / "inputs/runtime.json"), template_catalog)
        write_json(directory / "runtime-observation.json", observed_runtime)
        verify_inputs(root)
        result = execute(Request(Runtime(**plan["runtime"]), project, skills, prompt), directory / "application")
        outcome.update(state="attempted", native_state=result.state, native_valid=result.native_valid,
                       elapsed_s=result.elapsed_s, native_elapsed_s=result.native_elapsed_s, usage=result.usage,
                       application_receipt=Path(result.receipt).relative_to(root).as_posix())
        if result.capture is not None:
            with tempfile.TemporaryDirectory(prefix="parcel-") as temporary:
                replay(result.capture, Path(temporary) / "app")
            outcome["capture"] = {"directory": result.capture.directory.relative_to(root).as_posix(),
                                  "sha256": result.capture.sha256}
            verify_inputs(root)
            outcome["grade"] = grader(relative(private, case["oracle"]), result.capture, stage, directory / "acceptance")
        else:
            outcome["reason"] = "application returned no valid capture"
    except Exception as exc:
        outcome.update(state="incomplete", reason=f"{type(exc).__name__}: {exc}")
    write_json(directory / "outcome.json", outcome)
    return outcome


def run(root: Path, *, cell_id: str | None = None, limit: int | None = None, concurrency: int = 1,
        execute=run_application, grader=grade_capture, template_catalog=native_templates):
    root = root.resolve()
    with (root / "dispatch.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if concurrency not in (1, 2) or (limit is not None and limit <= 0):
            raise ValueError("concurrency must be one or two; limit must be positive")
        plan = verify_inputs(root)
        cells = plan["cells"]
        if cell_id is not None:
            cells = [cell for cell in cells if cell["id"] == cell_id]
            if not cells:
                raise ValueError("unknown planned cell")
        work = []
        for cell in cells:
            for stage in STAGES:
                slot = root / "lineages" / cell["id"] / stage
                if not slot.exists():
                    work.append((cell, stage))
        if limit is not None:
            work = work[:limit]
        groups = []
        for cell in cells:
            selected = [stage for selected_cell, stage in work if selected_cell == cell]
            if selected:
                groups.append((cell, selected))

        def lineage(group):
            cell, stages = group
            outcomes = []
            for stage in stages:
                try:
                    outcomes.append(run_stage(root, plan, cell, stage, execute=execute, grader=grader,
                                              template_catalog=template_catalog))
                except FileExistsError:
                    outcomes.append({"state": "spent"})
            return outcomes

        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            return list(pool.map(lineage, groups))


def duration(value):
    if value is None:
        return None
    try:
        if type(value) in (int, float) and math.isfinite(value) and value >= 0:
            return value
    except OverflowError:
        pass
    raise ValueError("duration must be null or a nonnegative finite number")


def validate_evidence(root: Path, plan: dict, cell: dict, stage: str, outcome: dict):
    capture, grade = outcome.get("capture"), outcome.get("grade")
    directory = root / "lineages" / cell["id"] / stage
    receipt = outcome.get("application_receipt")
    if receipt is None:
        if capture is not None or any(outcome.get(field) is not None for field in DURATIONS):
            raise ValueError("capture or duration lacks a retained application receipt")
        if (grade is not None or outcome.get("native_valid") is True
                or outcome.get("native_state") not in (None, "unknown", "unobserved")
                or outcome.get("usage") is not None):
            raise ValueError("native outcome, usage, or grade lacks a retained application receipt")
        return
    receipt_path = relative(root, receipt)
    if receipt_path != directory / "application/receipt.json":
        raise ValueError("application receipt is outside the planned stage")
    application = read_json(receipt_path)
    if not isinstance(application, dict):
        raise ValueError("application receipt must be an object")
    for field in DURATIONS:
        try:
            observed = duration(application.get(field))
        except ValueError as exc:
            raise ValueError(f"invalid application receipt {field}: {exc}") from exc
        if observed != outcome.get(field):
            raise ValueError(f"{field} disagrees with application receipt")
    if application.get("usage") != outcome.get("usage"):
        raise ValueError("usage disagrees with application receipt")
    if application["native_valid"] is not outcome["native_valid"] or application["state"] != outcome["native_state"]:
        raise ValueError("native outcome disagrees with application receipt")
    if outcome["native_valid"] is True and outcome["native_state"] != "completed":
        raise ValueError("native validity lacks completed state")
    claim = read_json(directory / "claim.json")
    if claim["cell"] != cell["id"] or claim["stage"] != stage:
        raise ValueError("claim does not bind the planned cell and stage")
    case = next(case for case in plan["cases"] if case["id"] == cell["case"])
    private = relative(root / "inputs", case["directory"])
    parent_sha256 = case["project_snapshot"]["sha256"]
    if stage == "maintenance":
        initial = read_json(directory.parent / "initial/outcome.json")
        if not isinstance(initial, dict) or not initial.get("capture"):
            raise ValueError("maintenance parent lacks a retained initial capture")
        validate_evidence(root, plan, cell, "initial", initial)
        parent_sha256 = initial["capture"]["sha256"]
    guidance_sha256 = None if cell["arm"] == "native" else plan["guidance_snapshots"][cell["arm"]]["sha256"]
    prompt = relative(private, case[f"{stage}_request"]).read_text(encoding="utf-8")
    for claim_key, spec_key, expected in (("parent_sha256", "project", parent_sha256),
                                          ("guidance_sha256", "skills", guidance_sha256),
                                          ("prompt_sha256", "prompt_sha256", digest(prompt.encode()))):
        if claim[claim_key] != expected:
            raise ValueError(f"claim {claim_key} disagrees with frozen stage inputs")
        if application["spec"][spec_key] != expected:
            raise ValueError(f"application receipt {spec_key} disagrees with frozen stage inputs")
    if application["spec"]["runtime"] != plan["runtime"]:
        raise ValueError("application receipt runtime disagrees with frozen plan")
    if capture is None:
        if grade is not None or outcome.get("native_valid") is True:
            raise ValueError("native completion or grade lacks a retained capture")
        return
    snapshot = snapshot_at(root, capture)
    if snapshot.directory.resolve() != (directory / "application/harvest/capture").resolve():
        raise ValueError("capture is outside the planned stage")
    with tempfile.TemporaryDirectory(prefix="port-evidence-") as temporary:
        replay(snapshot, Path(temporary) / "app")
    bound = application["capture"]
    if bound["sha256"] != snapshot.sha256 or Path(bound["directory"]).resolve() != snapshot.directory.resolve():
        raise ValueError("application receipt capture binding mismatch")
    if grade is None:
        return
    oracle = relative(private, case["oracle"])
    if (grade["stage"] != stage or grade["capture_sha256"] != snapshot.sha256
            or grade["oracle_sha256"] != digest(oracle.read_bytes())):
        raise ValueError("grade stage, capture, or oracle binding mismatch")
    if read_json(directory / "acceptance/receipt.json") != grade:
        raise ValueError("grade disagrees with retained acceptance receipt")
    if grade["state"] == "graded":
        fields = {key: grade[key] for key in ("passed", "assertions", "failures")}
        parsed = parse_grade((directory / "acceptance/oracle.stdout").read_bytes(), grade["returncode"])
        if parse_grade(json.dumps(fields).encode(), grade["returncode"]) != parsed:
            raise ValueError("grade disagrees with retained oracle output")
    elif grade["state"] != "oracle_error" or grade["passed"] is not None:
        raise ValueError("invalid grade state")


def report(root: Path):
    root = root.resolve()
    plan = read_json(root / "seal.json")["plan"]
    integrity = None
    try:
        verify_inputs(root)
    except (ValueError, OSError) as exc:
        integrity = str(exc)
    rows = []
    for cell in plan["cells"]:
        stages = {}
        for stage in STAGES:
            directory = root / "lineages" / cell["id"] / stage
            path = directory / "outcome.json"
            try:
                outcome = read_json(path) if path.exists() else {"state": "incomplete" if directory.exists() else "never_started"}
                if not isinstance(outcome, dict):
                    raise ValueError("outcome must be an object")
            except (OSError, ValueError) as exc:
                outcome = {"state": "incomplete", "evidence_error": f"unreadable outcome: {exc}"}
            invalid = []
            for field, fallback in (("state", "incomplete"), ("native_state", "unknown")):
                if (field == "state" or field in outcome) and (not isinstance(outcome.get(field), str) or not outcome[field]):
                    invalid.append(field)
                    outcome[field] = fallback
            if "native_valid" in outcome and type(outcome["native_valid"]) is not bool:
                invalid.append("native_valid")
                outcome["native_valid"] = False
            if outcome.get("usage") is not None and not isinstance(outcome["usage"], dict):
                invalid.append("usage")
                outcome["usage"] = None
            for field in DURATIONS:
                try:
                    outcome[field] = duration(outcome.get(field))
                except ValueError:
                    invalid.append(field)
                    outcome[field] = None
            if invalid:
                outcome["evidence_error"] = f"invalid outcome fields: {', '.join(invalid)}"
            try:
                validate_evidence(root, plan, cell, stage, outcome)
            except (ApplicationError, OSError, ValueError, KeyError, TypeError) as exc:
                outcome.setdefault("evidence_error", f"{type(exc).__name__}: {exc}")
            if "evidence_error" in outcome:
                outcome.update(native_state="unknown", native_valid=False, usage=None)
                for field in DURATIONS:
                    outcome[field] = None
            grade = outcome.get("grade") if isinstance(outcome.get("grade"), dict) else {}
            outcome["accepted"] = (integrity is None and "evidence_error" not in outcome
                                   and outcome.get("native_valid") is True
                                   and grade.get("state") == "graded" and grade.get("passed") is True)
            stages[stage] = outcome
        rows.append({**cell, **stages, "both_accepted": all(stages[stage]["accepted"] for stage in STAGES)})
    totals = {}
    for arm in ARMS:
        arm_rows = [row for row in rows if row["arm"] == arm]
        opportunities = [row[stage] for row in arm_rows for stage in STAGES]
        totals[arm] = {"planned_lineages": 6, "planned_opportunities": 12,
                       "accepted_initial": sum(row["initial"]["accepted"] for row in arm_rows),
                       "accepted_maintenance": sum(row["maintenance"]["accepted"] for row in arm_rows),
                       "accepted_both": sum(row["both_accepted"] for row in arm_rows),
                       "states": {state: sum(item["state"] == state for item in opportunities) for state in sorted({item["state"] for item in opportunities})},
                       "native_states": {state: sum(item.get("native_state", "unobserved") == state for item in opportunities) for state in sorted({item.get("native_state", "unobserved") for item in opportunities})},
                       "known_usage_opportunities": sum(item.get("usage") is not None for item in opportunities),
                       "unknown_usage_opportunities": sum(item.get("usage") is None for item in opportunities)}
        for field in DURATIONS:
            known = [item[field] for item in opportunities if item.get(field) is not None]
            totals[arm][field] = sum(known) if known else None
            totals[arm][f"known_{field}_opportunities"] = len(known)
            totals[arm][f"unknown_{field}_opportunities"] = len(opportunities) - len(known)
    pairs = [{"case": case["id"], "repetition": repetition,
              "arms": {row["arm"]: {stage: row[stage]["accepted"] for stage in STAGES} for row in rows if row["case"] == case["id"] and row["repetition"] == repetition}}
             for case in plan["cases"] for repetition in (1, 2)]
    result = {"planned_lineages": len(rows), "planned_opportunities": len(rows) * 2,
              "input_integrity_error": integrity, "totals": totals, "paired_outcomes": pairs,
              "rows": rows, "limitations": plan["limits"],
              "served_model": "unknown unless a native receipt records it", "discovery": "unmeasured; retained transcripts require separate exposure review"}
    write_json(root / "report.json", result)
    lines = ["# Port value comparison", "", plan["limits"], "", "All 18 planned lineages and 36 stage opportunities remain in the denominator.", "",
             "| Arm | Initial accepted / 6 | Maintenance accepted / 6 | Both accepted / 6 | Known usage / 12 |", "| --- | ---: | ---: | ---: | ---: |"]
    for arm, total in totals.items():
        lines.append(f"| {arm} | {total['accepted_initial']} | {total['accepted_maintenance']} | {total['accepted_both']} | {total['known_usage_opportunities']} |")
    lines += ["", "Durations sum only validated known measurements. A null sum means no measurement is known.", "",
              "| Arm | Native process seconds | Native known / 12 | Native unknown / 12 | Total seconds | Total known / 12 | Total unknown / 12 |",
              "| --- | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for arm, total in totals.items():
        lines.append(f"| {arm} | {total['native_elapsed_s']} | {total['known_native_elapsed_s_opportunities']} | {total['unknown_native_elapsed_s_opportunities']} | {total['elapsed_s']} | {total['known_elapsed_s_opportunities']} | {total['unknown_elapsed_s_opportunities']} |")
    lines += ["", "| Cell | Case | Rep | Arm | Initial | Maintenance | Both |", "| --- | --- | ---: | --- | --- | --- | --- |"]
    for row in rows:
        initial, maintenance = row["initial"], row["maintenance"]
        lines.append(f"| {row['id']} | {row['case']} | {row['repetition']} | {row['arm']} | {initial['state']}, accepted={initial['accepted']} | {maintenance['state']}, accepted={maintenance['accepted']} | {row['both_accepted']} |")
    if integrity:
        lines += ["", f"Input integrity failure: {integrity}"]
    evidence_errors = [(row["id"], stage, row[stage]["evidence_error"])
                       for row in rows for stage in STAGES if "evidence_error" in row[stage]]
    if evidence_errors:
        lines += ["", "Retained evidence errors invalidate acceptance for these stages.", ""]
        lines.extend(f"- {cell_id} {stage}: {error}" for cell_id, stage, error in evidence_errors)
    lines += ["", "Native validity, executable application grades, raw usage, native process duration, total elapsed time, and paired repetitions are separate fields in report.json.",
              "Requested README updates and broader task quality are unmeasured.",
              "Native duration covers the native process. Total elapsed time covers the application claim through sandbox cleanup and excludes acceptance grading.",
              "This paired sample has three tasks and two repetitions per arm. Remote inference capacity and its effect on concurrency are unmeasured.",
              "No winner or general performance or causal claim follows from this sample. Never-started and unknown measurements are not passes."]
    (root / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    prep = sub.add_parser("prepare")
    prep.add_argument("directory", type=Path)
    prep.add_argument("--cases", type=Path, default=ROOT / "cases")
    prep.add_argument("--runtime-receipt", type=Path, required=True)
    prep.add_argument("--model", required=True)
    prep.add_argument("--effort", required=True)
    prep.add_argument("--timeout", type=int, default=240)
    prep.add_argument("--seed", type=int, default=73129)
    execute = sub.add_parser("run")
    execute.add_argument("directory", type=Path)
    execute.add_argument("--cell")
    execute.add_argument("--limit", type=int)
    execute.add_argument("--concurrency", type=int, default=1, choices=(1, 2))
    inspect = sub.add_parser("report")
    inspect.add_argument("directory", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "prepare":
            result = prepare(args.directory, args.cases, args.runtime_receipt, model=args.model,
                             effort=args.effort, timeout_s=args.timeout, seed=args.seed)
            print(json.dumps({"planned_lineages": len(result["cells"]), "planned_opportunities": 36}))
        elif args.command == "run":
            run(args.directory, cell_id=args.cell, limit=args.limit, concurrency=args.concurrency)
            print(json.dumps(report(args.directory)["totals"], sort_keys=True))
        else:
            print(json.dumps(report(args.directory)["totals"], sort_keys=True))
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        parser.exit(1, f"{type(exc).__name__}: {exc}\n")


if __name__ == "__main__":
    main()
