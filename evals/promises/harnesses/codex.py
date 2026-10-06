import json
import os
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

import live
from grade_boundary import copy_file

SKILLS_DIR = ".agents/skills"
PRIVATE_DIRS = [".agents/", ".codex/"]
SHARES_HOST_TMP = True

APP_BIN = "/Applications/ChatGPT.app/Contents/Resources/codex-cli/CodexCLI.app/Contents/MacOS/codex"
MODEL = "gpt-6.1-sol"
EFFORT = "high"
ENV_KEPT = ("PATH", "LANG", "LC_ALL", "LC_CTYPE", "LC_MESSAGES", "TERM", "USER", "LOGNAME", "SHELL", "TZ",
            "SSL_CERT_FILE", "SSL_CERT_DIR", "HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY",
            "http_proxy", "https_proxy", "no_proxy")

READ_COMMANDS = {"cat", "head", "tail", "sed", "nl", "less", "more", "bat", "awk", "wc", "grep", "rg"}
SHELL_WRAPPERS = {"bash", "sh", "zsh", "/bin/bash", "/bin/sh", "/bin/zsh"}
PERSONA_LINE = re.compile(r"persona: ([\w-]+)")
REPLY_PERSONA_LINE = re.compile(r"^persona: ([\w-]+)[ \t]*$", re.M)
SKILL_INJECTION = re.compile(r"^<skill>\n<name>([^<]+)</name>\n<path>([^<]+)</path>")


def child_env(root):
    env = {k: os.environ[k] for k in ENV_KEPT if k in os.environ}
    env.update(HOME=str(root / "home"), CODEX_HOME=str(root / "codex-home"), TMPDIR=str(root / "tmp"))
    return env


def resolve_binary(env):
    """First candidate whose `--version` exits 0 under the run's own env, so a
    mise shim that needs the real HOME is rejected here and not mid-run."""
    candidates = [("CODEX_BIN", os.environ.get("CODEX_BIN")), ("PATH", shutil.which("codex", path=env.get("PATH"))),
                  ("chatgpt-app", APP_BIN)]
    rejected = []
    for source, path in candidates:
        if not path or not Path(path).exists():
            continue
        try:
            probe = subprocess.run([path, "--version"], env=env, capture_output=True, text=True, timeout=60)
        except (OSError, subprocess.TimeoutExpired) as error:
            rejected.append({"source": source, "path": path, "error": repr(error)})
            continue
        if probe.returncode == 0:
            return {"source": source, "path": path, "version": probe.stdout.strip(), "rejected": rejected}
        rejected.append({"source": source, "path": path, "exit_code": probe.returncode, "stderr": probe.stderr[-300:]})
    raise RuntimeError(f"no working codex binary; rejected: {json.dumps(rejected)}")


def prepare(run):
    root = run.root
    for name in ("home", "codex-home", "tmp", "transcripts"):
        (root / name).mkdir(exist_ok=True)
    auth = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex") / "auth.json"
    if not auth.is_file():
        raise RuntimeError(f"no codex login at {auth}")
    link = root / "codex-home" / "auth.json"
    if not link.is_symlink():
        link.symlink_to(auth)
    script = run.project / SKILLS_DIR / "pstack-harness" / "scripts" / "subagents.py"
    install = subprocess.run([sys.executable, str(script), "install", "--harness", "codex", "--project", str(run.project)],
                             check=True, capture_output=True, text=True).stdout
    (root / "personas-install.json").write_text(install)
    if json.loads(install).get("payload") != "ready":
        raise RuntimeError(f"persona registration not ready: {install[:300]}")
    binary = resolve_binary(child_env(root))
    (root / "launch.json").write_text(json.dumps(binary, indent=1) + "\n")


def config_flags(run):
    project = run.project
    plan = str(run.case.get("env", {}).get("todo_tools") is not False).lower()
    return ["--disable", "apps", "-c", f'model="{MODEL}"', "-c", f'model_reasoning_effort="{EFFORT}"',
            "-c", 'approval_policy="never"', "-c", 'sandbox_mode="workspace-write"',
            "-c", f"tools.update_plan.enabled={plan}",
            "-c", f'projects={{"{project}"={{trust_level="trusted"}}}}',
            "-c", f'sandbox_workspace_write.writable_roots=["{project}/.git"]']


