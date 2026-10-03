import json
import os
import re
import shlex
import shutil
import sqlite3
import subprocess
from pathlib import Path

import live

SKILLS_DIR = ".agents/skills"
PRIVATE_DIRS = [".agents"]
SHARES_HOST_TMP = False

GATEWAY_CONTAINER = "hermes-default-gateway"
HERMES_BIN = "/opt/hermes/.venv/bin/hermes"
PYTHON_BIN = "/opt/hermes/.venv/bin/python"
TOOLSETS = ("delegation", "file", "skills", "terminal", "todo")
USER_HERMES = Path.home() / ".hermes"
DOCKER_ENV_KEYS = ("PATH", "HOME", "DOCKER_HOST", "DOCKER_CONTEXT", "DOCKER_CONFIG")

PRELOAD_CHECK = """
import json, sys
sys.path.insert(0, "/opt/hermes")
from agent.skill_commands import build_preloaded_skills_prompt
text, loaded, missing = build_preloaded_skills_prompt([sys.argv[1]])
print(json.dumps({"loaded": loaded, "missing": missing, "chars": len(text)}))
"""

CONFIG = """{model}agent:
  max_turns: 90
  reasoning_effort: high
terminal:
  backend: local
  cwd: {project}
  timeout: 300
skills:
  trusted_project_dirs:
    - {project}
delegation:
  max_concurrent_children: 4
  max_spawn_depth: 1
  subagent_auto_approve: true
  oneshot_max_children: 0
platform_toolsets:
  cli:
{toolsets}{tools}"""
EAGER_TOOLS = 'tools:\n  tool_search:\n    enabled: "off"\n'

PERSONA_LINE = re.compile(r"^persona: ([\w-]+)[ \t]*$", re.M)
READ_COMMANDS = {"cat", "head", "tail", "sed", "nl", "less", "more", "awk", "bat", "wc", "grep", "rg", "diff", "cmp"}
TODO_STATES = {"pending": "pending", "in_progress": "in progress", "completed": "completed"}


def toolsets(run):
    off = run.case.get("env", {}).get("todo_tools") is False
    return [t for t in TOOLSETS if not (off and t == "todo")]


def profile(run):
    return run.root / "hroot" / "profiles" / "probe"


def transcripts(run):
    return run.root / "transcripts"


def hermes_image():
    if os.environ.get("HERMES_IMAGE"):
        return os.environ["HERMES_IMAGE"]
    fmt = "{{.Config.Image}}\n{{.Image}}"
    probe = subprocess.run(["docker", "inspect", GATEWAY_CONTAINER, "--format", fmt], capture_output=True, text=True)
    if probe.returncode:
        raise RuntimeError(f"no Hermes image: set HERMES_IMAGE or run the {GATEWAY_CONTAINER} container "
                           f"({probe.stderr.strip()})")
    ref, image_id = probe.stdout.split()
    return ref if "@sha256:" in ref else image_id


def user_model_block():
    text = (USER_HERMES / "config.yaml").read_text(encoding="utf-8")
    found = re.search(r"^model:\n(?:[ \t]+.*\n)+", text, re.M)
    if not found:
        raise RuntimeError(f"{USER_HERMES / 'config.yaml'} has no `model:` mapping to copy")
    return found.group(0)


def docker_env():
    return {k: os.environ[k] for k in DOCKER_ENV_KEYS if k in os.environ}


def container_argv(run, name, image, entrypoint, args):
    auth = profile(run).parents[1] / "auth.json"
    env = {"HOME": run.root / "home", "HERMES_HOME": profile(run), "TERMINAL_CWD": run.project,
           "HERMES_WRITE_SAFE_ROOT": f"{run.project}:{profile(run) / 'cache'}", "TMPDIR": run.root / "tmp"}
    flags = [x for k, v in env.items() for x in ("-e", f"{k}={v}")]
    return ["docker", "run", "--rm", "-i", "--init", "--name", name, "--entrypoint", entrypoint,
            "-v", f"{run.root}:{run.root}", "-v", f"{USER_HERMES / 'auth.json'}:{auth}:ro",
            *flags, "-w", run.project, image, *args]


