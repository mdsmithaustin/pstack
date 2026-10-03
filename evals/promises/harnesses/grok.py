import datetime
import json
import os
import re
import shlex
import shutil
import subprocess
import urllib.parse
import uuid
from pathlib import Path

import live

SKILLS_DIR = ".agents/skills"
PRIVATE_DIRS = [".agents/"]
SHARES_HOST_TMP = True

DEFAULT_BIN = Path.home() / ".grok" / "bin" / "grok"
EFFORT = "high"
ENV_KEPT = ("PATH", "LANG", "LC_ALL", "LC_CTYPE", "LC_MESSAGES", "TERM", "USER", "LOGNAME", "SHELL", "TZ",
            "SSL_CERT_FILE", "SSL_CERT_DIR", "HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY",
            "http_proxy", "https_proxy", "no_proxy")
HOME_DIRS = (".config", ".local", ".cache", ".npm")
GITCONFIG = """[user]
\tname = dev
\temail = dev@example.com
[commit]
\tgpgsign = false
[init]
\tdefaultBranch = main
"""
SESSION_FILES = ("chat_history.jsonl", "events.jsonl", "usage.json", "summary.json", "tool_definitions.json")

AUTH_PROVIDER = """#!{python}
import datetime, json, sys
entry = next(v for v in json.load(open({auth!r})).values() if isinstance(v, dict) and v.get("key"))
expires = datetime.datetime.fromisoformat(entry["expires_at"].replace("Z", "+00:00"))
ttl = int((expires - datetime.datetime.now(datetime.timezone.utc)).total_seconds())
if ttl < 300:
    sys.exit("host grok token expires in under 5 minutes; run any grok command on the host to refresh it")
print(json.dumps({{"access_token": entry["key"], "expires_in": ttl}}))
"""

CONFIG = """[cli]
auto_update = false

[models]
default_reasoning_effort = "{effort}"

[auth]
auth_provider_command = "{provider}"

[skills]
ignore = [{ignored}]

[compat.claude]
skills = false
agents = false
hooks = false
mcps = false
rules = false

[compat.cursor]
skills = false
agents = false
hooks = false
mcps = false
rules = false

[compat.codex]
skills = false
hooks = false

[marketplace]
default_skills_installs_purged = true
official_marketplace_auto_installed = true
"""

READ_COMMANDS = {"cat", "head", "tail", "sed", "less", "more", "nl", "bat", "awk"}
TODO_STATES = {"pending": "pending", "in_progress": "in progress", "completed": "completed",
               "cancelled": "skipped: cancelled"}
PERSONA_LINE = re.compile(r"^persona: ([\w-]+)[ \t]*$", re.M)
USER_QUERY = re.compile(r"<user_query>\s*(.*?)\s*</user_query>", re.S)
SKILL_REF = re.compile(r'<skill name="([^"]+)"')


def host_home():
    return Path.home()


def host_grok_home():
    return Path(os.environ.get("GROK_HOME") or host_home() / ".grok")


def home(run):
    return run.root / "home"


def grok_home(run):
    return run.root / "grok-home"


def child_env(run):
    env = {k: os.environ[k] for k in ENV_KEPT if k in os.environ}
    env.update(HOME=str(home(run)), GROK_HOME=str(grok_home(run)), GROK_FOLDER_TRUST="0",
               TMPDIR=str(run.root / "tmp"))
    return env


def resolve_binary(env):
    candidates = [("GROK_BIN", os.environ.get("GROK_BIN")), ("PATH", shutil.which("grok", path=env.get("PATH"))),
                  ("default", str(DEFAULT_BIN))]
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
    raise RuntimeError(f"no working grok binary; rejected: {json.dumps(rejected)}")


def host_token_expiry(auth):
    data = json.loads(auth.read_text())
    entry = next((v for v in data.values() if isinstance(v, dict) and v.get("expires_at")), None)
    return datetime.datetime.fromisoformat(entry["expires_at"].replace("Z", "+00:00")) if entry else None


