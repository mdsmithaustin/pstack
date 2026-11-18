#!/usr/bin/env python3
"""Reduce one matrix row's rollouts to a trimmed extract and a verdict.

    reduce.py ROOT --out EXTRACT.json

ROOT is a `run_row.py` run directory. The verdict compares each `spawn_agent` call's asked model and effort, and the
model and effort each child's own `turn_context` records, with `check-models-config.py --resolve` for the row's roles.

A v2 child is matched to its call by task name. A v1 child has none, so it is matched by id: the output of the call that
ran a spawn site lists the `agent_id` of every child it started. A child passes when it ran a model and effort that its
call's sites asked for. Sites in one code-mode `exec` call share the call's output, so their children cannot be told apart.
"""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
RESOLVER = REPO / "skills" / "setup-pstack" / "scripts" / "check-models-config.py"
ROWS = json.loads((HERE / "rows.json").read_text())
COLLAB_TOOLS = ("spawn_agent", "wait_agent", "close_agent", "list_agents", "send_message", "send_input",
                "followup_task", "resume_agent", "interrupt_agent")


BACKTICK = re.compile(r"`(?:\\.|[^`\\])*`", re.S)
CODE_SPAWN = re.compile(r"(\w*spawn_agent)\(\{([^{}]*)\}\)")
CODE_KEY = re.compile(r"(\w+):\s*(\"[^\"]*\"|true|false|-?\d+)")
AGENT_ID = re.compile(r'"agent_id"\s*:\s*"([^"]+)"')


def code_mode_spawns(source):
    """`spawn_agent` call sites inside a code-mode `exec` call, as the v1 tool is reached. Template-literal briefs are
    blanked first, so the scan sees only the argument keys. One call site can run once per brief."""
    sites = []
    for match in CODE_SPAWN.finditer(BACKTICK.sub("``", source)):
        arguments = {key: json.loads(value) for key, value in CODE_KEY.findall(match.group(2))}
        arguments["message"] = "<code-mode brief, not recorded>"
        sites.append((match.group(1), arguments))
    return sites


def rows_of(path):
    out = []
    for line in path.read_text(errors="replace").splitlines():
        try:
            record = json.loads(line)
        except ValueError:
            continue
        if isinstance(record, dict):
            out.append(record)
    return out


def agent_ids(output):
    blocks = output if isinstance(output, list) else [output]
    texts = [block.get("text", "") if isinstance(block, dict) else str(block) for block in blocks]
    return [found for text in texts for found in AGENT_ID.findall(text)]


def scrub(value, root):
    if isinstance(value, str):
        return value.replace(str(root), "<run>")
    if isinstance(value, list):
        return [scrub(v, root) for v in value]
    if isinstance(value, dict):
        return {k: scrub(v, root) for k, v in value.items()}
    return value


def thread(path, root):
    rows = rows_of(path)
    meta = next((r["payload"] for r in rows if r.get("type") == "session_meta"), {})
    contexts = [(r["payload"].get("model"), r["payload"].get("effort")) for r in rows if r.get("type") == "turn_context"]
    items = [r["payload"] for r in rows if r.get("type") == "response_item" and isinstance(r.get("payload"), dict)]
    calls, outputs, ids = [], {}, {}
    for item in items:
        if item.get("type") == "function_call" and item.get("name") in COLLAB_TOOLS:
            try:
                arguments = json.loads(item.get("arguments") or "{}")
            except ValueError:
                arguments = {"unparsed": str(item.get("arguments"))[:200]}
            if isinstance(arguments.get("message"), str):
                arguments["message"] = f"<{len(arguments['message'])} chars, not recorded>"
            calls.append({"call_id": item.get("call_id"), "tool": item["name"], "arguments": arguments})
        elif item.get("type") == "function_call_output":
            outputs[item.get("call_id")] = str(item.get("output"))[:300]
        if item.get("type") in ("function_call_output", "custom_tool_call_output"):
            ids[item.get("call_id")] = agent_ids(item.get("output"))
    for item in items:
        if item.get("type") == "custom_tool_call" and item.get("name") == "exec" and isinstance(item.get("input"), str):
            for tool_name, arguments in code_mode_spawns(item["input"]):
                calls.append({"call_id": item.get("call_id"), "tool": "spawn_agent", "style": "code-mode", "tool_name": tool_name,
                              "arguments": arguments})
    for call in calls:
        call["output"] = outputs.get(call["call_id"])
        call["agent_ids"] = ids.get(call["call_id"], [])
    prompts = [block["text"][:600] for item in items if item.get("type") == "message" and item.get("role") == "user"
               for block in item.get("content", []) if block.get("type") == "input_text" and not block["text"].lstrip().startswith("<")]
    source = meta.get("source")
    spawn = source.get("subagent", {}).get("thread_spawn", {}) if isinstance(source, dict) else {}
    return {"id": meta.get("id"), "file": path.name, "parent": meta.get("parent_thread_id"),
            "cli_version": meta.get("cli_version"), "agent_path": meta.get("agent_path"), "agent_role": spawn.get("agent_role"), "multi_agent_version": meta.get("multi_agent_version"),
            "turn_contexts": sorted({c for c in contexts}, key=str), "prompts": scrub(prompts, root), "calls": scrub(calls, root)}


def resolve(project, roles, work_model, home):
    argv = [sys.executable, str(RESOLVER), "--resolve", "--harness", "codex", "--project", str(project),
            "--user-file", str(home / ".agents" / "pstack-models.md")]
    if work_model:
        argv += ["--work-model", work_model]
    argv += roles
    done = subprocess.run(argv, capture_output=True, text=True)
    if done.returncode:
        raise SystemExit(f"resolver failed: {done.stderr}")
    return [json.loads(line) for line in done.stdout.splitlines() if line.startswith("{")]