def container_name(run, tag):
    return f"pstack-hermes-{run.root.name}-{tag}"


def run_in_container(run, tag, entrypoint, args, timeout_s=120):
    argv = container_argv(run, container_name(run, tag), hermes_image(), entrypoint, args)
    done = subprocess.run(argv, capture_output=True, text=True, timeout=timeout_s, env=docker_env())
    if done.returncode:
        raise RuntimeError(f"docker run {tag} exited {done.returncode}: {(done.stderr or done.stdout).strip()[-300:]}")
    return done.stdout.strip()


def prepare(run):
    if not (USER_HERMES / "auth.json").is_file():
        raise RuntimeError(f"{USER_HERMES / 'auth.json'} is missing; log in to Hermes first")
    home = profile(run)
    for d in (home, run.root / "home", run.root / "tmp", transcripts(run)):
        d.mkdir(parents=True, exist_ok=True)
    (home / ".no-bundled-skills").touch()
    (home.parents[1] / "auth.json").touch()
    eager = run.case.get("env", {}).get("todo_tools") is not False
    (home / "config.yaml").write_text(CONFIG.format(
        model=user_model_block(), project=run.project,
        toolsets="".join(f"    - {t}\n" for t in toolsets(run)),
        tools=EAGER_TOOLS if eager else ""))
    entry = run.case.get("entry")
    skills = list(dict.fromkeys(s for i, text in enumerate(run.case["turns"])
                                for s in [live.split_entry(run.case, text, i)[0]] if s))
    preloads = {}
    for skill in skills:
        out = run_in_container(run, f"preload-{skill}", PYTHON_BIN, ["-c", PRELOAD_CHECK, skill])
        preloads[skill] = json.loads(out.splitlines()[-1]) if out else {"loaded": [], "missing": [skill]}
    preload = preloads.get(entry, {})
    version = run_in_container(run, "version", HERMES_BIN, ["--version"])
    (run.root / "hermes.json").write_text(json.dumps({
        "image": hermes_image(), "cli_version": version.splitlines()[0] if version else None,
        "entry": entry, "preload": preload, "preloads": preloads, "todo_eager": eager,
        "todo_tools": "off" if run.case.get("env", {}).get("todo_tools") is False else "on"}, indent=1) + "\n")


def session_id_of(stdout_path):
    found = None
    for line in Path(stdout_path).read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith("{"):
            try:
                event = json.loads(line)
            except ValueError:
                continue
            if event.get("type") in ("system", "result") and event.get("session_id"):
                found = found or event["session_id"]
        elif line.startswith("session_id: "):
            found = found or line.split(": ", 1)[1].strip()
    return found


def turn(run, text, index):
    skill, rest = live.split_entry(run.case, text, index)
    entry = run.case.get("entry")
    sessions = [t.get("session_id") for t in run.turns if t.get("session_id")]
    if index and not sessions:
        raise RuntimeError(f"turn {index} cannot resume: no earlier turn reported a Hermes session id")
    query = rest or f"/{skill}"
    args = ["chat", "-Q", f"--query={query}", "--format", "stream-json", "--reasoning", "high",
            "-t", ",".join(toolsets(run)), "--yolo", "--run-budget", str(max(30, int(run.timeout_s * 0.9)))]
    for name in dict.fromkeys(n for n in (entry, skill) if n):
        args += ["-s", name]
    if index:
        args += ["--resume", sessions[0]]
    image = hermes_image()
    name = container_name(run, f"turn{index}")
    stream, stderr = (transcripts(run) / f"turn-{index}.{ext}" for ext in ("stream.jsonl", "stderr.txt"))
    try:
        record = live.execute(container_argv(run, name, image, HERMES_BIN, args), run.project, docker_env(),
                              run.timeout_s, stream, stderr)
    finally:
        subprocess.run(["docker", "rm", "-f", name], capture_output=True, env=docker_env())
    return {**record, "hermes_argv": ["hermes", *args], "image": image, "session_id": session_id_of(stream),
            "stream": str(stream)}