def thread_id(stream):
    for record in records(stream):
        if record.get("type") == "thread.started":
            return record.get("thread_id")
    return None


def turn(run, text, index):
    launch = json.loads((run.root / "launch.json").read_text())
    skill, rest = live.split_entry(run.case, text, index)
    prompt = f"${skill} {rest}".rstrip() if skill else text
    transcripts = run.root / "transcripts"
    stream, errors, last = (transcripts / f"turn-{index}.{ext}" for ext in ("jsonl", "err", "last-message.txt"))
    resume = []
    if index:
        previous = next((t["session_id"] for t in reversed(run.turns) if t.get("session_id")), None)
        if not previous:
            raise RuntimeError("no session id from an earlier turn to resume")
        resume = ["resume"]
    tail = ["--json", "-o", str(last), "--", *([previous] if index else []), prompt]
    argv = [launch["path"], "exec", *resume, *config_flags(run), *tail]
    record = live.execute(argv, run.project, child_env(run.root), run.timeout_s, stream, errors)
    record.update(index=index, session_id=thread_id(stream) or (previous if index else None), stream=str(stream),
                  stderr=str(errors), last_message=str(last), codex_bin=launch["path"], codex_bin_source=launch["source"])
    return record


def records(path):
    for line in Path(path).read_text(errors="replace").splitlines():
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(record, dict):
            yield record


def session_meta(path):
    for record in records(path):
        if record.get("type") == "session_meta":
            return record.get("payload") or {}
    return {}


def find_rollouts(store, threads):
    metas = {path: session_meta(path) for path in sorted(store.rglob("rollout-*.jsonl"))}
    leads = [p for p, m in metas.items() if m.get("id") in threads or any(p.name.endswith(f"-{t}.jsonl") for t in threads)]
    if not threads:
        leads = [p for p, m in metas.items() if not m.get("parent_thread_id")]
    chosen, seen = list(leads), {metas[p].get("id") for p in leads}
    while True:
        children = [p for p, m in metas.items() if p not in chosen and m.get("parent_thread_id") in seen]
        if not children:
            return leads, chosen[len(leads):]
        chosen += children
        seen |= {metas[p].get("id") for p in children}


def text_of(content):
    if isinstance(content, str):
        return content
    return "".join(part.get("text", "") for part in content or [] if isinstance(part, dict))


def parse_arguments(value):
    if isinstance(value, dict):
        return value
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, dict) else {"value": parsed}
    except (TypeError, json.JSONDecodeError):
        return {"raw": value}


def shell_script(command):
    if isinstance(command, list):
        if len(command) >= 3 and command[0] in SHELL_WRAPPERS and command[1] in ("-lc", "-c"):
            return command[2]
        return shlex.join(command)
    return command or ""


def paths_read(script, cwd):
    found = []
    for segment in re.split(r"\|\||&&|[|;\n]", script):
        try:
            words = shlex.split(segment)
        except ValueError:
            words = segment.split()
        if not words or Path(words[0]).name not in READ_COMMANDS:
            continue
        for word in words[1:]:
            if word.startswith(("-", "<", ">")):
                continue
            candidate = Path(word) if word.startswith("/") else cwd / word
            if candidate.is_file() or (re.search(r"\.[A-Za-z0-9]+$", word) and "/" in word):
                found.append(str(candidate.resolve() if candidate.exists() else candidate))
    return found


def text_worklist(text):
    return live.chat_worklist(text)

def plan_items(arguments):
    return [{"text": step.get("step", ""), "state": str(step.get("status", "pending")).replace("_", " ")}
            for step in arguments.get("plan") or [] if isinstance(step, dict)]