def verdict(lead, children, resolved):
    expected = {}
    for a in resolved:
        roles = expected.setdefault((a["model"], a["effort"]), [])
        if a["role"] not in roles:
            roles.append(a["role"])

    def role_of(pair):
        return " / ".join(expected[pair]) if pair in expected else None

    detail, problems, matched = [], [], set()
    for call in (c for c in lead["calls"] if c["tool"] == "spawn_agent"):
        a = call["arguments"]
        fork_field = "fork_turns" if "fork_turns" in a else "fork_context" if "fork_context" in a else None
        pair = (a.get("model"), a.get("reasoning_effort"))
        name = a.get("task_name") or a.get("agent_type")
        entry = {"style": call.get("style", "function"), "tool_name": call.get("tool_name", call["tool"]), "task_name": a.get("task_name"), "agent_type": a.get("agent_type"),
                 "fork_field": fork_field, "fork_value": a.get(fork_field) if fork_field else None, "agent_ids": call["agent_ids"],
                 "args_model": pair[0], "args_effort": pair[1], "matches_role": role_of(pair), "output": call.get("output")}
        if fork_field is None:
            problems.append(f"{name}: no fork field set")
        if pair[0] and fork_field == "fork_turns" and a.get("fork_turns") != "none":
            problems.append(f"{name}: model passed with fork_turns {a.get('fork_turns')!r}")
        if pair[0] and fork_field == "fork_context" and a.get("fork_context"):
            problems.append(f"{name}: model passed with fork_context true")
        if not pair[0]:
            problems.append(f"{name}: spawn call passed no model or effort")
        if a.get("task_name"):
            child = next((c for c in children if (c["agent_path"] or "").endswith("/" + a["task_name"])), None)
            entry["child_contexts"] = child["turn_contexts"] if child else []
            if child is None:
                problems.append(f"{name}: no child rollout")
            else:
                matched.add(child["id"])
                if pair[0] and not all(c == pair for c in child["turn_contexts"]):
                    problems.append(f"{name}: child ran {child['turn_contexts']}, spawn asked {pair}")
        else:
            entry["child_contexts"] = None
        if pair[0] and pair not in expected:
            problems.append(f"{name}: {pair} is no resolved role arm")
        detail.append(entry)
    v1_calls = [c for c in lead["calls"] if c["tool"] == "spawn_agent" and not c["arguments"].get("task_name")]
    child_ids = {c["id"] for c in children}
    for call in v1_calls:
        missing = [i for i in call["agent_ids"] if i not in child_ids]
        if missing or not call["agent_ids"]:
            problems.append(f"{call['arguments'].get('agent_type') or 'default'}: no child rollout" + (f" for {missing}" if missing else ""))
    for child in (c for c in children if c["id"] not in matched):
        role = child["agent_role"] or "default"
        pairs = child["turn_contexts"]
        sites = [c["arguments"] for c in v1_calls if child["id"] in c["agent_ids"]]
        detail.append({"style": "child", "tool_name": None, "task_name": None, "agent_type": role, "fork_field": None,
                       "fork_value": None, "args_model": None, "args_effort": None, "child_contexts": pairs,
                       "matches_role": next((role_of(p) for p in pairs if p in expected), None), "output": None})
        asked = {(site.get("model"), site.get("reasoning_effort")) for site in sites}
        types = {site.get("agent_type") or "default" for site in sites}
        if not sites:
            problems.append(f"child {role}: no spawn call's output lists its id")
        elif role not in types:
            problems.append(f"child {role}: spawn asked agent type {sorted(types)}")
        if sites and not all(p in asked for p in pairs):
            problems.append(f"child {role}: ran {pairs}, spawn asked {sorted(asked, key=str)}")
    return detail, problems


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--row", help="row key whose roles apply, when the run directory holds an earlier key")
    args = parser.parse_args()
    root = args.root.resolve()
    run = json.loads((root / "run.json").read_text())
    row = ROWS[args.row or run["row"]]
    paths = sorted((root / "codex-home" / "sessions").rglob("rollout-*.jsonl"))
    threads = [thread(p, root) for p in paths]
    leads = [t for t in threads if not t["parent"]]
    children = [t for t in threads if t["parent"]]
    resolved = resolve(root / "project", row["roles"], row.get("work_model"), root / "home")
    lead = {"id": leads[0]["id"], "turn_contexts": leads[0]["turn_contexts"], "calls": []}
    for t in leads:
        lead["calls"] += t["calls"]
    detail, problems = verdict(lead, children, resolved)
    tools = {}
    for t in threads:
        for call in t["calls"]:
            tools[call["tool"]] = tools.get(call["tool"], 0) + 1
    result = {"row": args.row or run["row"], "lead_model": run["model"], "v2_flag": run.get("v2_flag", True), "lead_contexts": lead["turn_contexts"], "lead_prompts": leads[0]["prompts"],
              "skills_at": run["skills_at"], "cli_versions": sorted({t["cli_version"] for t in threads if t["cli_version"]}), "turns": run["turns"], "resolved": resolved, "collab_tool_calls": tools,
              "spawns": detail, "lead_multi_agent_version": leads[0]["multi_agent_version"],
              "children": [{k: c[k] for k in ("id", "agent_path", "agent_role", "multi_agent_version", "turn_contexts")} for c in children],
              "spawn_fired": bool(detail), "problems": problems,
              "verdict": "PASS" if detail and not problems else "FAIL"}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=1) + "\n")
    print(json.dumps({k: result[k] for k in ("row", "spawn_fired", "problems", "verdict")}, indent=1))


if __name__ == "__main__":
    main()