def parse_json(text):
    try:
        return json.loads(text) if text else None
    except ValueError:
        return None


def resolve_path(path, cwd):
    p = Path(os.path.expanduser(path))
    return str((p if p.is_absolute() else Path(cwd) / p).resolve())


def shell_reads(command, cwd):
    found = []
    for segment in re.split(r"&&|\|\||;|\||\n", command):
        try:
            words = shlex.split(segment)
        except ValueError:
            continue
        if words[:1] == ["cd"] and len(words) > 1:
            cwd = resolve_path(words[1], cwd)
            continue
        if not words or Path(words[0]).name not in READ_COMMANDS:
            continue
        for w in words[1:]:
            if w.startswith("-") or not re.search(r"[/.]", w):
                continue
            full = resolve_path(w, cwd)
            if os.path.isfile(full):
                found.append(full)
    return found


def tool_reads(name, args, result, cwd):
    if name == "read_file" and args.get("path"):
        return [resolve_path(args["path"], cwd)]
    if name == "skill_view" and isinstance(result, dict) and result.get("skill_dir"):
        return [str(Path(result["skill_dir"]) / (args.get("file_path") or "SKILL.md"))]
    if name == "terminal" and args.get("command"):
        return shell_reads(args["command"], args.get("workdir") or cwd)
    return []


def result_ok(content):
    obj = parse_json(content)
    if not isinstance(obj, dict):
        return True
    return not (obj.get("success") is False or obj.get("error")) and obj.get("exit_code") in (None, 0)


def unwrap_bridge(name, args):
    """`tool_call` is Hermes' bridge to deferred tools; report each tool it invokes."""
    if name != "tool_call" or not isinstance(args, dict):
        return [(name, args)]
    calls = args.get("calls") if isinstance(args.get("calls"), list) else [args]
    out = []
    for c in calls:
        inner_args = c.get("arguments") or {}
        if isinstance(inner_args, str):
            inner_args = parse_json(inner_args) or {"_raw": inner_args}
        if c.get("name"):
            out.append((str(c["name"]), inner_args))
    return out or [(name, args)]


def find_todos(obj):
    if isinstance(obj, dict):
        if isinstance(obj.get("todos"), list):
            return obj["todos"]
        values = obj.values()
    elif isinstance(obj, list):
        values = obj
    else:
        return None
    for v in values:
        found = find_todos(v)
        if found is not None:
            return found
    return None


def todo_items(todos):
    return [{"text": t.get("content", ""), "state": TODO_STATES.get(t.get("status", "pending"),
                                                                  f"skipped: {t.get('status')}")} for t in todos]


def text_worklist(text):
    return live.chat_worklist(text) or []

def session_rows(con):
    con.row_factory = sqlite3.Row
    rows = [dict(r) for r in con.execute("select * from sessions order by started_at")]
    for r in rows:
        r["model_config"] = parse_json(r.get("model_config")) or {}
        r["delegate_from"] = r["parent_session_id"] or r["model_config"].get("_delegate_from")
    return rows


