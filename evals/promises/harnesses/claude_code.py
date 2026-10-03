import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

import live

SKILLS_DIR = ".claude/skills"
PRIVATE_DIRS = (".claude/",)
SHARES_HOST_TMP = True

KEEP_ENV = ("HOME", "PATH", "USER", "LOGNAME", "SHELL", "LANG", "TERM")
DEFAULT_EFFORT = "high"
SPAWN_TOOLS = ("Task", "Agent")
READ_COMMANDS = {"cat", "head", "tail", "sed", "awk", "less", "more", "nl", "bat", "wc", "grep", "rg",
                 "diff", "cmp", "jq", "python3", "python"}
SEPARATORS = {"&&", "||", ";", "|", "&"}
TASK_ID = re.compile(r"Task #?(\w+)")
ASSIGN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
VAR = re.compile(r"\$(?:\{([A-Za-z_][A-Za-z0-9_]*)\}|([A-Za-z_][A-Za-z0-9_]*))")
PERSONA_LINE = re.compile(r"^persona: ([\w-]+)[ \t]*$", re.M)
COMMAND_NAME = re.compile(r"<command-name>(/[^<]+)</command-name>")
COMMAND_ARGS = re.compile(r"<command-args>(.*?)</command-args>", re.S)


def config_dir():
    return Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude")


def store():
    return config_dir() / "projects"


def prepare(run):
    script = run.project / SKILLS_DIR / "pstack-harness/scripts/subagents.py"
    done = subprocess.run([sys.executable, str(script), "install", "--harness", "claude-code",
                           "--project", str(run.project)], capture_output=True, text=True)
    (run.root / "agents-install.json").write_text(done.stdout)
    report = json.loads(done.stdout or "{}")
    rows = [*report.get("roles", []), *report.get("efforts", [])]
    if done.returncode or report.get("payload") != "ready" or not rows or any(r["native_file"] != "current" for r in rows):
        raise RuntimeError(f"persona registration failed: {done.stdout}{done.stderr}")
    (run.project / ".claude/settings.json").write_text(json.dumps({"attribution": {"commit": "", "pr": ""}}) + "\n")
    (run.root / "tmp").mkdir(exist_ok=True)


def child_env(run):
    env = {k: os.environ[k] for k in (*KEEP_ENV, "CLAUDE_CONFIG_DIR") if k in os.environ}
    env["TMPDIR"] = str(run.root / "tmp")
    if run.case.get("env", {}).get("todo_tools"):
        env["CLAUDE_CODE_ENABLE_TODO_TOOLS"] = "1"
    return env


def turn(run, text, index):
    skill, rest = live.split_entry(run.case, text, index)
    prompt = f"/{skill} {rest}".rstrip() if skill else text
    if index == 0:
        session = str(uuid.uuid4())
        pin = ["--session-id", session]
    else:
        session = run.turns[0]["session_id"]
        pin = ["--resume", session]
        move_session(run.root / "transcripts", store(), session)
    argv = ["claude", "-p", "--output-format", "stream-json", "--verbose", "--setting-sources", "project",
            "--permission-mode", "bypassPermissions", *pin]
    effort = run.case.get("effort", DEFAULT_EFFORT)
    if effort:
        argv += ["--effort", effort]
    if run.case.get("model"):
        argv += ["--model", run.case["model"]]
    argv.append(prompt)
    stream, stderr = run.root / f"stream-{index}.jsonl", run.root / f"stderr-{index}.txt"
    record = live.execute(argv, run.project, child_env(run), run.timeout_s, stream, stderr)
    return {**record, "session_id": session, "index": index, "stream": str(stream), "stderr": str(stderr)}


def move_session(src_root, dst_root, session):
    for hit in sorted(src_root.glob(f"*/{session}*")):
        dest = dst_root / hit.parent.name / hit.name
        files = [f for f in hit.rglob("*") if f.is_file()] if hit.is_dir() else [hit]
        for f in files:
            target = dest / f.relative_to(hit) if hit.is_dir() else dest
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(f), str(target))
        if hit.is_dir():
            shutil.rmtree(hit)
        if not any(p.is_file() for p in hit.parent.rglob("*")):
            shutil.rmtree(hit.parent)


def forget_registry(session):
    """Drop the live-session registry rows and messaging socket a killed process leaves behind."""
    for record in (config_dir() / "sessions").glob("*.json"):
        try:
            row = json.loads(record.read_text())
            if row.get("sessionId") != session:
                continue
            os.kill(row["pid"], 0)
        except ProcessLookupError:
            pass
        except (OSError, ValueError, KeyError):
            continue
        else:
            continue
        for stale in (record, *record.parent.glob(f"{record.stem}.*.key"), Path(row.get("messagingSocketPath") or "/nonexistent")):
            stale.unlink(missing_ok=True)