def js_update_plan_calls(code):
    calls = []
    for match in re.finditer(r"tools\.update_plan\(", code):
        depth, start = 0, match.end()
        for index in range(start, len(code)):
            depth += code[index] in "({["
            depth -= code[index] in ")}]"
            if depth < 0:
                literal = code[start:index]
                quoted = re.sub(r"([{,]\s*)([A-Za-z_]\w*)\s*:", r'\1"\2":', literal)
                try:
                    calls.append(json.loads(quoted))
                except json.JSONDecodeError:
                    calls.append({"raw": literal})
                break
    return calls


def harvest_rollout(path, prompts=None):
    events, files, worklist, spawns = [], [], [], []
    final, injected, context, usage = "", [], {}, None
    meta = session_meta(path)
    cwd = Path(meta.get("cwd") or ".")
    names, plan_calls, spawn_by_call = {}, [], {}
    turn, upcoming = 0, list(enumerate(prompts or []))

    def add(event):
        event["seq"] = len(events)
        if prompts is not None:
            event["turn"] = turn
        events.append(event)
        return event["seq"]

    for record in records(path):
        kind, payload = record.get("type"), record.get("payload") or {}
        if kind == "turn_context" and not context:
            context = payload
        if kind == "event_msg" and payload.get("type") == "token_count":
            usage = (payload.get("info") or {}).get("total_token_usage") or usage
        if kind == "response_item":
            ptype = payload.get("type")
            if ptype == "message":
                text = text_of(payload.get("content"))
                hit = SKILL_INJECTION.match(text)
                if payload.get("role") == "user" and hit:
                    injected.append({"name": hit.group(1), "path": hit.group(2), "turn": turn if prompts is not None else None})
                if payload.get("role") == "user" and upcoming and text.strip() == upcoming[0][1].strip():
                    turn = upcoming.pop(0)[0]
                    add({"kind": "user", "text": text})
                if payload.get("role") == "assistant" and text.strip():
                    seq = add({"kind": "text", "text": text})
                    final = text
                    items = text_worklist(text)
                    if items:
                        worklist.append({"seq": seq, "carrier": "text", "items": items})
            elif ptype in ("custom_tool_call", "function_call"):
                name = payload.get("name")
                names[payload.get("call_id")] = name
                tool_input = {"code": payload.get("input")} if ptype == "custom_tool_call" else parse_arguments(payload.get("arguments"))
                seq = add({"kind": "tool_call", "name": name, "input": tool_input, "id": payload.get("call_id")})
                if name == "update_plan":
                    worklist.append({"seq": seq, "carrier": name, "items": plan_items(tool_input)})
                if name == "exec":
                    for call in js_update_plan_calls(tool_input.get("code") or ""):
                        worklist.append({"seq": seq, "carrier": "update_plan (inside exec)", "items": plan_items(call)})
                        plan_calls.append(seq)
                if name == "spawn_agent":
                    message = tool_input.get("message") or tool_input.get("prompt") or text_of(tool_input.get("items"))
                    persona = tool_input.get("agent_type")
                    if persona in (None, "default"):
                        hit = PERSONA_LINE.search(message or "")
                        persona = hit.group(1) if hit else persona
                    encrypted = (message or "").startswith("gAAAA")
                    spawn_by_call[payload.get("call_id")] = len(spawns)
                    spawns.append({"seq": seq, "turn": events[seq].get("turn"), "tool": name, "persona": persona, "model": tool_input.get("model"),
                                   "effort": tool_input.get("reasoning_effort"), "fork_turns": tool_input.get("fork_turns"),
                                   "prompt_head": None if encrypted else (message or "")[:300], "x_prompt_encrypted": encrypted})
            elif ptype in ("custom_tool_call_output", "function_call_output"):
                output = payload.get("output")
                body = text_of(output) if isinstance(output, list) else (output if isinstance(output, str) else json.dumps(output))
                ok = not re.search(r"^(Script failed|Error|error:)", body or "", re.M)
                add({"kind": "tool_result", "name": names.get(payload.get("call_id")), "ok": ok, "output_head": (body or "")[:400],
                     "id": payload.get("call_id")})
        if kind == "event_msg" and payload.get("type") == "item_completed":
            item = payload.get("item") or {}
            itype = item.get("type")
            if itype == "CommandExecution":
                script = shell_script(item.get("command"))
                item_cwd = Path(str(item.get("cwd", cwd)).removeprefix("file://"))
                add({"kind": "tool_call", "name": "exec_command", "input": {"cmd": script, "cwd": str(item_cwd)}, "id": item.get("id")})
                add({"kind": "tool_result", "name": "exec_command", "ok": item.get("exit_code") in (0, None) and item.get("status") == "completed",
                     "output_head": str(item.get("stdout") or item.get("aggregated_output") or "")[:400], "id": item.get("id")})
                read = [p.get("path") or p.get("name") for p in item.get("parsed_cmd") or [] if p.get("type") == "read"]
                files += [str((item_cwd / r).resolve()) for r in read if r] + paths_read(script, item_cwd)
            elif itype == "SubAgentActivity" and item.get("kind") == "started" and item.get("id") in spawn_by_call:
                spawns[spawn_by_call[item["id"]]]["x_thread_id"] = item.get("agent_thread_id")
                add({"kind": "tool_call", "name": itype, "input": {k: v for k, v in item.items() if k not in ("type", "id")}})
            elif itype not in ("UserMessage", "AgentMessage", "Reasoning", "CollabAgentToolCall", None):
                add({"kind": "tool_call", "name": itype, "input": {k: v for k, v in item.items() if k not in ("type", "id", "stdout", "aggregated_output")}})
    files += [e["input"]["path"] for e in events
              if e["kind"] == "tool_call" and e["name"] in ("view_image", "read_file") and e["input"].get("path")]
    return {"meta": meta, "context": context, "events": events, "files_read": list(dict.fromkeys(files)),
            "worklist": stamp_turns(worklist, events), "plan_calls": plan_calls, "spawns": spawns, "final_reply": final,
            "injected": injected, "usage": usage}


