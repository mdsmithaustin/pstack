#!/usr/bin/env python3
"""Freeze, collect, and assess six manually authorized current-Codex tasks."""
from __future__ import annotations

import argparse
import hashlib
import fcntl
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

from oracle import inspect_trace, unique_object

ROOT = Path(__file__).resolve().parent
DISABLED = ("apps", "plugins", "multi_agent", "goals", "hooks", "skill_search", "in_app_local_automation")
FORBIDDEN = ("eval", "test", "judge", "experiment", "rubric", "score", "compare", "benchmark", "candidate", "arena")
RUNTIMES = ("claude-code.md", "hermes.md", "grok.md", "other-runtime.md", "transcripts-claude-code.md", "transcripts-hermes.md", "transcripts-grok.md", "transcripts-other.md")


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique_object)


def write_json(path: Path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def now():
    return datetime.now(timezone.utc).isoformat()


def inventory(root: Path):
    result = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ValueError(f"symlink in workspace: {path}")
        if path.is_file():
            data = path.read_bytes()
            result[path.relative_to(root).as_posix()] = {"bytes": len(data), "sha256": digest(data)}
        elif not path.is_dir():
            raise ValueError(f"nonregular workspace entry: {path}")
    return result


def load_cases(path: Path):
    data = read_json(path)
    cases = data.get("cases", [])
    if data.get("version") != 1 or len(cases) != 6 or {c.get("label") for c in cases} != set("ABCDEF"):
        raise ValueError("contract requires exactly six unique cases A through F")
    if len({c["name"] for c in cases}) != 6:
        raise ValueError("workspace names must be unique")
    for case in cases:
        if not case["required"] or "SKILL.md" not in case["required"] or not case["prompt"]:
            raise ValueError("case requires an organic prompt and entry-file requirement")
        for value in (case["name"], case["prompt"], *case["fixtures"]):
            if any(re.search(rf"\b{word}", value, re.I) for word in FORBIDDEN):
                raise ValueError(f"introduced disclosure in {case['label']}")
    return cases


def cli_receipt(executable: Path, directory: Path):
    commands = [[str(executable), "--version"], [str(executable), "exec", "--help"],
                [str(executable), "-c", 'approval_policy="never"',
                 "features", "list", "--enable", "skip_host_skill_discovery"] +
                [part for feature in DISABLED for part in ("--disable", feature)]]
    receipts = []
    for index, argv in enumerate(commands):
        result = subprocess.run(argv, capture_output=True, timeout=30, check=False)
        (directory / f"native-{index}.stdout").write_bytes(result.stdout)
        (directory / f"native-{index}.stderr").write_bytes(result.stderr)
        receipts.append({"argv": argv, "cwd": str(Path.cwd()), "raw_returncode": result.returncode,
                         "stdout_sha256": digest(result.stdout), "stderr_sha256": digest(result.stderr),
                         "nonempty_work_count": len(result.stdout.splitlines()), "failure_signal": "nonzero exit or required native setting absent"})
        write_json(directory / "native-probes.json", receipts)
        if result.returncode:
            raise ValueError(f"native CLI capability check {index} exits {result.returncode}")
    help_text = (directory / "native-1.stdout").read_text()
    for flag in ("--ignore-user-config", "--ignore-rules", "--ephemeral", "--json", "--sandbox", "--output-last-message"):
        if flag not in help_text:
            raise ValueError(f"CLI help lacks {flag}")
    features = (directory / "native-2.stdout").read_text()
    for feature, expected in [(name, "false") for name in DISABLED] + [("skip_host_skill_discovery", "true")]:
        rows = [line.split() for line in features.splitlines() if line.split()[:1] == [feature]]
        if len(rows) != 1 or rows[0][-1] != expected:
            raise ValueError(f"CLI does not establish feature {feature}={expected}")
    return {"commands": receipts, "version": (directory / "native-0.stdout").read_text().strip(),
            "tool_inventory": "unknown", "provider_execution": "unknown"}


def argv_for(study: dict, case: dict, slot: Path):
    argv = [study["requested"]["executable"], "exec", "--json", "--ephemeral", "--ignore-user-config",
            "--ignore-rules", "--skip-git-repo-check", "--strict-config", "--sandbox", "read-only",
            "--model", study["requested"]["model"], "-c", f'model_reasoning_effort="{study["requested"]["effort"]}"',
            "-c", 'approval_policy="never"', "--enable", "skip_host_skill_discovery"]
    argv += [part for feature in DISABLED for part in ("--disable", feature)]
    return argv + ["--cd", case["workspace"], "--output-last-message", str(slot / "final.txt"), "-"]


def verify_study(directory: Path):
    raw = (directory / "frozen.json").read_bytes()
    if digest(raw) != (directory / "frozen.sha256").read_text().strip():
        raise ValueError("frozen contract hash mismatch")
    study = read_json(directory / "frozen.json")
    if study.get("version") != 1 or len(study.get("cases", [])) != 6 or {c["label"] for c in study["cases"]} != set("ABCDEF"):
        raise ValueError("frozen study requires six unique slots")
    for relative, expected in study["artifacts"].items():
        path = directory / relative
        if path.is_symlink() or digest(path.read_bytes()) != expected:
            raise ValueError(f"frozen artifact changed: {relative}")
    for case in study["cases"]:
        if inventory(directory / "packages" / case["label"]) != case["inventory"]:
            raise ValueError(f"frozen package changed: {case['label']}")
    return study


def freeze(source: Path, output: Path, executable: Path, model: str, effort: str):
    source, output, executable = source.resolve(), output.resolve(), executable.resolve()
    if output.exists() or not executable.is_file() or not os.access(executable, os.X_OK):
        raise ValueError("output must be new and executable must be an executable file")
    cases = load_cases(ROOT / "cases.json")
    rubric = read_json(ROOT / "rubric.json")
    calibration = calibrate()
    revision = subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"], text=True).strip()
    output.mkdir(parents=True)
    (output / "packages").mkdir()
    (output / "inputs").mkdir()
    (output / "slots").mkdir()
    shutil.copy2(ROOT / "cases.json", output / "cases.json")
    shutil.copy2(ROOT / "rubric.json", output / "rubric.json")
    shutil.copytree(ROOT / "calibration", output / "calibration")
    write_json(output / "calibration-result.json", calibration)
    native = cli_receipt(executable, output)
    catalog_path = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))) / "models_cache.json"
    native["model_catalog"] = {"basis": "local CLI cache only; invocation availability and provider identity remain unknown", "requested_model": model, "requested_effort": effort, "matching_entries": []}
    if catalog_path.is_file():
        catalog = read_json(catalog_path)
        native["model_catalog"]["matching_entries"] = [{"slug": entry.get("slug"), "supported_reasoning_levels": entry.get("supported_reasoning_levels")} for entry in catalog.get("models", []) if entry.get("slug") == model]
    neutral = Path(tempfile.mkdtemp(prefix="grove-")).resolve()
    if any(word in str(neutral).lower() for word in FORBIDDEN):
        raise ValueError("neutral workspace path contains study framing")
    source_paths = {}
    prepared, production_terms = [], []
    for case in cases:
        package = output / "packages" / case["label"]
        package.mkdir()
        skills = ["pstack-harness"] + case["support"]
        for skill in skills:
            prefix = f"skills/{skill}/"
            paths = subprocess.check_output(["git", "-C", str(source), "ls-tree", "-r", "--name-only", revision, "--", prefix], text=True).splitlines()
            if not paths:
                raise ValueError(f"missing source skill {skill}")
            for relative in paths:
                blob = subprocess.check_output(["git", "-C", str(source), "show", f"{revision}:{relative}"])
                destination = package / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(blob)
                source_paths[relative] = digest(blob)
                terms = [word for word in FORBIDDEN if re.search(rf"\b{word}", blob.decode("utf-8"), re.I)]
                if terms:
                    production_terms.append({"case": case["label"], "path": relative, "terms": terms, "sha256": digest(blob), "kind": "immutable production text"})
        for relative, value in case["fixtures"].items():
            path = package / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(value if isinstance(value, str) else json.dumps(value, indent=2) + "\n", encoding="utf-8")
        workspace = neutral / case["name"]
        shutil.copytree(package, workspace)
        prompt = "Read skills/pstack-harness/SKILL.md in full before handling this request. Use only the relevant installed instructions as the work needs them.\n\n" + case["prompt"] + "\n"
        (output / "inputs" / f"{case['label']}.txt").write_text(prompt, encoding="utf-8")
        required = ["skills/pstack-harness/" + name for name in case["required"]]
        forbidden = ["skills/pstack-harness/references/" + name for name in RUNTIMES]
        file_inventory = inventory(package)
        for path in file_inventory:
            if any(word in path.lower() for word in FORBIDDEN):
                raise ValueError(f"candidate-visible filename discloses framing: {path}")
        prepared.append({**case, "required": required, "forbidden": forbidden,
                         "workspace": str(workspace), "inventory": file_inventory})
    write_json(output / "production-terms.json", production_terms)
    write_json(output / "source-hashes.json", source_paths)
    write_json(output / "native.json", native)
    artifacts = {path.relative_to(output).as_posix(): digest(path.read_bytes()) for path in sorted(output.rglob("*")) if path.is_file() and "packages" not in path.relative_to(output).parts}
    study = {"version": 1, "created_at": now(), "source_revision": revision,
             "requested": {"executable": str(executable), "executable_sha256": digest(executable.read_bytes()), "model": model, "effort": effort, "timeout_seconds": 180},
             "native": native, "cases": prepared, "artifacts": artifacts,
             "implementation": {name: digest((ROOT / name).read_bytes()) for name in ("study.py", "oracle.py")},
             "limits": "six sampled current-tree tasks; no causal, token, quality, provider, or cross-runtime claim"}
    for case in prepared:
        case["planned_argv"] = argv_for(study, case, output / "slots" / case["label"])
    write_json(output / "frozen.json", study)
    (output / "frozen.sha256").write_text(digest((output / "frozen.json").read_bytes()) + "\n")
    return {"contract_sha256": digest((output / "frozen.json").read_bytes()), "labels": [c["label"] for c in prepared], "calibration": calibration, "directory": str(output)}