def load_jsonl(path):
    rows = []
    for line in Path(path).read_text(errors="replace").splitlines():
        try:
            rows.append(json.loads(line))
        except ValueError:
            continue
    return rows


def blocks(entry):
    content = entry.get("message", {}).get("content")
    if isinstance(content, str):
        return [{"type": "text", "text": content}]
    return content or []


def result_text(block):
    content = block.get("content")
    if isinstance(content, list):
        return "\n".join(part.get("text", "") for part in content if isinstance(part, dict))
    return content or ""


def shell_reads(command, cwd):
    try:
        lexer = shlex.shlex(command, posix=True, punctuation_chars=";&|")
        lexer.whitespace_split = True
        tokens = list(lexer)
    except ValueError:
        return []
    segments, current = [], []
    for token in tokens:
        if token in SEPARATORS or set(token) <= set(";&|"):
            segments.append(current)
            current = []
        else:
            current.append(token)
    segments.append(current)
    here, found, names = Path(cwd), [], {}
    for segment in segments:
        while segment and ASSIGN.match(segment[0]):
            key, value = segment.pop(0).split("=", 1)
            names[key] = value
        if segment and segment[0] == "export":
            for token in segment[1:]:
                if ASSIGN.match(token):
                    key, value = token.split("=", 1)
                    names[key] = value
            continue
        segment = [VAR.sub(lambda m: names.get(m.group(1) or m.group(2), m.group(0)), token) for token in segment]
        if not segment:
            continue
        name = Path(segment[0]).name
        if name == "cd" and len(segment) > 1:
            here = (here / segment[1]).resolve()
            continue
        if name not in READ_COMMANDS:
            continue
        for arg in segment[1:]:
            if arg[0] in "-<>":
                continue
            path = Path(arg) if arg.startswith("/") else here / arg
            try:
                if path.is_file():
                    found.append(str(path.resolve()))
            except OSError:
                pass
    return found


def files_read(rows, cwd):
    paths = []
    for entry in rows:
        if entry.get("type") != "assistant":
            continue
        for block in blocks(entry):
            if block.get("type") != "tool_use":
                continue
            given = block.get("input", {})
            if block["name"] == "Read" and given.get("file_path"):
                path = Path(given["file_path"])
                paths.append(str((path if path.is_absolute() else Path(cwd) / path).resolve()))
            elif block["name"] == "Bash" and given.get("command"):
                paths.extend(shell_reads(given["command"], entry.get("cwd") or cwd))
    return list(dict.fromkeys(paths))


def prompt_text(entry):
    text = "\n".join(b.get("text", "") for b in blocks(entry) if b.get("type") == "text")
    name = COMMAND_NAME.search(text)
    if not name:
        return text
    args = COMMAND_ARGS.search(text)
    return f"{name.group(1)} {args.group(1) if args else ''}".strip()


def is_prompt(entry):
    if entry.get("type") != "user" or entry.get("isMeta") or entry.get("isSidechain"):
        return False
    parts = blocks(entry)
    if not parts or any(p.get("type") == "tool_result" for p in parts):
        return False
    text = prompt_text(entry).strip()
    return bool(text) and not text.startswith(("<task-notification", "<system-reminder", "[Request interrupted"))


def tag_turns(rows):
    turn, seen, tagged = 0, False, []
    for entry in rows:
        if is_prompt(entry):
            turn += seen
            seen = True
        tagged.append((turn, entry))
    return tagged


def lead_events(rows):
    events = []
    names = {}

    def add(turn, event):
        events.append({"seq": len(events), "turn": turn, **event})

    for turn, entry in tag_turns(rows):
        kind = entry.get("type")
        if kind not in ("assistant", "user"):
            continue
        if is_prompt(entry):
            add(turn, {"kind": "user", "text": prompt_text(entry)})
            continue
        if entry.get("isMeta"):
            continue
        for block in blocks(entry):
            if block.get("type") == "tool_use":
                names[block["id"]] = block["name"]
                add(turn, {"kind": "tool_call", "name": block["name"], "input": block.get("input", {}), "id": block["id"]})
            elif block.get("type") == "tool_result":
                add(turn, {"kind": "tool_result", "name": names.get(block.get("tool_use_id"), "?"),
                           "ok": not block.get("is_error", False), "output_head": result_text(block)[:400],
                           "id": block.get("tool_use_id")})
            elif block.get("type") == "text" and kind == "assistant" and block.get("text", "").strip():
                add(turn, {"kind": "text", "text": block["text"]})
    return events


