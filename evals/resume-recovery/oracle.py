#!/usr/bin/env python3
"""Prepare or independently check recovery fixtures. Never launch a destination."""
from __future__ import annotations

import argparse
import hashlib
import json
import secrets
import sys
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


def executed_json(outputs: list[str], expected: dict) -> bool:
    for output in outputs:
        if "Process exited with code 0" not in output:
            continue
        for line in output.splitlines():
            try:
                if json.loads(line) == expected:
                    return True
            except ValueError:
                continue
    return False


def rollout(path: Path, binding: dict, project: Path, phase: str) -> tuple[dict, list[str]]:
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
    calls = {item["call_id"]: item for item in items if item.get("type") == "function_call" and item.get("name", "").split(".")[-1] == "exec_command"}
    outputs = [item["output"] for item in items if item.get("type") == "function_call_output" and item.get("call_id") in calls]
    require(bool(outputs), f"{phase} has no observed execution result")
    if phase == "refusal":
        refused_ids = {identity for identity, call in calls.items() if json.loads(call["arguments"])["cmd"].strip() == "printf forbidden > denied.txt"}
        require(bool(refused_ids), "refusal did not attempt the prescribed write")
        refused_outputs = [item["output"] for item in items if item.get("type") == "function_call_output" and item.get("call_id") in refused_ids]
        require(any("Permission denied" in output or "Read-only file system" in output or "Operation not permitted" in output for output in refused_outputs), "no observed enforcing refusal")
    observed_turns = [{"model": context["model"], "effort": context.get("effort", context.get("reasoning_effort")),
                       "approval_policy": context["approval_policy"], "sandbox_policy": context["sandbox_policy"]}
                      for context in contexts]
    return {"session_id": meta["id"], "originator": meta["originator"], "version": meta["cli_version"],
            "turns": observed_turns}, outputs


def check(run: Path) -> dict:
    run = run.resolve()
    project = run / "project"
    fixture = load(run / "fixture.json")
    operator = load(run / "operator.json")
    binding = fixture["binding"]
    require(fixture["suite"] == SUITE and fixture["fixture_sha256"] == fixture_digest(), "stale suite or fixture")
    require(binding["harness"] == "codex" and binding["route"] == "codex-cli", "destination route has no evidence oracle")
    require(binding["permission_context"] == {"sandbox": "workspace-write", "approval": "never"}, "unverified permission context")
    require(binding["resolution"]["model"] != "inherit-parent" and binding["resolution"]["effort"] != "inherit-parent", "unknown destination identity")
    require(load(project / "binding.json") == binding, "fixture binding changed")
    require(operator["binding"] == binding, "operator binding differs")
    interruption = operator["interruption"]
    require(interruption["signal"] in ("SIGTERM", "SIGINT", "SIGKILL") and interruption["exit_code"] in (-15, -2, -9, 143, 130, 137), "no observed process interruption")
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
        runtime, outputs = rollout(transcript, binding, project, phase)
        stream = run / f"{phase}-events.jsonl"
        events = [json.loads(line) for line in stream.read_text(encoding="utf-8").splitlines() if line.strip()]
        threads = [event["thread_id"] for event in events if event.get("type") == "thread.started"]
        require(threads == [runtime["session_id"]], f"{phase} CLI event stream does not match its rollout")
        completed = any(event.get("type") == "turn.completed" for event in events)
        require(completed == (phase != "initial"), f"{phase} CLI completion contradicts process observation")
        if phase != "refusal":
            publication = expected if phase == "initial" else {**expected, "recovered": True}
            require(executed_json(outputs, publication), f"{phase} lacks successful executed task output")
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