def kill_group(process):
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    process.wait(timeout=10)


def collect_slot(study: dict, directory: Path, case: dict, *, deadline_seconds=180):
    slot = directory / "slots" / case["label"]
    try:
        slot.mkdir()
    except FileExistsError:
        receipt_path = slot / "receipt.json"
        previous = read_json(receipt_path) if receipt_path.exists() else {}
        return {"label": case["label"], "state": "consumed", "launched": False,
                "previous_state": previous.get("state"), "raw_returncode": previous.get("raw_returncode"),
                "stop_wave": previous.get("stop_wave", False)}
    started = {"started_at": now(), "deadline_seconds": deadline_seconds, "label": case["label"]}
    write_json(slot / "started.json", started)
    workspace = Path(case["workspace"])
    actual_inventory = inventory(workspace)
    write_json(slot / "inventory-before.json", actual_inventory)
    if actual_inventory != case["inventory"]:
        write_json(slot / "receipt.json", {**started, "state": "invalid-input", "raw_returncode": None})
        return {"label": case["label"], "state": "invalid-input", "launched": False}
    stdin = (directory / "inputs" / f"{case['label']}.txt").read_bytes()
    (slot / "stdin.bin").write_bytes(stdin)
    argv = argv_for(study, case, slot)
    home = Path(tempfile.mkdtemp(prefix="leaf-"))
    codex_home = home / ".codex"
    codex_home.mkdir(mode=0o700)
    auth = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))) / "auth.json"
    if auth.is_file() and not auth.is_symlink():
        shutil.copyfile(auth, codex_home / "auth.json")
        (codex_home / "auth.json").chmod(0o600)
    env = {key: os.environ[key] for key in ("PATH", "LANG", "LC_ALL", "TMPDIR", "SSL_CERT_FILE", "SSL_CERT_DIR") if key in os.environ}
    env.update({"HOME": str(home), "CODEX_HOME": str(codex_home), "TERM": "dumb"})
    write_json(slot / "launch.json", {"argv": argv, "cwd": str(workspace), "environment_keys": sorted(env), "isolated_home": str(home), "auth_file_copied": (codex_home / "auth.json").is_file(), "stdin_sha256": digest(stdin)})
    process, state, code = None, "spawn-failed", None
    monotonic_start = time.monotonic()
    try:
        with (slot / "stream.jsonl").open("wb") as stdout, (slot / "stderr.bin").open("wb") as stderr:
            process = subprocess.Popen(argv, cwd=workspace, env=env, stdin=subprocess.PIPE, stdout=stdout, stderr=stderr, start_new_session=True)
            try:
                process.communicate(input=stdin, timeout=deadline_seconds)
                state = "completed"
            except subprocess.TimeoutExpired:
                state = "timeout"
                kill_group(process)
            except KeyboardInterrupt:
                state = "interrupted"
                kill_group(process)
            code = process.returncode
    except OSError as error:
        (slot / "spawn-error.txt").write_text(str(error))
    finally:
        if process is not None:
            kill_group(process)
        shutil.rmtree(home)
    for name in ("stream.jsonl", "stderr.bin", "final.txt"):
        if not (slot / name).exists():
            (slot / name).write_bytes(b"")
    after = inventory(workspace)
    write_json(slot / "inventory-after.json", after)
    receipt = {**started, "ended_at": now(), "elapsed_seconds": time.monotonic() - monotonic_start,
               "state": state, "raw_returncode": code, "requested": study["requested"],
               "runtime_reported": {"model": None, "effort": None, "basis": None}, "provider_execution": "unknown",
               "workspace_changed": after != actual_inventory,
               "artifacts": {name: {"bytes": (slot / name).stat().st_size, "sha256": digest((slot / name).read_bytes())} for name in ("stdin.bin", "stream.jsonl", "stderr.bin", "final.txt")}}
    trace = inspect_case(study, directory, case)
    runtime, usage = [], []
    from oracle import decode
    for entry in decode((slot / "stream.jsonl").read_bytes(), str(workspace)).records:
        record = entry["record"]
        if record.get("type") == "turn.completed" and isinstance(record.get("usage"), dict):
            usage.append({"line": entry["line"], "usage": record["usage"]})
        if record.get("type") == "session_meta" and isinstance(record.get("payload"), dict):
            payload = record["payload"]
            runtime.append({"line": entry["line"], "record": record})
            receipt["runtime_reported"] = {"model": payload.get("model") if isinstance(payload.get("model"), str) else None,
                                           "effort": payload.get("reasoning_effort") if isinstance(payload.get("reasoning_effort"), str) else None,
                                           "basis": {"file": "stream.jsonl", "line": entry["line"]}}
    write_json(slot / "runtime-records.json", runtime)
    receipt["usage"] = usage
    receipt["stop_wave"] = bool(trace["prohibited"] or receipt["workspace_changed"] or trace["context"]["exposures"] or state == "interrupted")
    write_json(slot / "receipt.json", receipt)
    return {"label": case["label"], "state": state, "raw_returncode": code, "launched": process is not None, "stop_wave": receipt["stop_wave"]}