def walk(con, session):
    cwd = session.get("cwd") or "/"
    pending = {}
    rows = con.execute("select * from messages where session_id=? order by id", (session["id"],))
    for m in map(dict, rows):
        if m["role"] == "user":
            if (m["content"] or "").strip():
                yield {"kind": "user", "text": m["content"]}, [], None
        elif m["role"] == "assistant":
            if (m["content"] or "").strip():
                yield {"kind": "text", "text": m["content"]}, [], None
            for call in parse_json(m["tool_calls"]) or []:
                fn = call.get("function") or {}
                args = parse_json(fn.get("arguments")) or {}
                inner = unwrap_bridge(fn.get("name", "unknown"), args)
                call_id = call.get("id") or call.get("call_id")
                single = len(inner) == 1
                pending[call_id] = (*inner[0], single) if single else ("tool_call", args, single)
                for name, inner_args in inner:
                    yield {"kind": "tool_call", "name": name, "input": inner_args, **({"id": call_id} if single else {})}, [], None
        elif m["role"] == "tool":
            name, args, single = pending.get(m["tool_call_id"], (m["tool_name"] or "unknown", {}, False))
            content = m["content"] or ""
            result = parse_json(content)
            yield ({"kind": "tool_result", "name": name, "ok": result_ok(content), "output_head": content[:400],
                    **({"id": m["tool_call_id"]} if single else {})}, tool_reads(name, args, result, cwd), result)


def copy_state(run):
    dest = transcripts(run)
    dest.mkdir(parents=True, exist_ok=True)
    for suffix in ("", "-wal", "-shm"):
        src = profile(run) / f"state.db{suffix}"
        if src.exists():
            shutil.copy2(src, dest / f"state.db{suffix}")
    return dest / "state.db"


def first_user_text(con, session):
    row = con.execute("select content from messages where session_id=? and role='user' order by id limit 1", (session["id"],)).fetchone()
    return (row[0] or "").strip() if row else ""


def match_child(con, children, claimed, task, outcome):
    free = [c for c in children if c["id"] not in claimed]
    usage = (outcome or {}).get("tokens") or {}
    if outcome and usage:
        for c in free:
            if (c.get("api_call_count") == outcome.get("api_calls") and c.get("output_tokens") == usage.get("output")
                    and (c.get("input_tokens") or 0) + (c.get("cache_read_tokens") or 0) == usage.get("input")):
                return c, "usage"
    goal = (task.get("goal") or "").strip()
    for c in free:
        if goal and first_user_text(con, c) == goal:
            return c, "goal"
    return (free[0], "order") if free else (None, None)


def first_reply(con, session):
    return next((e["text"] for e, _, _ in walk(con, session) if e["kind"] == "text"), None)


def turn_entries(run, meta):
    found = []
    for index, text in enumerate(run.case["turns"][:len(run.turns)]):
        skill = live.split_entry(run.case, text, index)[0]
        if skill:
            check = meta["preloads"].get(skill, {})
            state = "injected" if skill in check.get("loaded", []) else "not-registered" if skill in check.get("missing", []) else "not-observed"
            found.append({"turn": index, "skill": skill, "entry": state})
    return found


def entry_kind(entry, preload, events):
    if not entry:
        return "not-observed"
    if entry in preload.get("loaded", []):
        return "injected"
    if entry in preload.get("missing", []):
        return "not-registered"
    for e in events:
        if e["kind"] == "tool_call" and (e["input"].get("name") == entry or f"{entry}/SKILL.md" in json.dumps(e["input"])):
            return "read"
    return "not-observed"


