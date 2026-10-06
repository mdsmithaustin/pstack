from __future__ import annotations

import hashlib
import json
import re
import stat
from dataclasses import dataclass, replace
from pathlib import Path, PurePosixPath

PHASES = ("initial", "recovery", "refusal")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def unique_object(pairs):
    value = {}
    for key, item in pairs:
        require(key not in value, f"duplicate JSON key {key}")
        value[key] = item
    return value


def parse_json(content: bytes | str):
    def invalid_constant(value):
        raise ValueError(f"non-finite JSON value {value}")
    return json.loads(content, object_pairs_hook=unique_object, parse_constant=invalid_constant)


def raw(file: Path) -> bytes:
    for component in (file, *file.parents):
        require(not component.is_symlink(), f"evidence symlink {component}")
    require(stat.S_ISREG(file.stat().st_mode), f"evidence is not a regular file {file}")
    return file.read_bytes()


def load(file: Path):
    return parse_json(raw(file))


def sha(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def relative(value: str) -> str:
    require(isinstance(value, str) and value and "\\" not in value, "invalid snapshot path")
    name = PurePosixPath(value)
    require(not name.is_absolute() and all(part not in {"", ".", ".."} for part in value.split("/")), f"unsafe snapshot path {value}")
    return value


@dataclass(frozen=True)
class File:
    content: bytes
    executable: bool


@dataclass(frozen=True)
class Link:
    target: str


Snapshot = dict[str, File | Link]


def snapshot(directory: Path) -> Snapshot:
    manifest = load(directory / "files.json")
    require(isinstance(manifest, dict), "snapshot manifest must be an object")
    result = {}
    for name, entry in manifest.items():
        relative(name)
        require(isinstance(entry, dict), f"invalid snapshot entry {name}")
        if entry.get("kind") == "symlink":
            require(set(entry) == {"kind", "target"} and isinstance(entry["target"], str), f"invalid symlink entry {name}")
            result[name] = Link(entry["target"])
        else:
            require(set(entry) == {"kind", "sha256", "size", "executable", "blob"} and entry["kind"] == "file", f"invalid file entry {name}")
            require(isinstance(entry["sha256"], str) and re.fullmatch(r"[0-9a-f]{64}", entry["sha256"]) is not None, f"malformed blob hash {name}")
            require(entry["blob"] == entry["sha256"], f"unsafe blob identity {name}")
            require(type(entry["size"]) is int and entry["size"] >= 0 and type(entry["executable"]) is bool, f"invalid blob metadata {name}")
            content = raw(directory / entry["blob"])
            require(sha(content) == entry["sha256"] and len(content) == entry["size"], f"blob hash or size mismatch {name}")
            result[name] = File(content, entry["executable"])
    return result


@dataclass(frozen=True)
class PermissionDenial:
    tool_name: str
    decision_reason_type: str
    decision_reason: str


@dataclass(frozen=True)
class Operation:
    call_id: str
    target: str | None
    content: str | None
    command: str | None
    outcome: str
    output: str
    permission_denial: PermissionDenial | None = None
    tool_name: str | None = None


@dataclass(frozen=True)
class Trace:
    session: str | None
    served_models: tuple[str, ...]
    permission_mode: str | None
    operations: tuple[Operation, ...]
    terminal: bool
    gaps: tuple[str, ...]
    cli_version: str | None = None


def literal_write(command: str) -> tuple[str | None, str | None]:
    match = re.fullmatch(
        r'''printf[ \t]+(?:%s|'%s'|"%s")[ \t]+(?:'([^']*)'|([A-Za-z0-9_./:-]+))[ \t]*>[ \t]*(?:'([A-Za-z0-9_./-]+)'|([A-Za-z0-9_./-]+))''',
        command.strip())
    if match:
        return match[3] or match[4], match[1] if match[1] is not None else match[2]
    return None, None


def tool_text(value) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list) and all(isinstance(part, dict) and part.get("type") == "text" and isinstance(part.get("text"), str) for part in value):
        return "\n".join(part["text"] for part in value)
    return ""