def prepare(run):
    root = run.root
    for name in ("home", "grok-home", "tmp", "transcripts"):
        (root / name).mkdir(exist_ok=True)
    for name in HOME_DIRS:
        (home(run) / name).mkdir(exist_ok=True)
    (home(run) / ".gitconfig").write_text(GITCONFIG)
    auth = host_grok_home() / "auth.json"
    if not auth.is_file():
        raise RuntimeError(f"no grok login at {auth}")
    expiry = host_token_expiry(auth)
    if expiry is not None and expiry <= datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=5):
        raise RuntimeError(f"the host Grok token expired at {expiry:%Y-%m-%dT%H:%MZ}; run `grok login` on the host, "
                           "since the run's read-only provider never refreshes it")
    provider = root / "auth-provider.py"
    provider.write_text(AUTH_PROVIDER.format(python=shutil.which("python3") or "/usr/bin/python3", auth=str(auth)))
    provider.chmod(0o755)
    ignored = ", ".join(json.dumps(str(host_home() / d)) for d in
                        (".agents/skills", ".claude/skills", ".grok/skills", ".cursor/skills", ".codex/skills"))
    (grok_home(run) / "config.toml").write_text(CONFIG.format(effort=EFFORT, provider=provider, ignored=ignored))

    env = child_env(run)
    launch = resolve_binary(env)
    login = subprocess.run([launch["path"], "login"], env=env, stdin=subprocess.DEVNULL, capture_output=True,
                           text=True, timeout=120)
    (root / "login.log").write_text(login.stdout + login.stderr)
    if login.returncode != 0:
        raise RuntimeError(f"grok login failed under the run's own home: {(login.stdout + login.stderr)[-300:]}")
    inspected = subprocess.run([launch["path"], "inspect", "--json"], cwd=run.project, env=env,
                               capture_output=True, text=True, timeout=120, check=True)
    (root / "inspect.json").write_text(inspected.stdout)
    inspect = json.loads(inspected.stdout)
    launch["cli_version"] = inspect.get("grokVersion")
    outside = sorted({s["source"].get("path", "") for s in inspect.get("skills", [])
                      if s["source"].get("type") not in ("builtin", "bundled")
                      and not s["source"].get("path", "").startswith(str(run.project / SKILLS_DIR))})
    launch["host_skills"] = outside
    (root / "launch.json").write_text(json.dumps(launch, indent=1) + "\n")
    if outside:
        raise RuntimeError(f"grok discovers skills outside the run's skills tree: {outside[:5]}")


def session_files(run):
    return sorted((grok_home(run) / "sessions").glob("*/*/chat_history.jsonl"))


def turn(run, text, index):
    launch = json.loads((run.root / "launch.json").read_text())
    skill, rest = live.split_entry(run.case, text, index)
    prompt = f"/{skill} {rest}".rstrip() if skill else text
    transcripts = run.root / "transcripts"
    stream, errors = (transcripts / f"turn-{index}.{ext}" for ext in ("json", "err"))
    if index:
        session = next((t["session_id"] for t in reversed(run.turns) if t.get("session_id")), None)
        if not session:
            raise RuntimeError("no session id from an earlier turn to resume")
        session_args = ["--resume", session]
    else:
        session = str(uuid.uuid4())
        session_args = ["--session-id", session]
    tools = [] if run.case.get("env", {}).get("todo_tools") is not False else ["--disallowed-tools", "todo_write"]
    argv = [launch["path"], "-p", prompt, "--cwd", run.project, "--always-approve", "--effort", EFFORT,
            "--output-format", "json", *tools, *session_args]
    record = live.execute(argv, run.project, child_env(run), run.timeout_s, stream, errors)
    record.update(index=index, session_id=session, stream=str(stream), stderr=str(errors),
                  grok_bin=launch["path"], grok_bin_source=launch["source"])
    return record