def harvest(run):
    meta = json.loads((run.root / "hermes.json").read_text())
    db = copy_state(run)
    stream_files = sorted(str(p) for p in transcripts(run).glob("turn-*"))
    roots = list(dict.fromkeys(t["session_id"] for t in run.turns if t.get("session_id")))
    events, files_read, worklist, spawn_calls, spawns = [], [], [], [], []
    root_row, children, error = {}, [], None
    try:
        con = sqlite3.connect(db)
        rows = session_rows(con)
        by_id = {r["id"]: r for r in rows}
        root_rows = [by_id[i] for i in roots if i in by_id]
        root_row = root_rows[-1] if root_rows else {}
        children = [r for r in rows if r["delegate_from"] in roots]
        turn = -1
        for session in root_rows:
            for event, reads, result in walk(con, session):
                seq = len(events)
                turn += event["kind"] == "user"
                events.append({"seq": seq, "turn": max(turn, 0), **event})
                files_read.extend(reads)
                if event["kind"] == "tool_result" and event["name"] == "todo_list":
                    todos = find_todos(result)
                    if todos is not None:
                        worklist.append({"seq": seq, "turn": events[seq]["turn"], "carrier": "todo_list", "items": todo_items(todos)})
                if event["kind"] == "text" and (items := text_worklist(event["text"])):
                    worklist.append({"seq": seq, "turn": events[seq]["turn"], "carrier": "text", "items": items})
                if event["kind"] == "tool_call" and event["name"] == "delegate_task":
                    spawn_calls.append({"seq": seq, "args": event["input"], "ok": None, "turn": events[seq]["turn"],
                                        "id": event.get("id"), "result": None})
                if event["kind"] == "tool_result" and event["name"] == "delegate_task":
                    waiting = next((c for c in spawn_calls if c["ok"] is None and (not event.get("id") or c["id"] == event["id"])), None)
                    if waiting:
                        waiting["ok"], waiting["result"] = event["ok"], result
        claimed = set()
        for call in spawn_calls:
            seq, args, spawn_turn = call["seq"], call["args"], call["turn"]
            if call["ok"] is False:
                continue
            tasks = args.get("tasks") or ([{"goal": args["goal"], "context": args.get("context", "")}]
                                          if args.get("goal") else [])
            outcomes = {r.get("task_index"): r for r in (call["result"] or {}).get("results") or [] if isinstance(r, dict)}
            for index, task in enumerate(tasks):
                child, matched = match_child(con, children, claimed, task, outcomes.get(index))
                claimed.add(child["id"] if child else None)
                brief = f"{task.get('goal', '')}\n{task.get('context', '')}"
                reply = first_reply(con, child) if child else None
                line = PERSONA_LINE.search(reply or "")
                spawns.append({
                    "seq": seq, "turn": spawn_turn, "tool": "delegate_task",
                    "persona": "poteto-agent" if "poteto-agent" in brief else None,
                    "model": child["model"] if child else None,
                    "effort": ((child or {}).get("model_config", {}).get("reasoning_config") or {}).get("effort"),
                    "prompt_head": brief[:300], "x_child_first_reply": reply[:200] if reply else None,
                    "x_persona_line": line.group(1) if line else None,
                    "x_child_session": child["id"] if child else None, "x_child_match": matched})
        for child in children:
            for _, reads, _ in walk(con, child):
                files_read.extend(reads)
        con.close()
    except sqlite3.DatabaseError as exc:
        error = f"{type(exc).__name__}: {exc}"
    texts = [e["text"] for e in events if e["kind"] == "text"]
    argv = (run.turns[0].get("hermes_argv") if run.turns else None) or []
    effort = ((root_row.get("model_config") or {}).get("reasoning_config") or {}).get("effort")
    trace = {
        "harness": "hermes",
        "cli_version": meta["cli_version"],
        "model": root_row.get("model"),
        "effort": effort or ("high" if argv else None),
        "argv": argv,
        "cwd": root_row.get("cwd") or str(run.project),
        "exit_code": run.turns[-1].get("exit_code") if run.turns else None,
        "duration_s": round(sum(t.get("duration_s", 0) for t in run.turns), 1),
        "entry": entry_kind(meta["entry"], meta["preload"], events),
        "events": events,
        "files_read": list(dict.fromkeys(files_read)),
        "worklist": worklist,
        "spawns": spawns,
        "final_reply": texts[-1] if texts else "",
        "transcript_paths": [str(db), *stream_files],
        "x_image": meta["image"],
        "x_session_ids": roots,
        "x_delegate_sessions": [c["id"] for c in children],
        "x_turn_argvs": [t.get("hermes_argv") for t in run.turns],
        "x_todo_eager": meta["todo_eager"],
        "x_todo_tools": meta.get("todo_tools", "on"),
        "x_turn_entries": turn_entries(run, meta) if "preloads" in meta else [],
    }
    if error:
        trace["x_harvest_error"] = error
    return trace
