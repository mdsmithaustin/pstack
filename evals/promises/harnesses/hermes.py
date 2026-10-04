import json
import os
import re
import shlex
import posixpath
import uuid
from pathlib import Path

import live
from harnesses.hermes_evidence import (HermesEvidence, RunBinding, NativeSetup, NativeTurn,
    IncompleteEvidence, thaw, TOOLSETS, USER_HERMES)

SKILLS_DIR = ".agents/skills"
PRIVATE_DIRS = [".agents"]
SHARES_HOST_TMP = False

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


def user_model_block():
    text = (USER_HERMES / "config.yaml").read_text(encoding="utf-8")
    found = re.search(r"^model:\n(?:[ \t]+.*\n)+", text, re.M)
    if not found:
        raise RuntimeError(f"{USER_HERMES / 'config.yaml'} has no `model:` mapping to copy")
    return found.group(0)


def prepare(run):
    parent = getattr(run, "hermes_retain_out", None) or run.root.parent
    owner = HermesEvidence.bind(RunBinding(uuid.uuid4().hex, run.root, run.project, parent), run.timeout_s)
    run._hermes_evidence = owner
    if not (USER_HERMES / "auth.json").is_file():
        raise RuntimeError(f"{USER_HERMES / 'auth.json'} is missing; log in to Hermes first")
    skills = tuple(dict.fromkeys(s for i, text in enumerate(run.case["turns"])
                               for s in [live.split_entry(run.case, text, i)[0]] if s))
    eager = run.case.get("env", {}).get("todo_tools") is not False
    owner.prepare(NativeSetup(os.environ.get("HERMES_IMAGE"), user_model_block(), run.case.get("entry"),
                              skills, eager, "on" if eager else "off"))


def turn(run, text, index):
    skill, rest = live.split_entry(run.case, text, index)
    entry = run.case.get("entry")
    query = rest or f"/{skill}"
    args = ["chat", "-Q", f"--query={query}", "--format", "stream-json", "--reasoning", "high",
            "-t", ",".join(toolsets(run)), "--yolo", "--run-budget", str(max(30, int(run.timeout_s * 0.9)))]
    for name in dict.fromkeys(n for n in (entry, skill) if n):
        args += ["-s", name]
    return run._hermes_evidence.turn(NativeTurn(index, tuple(args), skill))


def parse_json(text):
    try:
        return json.loads(text) if text else None
    except ValueError:
        return None


def classify_path(path, cwd, fixture):
    inventory = {entry.components: entry.kind for entry in fixture.entries}
    root = fixture.original_spelling.rstrip("/")
    def components(value):
        if not isinstance(value, str) or any(c in value for c in ("~", "$", "`", "*", "?", "\x00")):
            return None
        if value == root:
            return []
        if value.startswith(root + "/"):
            return value[len(root) + 1:].split("/")
        return None
    def walk(parts, stack):
        for index, part in enumerate(parts):
            if part in ("", "."):
                continue
            if part == "..":
                if not stack:
                    return None, "escape"
                stack.pop()
                continue
            stack.append(part)
            kind = inventory.get(tuple(stack), "missing")
            if kind in ("symlink", "hardlink", "special", "unavailable"):
                return None, kind
            if index < len(parts) - 1 and kind != "directory":
                return None, "unavailable-prefix"
        return stack, inventory.get(tuple(stack), "directory" if not stack else "missing")
    base = components(cwd)
    if base is None:
        return {"requested": path, "cwd": cwd, "spelling": None, "disposition": "unavailable", "reason": "outside-cwd"}
    stack, kind = walk(base, [])
    if stack is None or kind != "directory":
        return {"requested": path, "cwd": cwd, "spelling": None, "disposition": "unavailable", "reason": "refused-cwd"}
    absolute = isinstance(path, str) and path.startswith("/")
    parts = components(path) if absolute else components(root + "/" + path) if isinstance(path, str) else None
    if parts is None:
        return {"requested": path, "cwd": cwd, "spelling": None, "disposition": "unavailable", "reason": "outside-or-uninterpreted"}
    stack, kind = walk(parts, [] if absolute else stack)
    return {"requested": path, "cwd": cwd, "spelling": root + ("/" + "/".join(stack) if stack else "") if stack is not None else None,
            "disposition": "unavailable" if stack is None else "fixture-missing" if kind == "missing" else "fixture-request",
            "reason": kind if stack is None else None, "kind": kind}


def tool_reads(name, args, result, cwd, fixture, evidence):
    found = []
    def classify(path, base, shell=False):
        record = classify_path(path, base, fixture)
        evidence.append(record)
        if record["disposition"] in ("fixture-request", "fixture-missing") and (not shell or record["kind"] == "regular"):
            found.append(record["spelling"])
        return record
    if name == "read_file" and args.get("path"):
        classify(args["path"], cwd)
    elif name == "skill_view" and isinstance(result, dict) and result.get("skill_dir"):
        directory = classify_path(result["skill_dir"], cwd, fixture)
        evidence.append(directory)
        if directory["disposition"] != "unavailable":
            classify(args.get("file_path") or "SKILL.md", directory["spelling"])
    elif name == "terminal" and args.get("command"):
        base = args.get("workdir") or cwd
        for segment in re.split(r"&&|\|\||;|\||\n", args["command"]):
            try:
                words = shlex.split(segment)
            except ValueError:
                continue
            if words[:1] == ["cd"] and len(words) > 1:
                record = classify_path(words[1], base, fixture)
                evidence.append(record)
                base = record["spelling"] if record["disposition"] != "unavailable" else ""
                continue
            if not words or posixpath.basename(words[0]) not in READ_COMMANDS:
                continue
            for word in words[1:]:
                if word.startswith("-") or not re.search(r"[/.]", word):
                    continue
                classify(word, base, shell=True)
    return found


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