def native_worklist(events):
    tasks, order, snapshots = {}, [], []
    results = {e["id"]: e for e in events if e["kind"] == "tool_result"}
    for event in events:
        if event["kind"] != "tool_call":
            continue
        name, given = event["name"], event["input"]
        if name == "TodoWrite":
            items = [{"text": t.get("content", ""), "state": t.get("status", "pending").replace("_", " ")}
                     for t in given.get("todos", [])]
            snapshots.append({"seq": event["seq"], "turn": event["turn"], "carrier": name, "items": items})
            continue
        if name == "TaskCreate":
            match = TASK_ID.search(results.get(event["id"], {}).get("output_head", ""))
            task_id = match.group(1) if match else f"?{len(order) + 1}"
            tasks[task_id] = {"text": given.get("subject") or given.get("description", ""), "state": "pending"}
            order.append(task_id)
        elif name == "TaskUpdate":
            task_id = str(given.get("taskId"))
            task = tasks.setdefault(task_id, {"text": "?", "state": "pending"})
            if task_id not in order:
                order.append(task_id)
            if given.get("subject"):
                task["text"] = given["subject"]
            if given.get("status"):
                status = given["status"].replace("_", " ")
                task["state"] = "skipped: deleted" if status == "deleted" else status
            note = (given.get("description") or "").strip()
            if note.lower().startswith("skipped"):
                task["state"] = "skipped: " + note.split(":", 1)[-1].strip()[:200]
        else:
            continue
        snapshots.append({"seq": event["seq"], "turn": event["turn"], "carrier": name, "items": [dict(tasks[t]) for t in order]})
    return snapshots


def text_worklist(events):
    return [{"seq": e["seq"], "turn": e["turn"], "carrier": "text", "items": items}
            for e in events if e["kind"] == "text" and (items := live.chat_worklist(e["text"]))]

def observed(rows):
    assistants = [e for e in rows if e.get("type") == "assistant"]
    return {"models": sorted({e.get("message", {}).get("model") for e in assistants} - {None, "<synthetic>"}),
            "efforts": sorted({e.get("perTurnEffort") or e.get("effort") for e in assistants} - {None})}


def first_reply(rows):
    for entry in rows:
        if entry.get("type") == "assistant":
            for block in blocks(entry):
                if block.get("type") == "text" and block.get("text", "").strip():
                    return block["text"]
    return None


def spawns(events, session_dir):
    metas = {}
    for meta in sorted((session_dir / "subagents").glob("*.meta.json")) if session_dir.is_dir() else []:
        data = json.loads(meta.read_text())
        metas[data.get("toolUseId")] = (data, meta)
    found = []
    for event in events:
        if event["kind"] != "tool_call" or event["name"] not in SPAWN_TOOLS:
            continue
        given = event["input"]
        meta, meta_path = metas.get(event["id"], ({}, None))
        agent_type = given.get("subagent_type") or meta.get("agentType")
        effort = agent_type.removeprefix("pstack-effort-") if agent_type and agent_type.startswith("pstack-effort-") else None
        prompt = given.get("prompt", "")
        persona = agent_type if agent_type and not effort else None
        if effort:
            persona = next((p for p in ("poteto-agent", "comment-sicko") if p in prompt[:2000]), None)
        transcript = Path(str(meta_path).removesuffix(".meta.json") + ".jsonl") if meta_path else None
        child = load_jsonl(transcript) if transcript and transcript.is_file() else None
        reply = first_reply(child) if child else None
        line = PERSONA_LINE.search(reply or "")
        found.append({"seq": event["seq"], "turn": event["turn"], "tool": event["name"], "subagent_type": agent_type, "persona": persona,
                      "model": given.get("model") or meta.get("model"), "effort": effort, "prompt_head": prompt[:300],
                      "transcript": str(transcript) if transcript else None,
                      "observed": observed(child) if child else None,
                      "x_child_first_reply": reply[:200] if reply else None,
                      "x_persona_line": line.group(1) if line else None})
    return found


def entry_state(entry_skill, init, rows):
    if not entry_skill:
        return "not-observed"
    if init and entry_skill not in (init.get("skills") or []) and entry_skill not in (init.get("slash_commands") or []):
        return "not-registered"
    for entry in rows:
        for block in blocks(entry) if entry.get("type") == "user" else []:
            if f"<command-name>/{entry_skill}</command-name>" in (block.get("text", "") if block.get("type") == "text" else ""):
                return "injected"
        for block in blocks(entry) if entry.get("type") == "assistant" else []:
            if block.get("type") == "tool_use" and block["name"] == "Skill" and block.get("input", {}).get("skill", "").lstrip("/") == entry_skill:
                return "injected"
    return "not-observed"