def trace(content: bytes, agent: str, workspace: str) -> Trace:
    try:
        rows = [parse_json(line) for line in content.decode("utf-8").splitlines() if line.strip()]
    except (ValueError, UnicodeError):
        return Trace(None, (), None, (), False, ("raw trace is incomplete or malformed",))
    require(all(isinstance(row, dict) for row in rows), "trace records must be objects")
    calls, completed, operations = {}, set(), []
    sessions, models, permissions, versions = [], set(), [], []
    terminal = False
    gaps = []
    if agent == "codex":
        active = False
        for row in rows:
            kind = row.get("type")
            if kind == "thread.started":
                sessions.append(row.get("thread_id"))
            if kind == "turn.started":
                active = len(sessions) == 1 and not terminal
            if kind == "turn.completed":
                require(not terminal, "duplicate Codex terminal event")
                terminal = True
            if kind in {"turn.failed", "error"}:
                gaps.append("native Codex trace reports failure")
            if kind in {"turn.started", "item.started", "item.updated", "item.completed"}:
                require(not terminal, "Codex content after terminal event")
            if kind not in {"item.started", "item.completed"}:
                continue
            item = row.get("item", {})
            if item.get("type") != "command_execution":
                continue
            if not active:
                gaps.append("command event has no active native turn")
                continue
            key = item.get("id")
            require(isinstance(key, str) and key and key not in completed, "ambiguous Codex operation id")
            if kind == "item.started":
                require(key not in calls, "duplicate Codex operation")
                calls[key] = item
            else:
                start = calls.pop(key, None)
                if start is None:
                    continue
                command = start.get("command")
                require(isinstance(command, str) and item.get("command", command) == command, "Codex operation changed command")
                status, exit_code = item.get("status"), item.get("exit_code")
                output = item.get("aggregated_output", "")
                require(isinstance(output, str), "invalid Codex operation output")
                outcome = "success" if status == "completed" and type(exit_code) is int and exit_code == 0 else "error" if status == "failed" and type(exit_code) is int and exit_code != 0 else "unknown"
                target, written = literal_write(command)
                operations.append(Operation(key, target, written, command, outcome, output))
                completed.add(key)
        for key, item in calls.items():
            command = item.get("command")
            if isinstance(command, str):
                target, written = literal_write(command)
                operations.append(Operation(key, target, written, command, "pending", ""))
    else:
        main = [row for row in rows if row.get("parent_tool_use_id") is None and row.get("isSynthetic") is not True]
        denials, terminal_denials = {}, []
        for row in main:
            kind = row.get("type")
            if kind == "system" and row.get("subtype") == "init":
                sessions.append(row.get("session_id"))
                if row.get("cwd") != workspace:
                    gaps.append("native cwd differs from client cwd; canonical workspace identity is unproven")
                if isinstance(row.get("permissionMode"), str):
                    permissions.append(row["permissionMode"])
                if isinstance(row.get("claude_code_version"), str) and row["claude_code_version"].strip():
                    versions.append(row["claude_code_version"])
                    require(len(set(versions)) == 1, "contradictory native CLI versions")
            if kind == "system" and row.get("subtype") == "permission_denied":
                require(not terminal, "Claude permission denial after terminal event")
                require(len(sessions) == 1 and row.get("session_id") == sessions[0], "Claude permission denial session mismatch")
                key = row.get("tool_use_id")
                call = calls.get(key) if isinstance(key, str) else None
                if call is not None and call.get("name") == row.get("tool_name") == "Write":
                    require(key not in denials, "duplicate Claude permission denial")
                    denials[key] = (call, row)
            if kind == "result":
                require(not terminal, "duplicate Claude terminal event")
                require(len(sessions) == 1 and row.get("session_id") == sessions[0], "Claude terminal session mismatch")
                terminal = True
                terminal_denials = row.get("permission_denials", [])
                if not isinstance(terminal_denials, list):
                    terminal_denials = []
                if row.get("is_error") is not False or row.get("subtype") != "success":
                    gaps.append("native Claude terminal result is not successful")
            elif kind in {"assistant", "user", "stream_event"}:
                require(not terminal, "Claude content after terminal event")
            if kind not in {"assistant", "user"}:
                continue
            require(len(sessions) == 1 and row.get("session_id") == sessions[0], "Claude tool or message session mismatch")
            message = row.get("message", {})
            if kind == "assistant" and isinstance(message.get("model"), str):
                models.add(message["model"])
            for item in message.get("content", []):
                if not isinstance(item, dict):
                    continue
                if kind == "assistant" and item.get("type") == "tool_use":
                    key = item.get("id")
                    require(isinstance(key, str) and key and key not in calls and key not in completed, "ambiguous Claude tool id")
                    calls[key] = item
                elif kind == "user" and item.get("type") == "tool_result":
                    key = item.get("tool_use_id")
                    require(key not in completed, "duplicate Claude tool result")
                    call = calls.pop(key, None)
                    if call is None:
                        continue
                    # The harness normalizer treats omitted SDK is_error as a completed non-error result.
                    error = item.get("is_error", False)
                    outcome = "error" if error is True else "success" if error is False else "unknown"
                    if not isinstance(item.get("content"), (str, list)):
                        outcome = "unknown"
                    operations.append(claude_operation(call, outcome, tool_text(item.get("content"))))
                    completed.add(key)
        operations.extend(claude_operation(call, "pending", "") for call in calls.values())
        for index, operation in enumerate(operations):
            pair = denials.get(operation.call_id)
            if pair is None or operation.outcome != "error":
                continue
            call, denial = pair
            reason_type, reason = denial.get("decision_reason_type"), denial.get("decision_reason")
            if reason_type != "workingDir" or reason != "Path is outside allowed working directories":
                continue
            if not operation.output or denial.get("message") != operation.output:
                continue
            matching = [item for item in terminal_denials if isinstance(item, dict) and item.get("tool_use_id") == operation.call_id]
            if len(matching) == 1 and matching[0].get("tool_name") == call["name"] and matching[0].get("tool_input") == call.get("input"):
                operations[index] = replace(operation, permission_denial=PermissionDenial(call["name"], reason_type, reason))
    require(len(sessions) <= 1 and all(isinstance(value, str) and value for value in sessions), "no unique native session id")
    require(len(set(permissions)) <= 1, "contradictory Claude permission modes")
    session = sessions[0] if sessions else None
    for row in rows:
        if row.get("parent_tool_use_id") is None and row.get("session_id") is not None and session is not None:
            require(row["session_id"] == session, "trace session mismatch")
    if session is None:
        gaps.append("native session identity is absent")
    return Trace(session, tuple(sorted(models)), permissions[0] if permissions else None, tuple(operations), terminal, tuple(gaps), versions[0] if versions else None)