def walk(messages, session, fixture, path_evidence):
    cwd = session.get("cwd") or "/"
    pending = {}
    for m in messages[session["id"]]:
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
                    **({"id": m["tool_call_id"]} if single else {})}, tool_reads(name, args, result, cwd, fixture, path_evidence), result)


def first_user_text(messages, session):
    return next(((m["content"] or "").strip() for m in messages[session["id"]] if m["role"] == "user"), "")


def match_child(messages, children, claimed, task, outcome):
    free = [c for c in children if c["id"] not in claimed]
    usage = (outcome or {}).get("tokens") or {}
    if outcome and usage:
        for c in free:
            if (c.get("api_call_count") == outcome.get("api_calls") and c.get("output_tokens") == usage.get("output")
                    and (c.get("input_tokens") or 0) + (c.get("cache_read_tokens") or 0) == usage.get("input")):
                return c, "usage"
    goal = (task.get("goal") or "").strip()
    for c in free:
        if goal and first_user_text(messages, c) == goal:
            return c, "goal"
    return (free[0], "order") if free else (None, None)


def first_reply(messages, session):
    return next((m["content"] for m in messages[session["id"]] if m["role"] == "assistant" and (m["content"] or "").strip()), None)


def turn_entries(skills, meta):
    found = []
    for index, skill in enumerate(skills):
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
    return build_trace(run._hermes_evidence.read())


def build_trace(evidence, skills=None):
    captured = evidence.entry_skills
    if skills is not None and captured is not None and skills != captured:
        raise ValueError("entry skills disagree with the acquisition context")
    skills = captured if captured is not None else skills or ()
    try:
        return _build_trace(evidence, skills)
    except (TypeError, ValueError, KeyError, AttributeError, RecursionError) as exc:
        incomplete = IncompleteEvidence(evidence.acquisition.run_id, evidence.acquisition.id, "invalid-native-records",
                                        str(exc), evidence.meta, evidence.turns, evidence.retained_paths)
        return _build_trace(incomplete, skills)


def _build_trace(evidence, skills=()):
    meta = thaw(evidence.meta) if evidence.meta else {"cli_version": None, "image": None, "entry": None, "preload": {}, "todo_eager": None}
    turns = [thaw(t.record) for t in evidence.turns]
    roots = list(dict.fromkeys(t["session_id"] for t in turns if t.get("session_id")))
    path_evidence = []
    events, files_read, worklist, spawn_calls, spawns = [], [], [], [], []
    root_row, children, error = {}, [], None
    if not isinstance(evidence, IncompleteEvidence):
        rows = [thaw(r.session) for r in evidence.sessions]
        messages = {thaw(r.session)["id"]: [thaw(m) for m in r.messages] for r in evidence.sessions}
        by_id = {r["id"]: r for r in rows}
        root_rows = [by_id[i] for i in roots if i in by_id]
        root_row = root_rows[-1] if root_rows else {}
        children = [r for r in rows if r["delegate_from"] in roots]
        turn = -1
        for session in root_rows:
            for event, reads, result in walk(messages, session, evidence.fixture, path_evidence):
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
                child, matched = match_child(messages, children, claimed, task, outcomes.get(index))
                claimed.add(child["id"] if child else None)
                brief = f"{task.get('goal', '')}\n{task.get('context', '')}"
                reply = first_reply(messages, child) if child else None
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
            for _, reads, _ in walk(messages, child, evidence.fixture, path_evidence):
                files_read.extend(reads)
    else:
        error = f"{evidence.reason}: {evidence.detail}"
    if any(p["disposition"] == "unavailable" for p in path_evidence):
        error = "path-refused: recorded read crosses an unavailable fixture prefix"
    texts = [e["text"] for e in events if e["kind"] == "text"]
    argv = (turns[0].get("hermes_argv") if turns else None) or []
    effort = ((root_row.get("model_config") or {}).get("reasoning_config") or {}).get("effort")
    trace = {
        "harness": "hermes",
        "cli_version": meta["cli_version"],
        "model": root_row.get("model"),
        "effort": effort or ("high" if argv else None),
        "argv": argv,
        "cwd": root_row.get("cwd") or evidence.fixture.original_spelling if not isinstance(evidence, IncompleteEvidence) else "",
        "exit_code": turns[-1].get("exit_code") if turns else None,
        "duration_s": round(sum(t.get("duration_s", 0) for t in turns), 1),
        "entry": entry_kind(meta["entry"], meta["preload"], events),
        "events": events,
        "files_read": list(dict.fromkeys(files_read)),
        "worklist": worklist,
        "spawns": spawns,
        "final_reply": texts[-1] if texts else "",
        "transcript_paths": list(evidence.retained_paths),
        "x_image": meta["image"],
        "x_session_ids": roots,
        "x_delegate_sessions": [c["id"] for c in children],
        "x_turn_argvs": [t.get("hermes_argv") for t in turns],
        "x_todo_eager": meta["todo_eager"],
        "x_todo_tools": meta.get("todo_tools", "on"),
        "x_turn_entries": turn_entries(skills, meta) if "preloads" in meta else [],
    }
    trace["x_path_evidence"] = path_evidence
    trace["x_acquisition"] = evidence.acquisition.id if not isinstance(evidence, IncompleteEvidence) else evidence.acquisition_id
    trace["x_provenance"] = evidence.acquisition.provenance if not isinstance(evidence, IncompleteEvidence) else "incomplete"
    if error:
        trace["x_harvest_error"] = error
    return trace