def stamp_turns(snapshots, events):
    for snapshot in snapshots:
        seq = snapshot.get("seq")
        if seq is not None and "turn" in events[seq]:
            snapshot["turn"] = events[seq]["turn"]
    return snapshots


def merge_stream_plans(lead, streams):
    """Replace plan snapshots whose arguments a code-mode exec script computed
    at runtime with the todo_list items `exec --json` streamed, matching the
    k-th todo_list event to the k-th update_plan call. The stream carries only
    a completed flag, so a step is completed or pending there."""
    snapshots = []
    for stream in streams:
        for record in records(stream):
            item = record.get("item") or {}
            if record.get("type") in ("item.started", "item.updated", "item.completed") and item.get("type") == "todo_list":
                snapshots.append([{"text": s.get("text", ""), "state": "completed" if s.get("completed") else "pending"}
                                  for s in item.get("items") or []])
    if not snapshots:
        return
    calls = lead["plan_calls"]
    kept = [e for e in lead["worklist"] if e["carrier"] != "update_plan (inside exec)"]
    for index, items in enumerate(snapshots):
        seq = calls[index] if index < len(calls) else (calls[-1] if calls else None)
        kept.append({"seq": seq, "carrier": "update_plan (inside exec; items from exec --json todo_list)", "items": items})
    lead["worklist"] = stamp_turns(sorted(kept, key=lambda e: (e["seq"] is None, e["seq"] or 0)), lead["events"])


def entry_state(run, lead):
    skill = run.case.get("entry")
    if not skill or not (run.project / SKILLS_DIR / skill / "SKILL.md").is_file():
        return "not-registered" if skill else "not-observed"
    if any(hit["name"] == skill for hit in lead["injected"]):
        return "injected"
    if any(path.endswith(f"{skill}/SKILL.md") for path in lead["files_read"]):
        return "read"
    return "not-observed"


def turn_entries(run, lead):
    found = []
    for index, text in enumerate(run.case["turns"][:len(run.turns)]):
        skill, _ = live.split_entry(run.case, text, index)
        if not skill:
            continue
        if not (run.project / SKILLS_DIR / skill / "SKILL.md").is_file():
            state = "not-registered"
        elif any(hit["name"] == skill and hit.get("turn") == index for hit in lead["injected"]):
            state = "injected"
        else:
            state = "not-observed"
        found.append({"turn": index, "skill": skill, "entry": state})
    return found