def claude_operation(call: dict, outcome: str, output: str) -> Operation:
    arguments = call.get("input", {})
    target, content, command = None, None, None
    if call.get("name") == "Write":
        target, content = arguments.get("file_path"), arguments.get("content")
    elif call.get("name") == "Bash" and isinstance(arguments.get("command"), str):
        command = arguments["command"]
        target, content = literal_write(command)
    return Operation(call["id"], target if isinstance(target, str) else None, content if isinstance(content, str) else None, command, outcome, output, tool_name=call.get("name"))


@dataclass(frozen=True)
class Process:
    pid: int
    state: str
    stopped: bool


@dataclass(frozen=True)
class Phase:
    name: str
    process: Process
    argv: tuple[str, ...]
    executable_sha256: str | None
    before: Snapshot
    after: Snapshot
    trace: Trace


@dataclass(frozen=True)
class RunnerEvidence:
    fixture: Snapshot | None
    final: Snapshot | None
    phases: tuple[Phase, ...]
    workspace: str | None
    gaps: tuple[str, ...]


def read_case(base: Path, row: dict, agent: str, expected_prompt: str) -> RunnerEvidence:
    record_file = base / "recovery.json"
    if not record_file.exists():
        return RunnerEvidence(None, None, (), None, ("runner capture is absent",))
    record = load(record_file)
    require(type(record.get("schema_version")) is int and record["schema_version"] == 1, "unknown recovery schema")
    require(all(record.get(field) is None for field in ("runtime_model", "runtime_effort", "certificate", "trace_checkpoint_correlation", "enforcing_denial")), "unsupported producer certification or runtime claim")
    workspace = record.get("workspace")
    require(isinstance(workspace, str) and Path(workspace).is_absolute(), "runner workspace is absent")
    require(record["case"] == row["recovery"], "runner recovery case differs from prepared row")
    require(record["requested_model"] == row["model"], "runner requested model mismatch")
    phases = record.get("phases")
    require(isinstance(phases, list) and [item["phase"] for item in phases] == list(PHASES[:len(phases)]), "invalid fixed phase order")
    evidence = base / "recovery"
    require(raw(evidence / "expected-checkpoint.bin") == row["recovery"]["expected_content"].encode(), "expected checkpoint bytes changed")
    gaps = []
    snapshots = {}
    for name in ("fixture", "final"):
        if (evidence / name / "files.json").exists():
            snapshots[name] = snapshot(evidence / name)
        else:
            gaps.append(name + " snapshot is absent")
    result = []
    for item in phases:
        name = item["phase"]
        directory = evidence / name
        required = ("prompt.bin", "invocation.json", "process.json", "stdout.bin", "stderr.bin", "before/files.json", "after/files.json")
        if any(not (directory / file).exists() for file in required):
            gaps.append(name + " phase evidence is incomplete")
            continue
        process = load(directory / "process.json")
        require(item.get("adapter_environment", {}).get("recovery_process") == process, name + " process facts disagree with adapter record")
        require(item["state"] == process["state"] and item["compatibility_returncode"] == process["compatibility_returncode"], name + " process summary mismatch")
        require(type(process["pid"]) is int and process["pid"] > 0 and process["process_group"] == process["pid"], name + " invalid process identity")
        require(type(process["process_group"]) is int and type(process["os_returncode"]) is int and type(process["compatibility_returncode"]) is int, name + " invalid process status")
        stream = raw(directory / "stdout.bin")
        stderr = raw(directory / "stderr.bin")
        for file, content in (("stdout.bin", stream), ("stderr.bin", stderr)):
            require(process["raw_files_present"].get(file) is True and process["raw_sha256"].get(file) == sha(content), name + " raw hash mismatch")
        prompt = raw(directory / "prompt.bin")
        expected = expected_prompt if name == "initial" else row["recovery"][name + "_prompt"]
        require(prompt == expected.encode() and item["prompt_sha256"] == sha(prompt), name + " prompt mismatch")
        invocation = load(directory / "invocation.json")
        require(invocation.get("version") is None and invocation.get("effective_exec_argv") is None, "unsupported wrapper runtime claim")
        require(invocation["cwd"] == workspace, name + " client workspace mismatch")
        argv = invocation.get("client_argv")
        require(isinstance(argv, list) and argv and all(isinstance(part, str) for part in argv), name + " invalid client argv")
        executable_hash = invocation.get("executable_sha256")
        require(executable_hash is None or isinstance(executable_hash, str) and re.fullmatch(r"[0-9a-f]{64}", executable_hash) is not None, name + " malformed executable hash")
        state = "checkpoint_stop" if name == "initial" else "complete"
        stopped = all(process.get(fact) is True for fact in ("leader_reaped", "pipes_drained", "group_stopped"))
        stopped = stopped and process["state"] == state and process.get("error") is None
        if name == "initial":
            stopped = stopped and process["os_returncode"] in {-15, -9} and process["signal_sent"] == 15 and process["checkpoint_observed_live"] is True
            observed_file = directory / "checkpoint-observed.bin"
            if observed_file.exists():
                observed = raw(observed_file)
                require(process["checkpoint_sha256"] == sha(observed), "observed checkpoint hash mismatch")
            else:
                stopped = False
        else:
            stopped = stopped and process["os_returncode"] == 0 and process["signal_sent"] is None and item.get("outcome") == "Completed"
        parsed = trace(stream, agent, workspace)
        gaps.extend(name + ": " + gap for gap in parsed.gaps)
        before, after = snapshot(directory / "before"), snapshot(directory / "after")
        require(type(item.get("forbidden_path_present")) is bool and item["forbidden_path_present"] == (row["recovery"]["forbidden_path"] in after), name + " forbidden sentinel summary mismatch")
        result.append(Phase(name, Process(process["pid"], process["state"], stopped), tuple(argv), executable_hash, before, after, parsed))
        if not stopped:
            gaps.append(name + " process lifecycle is unproven")
        if parsed.terminal != (name != "initial"):
            gaps.append(name + " terminal event contradicts the required lifecycle")
    require(len({phase.process.pid for phase in result}) == len(result), "phases reused a process id")
    sessions = [phase.trace.session for phase in result if phase.trace.session is not None]
    require(len(set(sessions)) == len(sessions), "phases reused a session")
    versions = {phase.trace.cli_version for phase in result if phase.trace.cli_version is not None}
    require(len(versions) <= 1, "contradictory native CLI versions across phases")
    if len(result) != 3:
        gaps.append("the fixed initial/recovery/refusal evidence is incomplete")
    if record.get("status") != "complete" or record.get("failure") is not None:
        gaps.append("runner lifecycle failed: " + str(record.get("failure")))
    return RunnerEvidence(snapshots.get("fixture"), snapshots.get("final"), tuple(result), workspace, tuple(gaps))


