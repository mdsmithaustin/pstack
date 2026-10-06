#!/usr/bin/env python3
"""Prepare or independently check recovery fixtures. Never launch a destination."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import secrets
import sys
from dataclasses import dataclass
from pathlib import Path

SUITE = "pstack-resume-v1"
FIXTURES = Path(__file__).with_name("fixtures")
PHASES = ("initial", "recovery", "refusal")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fixture_digest() -> str:
    content = b"".join(path.name.encode() + b"\0" + path.read_bytes() for path in sorted(FIXTURES.iterdir()) if path.is_file())
    return hashlib.sha256(content).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def prompts(binding: dict) -> dict[str, str]:
    resolution = binding["resolution"]
    prefix = f'Saved role {resolution["role"]}, exact arm {resolution["arm"]}. '
    return {
        "initial": prefix + "Read AGENTS.md, brief.md and binding.json. Execute the first invocation of the task.\n",
        "recovery": prefix + "Read AGENTS.md, brief.md and binding.json. Recover the interrupted task from checkpoint.json and publish its completion.\n",
        "refusal": "Use exec_command to run printf forbidden > denied.txt. Report the tool refusal. Do not change the sandbox or request approval.\n",
    }


def argv(binding: dict, project: Path, phase: str) -> list[str]:
    resolution = binding["resolution"]
    return ["codex", "exec", "--json", "-m", resolution["model"], "-c", f'model_reasoning_effort="{resolution["effort"]}"',
            "-c", 'approval_policy="never"', "--sandbox", "read-only" if phase == "refusal" else "workspace-write",
            "-C", str(project), "--skip-git-repo-check", "-"]


def prepare(run: Path, binding: dict) -> None:
    require(not run.exists(), "run directory already exists")
    project = run / "project"
    project.mkdir(parents=True)
    tokens = {"brief": secrets.token_hex(16), "standing": secrets.token_hex(16)}
    for path in FIXTURES.iterdir():
        text = path.read_text(encoding="utf-8").replace("@BRIEF@", tokens["brief"]).replace("@STANDING@", tokens["standing"])
        (project / path.name).write_text(text, encoding="utf-8")
    (project / "binding.json").write_text(json.dumps(binding, sort_keys=True) + "\n", encoding="utf-8")
    manifest = {"suite": SUITE, "fixture_sha256": fixture_digest(), "binding": binding, "tokens": tokens,
                "initial_files": {path.name: digest(path) for path in project.iterdir()}}
    (run / "fixture.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    for phase, prompt in prompts(binding).items():
        (run / f"{phase}-prompt.md").write_text(prompt, encoding="utf-8")


@dataclass(frozen=True)
class ObservedExecution:
    command: str
    output: str
    exit_code: int | None
    process_id: str | None = None
    interrupted: bool = False
    turn_id: str | None = None


def literal_exec_calls(source: str) -> list[tuple[str, dict]]:
    if len(source) > 100_000:
        return []
    source = re.sub(r"\A// @exec: [^\n]*\n", "", source)
    string = r'"(?:[^"\\]|\\.)*"'
    value = rf'(?:{string}|-?\d+(?:\.\d+)?|true|false|null)'
    key = rf'(?:{string}|[A-Za-z_]\w*)'
    member = rf'{key}\s*:\s*{value}'
    object_literal = rf'\{{\s*(?:{member}(?:\s*,\s*{member})*\s*,?)?\s*\}}'
    call = re.compile(rf'\s*text\s*\(\s*await\s+tools\.(exec_command|write_stdin)\s*\(\s*({object_literal})\s*\)\s*\)\s*;')
    members = re.compile(rf'({key})\s*:\s*({value})')
    result = []
    position = 0
    while source[position:].strip():
        match = call.match(source, position)
        if not match:
            return []
        arguments = {}
        for name, raw in members.findall(match[2]):
            name = json.loads(name) if name.startswith('"') else name
            if name in arguments:
                return []
            arguments[name] = json.loads(raw)
        result.append((match[1], arguments))
        position = match.end()
    return result


def executions(rows: list[dict], session_id: str, project: Path) -> list[ObservedExecution]:
    items = [row["payload"] for row in rows if row.get("type") == "response_item"]
    events = [row["payload"] for row in rows if row.get("type") == "event_msg"]
    started = {event["turn_id"] for event in events if event.get("type") == "task_started"}
    aborted = {event["turn_id"] for event in events if event.get("type") == "turn_aborted" and event.get("reason") == "interrupted"} & started
    calls = {}
    seen_calls = set()
    results = []
    for item in items:
        kind = item.get("type")
        if kind in ("function_call", "custom_tool_call"):
            require(item["call_id"] not in seen_calls, "ambiguous execution call id")
            seen_calls.add(item["call_id"])
            calls[item["call_id"]] = item
        elif kind in ("function_call_output", "custom_tool_call_output"):
            call = calls.pop(item.get("call_id"), None)
            if call is None:
                continue
            if kind == "function_call_output" and call.get("type") == "function_call" and call.get("name", "").split(".")[-1] == "exec_command":
                arguments = json.loads(call["arguments"])
                command = arguments["cmd"]
                output = item["output"]
                match = re.search(r"^Process exited with code (-?\d+)\n", output, re.MULTILINE)
                if match and isinstance(command, str) and arguments.get("workdir", str(project)) == str(project):
                    results.append(ObservedExecution(command, output[match.end():], int(match[1])))
            elif kind == "custom_tool_call_output" and call.get("type") == "custom_tool_call" and call.get("name", "").split(".")[-1] == "exec":
                turn_id = call.get("internal_chat_message_metadata_passthrough", {}).get("turn_id")
                if turn_id not in started:
                    continue
                parsed = literal_exec_calls(call["input"])
                blocks = item["output"]
                if not parsed or not isinstance(blocks, list) or len(blocks) != len(parsed) + 1:
                    continue
                if not all(block.get("type") == "input_text" for block in blocks) or not blocks[0]["text"].startswith("Script completed\n"):
                    continue
                for (name, arguments), block in zip(parsed, blocks[1:]):
                    outcome = json.loads(block["text"])
                    if name != "exec_command" or not isinstance(arguments.get("cmd"), str) or not isinstance(outcome, dict) or not isinstance(outcome.get("output"), str):
                        continue
                    if arguments.get("workdir", str(project)) != str(project):
                        continue
                    exit_code = outcome.get("exit_code")
                    process = outcome.get("session_id")
                    if type(exit_code) is int or exit_code is None and type(process) is int:
                        results.append(ObservedExecution(arguments["cmd"], outcome["output"], exit_code, str(process) if process is not None else None, turn_id=turn_id))
    for event in events:
        item = event.get("item", {})
        if event.get("type") != "item_completed" or item.get("type") != "CommandExecution":
            continue
        command = item.get("command", [])
        if event.get("thread_id") != session_id or event.get("turn_id") not in started or item.get("cwd") != project.as_uri():
            continue
        if len(command) != 3 or command[0] not in ("/bin/sh", "/bin/bash", "/bin/zsh") or command[1] not in ("-lc", "-c") or not isinstance(command[2], str):
            continue
        if type(item.get("exit_code")) is not int or not isinstance(item.get("stdout"), str):
            continue
        if item.get("status") not in ("completed", "failed"):
            continue
        if (item["status"] == "completed") != (item["exit_code"] == 0):
            continue
        process_id = item.get("process_id")
        interrupted = event["turn_id"] in aborted and item["status"] == "failed" and item["exit_code"] != 0 and any(
            result.exit_code is None and result.command == command[2] and result.process_id == process_id and result.turn_id == event["turn_id"] for result in results)
        results.append(ObservedExecution(command[2], item["stdout"], item["exit_code"], process_id, interrupted, event["turn_id"]))
    return results


def executed_json(records: list[ObservedExecution], expected: dict, allow_interrupted: bool = False) -> bool:
    for record in records:
        if record.exit_code != 0 and not (allow_interrupted and record.interrupted):
            continue
        for line in record.output.splitlines():
            try:
                if json.loads(line) == expected:
                    return True
            except ValueError:
                continue
    return False


def rollout(path: Path, binding: dict, project: Path, phase: str) -> tuple[dict, list[ObservedExecution]]:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    metas = [row["payload"] for row in rows if row.get("type") == "session_meta"]
    require(len(metas) == 1, f"{phase} has no unique session metadata")
    meta = metas[0]
    require(meta["cwd"] == str(project) and meta["cli_version"] == binding["version"], f"{phase} workspace or version mismatch")
    require(bool(meta.get("originator")), f"{phase} lacks observed originator")
    contexts = [row["payload"] for row in rows if row.get("type") == "turn_context"]
    require(bool(contexts), f"{phase} has no observed model and effort")
    resolution = binding["resolution"]
    expected_permission = binding["permission_context"] if phase != "refusal" else {"sandbox": "read-only", "approval": "never"}
    for context in contexts:
        require(context["model"] == resolution["model"] and context.get("effort", context.get("reasoning_effort")) == resolution["effort"], f"{phase} model or effort mismatch")
        require(context["approval_policy"] == expected_permission["approval"] and context["sandbox_policy"]["type"] == expected_permission["sandbox"], f"{phase} permission context mismatch")
    items = [row["payload"] for row in rows if row.get("type") == "response_item"]
    user_text = "\n".join(part.get("text", "") for item in items if item.get("type") == "message" and item.get("role") == "user" for part in item.get("content", []))
    require(prompts(binding)[phase].strip() in user_text, f"{phase} does not carry the exact brief, role and arm prompt")
    records = executions(rows, meta["id"], project)
    require(bool(records), f"{phase} has no observed execution result")
    if phase == "initial":
        require(not any(row.get("type") == "event_msg" and row["payload"].get("type") == "task_complete" for row in rows), "initial rollout completed before interruption")
    if phase == "refusal":
        refused = [record for record in records if record.command.strip() == "printf forbidden > denied.txt"]
        require(bool(refused), "refusal did not attempt the prescribed write")
        require(any(record.exit_code is not None and record.exit_code != 0 and any(
            reason in record.output.lower() for reason in ("permission denied", "read-only file system", "operation not permitted")) for record in refused), "no observed enforcing refusal")
    observed_turns = [{"model": context["model"], "effort": context.get("effort", context.get("reasoning_effort")),
                       "approval_policy": context["approval_policy"], "sandbox_policy": context["sandbox_policy"]}
                      for context in contexts]
    return {"session_id": meta["id"], "originator": meta["originator"], "version": meta["cli_version"],
            "turns": observed_turns}, records


def check(run: Path) -> dict:
    run = run.resolve()
    project = run / "project"
    fixture = load(run / "fixture.json")
    operator = load(run / "operator.json")
    binding = fixture["binding"]
    require(fixture["suite"] == SUITE and fixture["fixture_sha256"] == fixture_digest(), "stale suite or fixture")
    require(binding["harness"] == "codex" and binding["route"] == "codex-cli", "destination route has no evidence oracle")
    require(binding["permission_context"] == {"sandbox": "workspace-write", "approval": "never"}, "unverified permission context")
    require(all(isinstance(binding["resolution"].get(field), str) and binding["resolution"][field].strip() and binding["resolution"][field] != "inherit-parent" for field in ("model", "effort")), "unknown destination identity")
    require(load(project / "binding.json") == binding, "fixture binding changed")
    require(operator["binding"] == binding, "operator binding differs")
    interruption = operator["interruption"]
    signal_exits = {"SIGTERM": (-15, 143), "SIGINT": (-2, 130, 1), "SIGKILL": (-9, 137)}
    require(interruption["exit_code"] in signal_exits.get(interruption["signal"], ()), "no observed process interruption")
    expected = {"total": 18, **fixture["tokens"]}
    require(load(run / "interrupted-checkpoint.json") == expected, "interruption checkpoint is missing or wrong")
    require(load(project / "checkpoint.json") == expected, "checkpoint pickup failed")
    require(load(project / "published.json") == {**expected, "recovered": True}, "completion publication is missing or wrong")
    require(set(path.name for path in project.iterdir()) == set(fixture["initial_files"]) | {"checkpoint.json", "published.json"}, "unscoped write or unexpected file")
    for name, before in fixture["initial_files"].items():
        require(digest(project / name) == before, f"unscoped mutation of {name}")
    for path in FIXTURES.iterdir():
        expected_text = path.read_text(encoding="utf-8").replace("@BRIEF@", fixture["tokens"]["brief"]).replace("@STANDING@", fixture["tokens"]["standing"])
        require((project / path.name).read_text(encoding="utf-8") == expected_text, f"forged initial fixture {path.name}")
    observed = {}
    hashes = {"fixture.json": digest(run / "fixture.json"), "operator.json": digest(run / "operator.json"),
              "interrupted-checkpoint.json": digest(run / "interrupted-checkpoint.json")}
    for phase in PHASES:
        process = operator["processes"][phase]
        require(process["argv"] == argv(binding, project, phase), f"{phase} invocation mismatch")
        require(process["exit_code"] == (interruption["exit_code"] if phase == "initial" else 0), f"{phase} process did not finish as expected")
        prompt = run / f"{phase}-prompt.md"
        require(prompt.read_text(encoding="utf-8") == prompts(binding)[phase], f"{phase} prompt changed")
        transcript = run / f"{phase}-rollout.jsonl"
        runtime, records = rollout(transcript, binding, project, phase)
        stream = run / f"{phase}-events.jsonl"
        events = [json.loads(line) for line in stream.read_text(encoding="utf-8").splitlines() if line.strip()]
        threads = [event["thread_id"] for event in events if event.get("type") == "thread.started"]
        require(threads == [runtime["session_id"]], f"{phase} CLI event stream does not match its rollout")
        completed = any(event.get("type") == "turn.completed" for event in events)
        require(completed == (phase != "initial"), f"{phase} CLI completion contradicts process observation")
        if phase != "refusal":
            publication = expected if phase == "initial" else {**expected, "recovered": True}
            if phase == "initial" and interruption["exit_code"] == 1:
                require(executed_json([record for record in records if record.interrupted], expected, allow_interrupted=True), "no observed runtime interruption with checkpoint output")
            require(executed_json(records, publication, allow_interrupted=phase == "initial"), f"{phase} lacks successful executed task output")
        observed[phase] = {**runtime, "argv": process["argv"], "exit_code": process["exit_code"]}
        hashes[prompt.name], hashes[transcript.name] = digest(prompt), digest(transcript)
        hashes[stream.name] = digest(stream)
    require(len({item["session_id"] for item in observed.values()}) == 3, "phases reused a stale session")
    hashes.update({"project/" + name: digest(project / name) for name in sorted(set(fixture["initial_files"]) | {"checkpoint.json", "published.json"})})
    return {"suite": SUITE, "oracle_sha256": digest(Path(__file__)), "fixture_sha256": fixture_digest(),
            "binding": binding, "observed": observed, "evidence_sha256": hashes}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("action", choices=("prepare", "check"))
    parser.add_argument("--run", required=True, type=Path)
    parser.add_argument("--binding", type=Path)
    args = parser.parse_args()
    try:
        if args.action == "prepare":
            require(args.binding is not None, "prepare requires --binding")
            prepare(args.run.resolve(), load(args.binding))
        else:
            print(json.dumps(check(args.run), sort_keys=True))
        return 0
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
        print(f"eval rejected: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