def inspect_case(study, directory, case, decision=None):
    package = directory / "packages" / case["label"]
    files = {name: (package / name).read_bytes() for name in case["inventory"]}
    slot = directory / "slots" / case["label"]
    raw = (slot / "stream.jsonl").read_bytes() if (slot / "stream.jsonl").exists() else b""
    final = (slot / "final.txt").read_bytes() if (slot / "final.txt").exists() else b""
    rubric = read_json(directory / "rubric.json")
    private = [rubric["private_marker"]] + [criterion["pass"] for criterion in rubric["criteria"]]
    decision = decision or {}
    return inspect_trace(raw, final, Path(case["workspace"]), files, case["required"], case["forbidden"], private,
                         decision.get("first_committed_decision_line"), decision.get("earlier_action_line"))


def run(directory: Path, approved_contract: str):
    with (directory / "controller.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise ValueError("another controller owns this wave") from error
        return run_locked(directory, approved_contract)


def run_locked(directory: Path, approved_contract: str):
    study = verify_study(directory)
    if approved_contract != digest((directory / "frozen.json").read_bytes()):
        raise ValueError("explicit inspected contract digest is required")
    if digest(Path(study["requested"]["executable"]).read_bytes()) != study["requested"]["executable_sha256"]:
        raise ValueError("native executable changed after freeze")
    if any(digest((ROOT / name).read_bytes()) != expected for name, expected in study["implementation"].items()):
        raise ValueError("collector or oracle changed after freeze; inspect a new freeze before invocation")
    results = []
    for case in study["cases"]:
        verify_study(directory)
        result = collect_slot(study, directory, case)
        results.append(result)
        if result.get("stop_wave"):
            break
    for case in study["cases"][len(results):]:
        results.append({"label": case["label"], "state": "held-after-invalid-context", "launched": False})
    write_json(directory / "execution.json", results)
    return results


def assess(directory: Path, decisions_path: Path | None):
    study = verify_study(directory)
    decisions = read_json(decisions_path) if decisions_path else {}
    if decisions and set(decisions) != set("ABCDEF"):
        raise ValueError("semantic review must account for all six labels")
    report, packet = [], []
    rubric = read_json(directory / "rubric.json")
    for case in study["cases"]:
        result = inspect_case(study, directory, case, decisions.get(case["label"]))
        slot = directory / "slots" / case["label"]
        receipt = read_json(slot / "receipt.json") if (slot / "receipt.json").exists() else None
        if receipt:
            for name, expected in receipt.get("artifacts", {}).items():
                if digest((slot / name).read_bytes()) != expected["sha256"] or (slot / name).stat().st_size != expected["bytes"]:
                    raise ValueError(f"retained slot artifact changed: {case['label']}/{name}")
        result["label"] = case["label"]
        review = decisions.get(case["label"], {})
        semantic = review.get("safeguards")
        if semantic:
            if semantic.get("status") not in {"PASS", "FAIL", "INCONCLUSIVE"} or not isinstance(semantic.get("reasons"), list) or not semantic["reasons"]:
                raise ValueError("semantic safeguard verdict requires a status and reasons")
            result["semantic_safeguards"] = semantic
            if result["safeguards"]["status"] != "FAIL":
                result["safeguards"] = semantic
        first_exposure = result["context"]["first_exposure_line"]
        result["validity"] = {"blinded_context": "invalid after exposure" if first_exposure else "unverified" if result["context"]["coverage"] == "unverified" else "no exposure found within paired returned-content coverage",
                              "unsupported_later_observations": [o for o in result["observations"] if first_exposure and o["result_line"] >= first_exposure]}
        result["assessment_implementation"] = {name: digest((ROOT / name).read_bytes()) for name in ("study.py", "oracle.py")}
        result["invocation"] = receipt
        report.append(result)
        packet.append({"label": case["label"], "task": case["prompt"], "safeguards": case["safeguards"],
                       "statements": result["statements"], "actions": result["actions"],
                       "final": (slot / "final.txt").read_text() if (slot / "final.txt").exists() else ""})
    write_json(directory / "assessment.json", report)
    blinded = {"criteria": [c for c in rubric["criteria"] if c["name"] in {"task safeguards", "decision ordering", "observed context validity"}], "cases": packet,
               "instructions": "Read every assistant statement. Return first_committed_decision_line and optional earlier_action_line for each label, plus safeguards with status and reasons. Do not infer a tool's absence from a missing call. Preserve missing evidence. A greeting or intent to read is not a substantive decision."}
    packet_text = json.dumps(blinded, ensure_ascii=False, indent=2)
    for case in study["cases"]:
        packet_text = packet_text.replace(case["workspace"], "<workspace>")
    (directory / "semantic-packet.json").write_text(packet_text + "\n")
    return report


def calibrate():
    index = read_json(ROOT / "calibration" / "expected.json")
    if len(index) < 8:
        raise ValueError("calibration population is incomplete")
    results = []
    for item in index:
        result = inspect_trace((ROOT / "calibration" / item["trace"]).read_bytes(), item["final"].encode(),
                               Path("/grove/maple"), {"entry.md": b"first\nsecond\n", "foreign.md": b"remote\n"},
                               ["entry.md"], ["foreign.md"], ["parent-routing-criteria-6f82d1b9"], item.get("decision_line"))
        observed = {"reads": result["reads"]["status"], "routing": result["routing"]["status"], "exposure": result["context"]["first_exposure_line"]}
        if observed != item["expected"]:
            raise ValueError(f"calibration mismatch {item['id']}: {observed} != {item['expected']}")
        results.append({"id": item["id"], "expected": item["expected"], "observed": observed})
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    frozen = commands.add_parser("freeze")
    frozen.add_argument("--source", type=Path, required=True)
    frozen.add_argument("--out", type=Path, required=True)
    frozen.add_argument("--codex", type=Path, required=True)
    frozen.add_argument("--model", required=True)
    frozen.add_argument("--effort", choices=("low", "medium", "high", "xhigh", "max", "ultra"), required=True)
    collect = commands.add_parser("run")
    collect.add_argument("--study", type=Path, required=True)
    collect.add_argument("--approved-contract", required=True)
    grade = commands.add_parser("assess")
    grade.add_argument("--study", type=Path, required=True)
    grade.add_argument("--decisions", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "freeze":
            result = freeze(args.source, args.out, args.codex, args.model, args.effort)
        elif args.command == "run":
            result = run(args.study.resolve(), args.approved_contract)
        else:
            result = assess(args.study.resolve(), args.decisions)
        print(json.dumps(result, ensure_ascii=False))
        if args.command == "run" and any(r["state"] not in {"completed", "consumed"} or r.get("raw_returncode", 0) != 0 or r.get("stop_wave") for r in result):
            return 1
        return 0
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