def load_jsonl(path):
    rows = []
    if Path(path).is_file():
        for line in Path(path).read_text(errors="replace").splitlines():
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def text_of(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(part.get("text", "") for part in content if isinstance(part, dict))
    return ""


def shell_reads(command, cwd):
    paths, segments = [], []
    for line in command.splitlines():
        lexer = shlex.shlex(line, posix=True, punctuation_chars=";&|<>")
        lexer.whitespace_split = True
        try:
            tokens = list(lexer)
        except ValueError:
            continue
        current = []
        for tok in tokens:
            if tok and set(tok) <= set(";&|"):
                segments.append(current)
                current = []
            else:
                current.append(tok)
        segments.append(current)
    for seg in segments:
        while seg and ("=" in seg[0] and not seg[0].startswith("-")):
            seg = seg[1:]
        if not seg or os.path.basename(seg[0]) not in READ_COMMANDS:
            continue
        name = os.path.basename(seg[0])
        args = seg[1:]
        skip_script = name in ("sed", "awk") and not any(a in ("-e", "-f") for a in args)
        after_redirect = False
        for arg in args:
            if after_redirect:
                after_redirect = False
                continue
            if arg in (">", ">>", "<", "2>", "&>"):
                after_redirect = arg != "<"
                continue
            if arg.startswith("-"):
                continue
            if skip_script:
                skip_script = False
                continue
            if re.fullmatch(r"\d+", arg):
                continue
            full = arg if os.path.isabs(arg) else os.path.normpath(os.path.join(cwd or "", arg))
            if os.path.isfile(full):
                paths.append(full)
    return paths


def turn_prompts(run):
    prompts = []
    for record in run.turns:
        argv = record.get("argv") or []
        prompts.append(argv[argv.index("-p") + 1] if "-p" in argv else "")
    return prompts


def turn_of_prompt(prompt, prompts, previous):
    matches = [index for index, known in enumerate(prompts) if known.strip() == prompt.strip() and index > previous]
    return matches[0] if matches else previous + 1


def turns_without_events(events, turn_count):
    return [turn for turn in range(turn_count) if not any(e.get("turn") == turn for e in events)]


def text_worklist(text):
    return live.chat_worklist(text)

def todo_snapshot(args, previous):
    merged = {t["id"]: dict(t) for t in previous} if args.get("merge") else {}
    order = list(merged) if args.get("merge") else []
    for todo in args.get("todos") or []:
        key = todo.get("id") or str(len(order))
        if key in merged:
            merged[key].update({k: v for k, v in todo.items() if v is not None})
        else:
            merged[key] = dict(todo)
            order.append(key)
    return [merged[k] for k in order]


def parse_session(chat_path, cwd, entry_skill, lead=False, prompts=()):
    events, files, worklist, spawns, names = [], [], [], [], {}
    model = effort = final = first_reply = None
    turn, turn_skills = 0, []
    injected = False
    read_entry = False
    todos = []
    injection = re.compile(rf'<skill name="{re.escape(entry_skill)}"[^>]*args=') if entry_skill else None

    def mark():
        return {"turn": turn} if lead else {}

    def add(event):
        event["seq"] = len(events)
        event.update(mark())
        events.append(event)
        return event["seq"]

    for rec in load_jsonl(chat_path):
        kind = rec.get("type")
        if kind == "user" and not rec.get("synthetic_reason") and lead and (
                "prompt_index" in rec or USER_QUERY.search(text_of(rec.get("content")))):
            body = text_of(rec.get("content"))
            query = USER_QUERY.search(body)
            prompt = query.group(1) if query else body
            turn = rec["prompt_index"] if "prompt_index" in rec else turn_of_prompt(prompt, prompts, turn if events else -1)
            add({"kind": "user", "text": prompt})
            turn_skills += [{"turn": turn, "skill": name} for name in SKILL_REF.findall(body)]
        if kind == "user" and not rec.get("synthetic_reason") and injection and injection.search(text_of(rec.get("content"))):
            injected = True
        elif kind == "assistant":
            model = rec.get("model_id") or model
            effort = rec.get("reasoning_effort") or effort
            content = text_of(rec.get("content"))
            if content.strip():
                seq = add({"kind": "text", "text": content})
                final = content
                first_reply = first_reply or content
                items = text_worklist(content)
                if items:
                    worklist.append({"seq": seq, **mark(), "carrier": "text", "items": items})
            for call in rec.get("tool_calls") or []:
                try:
                    args = json.loads(call.get("arguments") or "{}")
                except json.JSONDecodeError:
                    args = {"_raw": call.get("arguments")}
                name = call.get("name")
                names[call.get("id")] = name
                seq = add({"kind": "tool_call", "name": name, "input": args, "id": call.get("id")})
                reads = []
                if name == "read_file" and args.get("target_file"):
                    path = args["target_file"]
                    reads = [path if os.path.isabs(path) else os.path.normpath(os.path.join(cwd, path))]
                elif name == "run_terminal_command":
                    reads = shell_reads(args.get("command", ""), cwd)
                elif name == "todo_write":
                    todos = todo_snapshot(args, todos)
                    worklist.append({"seq": seq, **mark(), "carrier": name, "items": [
                        {"text": t.get("content", ""), "state": TODO_STATES.get(t.get("status"), t.get("status") or "pending")}
                        for t in todos]})
                elif name == "spawn_subagent":
                    desc = args.get("description") or ""
                    tag = re.match(r"\s*\[([^\]]+)\]", desc)
                    spawns.append({"seq": seq, **mark(), "tool": name, "persona": tag.group(1) if tag else None,
                                   "model": args.get("model"), "effort": args.get("reasoning_effort"),
                                   "prompt_head": (args.get("prompt") or "")[:300], "x_description": desc,
                                   "x_background": args.get("background"), "x_resume_from": args.get("resume_from")})
                files.extend(reads)
                if entry_skill and any(p.endswith(f"{entry_skill}/SKILL.md") for p in reads):
                    read_entry = True
        elif kind == "tool_result":
            content = text_of(rec.get("content"))
            ok = not re.match(r"\s*(error|Error:|failed|Tool execution failed)", content or "")
            add({"kind": "tool_result", "name": names.get(rec.get("tool_call_id")), "ok": ok,
                 "output_head": (content or "")[:400], "id": rec.get("tool_call_id")})
    return {"events": events, "files_read": list(dict.fromkeys(files)), "worklist": worklist, "spawns": spawns,
            "final_reply": final, "model": model, "effort": effort, "injected": injected, "read_entry": read_entry,
            "first_reply": first_reply, "turn_skills": turn_skills}


def decoded_cwd(chat_path):
    return urllib.parse.unquote(chat_path.parent.parent.name)


def copy_session(session_dir, destination):
    target = destination / session_dir.parent.name / session_dir.name
    target.mkdir(parents=True, exist_ok=True)
    copied = []
    for name in SESSION_FILES:
        if (session_dir / name).is_file():
            shutil.copy2(session_dir / name, target / name)
            copied.append(str(target / name))
    for meta in sorted(session_dir.glob("subagents/*/meta.json")):
        out = target / "subagents" / meta.parent.name
        out.mkdir(parents=True, exist_ok=True)
        shutil.copy2(meta, out / "meta.json")
        copied.append(str(out / "meta.json"))
    return copied


def entry_state(run, lead):
    skill = run.case.get("entry")
    if not skill:
        return "not-observed"
    if not (run.project / SKILLS_DIR / skill / "SKILL.md").is_file():
        return "not-registered"
    if lead["injected"]:
        return "injected"
    return "read" if lead["read_entry"] else "not-observed"


def turn_entries(run, lead):
    found = []
    for index, text in enumerate(run.case["turns"][:len(run.turns)]):
        skill = live.split_entry(run.case, text, index)[0]
        if not skill:
            continue
        if not (run.project / SKILLS_DIR / skill / "SKILL.md").is_file():
            state = "not-registered"
        elif {"turn": index, "skill": skill} in lead["turn_skills"]:
            state = "injected"
        else:
            state = "not-observed"
        found.append({"turn": index, "skill": skill, "entry": state})
    return found


def host_skill_hits(paths):
    roots = [str(host_home() / d) for d in (".claude/skills", ".agents/skills", ".grok/skills", ".cursor/skills", ".codex/skills")]
    return sorted({root for p in paths if Path(p).is_file() for root in roots if root in Path(p).read_text(errors="replace")})


def harvest(run):
    chats = session_files(run)
    lead_ids = list(dict.fromkeys(t["session_id"] for t in run.turns if t.get("session_id")))
    leads = [c for c in chats if c.parent.name in lead_ids]
    children = [c for c in chats if c not in leads]
    transcripts = run.root / "transcripts" / "sessions"
    copied = [p for c in [*leads, *children] for p in copy_session(c.parent, transcripts)]
    entry = run.case.get("entry")
    cwd = str(run.project)
    empty = {"events": [], "files_read": [], "worklist": [], "spawns": [], "final_reply": None,
             "model": None, "effort": None, "injected": False, "read_entry": False,
             "first_reply": None, "turn_skills": []}
    lead = parse_session(leads[0], decoded_cwd(leads[0]), entry, lead=True, prompts=turn_prompts(run)) if leads else empty
    launch = json.loads((run.root / "launch.json").read_text()) if (run.root / "launch.json").is_file() else {}

    metas = {}
    for lead_chat in leads:
        for meta_path in lead_chat.parent.glob("subagents/*/meta.json"):
            metas[meta_path] = json.loads(meta_path.read_text())
    subagents, matched, first_replies = [], set(), {}
    for chat in children:
        child = parse_session(chat, decoded_cwd(chat), entry)
        first_replies[chat.parent.name] = child["first_reply"]
        meta = next((m for m in metas.values() if m.get("child_session_id") == chat.parent.name), {})
        matched.add(chat.parent.name)
        subagents.append({
            "session_id": chat.parent.name, "parent_session_id": meta.get("parent_session_id"),
            "cwd": decoded_cwd(chat), "worktree": "/worktrees/" in decoded_cwd(chat),
            "subagent_type": meta.get("subagent_type"), "description": meta.get("description"),
            "model": child["model"] or meta.get("effective_model_id"), "effort": child["effort"],
            "files_read": child["files_read"], "worklist": child["worklist"], "spawns": child["spawns"],
            "event_count": len(child["events"]), "final_reply": child["final_reply"], "chat": str(chat)})
    by_description = list(metas.values())
    for spawn in lead["spawns"]:
        for i, meta in enumerate(by_description):
            if meta.get("description") == spawn["x_description"] and (meta.get("prompt") or "")[:300] == spawn["prompt_head"]:
                spawn["model"] = spawn["model"] or meta.get("effective_model_id")
                spawn["x_child_session_id"] = meta.get("child_session_id")
                by_description.pop(i)
                break
    for spawn in lead["spawns"]:
        reply = first_replies.get(spawn.get("x_child_session_id"))
        line = PERSONA_LINE.search(reply or "")
        spawn["x_child_first_reply"] = reply[:200] if reply else None
        spawn["x_persona_line"] = line.group(1) if line else None
    for spawn in lead["spawns"]:
        for key in ("x_description", "x_background", "x_resume_from"):
            spawn.pop(key, None)

    last = run.turns[-1] if run.turns else {}
    all_paths = [Path(p) for p in copied] + [Path(t["stream"]) for t in run.turns if t.get("stream")]
    return {
        "harness": "grok",
        "cli_version": launch.get("cli_version") or launch.get("version"),
        "model": lead["model"],
        "effort": lead["effort"] or EFFORT,
        "argv": run.turns[0]["argv"] if run.turns else [],
        "cwd": cwd,
        "exit_code": last.get("exit_code"),
        "duration_s": round(sum(t.get("duration_s", 0) for t in run.turns), 1),
        "entry": entry_state(run, lead),
        "events": lead["events"],
        "files_read": lead["files_read"],
        "worklist": lead["worklist"],
        "spawns": lead["spawns"],
        "final_reply": lead["final_reply"],
        "transcript_paths": [str(p) for p in all_paths if p.is_file()],
        "x_binary": {k: launch.get(k) for k in ("path", "source", "version", "rejected")},
        "x_turns": [{k: t.get(k) for k in ("index", "session_id", "argv", "exit_code", "timed_out", "duration_s")}
                    for t in run.turns],
        "x_session_ids": lead_ids,
        "x_todo_tools": "off" if run.case.get("env", {}).get("todo_tools") is False else "on",
        "x_turn_entries": turn_entries(run, lead),
        "x_turns_without_events": turns_without_events(lead["events"], len(run.turns)),
        "x_subagents": subagents,
        "x_unlinked_children": sorted(s["session_id"] for s in subagents if not s["parent_session_id"]),
        "x_host_skill_hits": host_skill_hits(all_paths),
        "x_cost_usd_lead": lead_cost(leads),
        "x_timed_out": any(t.get("timed_out") for t in run.turns),
    }


def lead_cost(leads):
    ticks = 0
    for chat in leads:
        usage = chat.parent / "usage.json"
        if usage.is_file():
            try:
                ticks += json.loads(usage.read_text()).get("session", {}).get("costUsdTicks", 0) or 0
            except (json.JSONDecodeError, AttributeError):
                pass
    return round(ticks / 1e10, 4)