def copy_into(sources, destination):
    copied = []
    for source in sources:
        target = destination / source.name
        copy_file(source, target)
        copied.append(str(target))
    return copied


def harvest(run):
    store = run.root / "codex-home" / "sessions"
    streams = [Path(t["stream"]) for t in run.turns if Path(t.get("stream", "")).is_file()]
    threads = {t["session_id"] for t in run.turns if t.get("session_id")}
    leads, child_paths = find_rollouts(store, threads)
    lead_path = leads[0] if leads else None
    prompts = [t["argv"][-1] for t in run.turns if t.get("argv")]
    lead = harvest_rollout(lead_path, prompts) if lead_path else {
        "meta": {}, "context": {}, "events": [], "files_read": [], "worklist": [], "plan_calls": [], "spawns": [],
        "final_reply": "", "injected": [], "usage": None}
    merge_stream_plans(lead, streams)
    launch = json.loads((run.root / "launch.json").read_text())
    context = lead["context"]
    rollouts = copy_into([*leads, *child_paths], run.root / "transcripts" / "rollouts")
    last = run.turns[-1] if run.turns else {}
    trace = {
        "harness": "codex",
        "cli_version": lead["meta"].get("cli_version") or launch.get("version"),
        "model": context.get("model"),
        "effort": context.get("effort") or context.get("reasoning_effort"),
        "argv": run.turns[0]["argv"] if run.turns else [],
        "cwd": str(run.project),
        "exit_code": last.get("exit_code"),
        "duration_s": round(sum(t.get("duration_s", 0) for t in run.turns), 1),
        "entry": entry_state(run, lead),
        "events": lead["events"],
        "files_read": lead["files_read"],
        "worklist": lead["worklist"],
        "spawns": lead["spawns"],
        "final_reply": lead["final_reply"],
        "transcript_paths": rollouts + [str(s) for s in streams],
        "x_binary": {"path": launch["path"], "source": launch["source"], "version": launch["version"], "rejected": launch["rejected"]},
        "x_turns": [{k: t.get(k) for k in ("index", "session_id", "argv", "exit_code", "timed_out", "duration_s")} for t in run.turns],
        "x_entry_injections": lead["injected"],
        "x_turn_entries": turn_entries(run, lead),
        "x_todo_tools": "off" if run.case.get("env", {}).get("todo_tools") is False else "on",
        "x_token_usage": lead["usage"],
        "x_subagents": [],
    }
    for path in child_paths:
        child = harvest_rollout(path)
        first = next((e["text"] for e in child["events"] if e["kind"] == "text"), "")
        line = REPLY_PERSONA_LINE.search(first)
        trace["x_subagents"].append({
            "thread_id": child["meta"].get("id"), "parent_thread_id": child["meta"].get("parent_thread_id"),
            "agent_role": child["meta"].get("agent_role") or child["meta"].get("agent_type"),
            "model": child["context"].get("model"), "effort": child["context"].get("effort") or child["context"].get("reasoning_effort"),
            "persona_line": line.group(0) if line else None, "first_reply": first[:200] or None,
            "files_read": child["files_read"], "worklist": child["worklist"], "spawns": child["spawns"],
            "event_count": len(child["events"]), "final_reply": child["final_reply"], "rollout": str(path),
        })
    by_thread = {c["thread_id"]: c for c in trace["x_subagents"]}
    for spawn in trace["spawns"]:
        child = by_thread.get(spawn.get("x_thread_id"))
        spawn["x_child_first_reply"] = child["first_reply"] if child else None
        spawn["x_persona_line"] = child["persona_line"].split(": ", 1)[1] if child and child["persona_line"] else None
        if child and spawn["persona"] in (None, "default") and child["persona_line"]:
            spawn["persona"] = child["persona_line"].split(": ", 1)[1]
            spawn["x_persona_source"] = "child first reply"
        if spawn["persona"] == "default":
            spawn["x_agent_role"], spawn["persona"] = "default", None
    return trace