def injected_base(rows):
    for entry in rows:
        if entry.get("type") == "user" and entry.get("isMeta"):
            for block in blocks(entry):
                match = re.match(r"Base directory for this skill: (\S+)", block.get("text", ""))
                if match:
                    return match.group(1)
    return None


def host_skill_hits(paths):
    roots = [str(Path.home() / ".claude/skills"), str(Path.home() / ".agents/skills")]
    return sorted({root for p in paths if p.is_file() for root in roots if root in p.read_text(errors="replace")})


def harvest(run):
    session = run.turns[0]["session_id"] if run.turns else None
    transcripts = run.root / "transcripts"
    if session:
        move_session(store(), transcripts, session)
        forget_registry(session)
    main_paths = sorted(transcripts.glob(f"*/{session}.jsonl")) if session else []
    rows = load_jsonl(main_paths[0]) if main_paths else []
    session_dir = main_paths[0].with_suffix("") if main_paths else run.root / "missing"
    delegate_paths = sorted(session_dir.glob("subagents/*.jsonl")) if session_dir.is_dir() else []
    cwd = str(run.project)

    streams = [load_jsonl(t["stream"]) for t in run.turns if Path(t["stream"]).is_file()]
    init = next((e for s in streams for e in s if e.get("subtype") == "init"), {})
    results = [next((e for e in reversed(s) if e.get("type") == "result"), {}) for s in streams]
    events = lead_events(rows)
    reads_by = {"lead": files_read(rows, cwd)}
    for path in delegate_paths:
        reads_by[path.stem] = files_read(load_jsonl(path), cwd)
    state = entry_state(run.case.get("entry"), init, rows)
    if state == "not-observed" and any(p.endswith(f"/{run.case.get('entry')}/SKILL.md") for p in reads_by["lead"]):
        state = "read"
    tagged = tag_turns(rows)
    turn_entries = []
    for i in range(len(run.turns)):
        skill, _ = live.split_entry(run.case, run.case["turns"][i], i)
        if skill:
            turn_entries.append({"turn": i, "skill": skill,
                                 "entry": entry_state(skill, init, [e for t, e in tagged if t == i])})
    final = results[-1].get("result") if results else None
    if final is None:
        final = next((e["text"] for e in reversed(events) if e["kind"] == "text"), "")
    spawn_rows = spawns(events, session_dir)
    argvs = [t["argv"] for t in run.turns]
    requested = next((a[i + 1] for a in argvs[:1] for i, v in enumerate(a) if v == "--effort"), None)
    return {
        "harness": "claude-code",
        "cli_version": init.get("claude_code_version"),
        "model": init.get("model"),
        "effort": ",".join(observed(rows)["efforts"]) or requested,
        "argv": argvs[0] if argvs else [],
        "cwd": cwd,
        "exit_code": run.turns[-1]["exit_code"] if run.turns else None,
        "duration_s": round(sum(t["duration_s"] for t in run.turns), 1),
        "entry": state,
        "events": events,
        "files_read": list(dict.fromkeys(p for paths in reads_by.values() for p in paths)),
        "worklist": sorted(native_worklist(lead_events(rows)) + text_worklist(events), key=lambda s: s["seq"]),
        "spawns": spawn_rows,
        "final_reply": final,
        "transcript_paths": [str(p) for p in [*main_paths, *delegate_paths]],
        "x_session_id": session,
        "x_argvs": argvs,
        "x_turn_exit_codes": [t["exit_code"] for t in run.turns],
        "x_timed_out": any(t["timed_out"] for t in run.turns),
        "x_effort_requested": requested,
        "x_todo_tools": "on" if run.case.get("env", {}).get("todo_tools") else "off",
        "x_turn_entries": turn_entries,
        "x_entry_base_dir": injected_base(rows),
        "x_files_read_by": reads_by,
        "x_cost_usd": round(sum(r.get("total_cost_usd") or 0 for r in results), 4),
        "x_deferred_tools": next((e["attachment"].get("addedNames") for e in rows if e.get("type") == "attachment"
                                  and e["attachment"].get("type") == "deferred_tools_delta"), None),
        "x_init_tools": init.get("tools"),
        "x_host_skill_hits": host_skill_hits([*main_paths, *delegate_paths]),
    }