def hash_json(value: object) -> str:
    return "sha256:" + sha(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode())


def validate_design(runs: Path, row: dict, inputs: dict[str, bytes], effort: str, agent: str) -> None:
    common = {key: row[key] for key in ("case_id", "split", "kind", "skill_name", "repo_root", "input_files", "prompt", "tags", "recovery")}
    case_input = {"schema_version": 1, **common, "turns": []}
    treatment = {"schema_version": 2, **common, "model": row["model"], "variant": row["variant"], "skill_paths": [], "skill_root_keys": [], "skill_tree_hash": None, "ablation": None, "instruction": row["instruction"], "turns": [], "answer_key": None}
    tree = sha(b"".join(PurePosixPath(name).name.encode() + b"\0" + content for name, content in sorted(inputs.items())))
    identity = {"case_id": row["case_id"], "model": row["model"], "variant": row["variant"], "run_number": row["run_number"], "run_dir": row["run_dir"],
                "task_sha256": hash_json(treatment), "case_input_sha256": hash_json(case_input), "instruction_sha256": hash_json({"instruction": row["instruction"]}), "planned_skill_tree_hash": None, "fixture_tree_hash": tree}
    payload = {"schema_version": 2, "population": "answer", "eval_contract_sha256": row["eval_contract_sha256"], "identities": [identity]}
    require(load(runs / "answer-design.json") == {**payload, "design_sha256": hash_json(payload)}, "retained answer design fingerprint differs from prepared case")
    record = load(runs / row["run_dir"] / "recovery.json")
    require(record["requested_effort"] == effort, "runner requested effort mismatch")
    expected = {"population": "answer", "case_id": row["case_id"], "run_number": 1, "variant": "without_skill", "billing_scope": "run", "answer_design_sha256": hash_json(payload), "answer_task_sha256": identity["task_sha256"], "answer_instruction_sha256": identity["instruction_sha256"], "effort": {"requested": effort, "applied_by": "codex -c model_reasoning_effort" if agent == "codex" else "claude --effort"}}
    require(record["provenance"] == expected, "runner prepared/design provenance mismatch")
    require(record["workspace_attestation"] == {"fixture_tree_hash": tree, "mounted_skill_tree_hash": None}, "runner fixture attestation mismatch")
