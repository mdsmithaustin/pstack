import json
import re
import shlex
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
HISTORIES = HERE / "histories"
PASS, FAIL, INCONCLUSIVE = "PASS", "FAIL", "INCONCLUSIVE"

PLAYBOOK = re.compile(r"^poteto-mode/playbooks/([a-z0-9-]+)\.md$")
SKILL_FILE = re.compile(r"^([a-z0-9-]+)/SKILL\.md$")
SKILLS_SEGMENT = re.compile(r"(?:^|[\s/'\"=:(,])skills/([A-Za-z0-9_.\-]+(?:/[A-Za-z0-9_.\-]+)*)")
STEP_LINE = re.compile(r"^(\d+)\. ")
ITEM_NUMBER = re.compile(r"^\s*(\d+)[.)]\s+")
SHA = re.compile(r"\b[0-9a-f]{7,40}\b")
SKIP_MARK = re.compile(r"skipped:\s*(?!<reason>)\S", re.I)

READ_TOOLS = {"Read": ("file_path",), "read_file": ("target_file", "path", "file_path"),
              "view_file": ("path", "file_path"), "skill_view": ("name",), "view": ("path",)}
SHELL_TOOLS = {"Bash": "command", "exec_command": "cmd", "terminal": "command",
               "run_terminal_command": "command", "shell": "command", "bash": "command"}
READ_VERBS = {"cat", "head", "tail", "sed", "less", "more", "nl", "bat", "awk", "grep", "rg", "python3", "python"}
EDIT_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit", "patch", "write_file", "apply_patch",
              "edit_file", "create_file", "str_replace_editor", "str_replace_based_edit_tool",
              "edit", "write", "insert", "create", "replace_in_file"}
PATH_FIELDS = ("file_path", "path", "target_file", "target_path", "filename", "file", "notebook_path")
SPAWN_TOOLS = {"Agent", "Task", "spawn_agent", "spawn_subagent", "delegate_task", "SubAgentActivity"}
WAIT_TOOLS = {"get_command_or_subagent_output", "wait_agent", "TaskOutput"}
FOLLOWUP_TOOLS = {"followup_task", "send_message"}
ASK_TOOLS = {"AskUserQuestion", "ask_user", "request_user_input", "AskQuestion", "ask_question"}
PRIVATE_PREFIXES = (".claude/", ".agents/", ".codex/", ".hermes/", ".grok/", ".git/")
CACHE_PATH = re.compile(r"(?:^|/)(?:__pycache__|\.pytest_cache)(?:/|$)|\.pyc$|(?:^|/)node_modules/\.cache(?:/|$)")
HEREDOC = re.compile(r"(?<!<)<<(?!<)-?\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1")
GIT_VALUE_OPTIONS = {"-C", "-c", "--git-dir", "--work-tree"}
GIT_HISTORY_COMMANDS = {"commit", "merge", "cherry-pick"}
GIT_NO_WRITE_FLAGS = {"--abort", "--dry-run", "--quit"}
PLAYBOOK_ENTRY = re.compile(r"^- \*\*(.+?)\.\*\*.*?`playbooks/([a-z0-9-]+)\.md`")
ENCODING_OFFER = re.compile(r"\bencod\w*|\boffer\w*|\bcheapest\b", re.I)
CONSTRAINT_ALIASES = {"newline": (r"\n", "linesep", "endswith"), "trailing": (r"\n",)}
SCRATCH_PREFIXES = ("/tmp/", "/private/tmp/", "/var/folders/")
LOG_NAMES = ("decisions.tsv", ".audit/")
WHY_CATEGORIES = ("issue", "ticket", "document", "docs", "chat", "slack", "observability", "error tracking",
                  "sentry", "analytics", "warehouse")
HOW_SECTIONS = ("overview", "key concepts", "how it works", "where things live", "gotchas")
BUCKETS = ("act on", "consider", "noted", "dismissed")
STOP = {"the", "a", "an", "of", "to", "in", "on", "for", "and", "or", "is", "it", "its", "this", "that",
        "with", "per", "as", "be", "by", "at", "from", "over", "into", "if", "then", "run", "use"}
QUESTION_CUES = ("should i", "do you want", "would you like", "let me know", "shall i", "want me to",
                 "can you confirm", "which approach", "please confirm", "may i")


def verdict(kind, failures=(), evidence=(), **extra):
    out = {"verdict": kind, "failures": list(failures), "evidence": list(evidence)}
    out.update(extra)
    return out


def passed(*evidence):
    return verdict(PASS, (), evidence)


def failed(failures, *evidence):
    return verdict(FAIL, failures if isinstance(failures, (list, tuple)) else [failures], evidence)


def inconclusive(reasons, *evidence, needs_judge=False, excerpt=None, **extra):
    if needs_judge:
        extra["needs_judge"] = True
        extra["excerpt"] = (excerpt or "")[:4000]
    return verdict(INCONCLUSIVE, reasons if isinstance(reasons, (list, tuple)) else [reasons], evidence, **extra)


def norm(text):
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text or "")
    text = text.replace("**", "").replace("`", "").replace("*", "")
    text = re.sub(r"^\s*(?:\d+[.)]|[-*]|\[[ x~-]\])\s+", "", text)
    return " ".join(text.lower().split())


def content_tokens(text):
    return [t for t in re.findall(r"[a-z0-9][a-z0-9\-]+", norm(text)) if t not in STOP and len(t) > 1]


def first_sentence(text):
    text = norm(text)
    match = re.match(r"(.+?[.!?])(\s|$)", text)
    return match.group(1) if match else text


def similar(item_text, target_text, floor=0.6):
    item, target = norm(item_text), norm(target_text)
    if not item or not target:
        return False
    if target.startswith(item[:40]) or item.startswith(target[:40]):
        return True
    wanted = content_tokens(item_text)
    if len(wanted) < 2:
        return False
    have = set(content_tokens(target_text))
    overlap = sum(1 for t in wanted if t in have)
    return overlap >= 2 and overlap / len(wanted) >= floor


def excerpt_of(text, limit=1500):
    return (text or "")[:limit]


def plain(command):
    return " ".join(re.sub(r"[\"'\[\],()]", " ", command or "").split())


def completion_gate(view):
    if view.killed:
        return inconclusive("run killed; the last text is not a completion reply")
    if not view.final_reply:
        return inconclusive("no final reply")
    return None


def extract_steps(text):
    lines = text.split("\n")
    printed, in_steps = [], False
    for line in lines:
        if STEP_LINE.match(line):
            in_steps = True
        if not in_steps and not line.startswith("#") and line.strip(" \t"):
            printed.append(line)
            continue
        if in_steps and line and line[0] != " " and not STEP_LINE.match(line):
            break
        if in_steps:
            printed.append(line)
    return printed


def playbook_shape(name, skills_root):
    path = Path(skills_root) / "poteto-mode" / "playbooks" / f"{name}.md"
    if not path.is_file():
        return None
    prose, steps = [], []
    for line in extract_steps(path.read_text(encoding="utf-8")):
        match = STEP_LINE.match(line)
        if match:
            steps.append({"n": int(match.group(1)), "text": line[match.end():], "subitems": []})
        elif steps and line.strip():
            steps[-1]["subitems"].append(line.strip())
            steps[-1]["text"] += " " + line.strip()
        elif not steps and line.strip():
            prose.append(line.strip())
    for step in steps:
        bold = re.match(r"\*\*([^*]+)\*\*", step["text"])
        step["title"] = bold.group(1).strip(" .") if bold else first_sentence(step["text"])
    return {"name": name, "prose": prose, "steps": steps}


def all_playbooks(skills_root):
    folder = Path(skills_root) / "poteto-mode" / "playbooks"
    return sorted(p.stem for p in folder.glob("*.md")) if folder.is_dir() else []


def item_matches_prose(item_text, shape):
    if not shape["prose"]:
        return False
    if similar(item_text, shape["prose"][0]) or similar(item_text, first_sentence(shape["prose"][0])):
        return True
    item = norm(item_text)
    tag = shape["name"].replace("-", " ")
    return tag in item and any(w in item for w in ("playbook", "preamble", "prose", "opening", "lead-in"))


def item_matches_step(item_text, step):
    number = ITEM_NUMBER.match(item_text or "")
    if number and int(number.group(1)) == step["n"]:
        wanted = content_tokens(item_text)
        have = set(content_tokens(step["text"]))
        if wanted and sum(1 for t in wanted if t in have) / len(wanted) >= 0.5:
            return True
    return similar(item_text, step["text"]) or similar(item_text, step["title"], 0.8)


def steps_in_order(items, shape, start=1):
    pointer, matched, missing, verbatim = start, [], [], []
    for step in shape["steps"]:
        hit = next((i for i in range(pointer, len(items)) if item_matches_step(items[i]["text"], step)), None)
        if hit is None:
            missing.append(step["n"])
            continue
        matched.append(step["n"])
        verbatim.append(norm(items[hit]["text"]) == norm(step["text"]) or norm(items[hit]["text"]) == norm(first_sentence(step["text"])))
        pointer = hit + 1
    return matched, missing, verbatim


def identify_playbook(items, skills_root):
    best, best_score = None, 0
    for name in all_playbooks(skills_root):
        shape = playbook_shape(name, skills_root)
        if not shape or not items:
            continue
        prose_hit = item_matches_prose(items[0]["text"], shape)
        matched, _, _ = steps_in_order(items, shape, 1 if prose_hit else 0)
        score = (2 if prose_hit else 0) + len(matched)
        if score > best_score:
            best, best_score = name, score
    if best_score >= 3:
        return best
    if items and "principles" in norm(items[0]["text"]) and "poteto" in norm(items[0]["text"]):
        return "figure-it-out"
    return None


def skill_rel(path):
    hits = SKILLS_SEGMENT.findall(path or "")
    return hits[-1] if hits else None


ASSIGNMENT = re.compile(r"(?:^|[;&|\s])([A-Za-z_][A-Za-z0-9_]*)=([^\s;&|$`'\"]+)")


FOR_LOOP = re.compile(r"\bfor\s+([A-Za-z_][A-Za-z0-9_]*)\s+in\s+([^;]+?)\s*;\s*do\s+(.*?)\s*;?\s*done\b", re.S)


def unroll_loops(command):
    def unroll(match):
        name, words, body = match.groups()
        pattern = re.compile(r"\$\{" + name + r"\}|\$" + name + r"\b")
        return "; ".join(pattern.sub(lambda _: word, body) for word in words.split())
    return FOR_LOOP.sub(unroll, command)


def expand_assignments(command):
    command = unroll_loops(command)
    for match in ASSIGNMENT.finditer(command):
        name, value = match.groups()
        tail = command[match.end():]
        tail = re.sub(r"\$\{" + name + r"\}|\$" + name + r"\b", lambda _: value, tail)
        command = command[:match.end()] + tail
    return command


def resolved_shell_paths(command):
    base, out = "", []
    for segment in re.split(r"&&|\|\||[;|\n]", expand_assignments(command)):
        words = segment.strip().split()
        if words[:1] == ["cd"] and len(words) > 1:
            target = words[1].strip("\"'")
            base = target if target.startswith("/") or not base else f"{base}/{target}"
            continue
        for token in shell_paths(segment):
            out.append(token if token.startswith("/") or not base else f"{base}/{token}")
    return out


def shell_paths(command):
    try:
        tokens = shlex.split(command.replace("\n", " "))
    except ValueError:
        tokens = command.split()
    return [t for t in tokens if "/" in t or t.endswith((".md", ".py", ".ts", ".sh", ".json", ".txt", ".csv", ".tsv"))]


class View:
    def __init__(self, trace, case, project):
        self.trace = trace
        self.case = case or {}
        self.project = Path(project) if project else None
        self.events = sorted(trace.get("events") or [], key=lambda e: e.get("seq", 0))
        self.worklist = sorted(trace.get("worklist") or [], key=lambda s: s.get("seq") or 0)
        self.spawns = sorted(trace.get("spawns") or [], key=lambda s: s.get("seq") or 0)
        self.final_reply = trace.get("final_reply") or ""
        self.harness = trace.get("harness")
        self.model = trace.get("model")
        self.exit_code = trace.get("exit_code")
        self.skills_root = self.find_skills_root()
        self._turns = self.turn_boundaries()
        self._answers = self.pair_results()

    def find_skills_root(self):
        if self.project and self.project.is_dir():
            for sub in (".claude/skills", ".agents/skills", ".hermes/skills", ".grok/skills", "skills"):
                if (self.project / sub / "poteto-mode" / "SKILL.md").is_file():
                    return self.project / sub
        return ROOT / "skills"

    @property
    def killed(self):
        return self.exit_code not in (0, None)

    @property
    def tool_calls(self):
        return [e for e in self.events if e.get("kind") == "tool_call"]

    def pair_results(self):
        calls = self.tool_calls
        by_id = {}
        for c in calls:
            if c.get("id"):
                by_id.setdefault(c["id"], []).append(c)
        answers, loose = {}, []
        for event in self.events:
            if event.get("kind") != "tool_result":
                continue
            if event.get("id"):
                call = next((c for c in by_id.get(event["id"], []) if id(c) not in answers and c.get("seq", 0) < event.get("seq", 0)), None)
                if call is not None:
                    answers[id(call)] = event
            else:
                loose.append(event)
        for event in loose:
            for call in calls:
                if (id(call) not in answers and not call.get("id") and call.get("name") == event.get("name")
                        and call.get("seq", 0) < event.get("seq", 0)):
                    answers[id(call)] = event
                    break
        return answers

    def results_for(self, call):
        return self._answers.get(id(call))

    def turn_boundaries(self):
        marks = [e for e in self.events if "turn" in e]
        if marks:
            return "field"
        if any(e.get("kind") == "user" for e in self.events):
            return "user"
        return None

    @property
    def has_turns(self):
        return self._turns is not None or len(self.case.get("turns", [])) <= 1

    def turn_of(self, seq):
        if self._turns == "field":
            for event in self.events:
                if event.get("seq") == seq:
                    return event.get("turn")
            return None
        if self._turns == "user":
            turn = -1
            for event in self.events:
                if event.get("kind") == "user":
                    turn += 1
                if event.get("seq") == seq:
                    return max(turn, 0)
            return None
        return 0 if len(self.case.get("turns", [])) <= 1 else None

    def events_in_turn(self, turn):
        return [e for e in self.events if self.turn_of(e.get("seq")) == turn]

    def texts(self, turn=None):
        return [e.get("text") or "" for e in self.events if e.get("kind") == "text" and (turn is None or self.turn_of(e.get("seq")) == turn)]

    def reply_of_turn(self, turn):
        texts = self.texts(turn)
        return texts[-1] if texts else ""

    def read_attempts(self):
        out = []
        for call in self.tool_calls:
            name, given = call.get("name"), call.get("input") or {}
            if name in READ_TOOLS:
                for field in READ_TOOLS[name]:
                    value = given.get(field)
                    if isinstance(value, str) and value:
                        rel = f"{value}/SKILL.md" if name == "skill_view" else skill_rel(value)
                        if rel:
                            out.append((call.get("seq"), rel, self.read_returned(call)))
                        break
            elif name in SHELL_TOOLS:
                for token in resolved_shell_paths(str(given.get(SHELL_TOOLS[name]) or "")):
                    rel = skill_rel(token)
                    if rel:
                        out.append((call.get("seq"), rel, True))
        return out

    def read_returned(self, call):
        answer = self.results_for(call)
        if answer is not None:
            return answer.get("ok") is not False
        seq = call.get("seq", 0)
        return not self.killed or any(e.get("seq", 0) > seq and e.get("kind") in ("text", "tool_call") for e in self.events)

    def event_reads(self):
        return [(seq, rel) for seq, rel, ok in self.read_attempts() if ok]

    def unread(self):
        attempts = self.read_attempts()
        return {rel for _, rel, ok in attempts if not ok} - {rel for _, rel, ok in attempts if ok}

    def lead_read_list(self):
        by = self.trace.get("x_files_read_by") or self.trace.get("files_read_by") or {}
        return by.get("lead") if isinstance(by, dict) and by.get("lead") is not None else (self.trace.get("files_read") or [])

    def lead_reads(self):
        seen, out = set(), []
        for _, rel in self.event_reads():
            if rel not in seen:
                seen.add(rel)
                out.append(rel)
        unread = self.unread()
        for path in self.lead_read_list():
            rel = skill_rel(path)
            if rel and rel not in seen and rel not in unread:
                seen.add(rel)
                out.append(rel)
        return out

    def all_reads(self):
        out = list(self.lead_reads())
        by = self.trace.get("x_files_read_by") or self.trace.get("files_read_by") or {}
        pools = [self.trace.get("files_read") or []]
        if isinstance(by, dict):
            pools.extend(v for k, v in by.items() if k != "lead" and isinstance(v, list))
        for child in self.trace.get("x_subagents") or []:
            pools.append(child.get("files_read") or [])
        for spawn in self.spawns:
            pools.append(spawn.get("files_read") or [])
        elsewhere = {skill_rel(path) for pool in pools[1:] for path in pool}
        unread = self.unread() - elsewhere
        for pool in pools:
            for path in pool:
                rel = skill_rel(path)
                if rel and rel not in out and rel not in unread:
                    out.append(rel)
        return out

    def read_seq(self, rel_suffix):
        for seq, rel in self.event_reads():
            if rel.endswith(rel_suffix):
                return seq
        return None

    def skill_read(self, skill, anywhere=True):
        pool = self.all_reads() if anywhere else self.lead_reads()
        return any(rel == f"{skill}/SKILL.md" or rel.startswith(f"{skill}/") for rel in pool)

    def playbooks_read(self):
        out = []
        for rel in self.lead_reads():
            match = PLAYBOOK.match(rel)
            if match and match.group(1) not in out:
                out.append(match.group(1))
        return out

    def commands(self, turn=None):
        out = []
        for call in self.tool_calls:
            name = call.get("name")
            if name not in SHELL_TOOLS:
                continue
            if turn is not None and self.turn_of(call.get("seq")) != turn:
                continue
            command = str((call.get("input") or {}).get(SHELL_TOOLS[name]) or "")
            result = self.results_for(call) or {}
            out.append((call.get("seq"), command, result.get("ok"), (result.get("output_head") or "").replace("\\n", "\n")))
        return out

    def edits(self, turn=None):
        out = []
        for call in self.tool_calls:
            name, given = call.get("name"), call.get("input") or {}
            if turn is not None and self.turn_of(call.get("seq")) != turn:
                continue
            if name in EDIT_TOOLS:
                if (self.results_for(call) or {}).get("ok") is False:
                    continue
                paths = [given[f] for f in PATH_FIELDS if isinstance(given.get(f), str)]
                patch = given.get("patch") or given.get("input") or ""
                if isinstance(patch, str):
                    paths.extend(re.findall(r"\*\*\* (?:Update|Add|Delete) File: (\S+)", patch))
                for path in paths or ["?"]:
                    out.append((call.get("seq"), path, self.classify(path)))
            elif name in SHELL_TOOLS:
                command = str(given.get(SHELL_TOOLS[name]) or "")
                for path in shell_writes(command) + [w for w in python_writes(command) if self.inside_project(w)]:
                    out.append((call.get("seq"), path, self.classify(path)))
        return out

    def inside_project(self, path):
        if not path.startswith("/") or not self.project:
            return True
        return Path(path).resolve().is_relative_to(self.project.resolve())

    def classify(self, path):
        path = path.strip("\"'")
        if CACHE_PATH.search(path):
            return "scratch"
        rel = path
        if self.project and path.startswith(str(self.project)):
            rel = path[len(str(self.project)):].lstrip("/")
        if rel.startswith(PRIVATE_PREFIXES) or "/skills/" in path:
            return "private"
        if path.startswith(SCRATCH_PREFIXES + ("$TMPDIR", "${TMPDIR", "$T/", "$V/", "$S/")) or rel.startswith(("tmp/", "scratch", "repro", "verify", "baseline")):
            return "scratch"
        if any(tag in rel for tag in LOG_NAMES):
            return "log"
        if "test" in rel.lower():
            return "test"
        if rel.endswith((".md", ".rst")) or rel.lower().startswith("readme"):
            return "doc"
        if rel.endswith((".txt", ".out", ".bin", ".log", ".csv", ".tsv", ".json", ".expected")):
            return "data"
        return "source"

    def source_edits(self, turn=None):
        return [e for e in self.edits(turn) if e[2] == "source"]

    def project_edits(self, turn=None):
        return [e for e in self.edits(turn) if e[2] in ("source", "test", "doc", "data")]

    def asked_user(self, turn=None):
        for call in self.tool_calls:
            if call.get("name") in ASK_TOOLS and (turn is None or self.turn_of(call.get("seq")) == turn):
                return call
        return None

    def question_texts(self, turn=None):
        hits = []
        for text in self.texts(turn):
            tail = text.strip().lower()[-400:]
            if tail.endswith("?") and any(cue in tail for cue in QUESTION_CUES):
                hits.append(text.strip()[-200:])
        return hits

    def spawn_text(self, spawn):
        call = next((c for c in self.tool_calls if str(c.get("seq")) == str(spawn.get("seq"))), None)
        given = (call or {}).get("input") or {}
        extra = [str(given.get(k) or "") for k in ("description", "task_name", "name")] if isinstance(given, dict) else []
        return " ".join([str(spawn.get(k) or "") for k in ("persona", "subagent_type", "description", "prompt_head", "task_name", "role")] + extra).lower()

    def spawns_where(self, *needles, turn=None):
        out = []
        for spawn in self.spawns:
            if turn is not None and self.turn_of(spawn.get("seq")) != turn:
                continue
            text = self.spawn_text(spawn)
            if any(n.lower() in text for n in needles):
                out.append(spawn)
        return out

    def encrypted(self):
        return any(s.get("x_prompt_encrypted") for s in self.spawns) or (self.spawns and all(not s.get("prompt_head") for s in self.spawns))

    def one_message(self, spawns):
        if len(spawns) < 2:
            return True
        seqs = sorted(s.get("seq") or 0 for s in spawns)
        for event in self.events:
            seq = event.get("seq", 0)
            if seqs[0] < seq < seqs[-1]:
                if event.get("kind") == "text":
                    return False
                if event.get("name") not in SPAWN_TOOLS:
                    return False
        return True

    def spawn_result(self, spawn):
        seq = spawn.get("seq") or 0
        call = next((c for c in self.tool_calls if c.get("seq") == seq), None)
        heads = [(self.results_for(call) or {}).get("output_head") or ""] if call else []
        if len(self.spawns) == 1:
            heads += [e.get("output_head") or "" for e in self.events
                      if e.get("kind") == "tool_result" and e.get("seq", 0) > seq and e.get("name") in WAIT_TOOLS]
        return "\n".join(h for h in heads if h)

    def code_delegate_seqs(self):
        out = []
        for s in self.spawns:
            text = self.spawn_text(s)
            if (s.get("persona") or "").lower() == "poteto-agent" and not re.search(r"review|judge|explain", text):
                out.append(s.get("seq") or 0)
            elif re.search(r"\bimplement\b|feature role|bug-fix role|write the code", text) and not re.search(r"review|judge|explain", text):
                out.append(s.get("seq") or 0)
        return out

    def git(self, *args):
        if not self.project or not (self.project / ".git").exists():
            return None
        return self.git_in(self.project, *args)

    def git_log(self):
        out = self.git("log", "--format=%H%x09%s")
        return [tuple(line.split("\t", 1)) for line in out.splitlines()] if out else None

    def git_dirty(self, path=None):
        out = self.git("status", "--porcelain", "-uall") if path is None else self.git_in(path, "status", "--porcelain", "-uall")
        if out is None:
            return None
        return [l for l in out.splitlines() if not l[3:].startswith(PRIVATE_PREFIXES) and not CACHE_PATH.search(l[3:])]

    def git_in(self, path, *args):
        proc = subprocess.run(["git", "-C", str(path), *args], capture_output=True, text=True)
        return proc.stdout if proc.returncode == 0 else None

    def base_commits(self):
        history = self.case.get("history")
        steps = history_steps(history) if history else []
        return 1 + sum(1 for step in steps if step.get("commit", True))

    def base_shas(self):
        if self.trace.get("x_baseline"):
            return self.trace["x_baseline"]
        out = self.git("rev-list", "--reverse", "HEAD")
        return out.split()[:self.base_commits()] if out else None

    def run_commits(self):
        base = self.base_shas()
        if base is None:
            return None
        found = {}
        for path in self.worktrees() or [self.project]:
            out = self.git_in(path, "log", "--branches", "HEAD", "--format=%H%x09%s")
            for line in (out or "").splitlines():
                sha, subject = line.split("\t", 1)
                if sha not in base:
                    found.setdefault(sha, subject)
        return list(found.items())

    def changed_since_base(self):
        base = self.base_shas()
        if base is None:
            return None
        names = set()
        for path in self.worktrees() or [self.project]:
            names |= set((self.git_in(path, "diff", "--name-only", base[-1], "HEAD") or "").split())
            names |= {line[3:].strip() for line in self.git_dirty(path) or []}
        for branch in (self.git("for-each-ref", "--format=%(refname)", "refs/heads") or "").split():
            if (self.git("rev-parse", branch) or "").strip() not in base:
                names |= set((self.git("diff", "--name-only", base[-1], branch) or "").split())
        return names

    def worktrees(self):
        out = self.git("worktree", "list", "--porcelain")
        return re.findall(r"^worktree (.+)$", out or "", re.M)


def strip_heredocs(command):
    out, end = [], None
    for line in command.split("\n"):
        if end is not None:
            if line.strip() == end:
                end = None
            continue
        out.append(line)
        match = HEREDOC.search(line)
        if match:
            end = match.group(2)
    return "\n".join(out)


def heredoc_bodies(command):
    bodies, end, header, body = [], None, "", []
    for line in command.split("\n"):
        if end is not None:
            if line.strip() == end:
                bodies.append((header, "\n".join(body)))
                end, body = None, []
            else:
                body.append(line)
            continue
        match = HEREDOC.search(line)
        if match:
            end, header = match.group(2), line
    return bodies


def mask_quoted(text):
    masked, quote, escaped = [], None, False
    for char in text:
        if quote is None:
            quote = char if char in "'\"" else None
            masked.append(char)
        elif escaped:
            escaped = False
            masked.append("_")
        elif char == "\\" and quote == '"':
            escaped = True
            masked.append("_")
        elif char == quote:
            quote = None
            masked.append(char)
        else:
            masked.append("_")
    return "".join(masked)


def shell_segments(command):
    masked = mask_quoted(command)
    segments, start = [], 0
    for separator in re.finditer(r"&&|\|\||;|\n", masked):
        segments.append((command[start:separator.start()], masked[start:separator.start()]))
        start = separator.end()
    segments.append((command[start:], masked[start:]))
    return segments


def is_write_target(target):
    if not target or target.startswith(("&", "/dev/")) or target.isdigit():
        return False
    return "$" not in target and not re.fullmatch(r"\{\}[+;\\]*", target)


def shell_writes(command):
    out = []
    for segment, masked in shell_segments(strip_heredocs(command)):
        found = [m for pattern in (r"(?:>>?|\btee\s+(?:-a\s+)?)\s*([^\s;&|]+)",
                                   r"\bsed\s+-i[^\s]*\s+(?:-e\s+)?(?:'[^']*'|\"[^\"]*\"|\S+)\s+(\S+)",
                                   r"\b(?:rm|git rm)\s+(?:-\w+\s+)*([^\s;&|]+)",
                                   r"\bmv\s+(?:-\w+\s+)*\S+\s+([^\s;&|]+)")
                 for m in re.finditer(pattern, masked)]
        for match in found:
            target = segment[match.start(1):match.end(1)].strip("\"'")
            if is_write_target(target):
                out.append(target)
    return out


PYTHON_HEADER = re.compile(r"\bpython[0-9.]*\b|\buv run\b")
PYTHON_DIRECT_WRITE = re.compile(r"(?:pathlib\.)?Path\(\s*(['\"])([^'\"\n]+)\1\s*\)\s*\.(?:write_text|write_bytes)\(")
PYTHON_BOUND_PATH = re.compile(r"(\w+)\s*=\s*(?:pathlib\.)?Path\(\s*(['\"])([^'\"\n]+)\2\s*\)")
PYTHON_BOUND_WRITE = re.compile(r"(\w+)\.(?:write_text|write_bytes)\(")
PYTHON_OPEN_WRITE = re.compile(r"\bopen\(\s*(['\"])([^'\"\n]+)\1\s*,\s*(['\"])([^'\"\n]*)\3")


def python_sources(command):
    sources = [body for header, body in heredoc_bodies(command) if PYTHON_HEADER.search(header)]
    rest = strip_heredocs(command)
    return sources + ([rest] if PYTHON_HEADER.search(rest) else [])


def python_writes(command):
    out = []
    for source in python_sources(command):
        found = [(m.start(), m.group(2)) for m in PYTHON_DIRECT_WRITE.finditer(source)]
        bound = {m.group(1): m.group(3) for m in PYTHON_BOUND_PATH.finditer(source)}
        found += [(m.start(), bound[m.group(1)]) for m in PYTHON_BOUND_WRITE.finditer(source) if m.group(1) in bound]
        found += [(m.start(), m.group(2)) for m in PYTHON_OPEN_WRITE.finditer(source) if re.search(r"[wax]", m.group(4))]
        out += [path for _, path in sorted(found)]
    return out


def history_steps(name):
    path = HISTORIES / name / "steps.json"
    if not path.is_file():
        return []
    return json.loads(path.read_text(encoding="utf-8")).get("steps", [])


def history_subjects(name):
    return [s.get("message", "").split("\n", 1)[0] for s in history_steps(name)]


def title(item_text):
    return norm(re.split(r"skipped:", item_text or "", flags=re.I)[0])[:40]


def opening_worklist(view):
    snaps = view.worklist
    if not snaps:
        return None
    current = snaps[0]
    for nxt in snaps[1:]:
        same = nxt.get("carrier") == current.get("carrier")
        grows = len(nxt.get("items", [])) > len(current.get("items", []))
        prefix = all(norm(a["text"]) == norm(b["text"]) and a.get("state") == b.get("state")
                     for a, b in zip(current.get("items", []), nxt.get("items", [])))
        if same and grows and prefix:
            current = nxt
        else:
            break
    return current


ORACLES = {}


def oracle(*pids):
    def wrap(fn):
        for pid in pids:
            ORACLES[pid] = fn
        return fn
    return wrap


def run_never_started(view):
    if view.tool_calls:
        return False
    codes = [turn.get("exit_code") for turn in view.trace.get("x_turns") or []] or [view.exit_code]
    return all(code not in (0, None) for code in codes)


def check(pid, trace, case, project):
    fn = ORACLES.get(pid)
    if fn is None:
        return inconclusive(f"no oracle for {pid}")
    if trace.get("x_harvest_error"):
        return inconclusive(f"the harness transcript could not be read: {trace['x_harvest_error']}")
    hits = trace.get("x_host_skill_hits")
    if hits:
        return inconclusive(f"the harness reported host skills in this run, so its behavior may not come from the installed skills: {sorted(hits)}")
    view = View(trace, case, project)
    if run_never_started(view):
        return inconclusive(f"run never started: every turn exited nonzero with no tool call; last reply {view.final_reply[:80]!r}")
    result = fn(view)
    result.setdefault("failures", [])
    result.setdefault("evidence", [])
    return result


def route_target(view):
    expect = view.case.get("expect") or {}
    return expect.get("playbook"), expect.get("skill")


def first_route_read(view, skill):
    for rel in view.lead_reads():
        match = PLAYBOOK.match(rel)
        if match:
            return ("playbook", match.group(1))
        if skill and rel == f"{skill}/SKILL.md":
            return ("skill", skill)
    return None


def route_verdict(view):
    want_pb, want_skill = route_target(view)
    want = want_skill or want_pb
    if not want:
        return inconclusive("case names no expect.playbook or expect.skill")
    first = first_route_read(view, want_skill)
    opening = opening_worklist(view)
    opened = identify_playbook(opening["items"], view.skills_root) if opening else None
    evidence = [f"first playbook or target skill read by the lead: {first[1] if first else None}",
                f"playbooks read in order: {view.playbooks_read()}",
                f"opening worklist identified as: {opened} (carrier {opening.get('carrier') if opening else None})"]
    failures = []
    if first and first[1] != want:
        failures.append(f"lead opened {first[1]} before {want}")
    if opened and opened != want:
        failures.append(f"opening worklist holds the {opened} playbook, not {want}")
    if failures:
        return failed(failures, *evidence)
    if first and first[1] == want:
        return passed(*evidence)
    if opened == want:
        return passed(*evidence)
    if len(view.tool_calls) < 3 and view.killed:
        return inconclusive("run ended before any playbook read or worklist", *evidence)
    return failed(f"no read of {want} and no worklist carrying it", *evidence)


def writes_git_history(words):
    if words[:1] != ["git"]:
        return False
    i = 1
    while i < len(words) and words[i].startswith("-"):
        i += 2 if words[i] in GIT_VALUE_OPTIONS else 1
    return (i < len(words) and words[i] in GIT_HISTORY_COMMANDS
            and not GIT_NO_WRITE_FLAGS.intersection(words[i + 1:]))


def commits_made(view, turn):
    made = 0
    for _, command, ok, _ in view.commands(turn):
        if ok is False:
            continue
        for segment in re.split(r"&&|\|\||[;|\n]", strip_heredocs(command)):
            words = segment.strip().split()
            while words and ASSIGNMENT.fullmatch(" " + words[0]):
                words = words[1:]
            made += writes_git_history(words)
    return made


def no_edits_verdict(view, turn=None):
    edits = view.project_edits(turn)
    dirty = view.git_dirty() if turn is None else None
    log = view.git_log()
    commits = view.run_commits()
    failures, evidence = [], []
    if edits:
        failures.append(f"edited project files: {[e[1] for e in edits][:6]}")
    if dirty:
        failures.append(f"working tree dirty after the run: {dirty[:6]}")
    if turn is None:
        if commits:
            failures.append(f"{len(commits)} commit(s) added past the fixture")
    elif commits_made(view, turn):
        failures.append(f"{commits_made(view, turn)} commit(s) made in turn {turn}")
    evidence.append(f"project edits: {len(edits)}, dirty paths: {len(dirty or [])}, commits: {len(log) if log else 'n/a'}")
    return failures, evidence


ROUTING_PROMISES = (
    "feature-prompt-routes-to-feature", "bug-prompt-routes-to-bug-fix", "perf-prompt-routes-to-perf-issue",
    "refactoring-prompt-routes-to-refactoring", "research-prompt-routes-to-research-playbook",
    "review-prompt-routes-to-code-review", "babysit-prompt-routes-to-babysit-drive", "land-prompt-routes-to-shipping",
    "autopilot-prompt-routes-to-autopilot-full", "stack-prompt-routes-to-autopilot-stack",
    "orchestrate-prompt-routes-to-orchestrate", "takeover-prompt-routes-to-session-pickup",
    "disk-prompt-routes-to-worktree-cleanup", "skill-prompt-routes-to-authoring-playbook",
    "eval-prompt-routes-to-eval-playbook", "open-pr-prompt-routes-to-opening-a-pr",
)


@oracle(*ROUTING_PROMISES)
def routing(view):
    return route_verdict(view)


@oracle("step-away-routes-to-figure-it-out")
def step_away(view):
    result = route_verdict(view)
    if result["verdict"] == PASS and not view.skill_read("figure-it-out", anywhere=False):
        return failed("figure-it-out/SKILL.md was never read by the lead", *result["evidence"])
    return result


@oracle("read-only-phrase-pins-investigation")
def read_only_pin(view):
    turn = None
    if len(view.case.get("turns", [])) > 1:
        if not view.has_turns:
            return inconclusive("multi-turn case but the trace carries no turn markers (core change: stamp events with `turn`)")
        turn = len(view.case["turns"]) - 1
        reads = [rel for seq, rel in view.event_reads() if view.turn_of(seq) == turn]
        routed = any(PLAYBOOK.match(r) and PLAYBOOK.match(r).group(1) == "investigation" for r in reads)
        evidence = [f"turn {turn} playbook reads: {[PLAYBOOK.match(r).group(1) for r in reads if PLAYBOOK.match(r)]}"]
        failures, more = no_edits_verdict(view, turn)
        evidence += more
        if not routed:
            failures.insert(0, "investigation.md not read in the `new task` turn")
        return failed(failures, *evidence) if failures else passed(*evidence)
    result = route_verdict(view)
    failures, evidence = no_edits_verdict(view)
    if result["verdict"] != PASS:
        return result
    return failed(failures, *result["evidence"], *evidence) if failures else passed(*result["evidence"], *evidence)


def runs_watcher(command):
    for segment in re.split(r"&&|\|\||[;|]", command):
        words = segment.strip().split()
        while words and ASSIGNMENT.fullmatch(" " + words[0]):
            words = words[1:]
        if words and words[0] in ("cd", "env", "bun", "exec"):
            words = words[1:]
        if words and words[0].rstrip("/").endswith("watch-pr") and not words[0].endswith("/"):
            return True
    return False


@oracle("babysit-status-request-no-loop")
def babysit_check_mode(view):
    result = route_verdict(view)
    if result["verdict"] != PASS:
        return result
    watchers = [c for c in view.commands() if runs_watcher(c[1])]
    looping = [c for c in watchers if re.search(r"--(?:until|follow|loop|watch)\b", c[1])] or \
        [c for c in view.commands() if re.search(r"\bwhile\s+(?:true|:)\b|\bsleep\s+\d{2,}", c[1])]
    monitor = [c for c in view.tool_calls if c.get("name") in ("Monitor", "loop")]
    evidence = [f"watch-pr invocations: {len(watchers)}, looping commands: {len(looping)}, monitor calls: {len(monitor)}",
                *result["evidence"]]
    mode = re.search(r"\b(check|drive|background)\b", view.final_reply.lower())
    evidence.append(f"declared mode in reply: {mode.group(1) if mode else None}")
    polling = [c for c in watchers if "--status-only" not in c[1]]
    if looping or monitor or polling:
        return failed("check request started a polling loop", *evidence,
                      f"watcher runs without --status-only: {len(polling)}")
    if not view.final_reply and view.killed:
        return inconclusive("run killed before the status reply", *evidence)
    return passed(*evidence)


@oracle("worklist-opens-with-playbook-steps")
def worklist_opens(view):
    want = (view.case.get("expect") or {}).get("playbook")
    shape = playbook_shape(want, view.skills_root) if want else None
    if not shape:
        return inconclusive(f"no playbook shape for {want!r}")
    opening = opening_worklist(view)
    if not opening:
        if view.killed and len(view.tool_calls) < 3:
            return inconclusive("run ended before any worklist appeared")
        return failed("no worklist snapshot in the trace (no native carrier call and no numbered list in chat)")
    items = opening["items"]
    prose = item_matches_prose(items[0]["text"], shape)
    matched, missing, verbatim = steps_in_order(items, shape, 1 if prose else 0)
    evidence = [f"carrier {opening.get('carrier')} at seq {opening.get('seq')} with {len(items)} items",
                f"first item: {items[0]['text'][:120]!r}", f"steps matched in order: {matched}, missing: {missing}",
                f"verbatim copies: {sum(verbatim)}/{len(verbatim)}"]
    failures = []
    if not prose:
        failures.append("first item is not the playbook's opening prose")
    if missing:
        failures.append(f"steps missing or out of order: {missing}")
    return failed(failures, *evidence) if failures else passed(*evidence)


@oracle("worklist-in-native-task-tool")
def worklist_native(view):
    env = view.case.get("env") or {}
    if env.get("todo_tools") is False:
        return inconclusive("case switches the task tools off; promise not exercised")
    carriers = [s.get("carrier") for s in view.worklist]
    native = [c for c in carriers if c and c != "text"]
    evidence = [f"carriers seen: {sorted(set(carriers))}"]
    if native:
        return passed(*evidence)
    if not carriers:
        if view.killed and len(view.tool_calls) < 3:
            return inconclusive("run ended before any worklist appeared", *evidence)
        return failed("no worklist in any carrier", *evidence)
    return failed("worklist appeared only as chat text while the task tool was on", *evidence)


@oracle("worklist-falls-back-to-numbered-list")
def worklist_fallback(view):
    env = view.case.get("env") or {}
    if env.get("todo_tools") is not False:
        return inconclusive("case leaves the task tools on; promise not exercised")
    carriers = [s.get("carrier") for s in view.worklist]
    evidence = [f"carriers seen: {sorted(set(carriers))}"]
    text = [s for s in view.worklist if s.get("carrier") == "text"]
    if text:
        want = (view.case.get("expect") or {}).get("playbook")
        shape = playbook_shape(want, view.skills_root) if want else None
        if shape:
            matched, missing, _ = steps_in_order(text[0]["items"], shape, 0)
            evidence.append(f"numbered list matches steps {matched}, missing {missing}")
            if len(matched) < max(1, len(shape["steps"]) // 2):
                return failed("numbered list in chat does not carry the playbook steps", *evidence)
        return passed(*evidence)
    if not carriers and view.killed and len(view.tool_calls) < 3:
        return inconclusive("run ended before any worklist appeared", *evidence)
    return failed("no numbered list with states in chat", *evidence)


@oracle("skipped-step-stays-in-worklist")
def skipped_step(view):
    if not view.worklist:
        return inconclusive("no worklist to inspect")
    skipped = []
    for snap in view.worklist:
        for item in snap.get("items", []):
            if (item.get("state") or "").lower().startswith("skipped") or SKIP_MARK.search(item.get("text") or ""):
                skipped.append((snap.get("seq"), item))
    final = view.worklist[-1].get("items", [])
    evidence = [f"skip markers seen: {len(skipped)}", f"final worklist has {len(final)} items"]
    if skipped:
        gone = [i["text"][:60] for _, i in skipped if not any(title(i["text"]) == title(f["text"]) for f in final)]
        if gone:
            return failed(f"skipped items vanished from the final list: {gone}", *evidence)
        evidence.append(f"example: {skipped[0][1].get('state', '')[:100]!r} on {skipped[0][1].get('text', '')[:60]!r}")
        return passed(*evidence)
    opening = opening_worklist(view)
    dropped = [i["text"][:60] for i in (opening or {}).get("items", [])
               if not any(norm(i["text"])[:40] == norm(f["text"])[:40] for f in final)]
    if dropped:
        return failed(f"steps dropped from the worklist without a skipped marker: {dropped}", *evidence)
    if view.killed:
        return inconclusive("run killed; no step reached a skip decision", *evidence)
    return inconclusive("no step was skipped or dropped; promise not exercised", *evidence)


TRIVIAL = re.compile(r"^(cat|ls|cd|cp|mkdir|rm|wc|echo|printf|export|git (?:status|log|diff|show|add|switch|checkout|remote)|sed|head|tail|grep|rg|find|pwd|which|S=|V=)\b")


def command_segments(command):
    out = []
    for segment in re.split(r"&&|\|\||;|\||\n", command):
        core = " ".join(re.sub(r"\s*\d?>>?\s*\S+", "", segment).split())
        if len(core) >= 10 and not TRIVIAL.match(core):
            out.append(core)
        out += [m for m in re.findall(r"(?:python3?|node|bash|sh)\s+(\S+\.(?:py|sh|ts|js))|^(\.?/\S+\.(?:py|sh))", core) for m in (m if isinstance(m, str) else next(x for x in m if x),) if len(m) >= 8]
    return out


COMMAND_LIKE = re.compile(r"(?m)^\s*\$ \S|`(?:python3?|node|npm|npx|bash|sh|git|pytest|make|cargo|go|\./)[^`]{4,}`")


def command_like(reply):
    return COMMAND_LIKE.findall(reply or "")


def quoted_commands(view):
    hits = []
    reply = " ".join(view.final_reply.split())
    for seq, command, ok, head in view.commands():
        if any(piece in reply for piece in command_segments(command)):
            lines = [" ".join(l.split()) for l in head.splitlines() if len(l.strip()) >= 6]
            hits.append((command, any(l in reply for l in lines)))
    return hits


@oracle("reply-carries-commands-and-outputs")
def reply_commands(view):
    gate = completion_gate(view)
    if gate:
        return gate
    hits = quoted_commands(view)
    shaped = command_like(view.final_reply)
    evidence = [f"commands quoted in reply: {len(hits)}", f"with a matching output line: {sum(1 for _, o in hits if o)}",
                f"command-shaped spans in reply: {len(shaped)}"]
    if any(o for _, o in hits):
        return passed(*evidence)
    if hits:
        return inconclusive("commands quoted but outputs could not be matched against the 400-char result heads",
                            *evidence, needs_judge=True, excerpt=excerpt_of(view.final_reply))
    if shaped:
        return inconclusive("reply quotes commands the lead's stream never ran (a delegate may have); a judge must read the transcript",
                            *evidence, needs_judge=True, excerpt=excerpt_of(view.final_reply))
    return failed("final reply quotes none of the commands the run executed", *evidence, excerpt_of(view.final_reply, 600))


def artifact_regex(view):
    return re.compile((view.case.get("expect") or {}).get("artifact_command") or r"-m\s+\w+")


def artifact_runs(view, pattern):
    return [(seq, c, ok) for seq, c, ok, _ in view.commands() if pattern.search(plain(c))]


@oracle("reply-says-inconclusive-when-check-cannot-run")
def reply_inconclusive(view):
    pattern = artifact_regex(view)
    checks = [(seq, c, ok) for seq, c, ok, _ in view.commands() if pattern.search(plain(c)) or re.search(r"unittest|pytest|npm test|node .*\.ts", c)]
    broken = [c for seq, c, ok in checks if ok is False and not any(s > seq and o is not False and pattern.search(plain(cc)) for s, cc, o in checks)]
    evidence = [f"check commands: {len(checks)}, last attempt failed to run: {len(broken)}"]
    if not checks:
        return inconclusive("no check command ran; promise not exercised", *evidence)
    if not broken:
        return inconclusive("every check ran; promise not exercised", *evidence)
    gate = completion_gate(view)
    if gate:
        return gate
    if "inconclusive" in view.final_reply.lower():
        return passed(*evidence, "reply says inconclusive")
    return failed("a check failed to run and the reply does not say inconclusive", *evidence)


@oracle("prove-it-works-checks-real-artifact")
def prove_it_works(view):
    pattern = artifact_regex(view)
    anchors = [e[0] for e in view.source_edits()] + view.code_delegate_seqs()
    if not anchors:
        return inconclusive("no source edit by the lead and no code delegate" + (" (run killed)" if view.killed else ""))
    anchor = max(anchors)
    after = [r for r in artifact_runs(view, pattern) if r[0] > anchor]
    evidence = [f"change anchor at seq {anchor} (last lead source edit or code-delegate spawn)",
                f"artifact runs after it: {[plain(c)[:80] for _, c, _ in after][:3]}"]
    if any(ok is not False for _, _, ok in after):
        return passed(*evidence)
    if view.killed:
        return inconclusive("run killed before verification", *evidence)
    if pattern.search(plain(view.final_reply)):
        return inconclusive("no artifact run by the lead after the change; the reply quotes one, so it may have run in a delegate",
                            *evidence, needs_judge=True, excerpt=excerpt_of(view.final_reply))
    return failed("no run of the real artifact after the change", *evidence)


@oracle("poteto-mode-routes-to-playbook")
def routes_and_runs(view):
    route = route_verdict(view)
    siblings = sorted({SKILL_FILE.match(r).group(1) for r in view.all_reads()
                       if SKILL_FILE.match(r) and not r.startswith(("poteto-mode/", "principle-", "pstack-harness/", "unslop/"))})
    evidence = [*route["evidence"], f"sibling skills read: {siblings}", f"spawns: {len(view.spawns)}"]
    if route["verdict"] != PASS:
        return verdict(route["verdict"], route["failures"], evidence)
    if not siblings and not view.spawns:
        return failed("no sibling skill ran as a playbook step", *evidence)
    gate = completion_gate(view)
    if gate:
        return verdict(INCONCLUSIVE, gate["failures"], evidence)
    if not quoted_commands(view):
        if command_like(view.final_reply):
            return inconclusive("reply quotes commands the lead's stream never ran; a judge must read the transcript",
                                *evidence, needs_judge=True, excerpt=excerpt_of(view.final_reply))
        return failed("reply carries no executed command as evidence", *evidence)
    return passed(*evidence)


DESIGN_BRIEF = re.compile(r"design candidate|candidate design|design sketch|architect runner", re.I)
SPAWN_TOOL_NAMES = {"Agent", "Task", "spawn_agent", "delegate_task", "spawn_subagent"}


def design_fan_out(view):
    runners = runner_spawns(view)
    briefed = [r for r in view.all_reads() if r == "architect/references/runner-prompt.md"]
    signals = []
    if briefed:
        signals.append("read architect/references/runner-prompt.md to brief runners")
    if len(runners) >= 2:
        signals.append(f"{len(runners)} design runner spawns")
    if runners and judge_spawns(view):
        signals.append("a design judge beside the runners")
    attempted = sum(len(DESIGN_BRIEF.findall(json.dumps(c.get("input") or {}))) for c in view.tool_calls
                    if c.get("name") in SPAWN_TOOL_NAMES)
    if not runners and attempted >= 2:
        signals.append(f"{attempted} design runner briefs in spawn calls, including refused ones")
    return signals


@oracle("design-ladder-spares-small-changes")
def design_ladder(view):
    signals = design_fan_out(view)
    reads = [r for r in view.lead_reads() if r.startswith(("architect/", "arena/"))]
    evidence = [f"design skills read by the lead: {reads}", f"fan-out signals: {signals}"]
    if signals:
        return failed("a small self-contained change ran the architect/arena design fan-out", *evidence)
    if len(view.tool_calls) < 3 and view.killed:
        return inconclusive("run ended before a design decision", *evidence)
    return passed(*evidence)


@oracle("poteto-mode-triggers-architect-on-boundary-crossing")
def architect_on_boundary(view):
    signals = design_fan_out(view)
    evidence = [f"fan-out signals: {signals}"]
    if signals:
        return passed(*evidence)
    if view.killed and not view.project_edits():
        return inconclusive("run ended before a design decision", *evidence)
    return failed("a change across several modules skipped the architect design fan-out", *evidence)


@oracle("claude-effort-applies-via-effort-agents")
def claude_effort(view):
    if view.harness != "claude-code":
        return inconclusive(f"applies to claude-code only; this run is {view.harness}", not_applicable=True)
    written = [s for s in view.spawns if s.get("effort")]
    if not written:
        return inconclusive("no spawn wrote an effort")
    failures, evidence = [], []
    for spawn in written:
        kind, effort = spawn.get("subagent_type") or "", spawn["effort"]
        observed = (spawn.get("observed") or {}).get("efforts") or []
        evidence.append(f"seq {spawn.get('seq')}: type {kind!r} effort {effort!r} observed {observed}")
        if kind != f"pstack-effort-{effort}":
            failures.append(f"seq {spawn.get('seq')} wrote effort {effort} without the pstack-effort-{effort} agent")
        elif observed and effort not in observed:
            failures.append(f"seq {spawn.get('seq')} ran at {observed}, not {effort}")
    if failures:
        return failed(failures, *evidence)
    if not any((s.get("observed") or {}).get("efforts") for s in written):
        return inconclusive("effort agents used but the child's observed effort is not in the trace", *evidence)
    return passed(*evidence)


@oracle("persona-delivery-hermes-grok")
def persona_delivery(view):
    if view.harness not in ("hermes", "grok"):
        return inconclusive(f"applies to hermes and grok only; this run is {view.harness}", not_applicable=True)
    personas = [s for s in view.spawns if (s.get("persona") or "").lower() == "poteto-agent"
                or "poteto-agent" in (s.get("prompt_head") or "").lower()]
    if not personas:
        if view.killed:
            return inconclusive("run killed before a poteto-agent spawn", f"spawns so far: {len(view.spawns)}")
        if view.spawns:
            return failed("spawns exist but none carries the poteto-agent persona", f"spawns: {len(view.spawns)}")
        return inconclusive("no spawn in the trace")
    briefed = [s for s in personas if re.search(r"pstack installed skill paths|persona: poteto-agent|poteto subagent", s.get("prompt_head") or "", re.I)]
    announced = [s for s in personas if s.get("x_persona_line") == "poteto-agent"
                 or "persona: poteto-agent" in view.spawn_result(s).lower()
                 or "persona: poteto-agent" in (s.get("x_child_first_reply") or "").lower()]
    evidence = [f"poteto-agent spawns: {len(personas)}, with the briefing in the prompt: {len(briefed)}, child announced the persona: {len(announced)}"]
    if not briefed:
        return failed("poteto-agent spawn prompt lacks the persona briefing", *evidence)
    if announced:
        return passed(*evidence)
    return inconclusive("briefing delivered; the child's first reply is not visible in the harvested trace", *evidence)


def principle_index(skills_root):
    text = (Path(skills_root) / "poteto-mode" / "SKILL.md").read_text(encoding="utf-8")
    return re.findall(r"\*\*([^*]+)\*\* \(\*\*(principle-[a-z-]+)\*\*\)", text)


def principles_named(reply, index):
    low = reply.lower()
    return [(name, slug) for name, slug in index if name.lower() in low or slug in low or slug.replace("principle-", "") in low]


@oracle("poteto-mode-reads-principles-and-names-applied")
def principles_named_and_read(view):
    gate = completion_gate(view)
    if gate:
        return gate
    index = principle_index(view.skills_root)
    named = principles_named(view.final_reply, index)
    reads = view.all_reads()
    read_slugs = sorted({SKILL_FILE.match(r).group(1) for r in reads if SKILL_FILE.match(r) and r.startswith("principle-")})
    unread = [slug for _, slug in named if f"{slug}/SKILL.md" not in reads]
    evidence = [f"principles named in reply: {[n for n, _ in named]}", f"principle leaves read: {read_slugs}"]
    if not named:
        return failed("reply names no principle", *evidence)
    if unread:
        return failed(f"named without reading the leaf: {unread}", *evidence)
    return inconclusive("principles named and read; whether each names the decision it changed needs a judge",
                        *evidence, needs_judge=True, excerpt=excerpt_of(view.final_reply, 2500))


@oracle("principle-name-steers-agent")
def principle_steers(view):
    steers = (view.case.get("expect") or {}).get("steers") or []
    if not steers:
        return inconclusive("case names no expect.steers")
    if not view.has_turns:
        return inconclusive("multi-turn case but the trace carries no turn markers (core change: stamp events with `turn`)")
    failures, evidence = [], []
    for steer in steers:
        turn, slug = steer["turn"], steer["principle"]
        reads = [rel for seq, rel in view.event_reads() if view.turn_of(seq) is not None and view.turn_of(seq) <= turn]
        read = f"{slug}/SKILL.md" in reads or f"{slug}/SKILL.md" in view.all_reads()
        cmds = view.commands(turn)
        edits = view.edits(turn)
        acted = False
        if steer.get("command"):
            acted = any(re.search(steer["command"], c) for _, c, _, _ in cmds)
        if steer.get("deletes"):
            delegated = [sp for sp in view.spawns if view.turn_of(sp.get("seq")) == turn
                         and re.search(r"\b(delete|remove)\b", view.spawn_text(sp), re.I)
                         and re.search(steer["deletes"].replace("_", "[_ ]?"), view.spawn_text(sp), re.I)]
            acted = acted or bool(delegated) or any(re.search(steer["deletes"], c) and re.search(r"\b(rm|git rm|mv)\b", c) for _, c, _, _ in cmds) \
                or (view.project is not None and all(not (view.project / p).exists() for p in steer.get("gone", [])) and bool(steer.get("gone")))
        evidence.append(f"turn {turn}: leaf read {read}, acted {acted}, commands {len(cmds)}, edits {len(edits)}")
        if not read:
            failures.append(f"turn {turn}: {slug}/SKILL.md not read")
        if not acted:
            failures.append(f"turn {turn}: no action matching the steer")
    return failed(failures, *evidence) if failures else passed(*evidence)


@oracle("steering-prompt-redirects-run")
def steering_redirects(view):
    turns = view.case.get("turns", [])
    if len(turns) < 2:
        return inconclusive("case has one turn; nothing to redirect")
    if not view.has_turns:
        return inconclusive("multi-turn case but the trace carries no turn markers (core change: stamp events with `turn`)")
    turn = len(turns) - 1
    edits = view.source_edits(turn)
    reply = view.reply_of_turn(turn)
    evidence = [f"source edits after the correction: {[e[1] for e in edits][:4]}", f"reply head: {reply[:160]!r}"]
    if edits:
        return failed("the run kept editing source after being told the goal is to reproduce", *evidence)
    if not reply:
        return inconclusive("no reply in the correction turn", *evidence)
    return passed(*evidence)


@oracle("bug-fix-reproduces-before-fixing")
def repro_first(view):
    pattern = re.compile((view.case.get("expect") or {}).get("repro_command") or r"-m\s+\w+")
    repros = [(seq, c) for seq, c, _, _ in view.commands() if pattern.search(plain(c))]
    edits = view.source_edits()
    evidence = [f"repro commands: {len(repros)} (first at seq {repros[0][0] if repros else None})",
                f"first source edit at seq {edits[0][0] if edits else None}"]
    if not edits:
        delegated = view.spawns_where("bug-fix", "fix", "implement") or any(repros and repros[0][0] < seq for seq in view.code_delegate_seqs())
        if delegated and repros:
            return passed(*evidence, "fix delegated; the lead reproduced before spawning")
        return inconclusive("no source edit by the lead" + (" (run killed)" if view.killed else ""), *evidence)
    if repros and repros[0][0] < edits[0][0]:
        return passed(*evidence)
    if repros:
        return failed("first source edit precedes the first reproduction", *evidence)
    return failed("no reproduction command before editing source", *evidence)


@oracle("bug-fix-uses-poteto-tdd-when-cheap")
def tdd_in_bug_fix(view):
    read = view.skill_read("poteto-tdd") or view.skill_read("tdd")
    tests = [e for e in view.edits() if e[2] == "test"]
    sources = view.source_edits()
    runs = [(seq, c, ok, head) for seq, c, ok, head in view.commands() if re.search(r"unittest|pytest|test_", c)]
    failing = [r for r in runs if r[2] is False or re.search(r"\bFAIL|Error|failures=\d*[1-9]", r[3])]
    green = [r for r in runs if r[2] is not False and re.search(r"\bOK\b|passed|ok\b", r[3]) and not re.search(r"FAIL|Error", r[3])]
    evidence = [f"tdd skill read: {read}", f"test edits: {len(tests)}, source edits: {len(sources)}",
                f"test runs: {len(runs)}, failing runs: {len(failing)}"]
    commits = view.run_commits()
    if commits:
        evidence.append(f"commits past the fixture: {[subject for _, subject in commits]}")
    if not sources and view.code_delegate_seqs() and failing and any(g[0] > failing[0][0] for g in green):
        return passed(*evidence, "a delegate owns the fix; the lead saw the test fail, then pass")
    if not sources and not tests:
        return inconclusive("no edits by the lead; a delegate may own the test and fix", *evidence)
    if tests and sources and tests[0][0] < sources[0][0]:
        if any(tests[0][0] <= f[0] < sources[0][0] for f in failing):
            return passed(*evidence)
        return inconclusive("test written before the fix but no failing run is visible", *evidence)
    return failed("no failing test ran before the fix", *evidence)


def how_evidence(view):
    seqs = []
    seq = view.read_seq("how/SKILL.md")
    if seq is not None:
        seqs.append(seq)
    seqs += [s.get("seq") for s in view.spawns_where("explainer", "explorer", "architectural explanation", "how explainer", "how skill")]
    return min(seqs) if seqs else None


def why_evidence(view):
    seqs = []
    seq = view.read_seq("why/SKILL.md")
    if seq is not None:
        seqs.append(seq)
    seqs += [s.get("seq") for s in view.spawns_where("investigator", "synthesizer", "historical context", "source control", "git history")]
    return min(seqs) if seqs else None


@oracle("how-narrow-question-no-explorers")
def how_narrow(view):
    explorers = view.spawns_where("explorer", "exploration angle", "exploring a codebase")
    evidence = [f"explorer spawns: {len(explorers)}", f"total spawns: {len(view.spawns)}"]
    if explorers:
        return failed(f"{len(explorers)} explorer(s) spawned for a narrow question", *evidence)
    if not view.final_reply and view.killed:
        return inconclusive("run killed before the answer", *evidence)
    return passed(*evidence)


@oracle("how-fans-out-explorers-for-big-subsystem")
def how_wide(view):
    explorers = view.spawns_where("explorer", "exploration angle", "exploring a codebase")
    explainers = view.spawns_where("explainer", "architectural explanation", "synthesis")
    evidence = [f"explorer spawns: {len(explorers)}", f"explainer spawns: {len(explainers)}"]
    if not explorers:
        if view.killed and not view.spawns:
            return inconclusive("run killed before any spawn", *evidence)
        return failed("no explorers for a subsystem-scale question", *evidence)
    if not 2 <= len(explorers) <= 4:
        return failed(f"{len(explorers)} explorers; the skill fans out two to four", *evidence)
    if explainers and min(s.get("seq") for s in explainers) < max(s.get("seq") for s in explorers):
        return failed("explainer spawned before the explorers finished launching", *evidence)
    if not view.one_message(explorers):
        return failed("explorers were not spawned in one message", *evidence)
    readonly = all(re.search(r"read[- ]only|do not (?:edit|write)", (s.get("prompt_head") or ""), re.I) for s in explorers)
    evidence.append(f"explorer prompts marked read-only: {readonly}")
    return passed(*evidence)


@oracle("how-explains-current-code")
def how_explains(view):
    gate = completion_gate(view)
    if gate:
        return gate
    low = view.final_reply.lower()
    sections = [s for s in HOW_SECTIONS if s in low]
    files = set(re.findall(r"\b[\w/.-]+\.(?:py|ts|sh|md|json|csv)\b", view.final_reply))
    evidence = [f"how sections present: {sections}", f"files cited: {sorted(files)[:6]}"]
    if not files:
        return failed("reply cites no project file", *evidence)
    if len(sections) >= 2:
        return inconclusive("structure and citations present; onboarding depth needs a judge", *evidence,
                            needs_judge=True, excerpt=excerpt_of(view.final_reply, 2500))
    return inconclusive("reply lacks the how sections; depth needs a judge", *evidence,
                        needs_judge=True, excerpt=excerpt_of(view.final_reply, 2500))


@oracle("how-then-why-sequence-honored")
def how_then_why(view):
    how, why = how_evidence(view), why_evidence(view)
    evidence = [f"first how evidence at seq {how}", f"first why evidence at seq {why}"]
    if how is None or why is None:
        if view.killed:
            return inconclusive("run killed before both skills ran", *evidence)
        return failed("one of how or why never ran", *evidence)
    if how < why:
        return passed(*evidence) if "source" in view.final_reply.lower() else \
            inconclusive("order honored; the reports' sources sections need a judge", *evidence, needs_judge=True, excerpt=excerpt_of(view.final_reply))
    return failed("why ran before how", *evidence)


@oracle("why-then-how-composition")
def why_then_how(view):
    how, why = how_evidence(view), why_evidence(view)
    evidence = [f"first how evidence at seq {how}", f"first why evidence at seq {why}"]
    if how is None or why is None:
        if view.killed:
            return inconclusive("run killed before both skills ran", *evidence)
        return failed("one of how or why never ran", *evidence)
    return passed(*evidence) if why < how else failed("how ran before why", *evidence)


@oracle("why-queries-evidence-categories-in-parallel")
def why_parallel(view):
    investigators = view.spawns_where("investigator", "historical context", "source control", "git history")
    evidence = [f"investigator spawns: {len(investigators)}", f"one message: {view.one_message(investigators)}"]
    if not investigators:
        if view.killed and not view.spawns:
            return inconclusive("run killed before any spawn", *evidence)
        return failed("no investigator spawned (the source-control investigator is always spawned)", *evidence)
    if len(investigators) >= 2 and not view.one_message(investigators):
        return failed("investigators spawned sequentially", *evidence)
    if len(investigators) == 1:
        evidence.append("only source control is available in the run; one investigator is the full roster")
    return passed(*evidence)


@oracle("why-reports-cited-history")
def why_cited(view):
    gate = completion_gate(view)
    if gate:
        return gate
    subjects = history_subjects(view.case.get("history", "")) if view.case.get("history") else []
    reply = view.final_reply
    shas = SHA.findall(reply)
    quoted = [s for s in subjects if s and s.lower() in reply.lower()]
    inference = re.search(r"appears to|infer|inference|likely|probably|we can reasonably", reply, re.I)
    unknown = re.search(r"what we don't know|don't know|unknown|no record|not recorded|thin", reply, re.I)
    evidence = [f"shas cited: {len(shas)}", f"history subjects quoted: {quoted}", f"inference marked: {bool(inference)}", f"gaps marked: {bool(unknown)}"]
    if not shas and not quoted:
        return failed("reply cites no commit from the history", *evidence)
    if not inference:
        return failed("reply never separates inference from evidence", *evidence)
    return passed(*evidence)


@oracle("why-reports-null-results")
def why_null(view):
    gate = completion_gate(view)
    if gate:
        return gate
    low = view.final_reply.lower()
    named = [c for c in WHY_CATEGORIES if c in low]
    nulls = re.search(r"null result|not available|unavailable|no (?:mcp|issue tracker|chat|docs)|none (?:available|found)|not searched|skipped", low)
    evidence = [f"categories mentioned: {named}", f"null wording present: {bool(nulls)}"]
    if named and nulls:
        return passed(*evidence)
    return failed("reply does not report the absent evidence categories as null results", *evidence)


@oracle("how-why-reports-name-sources-searched")
def sources_named(view):
    gate = completion_gate(view)
    if gate:
        return gate
    low = view.final_reply.lower()
    section = re.search(r"sources (?:consulted|searched|checked)|### sources|\*\*sources", low)
    git = re.search(r"\bgit\b|commit", low)
    evidence = [f"sources section: {bool(section)}", f"git named: {bool(git)}"]
    return passed(*evidence) if section and git else failed("reply has no sources section naming what was searched", *evidence)


@oracle("poteto-teach-runs-how-and-why")
def teach(view):
    how, why = how_evidence(view), why_evidence(view)
    diagrams = len(re.findall(r"```mermaid|```(?:text|ascii)?\n[^`]*(?:-->|->|\+--|\|  )", view.final_reply))
    evidence = [f"how evidence at seq {how}", f"why evidence at seq {why}", f"diagrams in reply: {diagrams}"]
    if how is None and why is None:
        if view.killed:
            return inconclusive("run killed before how or why ran", *evidence)
        return failed("neither how nor why ran", *evidence)
    if not view.final_reply:
        return inconclusive("no final reply", *evidence)
    if how is None or why is None:
        evidence.append("one of the two ran; the skill allows that for a small change")
    return inconclusive("how/why ran; whether the reply teaches diagram by diagram needs a judge",
                        *evidence, needs_judge=True, excerpt=excerpt_of(view.final_reply, 3000))


def reviewer_arms(view):
    entry = view.case.get("entry") or view.trace.get("entry")
    calls = {c.get("seq"): c.get("input") or {} for c in view.tool_calls if c.get("name") in SPAWN_TOOLS}
    picked, sealed_count = [], 0
    for spawn in view.spawns:
        given = calls.get(spawn.get("seq")) or {}
        label = " ".join([view.spawn_text(spawn)] + [str(given.get(k) or "") for k in ("task_name", "description", "name")]).lower()
        sealed = bool(spawn.get("x_prompt_encrypted")) or str(given.get("message") or "").startswith("gAAAA")
        if "review" in label or "adversarial" in label:
            picked.append(spawn)
        elif sealed and entry == "interrogate":
            picked.append(spawn)
            sealed_count += 1
    return picked, sealed_count


def reviewer_spawns(view):
    return reviewer_arms(view)[0]


def reviewer_evidence(view):
    count = reviewer_arms(view)[1]
    return [f"{count} reviewer(s) counted by entry: their briefs are encrypted and name no role"] if count else []


@oracle("interrogate-read-only-when-asked")
def interrogate_readonly(view):
    failures, evidence = no_edits_verdict(view)
    return failed(failures, *evidence) if failures else passed(*evidence)


@oracle("interrogate-multi-reviewer-adversarial")
def interrogate_multi(view):
    reviewers = reviewer_spawns(view)
    evidence = [f"reviewer spawns: {len(reviewers)}", f"one message: {view.one_message(reviewers)}",
                f"reply has a verdict section: {'verdict' in view.final_reply.lower() or 'act on' in view.final_reply.lower()}",
                *reviewer_evidence(view)]
    if len(reviewers) < 2:
        if view.killed and not view.spawns:
            return inconclusive("run killed before reviewers spawned", *evidence)
        return failed(f"{len(reviewers)} reviewer(s); interrogate sends the diff to several", *evidence)
    if not view.one_message(reviewers):
        return failed("reviewers spawned sequentially, not in one message", *evidence)
    if not view.final_reply:
        return inconclusive("no synthesized verdict in a final reply", *evidence)
    return passed(*evidence)


@oracle("interrogate-reviewers-on-different-models")
def interrogate_models(view):
    reviewers = reviewer_spawns(view)
    if len(reviewers) < 2:
        return inconclusive("fewer than two reviewer spawns; nothing to differentiate")
    models = [s.get("model") for s in reviewers]
    distinct = {m for m in models if m}
    evidence = [f"reviewer models: {models}", *reviewer_evidence(view)]
    if len(distinct) >= 2:
        return passed(*evidence)
    labels = {hit.group(0) for hit in (re.search(r"reviewer [a-c]\b", (s.get("prompt_head") or "").lower()) for s in reviewers) if hit}
    if not any(models):
        if len(labels) >= 2:
            return passed(*evidence, f"no model field on this harness; arms differentiated by label: {len(labels)}")
        return inconclusive("spawn carries no model and the prompts show no differentiated arms", *evidence)
    if len(labels) >= 2:
        return passed(*evidence, "same model, differentiated arms (single-vendor harness)")
    return failed("all reviewers on one model with identical arms", *evidence)


@oracle("interrogate-sorts-four-buckets-no-auto-apply")
def interrogate_buckets(view):
    gate = completion_gate(view)
    if gate:
        return gate
    low = view.final_reply.lower()
    present = [b for b in BUCKETS if re.search(rf"(?:^|\n)\W*{b}\b", low)]
    failures, evidence = no_edits_verdict(view)
    evidence.append(f"buckets present: {present}")
    if len(present) < 4:
        failures.append(f"missing buckets: {[b for b in BUCKETS if b not in present]}")
    return failed(failures, *evidence) if failures else passed(*evidence)


def swarm_workers(view):
    return [s for s in view.spawns if not re.search(r"judge|aggregat|synthes", view.spawn_text(s))]


@oracle("swarm-fans-out-and-aggregates")
def swarm_fanout(view):
    packages = (view.case.get("expect") or {}).get("packages") or []
    workers = swarm_workers(view)
    evidence = [f"worker spawns: {len(workers)} for {len(packages)} packages", f"one message: {view.one_message(workers)}"]
    if not workers:
        return inconclusive("run killed before any spawn", *evidence) if view.killed else failed("no workers spawned", *evidence)
    if len(workers) != len(packages):
        return failed(f"{len(workers)} workers for {len(packages)} packages", *evidence)
    if view.encrypted():
        return inconclusive("worker briefs are encrypted; the package-to-worker mapping cannot be read", *evidence)
    owners = {p: [s.get("seq") for s in workers if p in (s.get("prompt_head") or "").lower()] for p in packages}
    evidence.append(f"package owners: {owners}")
    if any(len(v) != 1 for v in owners.values()):
        return failed("packages are not each named by exactly one worker brief", *evidence)
    if not view.one_message(workers):
        return failed("workers spawned sequentially", *evidence)
    if not view.final_reply:
        return inconclusive("no aggregated report in a final reply", *evidence)
    return passed(*evidence)


@oracle("swarm-workers-report-pass-issues-blocked")
def swarm_statuses(view):
    expect = view.case.get("expect") or {}
    packages, failing = expect.get("packages") or [], expect.get("failing")
    gate = completion_gate(view)
    if gate:
        return gate
    statuses = {}
    for line in view.final_reply.splitlines():
        low = line.lower()
        for p in packages:
            if p in low:
                found = re.search(r"\b(PASS|ISSUES|BLOCKED)\b", line)
                if found:
                    statuses.setdefault(p, found.group(1))
    evidence = [f"statuses in reply: {statuses}"]
    missing = [p for p in packages if p not in statuses]
    if missing:
        return failed(f"no PASS/ISSUES/BLOCKED for: {missing}", *evidence)
    if failing and statuses.get(failing) == "PASS":
        return failed(f"{failing} fails its check but is reported PASS", *evidence)
    return passed(*evidence)


@oracle("swarm-returns-one-report-with-gaps")
def swarm_report(view):
    gate = completion_gate(view)
    if gate:
        return gate
    tables = len(re.findall(r"^\|?\s*:?-{3,}", view.final_reply, re.M))
    gaps = re.search(r"\bgaps?\b|dropout|none missing|no gaps", view.final_reply, re.I)
    packages = (view.case.get("expect") or {}).get("packages") or []
    covered = [p for p in packages if p in view.final_reply.lower()]
    evidence = [f"table separators: {tables}", f"gaps mentioned: {bool(gaps)}", f"packages covered: {covered}"]
    if len(covered) < len(packages):
        return failed("report omits packages", *evidence)
    if tables >= 1 and gaps:
        return passed(*evidence)
    return inconclusive("one reply covers every package; compactness and gap reporting need a judge",
                        *evidence, needs_judge=True, excerpt=excerpt_of(view.final_reply))


ENCODING_FILE = re.compile(r"(?:^|/)(?:tests?|__tests__)/|(?:^|/)test_[^/]*$|_test\.|\.test\.|\.spec\.|(?:^|/)(?:ruff\.toml|mypy\.ini|\.flake8|pyproject\.toml|setup\.cfg|tsconfig[^/]*\.json)$|\.pyi$|\.github/workflows/")


def added_since_base(view):
    log = view.git_log()
    if log is None:
        return None
    base = log[min(max(len(log) - view.base_commits(), 0), len(log) - 1)][0]
    changes, path = {}, None
    for line in (view.git("diff", "--unified=0", base) or "").splitlines():
        if line.startswith("+++ "):
            path = line[4:].removeprefix("b/")
        elif line.startswith("+") and path:
            changes[path] = changes.get(path, "") + line[1:] + "\n"
    for rel in (view.git("ls-files", "--others", "--exclude-standard") or "").split():
        try:
            changes[rel] = (view.project / rel).read_text(encoding="utf-8", errors="replace")
        except OSError:
            pass
    return changes


def encoding_landed(changes, constraint):
    words = [t for t in content_tokens(constraint) if t not in ("not", "remove")]
    needles = words + [a for w in words for a in CONSTRAINT_ALIASES.get(w, ())]
    for path, added in sorted(changes.items()):
        if ENCODING_FILE.search(path) and any(n in added.lower() for n in needles):
            return path
    return None


@oracle("no-comments-spawns-comment-sicko")
def comment_sicko(view):
    sicko = view.spawns_where("comment-sicko", "comment sicko", "comment_sicko")
    evidence = [f"comment-sicko spawns: {len(sicko)}"]
    if not sicko:
        return inconclusive("run killed before any spawn", *evidence) if view.killed and not view.spawns else failed("no Comment Sicko spawn", *evidence)
    signature = any("ha ha ha" in view.spawn_result(s).lower() for s in sicko)
    evidence.append(f"persona signature visible in a result: {signature}")
    expect = view.case.get("expect") or {}
    offer = bool(ENCODING_OFFER.search(view.final_reply))
    evidence.append(f"encoding offer in reply: {offer}")
    if view.project and view.project.is_dir():
        texts = "\n".join(p.read_text(encoding="utf-8", errors="replace") for p in view.project.rglob("*.py") if ".agents" not in p.parts and ".claude" not in p.parts)
        gone = [c for c in expect.get("gone", []) if c in texts]
        survived = [c for c in expect.get("kept", []) if c in texts]
        changes = added_since_base(view) or {}
        encoded = {c: encoding_landed(changes, c) for c in expect.get("kept", []) if c not in survived}
        evidence.append(f"narrating comments still present: {gone}; constraint comments still present: {survived}; encodings landed: {encoded}")
        if gone:
            return failed(f"narrating comments survived: {gone}", *evidence)
        if survived:
            return failed(f"constraint comment survived: {survived}; the comment comes out whether or not it is encoded", *evidence)
        bare = [c for c, path in encoded.items() if not path]
        if bare and not offer:
            return failed(f"constraint comment removed without an encoding or an offer to encode it: {bare}", *evidence)
        return passed(*evidence)
    if signature and offer:
        return passed(*evidence)
    return inconclusive("no project to inspect, so constraint comments cannot be checked; the reply or the spawn result lacks what would stand in", *evidence)


def project_files(view):
    tracked = (view.git("ls-files") or "").split()
    untracked = (view.git("ls-files", "--others", "--exclude-standard") or "").split()
    return {rel for rel in tracked + untracked if not rel.startswith(PRIVATE_PREFIXES) and not CACHE_PATH.search(rel)}


@oracle("deslop-cleans-code-slop")
def deslop_cleans(view):
    expect = view.case.get("expect") or {}
    loaded = "deslop/SKILL.md" in view.lead_reads() or any(
        c.get("name") == "Skill" and (c.get("input") or {}).get("skill") == "deslop" for c in view.tool_calls)
    evidence = [f"deslop skill read by the lead: {loaded}"]
    if not (view.project and view.project.is_dir()):
        return inconclusive("no project to inspect; this pass is graded on the tree, not the reply", *evidence)
    if view.killed and not view.edits():
        return inconclusive("run killed before any edit", *evidence)
    base = view.base_shas()
    if not base:
        return inconclusive("project has no git history to diff against", *evidence)
    texts = "\n".join(p.read_text(encoding="utf-8", errors="replace") for p in view.project.rglob("*.py")
                      if not str(p.relative_to(view.project)).startswith(PRIVATE_PREFIXES))
    survived = [c for c in expect.get("gone", []) if c in texts]
    missing = [f"{rel}: {c}" for rel, wanted in expect.get("kept", {}).items() for c in wanted
               if not (view.project / rel).is_file() or c not in (view.project / rel).read_text(encoding="utf-8", errors="replace")]
    churn = [rel for rel in expect.get("untouched", [])
             if not (view.project / rel).is_file()
             or (view.git("show", f"{base[0]}:{rel}") or "") != (view.project / rel).read_text(encoding="utf-8", errors="replace")]
    planted = {rel for rel in (view.git("ls-tree", "-r", "--name-only", base[-1]) or "").split()
               if not rel.startswith(PRIVATE_PREFIXES) and not CACHE_PATH.search(rel)}
    added = sorted(project_files(view) - planted)
    deleted = sorted(rel for rel in planted if not (view.project / rel).exists())
    changed = [rel for rel in expect.get("preserved", []) if not same_as_history(view, rel)]
    broken = [problem for problem in map(lambda c: check_problem(view.project, c), expect.get("checks", [])) if problem]
    evidence += [f"planted slop still present: {survived}", f"branch work missing: {missing}", f"unrelated edits kept: {churn}",
                 f"files added: {added}", f"files deleted: {deleted}", f"uncommitted work changed: {changed}", f"checks run: {len(expect.get('checks', []))}, failing: {len(broken)}"]
    failures = [] if loaded else ["the deslop skill was never loaded"]
    if survived:
        failures.append(f"planted slop survived: {survived}")
    if missing:
        failures.append(f"the branch's own work went missing: {missing}")
    if churn:
        failures.append(f"unrelated edit kept instead of reverted: {churn}")
    if added:
        failures.append(f"new files appeared: {added}")
    if deleted:
        failures.append(f"files deleted: {deleted}")
    if changed:
        failures.append(f"uncommitted work changed: {changed}")
    failures += [f"check failed after the pass: {problem}" for problem in broken]
    return failed(failures, *evidence) if failures else passed(*evidence)


def same_as_history(view, rel):
    sources = [HISTORIES / view.case["history"] / s["dir"] / rel for s in history_steps(view.case["history"])
               if (HISTORIES / view.case["history"] / s["dir"] / rel).is_file()]
    current = view.project / rel
    return bool(sources) and current.is_file() and current.read_bytes() == sources[-1].read_bytes()


def check_problem(project, check):
    timeout = check.get("timeout_s", 120)
    try:
        run = subprocess.run(shlex.split(check["cmd"]), cwd=project, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return f"{check['cmd']} timed out after {timeout}s"
    if run.returncode != 0:
        return f"{check['cmd']} exited {run.returncode}: {(run.stderr or run.stdout).strip().splitlines()[-1:]}"
    if "stdout" in check and run.stdout != check["stdout"]:
        return f"{check['cmd']} printed {run.stdout!r}, expected {check['stdout']!r}"
    return None


def need_turns(view):
    if len(view.case.get("turns", [])) > 1 and not view.has_turns:
        return inconclusive("multi-turn case but the trace carries no turn markers (core change: stamp events with `turn`)")
    return None


def playbook_titles(skills_root):
    path = Path(skills_root) / "poteto-mode" / "SKILL.md"
    if not path.is_file():
        return {}
    found = (PLAYBOOK_ENTRY.match(line) for line in path.read_text(encoding="utf-8").splitlines())
    return {m.group(1).lower(): m.group(2) for m in found if m}


def continuation_playbooks(name, skills_root):
    allowed = {name} if name else set()
    shape = playbook_shape(name, skills_root) if name else None
    titles = playbook_titles(skills_root)
    for step in (shape or {}).get("steps", []):
        allowed.update(re.findall(r"playbooks/([a-z0-9-]+)\.md", step["text"]))
        allowed.update(titles[t.strip(" .").lower()] for t in re.findall(r"\*\*([^*]+)\*\*", step["text"]) if t.strip(" .").lower() in titles)
    return allowed


def fresh_opening(snapshot, allowed, skills_root):
    first = norm(snapshot["items"][0]["text"])[:40] if snapshot["items"] else ""
    for name in all_playbooks(skills_root):
        shape = playbook_shape(name, skills_root)
        if name not in allowed and shape and shape["prose"] and first and first == norm(shape["prose"][0])[:40]:
            return name
    return None


@oracle("short-prompt-continues-in-context", "poteto-mode-sticky")
def sticky(view):
    gate = need_turns(view)
    if gate:
        return gate
    turns = view.case.get("turns", [])
    follow = [i for i, t in enumerate(turns) if i > 0 and not re.search(r"new task", str(t), re.I)]
    failures, evidence = [], []
    allowed = continuation_playbooks((view.case.get("expect") or {}).get("playbook"), view.skills_root)
    lost = sorted(set(follow) & set(view.trace.get("x_turns_without_events") or []))
    if lost and lost == follow:
        return inconclusive(f"turns {lost} have no events in the lead's chat history, so a re-route cannot be seen")
    for turn in [t for t in follow if t not in lost]:
        events = view.events_in_turn(turn)
        reads = [PLAYBOOK.match(rel).group(1) for seq, rel in view.event_reads() if view.turn_of(seq) == turn and PLAYBOOK.match(rel)]
        worklist = [s for s in view.worklist if view.turn_of(s.get("seq")) == turn]
        opened = identify_playbook(worklist[0]["items"], view.skills_root) if worklist else None
        evidence.append(f"turn {turn}: {len(events)} events, playbook reads {reads}, worklist updates {len(worklist)}, re-opened {opened}")
        if not events:
            failures.append(f"turn {turn}: no activity")
        if reads and set(reads) - allowed:
            failures.append(f"turn {turn}: re-routed to {sorted(set(reads) - allowed)}")
        fresh = fresh_opening(worklist[0], allowed, view.skills_root) if worklist else None
        if fresh:
            failures.append(f"turn {turn}: opened a fresh {fresh} worklist")
        if view.question_texts(turn) and not worklist:
            failures.append(f"turn {turn}: asked the user instead of continuing")
    return failed(failures, *evidence) if failures else passed(*evidence)


@oracle("new-task-rematches")
def new_task(view):
    gate = need_turns(view)
    if gate:
        return gate
    turns = view.case.get("turns", [])
    target = next((i for i, t in enumerate(turns) if re.search(r"new task", str(t), re.I)), None)
    if target is None:
        return inconclusive("no `new task` turn in the case")
    reads = [PLAYBOOK.match(rel).group(1) for seq, rel in view.event_reads() if view.turn_of(seq) == target and PLAYBOOK.match(rel)]
    worklist = [s for s in view.worklist if view.turn_of(s.get("seq")) == target]
    opened = identify_playbook(worklist[0]["items"], view.skills_root) if worklist else None
    want = (view.case.get("expect") or {}).get("rematch", "investigation")
    evidence = [f"turn {target}: playbook reads {reads}, worklist opened {opened}"]
    if (reads and reads[0] == want) or opened == want:
        return passed(*evidence)
    if not view.events_in_turn(target):
        return inconclusive("no events in the `new task` turn", *evidence)
    return failed(f"`new task` did not re-match to {want}", *evidence)


@oracle("overnight-contract-routes-to-figure-it-out")
def overnight_route(view):
    result = step_away(view)
    if result["verdict"] != PASS:
        return result
    log_writes = [e for e in view.edits() if e[2] == "log"] + [c for c in view.commands() if re.search(r"decisions\.tsv|\.audit/", c[1])]
    on_disk = []
    if view.project and view.project.is_dir():
        for root in [view.project] + [Path(w) for w in view.worktrees() or []]:
            on_disk += [str(p) for p in Path(root).glob("decisions.tsv")] + [str(p) for p in Path(root).glob(".audit/*.tsv")]
    evidence = [*result["evidence"], f"decision log writes: {len(log_writes)}", f"logs on disk: {on_disk[:3]}"]
    if log_writes or on_disk:
        return passed(*evidence)
    if view.killed:
        return inconclusive("routed through figure-it-out; run killed before a decision log row", *evidence)
    return failed("no decision log kept", *evidence)


def finished_in_first_turn(view, commits):
    later_turns = range(1, len(view.case.get("turns", [])))
    return (not view.killed and bool(commits) and view.has_turns and bool(view.reply_of_turn(0))
            and not any(commits_made(view, turn) or view.source_edits(turn) for turn in later_turns))


@oracle("autonomous-run-uses-loop-facility")
def loop_facility(view):
    prompt = " ".join(str(t) for t in view.case.get("turns", []))
    loops = [c for c in view.tool_calls if c.get("name") in ("Monitor", "loop", "Loop", "schedule")]
    watchers = view.spawns_where("watch", "wake", "re-check", "heartbeat")
    shell_loops = [c for c in view.commands() if re.search(r"\bwhile\s+(?:true|:|\[)|\bsleep\s+\d+", c[1])]
    commits = len(view.run_commits()) if view.run_commits() is not None else None
    evidence = [f"loop tool calls: {len(loops)}", f"watcher spawns: {len(watchers)}", f"shell loops: {len(shell_loops)}",
                f"commits past fixture: {commits}", f"prompt asks for /loop: {'/loop' in prompt}"]
    if loops or watchers or shell_loops:
        return passed(*evidence)
    if finished_in_first_turn(view, commits):
        return inconclusive("the run met its finish condition inside the first turn and never needed a wake", *evidence)
    if commits is not None and commits >= 2:
        return inconclusive("iterations happened but no loop facility is visible in the trace", *evidence)
    return inconclusive("no loop facility visible; the harness may have ended the turn", *evidence) if view.killed else \
        failed("no loop facility, watcher, or iteration evidence", *evidence)


@oracle("pre-answered-permission-not-asked")
def no_permission_ask(view):
    asked = view.asked_user()
    questions = [q for q in view.question_texts() if "commit" in q.lower()]
    commits = len(view.run_commits()) if view.run_commits() is not None else None
    evidence = [f"ask tool calls: {bool(asked)}", f"commit questions in text: {questions[:2]}", f"commits past fixture: {commits}"]
    if asked or questions:
        return failed("the run asked before committing despite the pre-answer", *evidence)
    if commits is None:
        return inconclusive("no project to count commits; no asks seen", *evidence)
    if commits == 0:
        return inconclusive("nothing committed, so the permission was never reached", *evidence)
    return passed(*evidence)


@oracle("session-override-keeps-going")
def keeps_going(view):
    asked = view.asked_user(0)
    questions = view.question_texts(0)
    calls = len([c for c in view.tool_calls if view.turn_of(c.get("seq")) in (0, None)])
    evidence = [f"ask tool calls: {bool(asked)}", f"questions to the user: {questions[:2]}", f"tool calls in the run: {calls}"]
    if asked or questions:
        return failed("the run stopped to ask after `going to bed`", *evidence)
    if calls < 10:
        return inconclusive("too little activity to show sustained work", *evidence)
    return passed(*evidence)


def review_threads(view):
    spawned = {s.get("seq"): view.spawn_text(s) for s in view.spawns}
    threads = set()
    for call in view.tool_calls:
        given = call.get("input") or {}
        if call.get("name") in SPAWN_TOOLS and given.get("task_name"):
            label = " ".join([spawned.get(call.get("seq"), "")] + [str(given.get(k) or "") for k in ("task_name", "agent_type", "description")])
            if "review" in label.lower():
                threads.add(str(given["task_name"]))
    return threads


def review_followups(view, turn):
    threads = review_threads(view)
    return [c for c in view.tool_calls
            if c.get("name") in FOLLOWUP_TOOLS and (turn is None or view.turn_of(c.get("seq")) == turn)
            and str((c.get("input") or {}).get("target") or "").rsplit("/", 1)[-1] in threads]


@oracle("show-me-your-work-spawns-trail-reviewer")
def trail_reviewer(view):
    turns = view.case.get("turns", [])
    turn = len(turns) - 1 if len(turns) > 1 else None
    if turn is not None and not view.has_turns:
        return inconclusive("multi-turn case but the trace carries no turn markers (core change: stamp events with `turn`)")
    reviewers = view.spawns_where("trail reviewer", "decision log", "decision trail", "decisions.tsv", "review the trail", turn=turn)
    followups = review_followups(view, turn)
    evidence = [f"trail reviewer spawns: {len(reviewers)}", f"lead model: {view.model}", f"reviewer models: {[s.get('model') for s in reviewers]}"]
    if followups and not reviewers:
        return passed(*evidence, f"follow-ups to a review thread: {len(followups)}")
    if not reviewers:
        if view.killed and turn is None:
            return inconclusive("run killed before the review", *evidence)
        return failed("no trail reviewer spawned before the summary", *evidence)
    model = reviewers[0].get("model")
    if model and view.model and model.split("-")[0] in str(view.model):
        evidence.append("reviewer shares the lead's model family; step-down expected when it equals the working model")
    return passed(*evidence)


@oracle("show-me-your-work-review-ends-with-attention")
def attention_section(view):
    gate = completion_gate(view)
    if gate:
        return gate
    text = view.final_reply
    heads = list(re.finditer(r"(?im)^\W*attention\W*$|^#+\s*attention\b|\*\*attention\*\*", text))
    reviewed = re.search(r"reviewed by \S+@\S+", text, re.I)
    evidence = [f"attention headings: {len(heads)}", f"reviewed-by line: {bool(reviewed)}"]
    if not heads:
        return failed("reply has no Attention section", *evidence)
    tail = text[heads[-1].end():]
    later_heads = re.findall(r"(?m)^#+\s+\S|^\*\*[A-Z][^*]+\*\*\s*$", tail)
    if later_heads:
        return failed("Attention is not the last section", *evidence, f"later headings: {later_heads[:2]}")
    return passed(*evidence) if reviewed else failed("Attention section lacks the `reviewed by <model>@<effort>` line", *evidence)


@oracle("poteto-tdd-failing-test-first")
def tdd_first(view):
    tests = [e for e in view.edits() if e[2] == "test"]
    sources = view.source_edits()
    runs = [(seq, c, ok, head) for seq, c, ok, head in view.commands() if re.search(r"unittest|pytest|test_|npm test|node .*test", c)]
    failing = [r for r in runs if r[2] is False or re.search(r"\bFAIL|Error|failures=\d*[1-9]|✗|not ok", r[3])]
    green = [r for r in runs if r[2] is not False and re.search(r"\bOK\b|passed|ok\b", r[3]) and not re.search(r"FAIL|Error", r[3])]
    evidence = [f"test edits: {[e[1] for e in tests][:2]}", f"source edits: {[e[1] for e in sources][:2]}",
                f"failing runs: {len(failing)}, green runs after a source edit: {len([g for g in green if sources and g[0] > sources[0][0]])}"]
    if not tests:
        if view.spawns and not sources:
            return inconclusive("work delegated; the delegate's test-first order is not visible", *evidence)
        return failed("no test file written", *evidence) if not view.killed else inconclusive("run killed before a test was written", *evidence)
    if not sources:
        return inconclusive("test written but no fix edit visible" + (" (run killed)" if view.killed else ""), *evidence)
    if tests[0][0] > sources[0][0]:
        return failed("source edited before the test", *evidence)
    if not any(f[0] > tests[0][0] and f[0] < sources[0][0] for f in failing):
        return failed("no failing run between writing the test and the fix", *evidence)
    if not any(g[0] > sources[0][0] for g in green):
        return inconclusive("failing test first and fix on top, but no green rerun visible", *evidence)
    return passed(*evidence)


@oracle("unslop-takes-target-and-rules")
def unslop_target(view):
    changed = view.changed_since_base()
    if changed is None:
        return inconclusive("no project git state to inspect")
    only = set((view.case.get("expect") or {}).get("only") or ["README.md"])
    stray = sorted(changed - only)
    readme = view.project / "README.md"
    dashes = readme.read_text(encoding="utf-8").count("—") if readme.is_file() else None
    evidence = [f"files changed since the fixture: {sorted(changed)}", f"em dashes left in README: {dashes}"]
    if not changed:
        return inconclusive("nothing changed" + (" (run killed)" if view.killed else ""), *evidence)
    if stray:
        return failed(f"edited outside the target: {stray}", *evidence)
    if dashes:
        return failed(f"{dashes} em dash(es) remain", *evidence)
    return passed(*evidence)


@oracle("bro-restates-last-message")
def bro(view):
    gate = need_turns(view)
    if gate:
        return gate
    last = len(view.case.get("turns", [])) - 1
    before, after = view.reply_of_turn(last - 1), view.reply_of_turn(last) or view.final_reply
    evidence = [f"prior reply length {len(before)}, restatement length {len(after)}", f"code spans in restatement: {after.count('`')}"]
    if not before or not after:
        return inconclusive("one of the two replies is missing", *evidence)
    if len(after) >= len(before):
        return failed("restatement is not shorter", *evidence)
    if after.count("`") == 0:
        return passed(*evidence)
    return inconclusive("shorter, but still carries code spans; plainness needs a judge", *evidence, needs_judge=True, excerpt=after[:1500])


@oracle("typescript-rules-auto-load-on-ts-files")
def ts_autoload(view):
    prompt = " ".join(str(t) for t in view.case.get("turns", []))
    if "typescript-best-practices" in prompt:
        return inconclusive("prompt names the skill; auto-load not exercised")
    touched = [e for e in view.edits() if e[1].endswith((".ts", ".tsx"))] + \
        [(seq, rel) for seq, rel in view.event_reads() if rel.endswith((".ts", ".tsx"))]
    loaded = view.skill_read("typescript-best-practices")
    evidence = [f".ts files touched by the lead: {len(touched)}", f"skill loaded (lead or delegate): {loaded}"]
    if loaded:
        return passed(*evidence)
    if not touched and not view.spawns:
        return inconclusive("no .ts file touched" + (" (run killed)" if view.killed else ""), *evidence)
    return failed("a .ts file was touched without loading typescript-best-practices", *evidence)


@oracle("blast-radius-finds-breakage")
def blast_finds(view):
    gate = completion_gate(view)
    if gate:
        return gate
    diff_files = set((view.case.get("expect") or {}).get("diff_files") or [])
    cited = set(re.findall(r"\b[\w/.-]+\.(?:py|ts|sh|md|json)\b", view.final_reply))
    beyond = sorted(f for f in cited if f not in diff_files and not any(f.endswith("/" + d) or d.endswith("/" + f) for d in diff_files))
    fact = re.search(r"one fact|safe because", view.final_reply, re.I)
    evidence = [f"files cited beyond the diff: {beyond[:5]}", f"one-fact wording: {bool(fact)}"]
    if not beyond:
        return failed("reply names nothing beyond the diff", *evidence)
    return passed(*evidence) if fact else inconclusive("breakage beyond the diff named; the one-fact framing needs a judge",
                                                        *evidence, needs_judge=True, excerpt=excerpt_of(view.final_reply))


@oracle("blast-radius-proves-one-fact-by-running-code")
def blast_proves(view):
    runs = [(seq, c, ok, head) for seq, c, ok, head in view.commands() if re.search(r"\bpython3?\b|\bnode\b|\bbash\b|\.sh\b|unittest|pytest", c)
            and not re.match(r"^(cat|ls|git)\b", c.strip())]
    evidence = [f"code runs: {len(runs)}", f"reply mentions a fact: {bool(re.search(r'fact', view.final_reply, re.I))}"]
    if not runs:
        return inconclusive("run killed before any code ran", *evidence) if view.killed else failed("no code was run to prove the fact", *evidence)
    if not view.final_reply:
        return inconclusive("no final reply", *evidence)
    pasted = any(" ".join(c.split())[:40] in " ".join(view.final_reply.split()) for _, c, _, _ in runs)
    evidence.append(f"a run command is pasted in the reply: {pasted}")
    if pasted and re.search(r"fact", view.final_reply, re.I):
        return passed(*evidence)
    return inconclusive("code ran; whether it proves the one fact needs a judge", *evidence, needs_judge=True, excerpt=excerpt_of(view.final_reply))


@oracle("technical-writing-picks-mode-then-sentences")
def tw_mode_first(view):
    gate = completion_gate(view)
    if gate:
        return gate
    low = view.final_reply.lower()
    modes = [(low.find(m), m) for m in ("tutorial", "how-to", "reference", "explanation") if m in low]
    first_finding = min([p for p in (low.find("`"), low.find("line "), low.find("sentence")) if p >= 0] or [len(low)])
    evidence = [f"modes mentioned: {sorted(modes)}", f"first sentence-level finding at {first_finding}"]
    if not modes:
        return failed("reply never names the document's mode", *evidence)
    if min(modes)[0] < first_finding:
        return passed(*evidence)
    return failed("sentence-level findings start before the mode is named", *evidence)


def author_result(text):
    low = (text or "").lower()
    if "independent review not required" in low:
        return "not required"
    if "independent review required" in low or "independent review is required" in low:
        return "required"
    return None


@oracle("poteto-runs-documentation-impact-before-completion")
def doc_impact_before_completion(view):
    turn = 0 if len(view.case.get("turns", [])) > 1 else None
    if turn is not None and not view.has_turns:
        return inconclusive("multi-turn case but the trace carries no turn markers (core change: stamp events with `turn`)")
    reads = [(seq, rel) for seq, rel in view.event_reads() if rel.startswith("documentation-impact/") and (turn is None or view.turn_of(seq) == turn)]
    read_any = bool(reads) or view.skill_read("documentation-impact")
    reply = view.reply_of_turn(turn) if turn is not None else view.final_reply
    result = author_result(reply) or author_result(" ".join(view.texts(turn)))
    evidence = [f"documentation-impact read in the change turn: {bool(reads)} (anywhere: {read_any})", f"author result in reply: {result}"]
    if not read_any:
        return inconclusive("run killed before completion", *evidence) if view.killed else failed("documentation-impact never ran before completion", *evidence)
    if not result:
        return failed("completion reply carries no author result", *evidence) if reply else inconclusive("no completion reply", *evidence)
    return passed(*evidence)


@oracle("documentation-impact-independent-review-pass-required")
def doc_impact_review(view):
    turn = 0 if len(view.case.get("turns", [])) > 1 else None
    if turn is not None and not view.has_turns:
        return inconclusive("multi-turn case but the trace carries no turn markers (core change: stamp events with `turn`)")
    reply = view.reply_of_turn(turn) if turn is not None else view.final_reply
    result = author_result(reply) or author_result(" ".join(view.texts(turn)))
    reviewers = view.spawns_where("trail reviewer", "independent review", "review the documentation", "documentation-impact", turn=turn)
    verdict_word = re.search(r"\bpass\b", reply or "", re.I)
    evidence = [f"author result: {result}", f"review spawns: {len(reviewers)}", f"pass verdict in reply: {bool(verdict_word)}"]
    if result is None:
        return inconclusive("no author result to gate on" + (" (run killed)" if view.killed else ""), *evidence)
    if result == "not required":
        return failed("a documented flag changed yet the author result says review is not required", *evidence)
    if not reviewers:
        return failed("review required but no independent reviewer spawned", *evidence)
    return passed(*evidence) if verdict_word else failed("reviewer spawned but no `pass` verdict reported before completion", *evidence)


@oracle("documentation-impact-modes-invocable")
def doc_impact_modes(view):
    turns = view.case.get("turns", [])
    turn = len(turns) - 1 if len(turns) > 1 else None
    if turn is not None and not view.has_turns:
        return inconclusive("multi-turn case but the trace carries no turn markers (core change: stamp events with `turn`)")
    reads = [rel for seq, rel in view.event_reads() if rel.startswith("documentation-impact/") and (turn is None or view.turn_of(seq) == turn)]
    edits = view.project_edits(turn)
    reply = view.reply_of_turn(turn) if turn is not None else view.final_reply
    word = re.search(r"\b(pass|needs changes|unverified)\b", reply or "", re.I)
    evidence = [f"skill read in the review turn: {bool(reads)}", f"edits in the review turn: {[e[1] for e in edits][:3]}", f"review verdict word: {word.group(1) if word else None}"]
    failures = []
    if not reads and not view.skill_read("documentation-impact"):
        failures.append("documentation-impact not read in review mode")
    if edits:
        failures.append("review mode edited files")
    if not word:
        failures.append("no review verdict (pass / needs changes / unverified)")
    return failed(failures, *evidence) if failures else passed(*evidence)


def candidate_spawns(view):
    return [s for s in view.spawns if not re.search(r"judge|cross-judge|score|rubric", view.spawn_text(s))]


def judge_spawns(view):
    return [s for s in view.spawns if re.search(r"judge|cross-judge|rubric", view.spawn_text(s))]


@oracle("arena-candidate-count-adjustable")
def arena_count(view):
    want = int((view.case.get("expect") or {}).get("candidates") or 0)
    candidates = candidate_spawns(view)
    evidence = [f"candidate spawns: {len(candidates)} (wanted {want})", f"judge spawns: {len(judge_spawns(view))}", f"total spawns: {len(view.spawns)}"]
    if not view.spawns:
        return inconclusive("run killed before any spawn", *evidence) if view.killed else failed("no spawns", *evidence)
    if view.encrypted():
        return inconclusive(f"briefs encrypted; {len(view.spawns)} spawns total, roles unreadable", *evidence)
    return passed(*evidence) if len(candidates) == want else failed(f"{len(candidates)} candidates, not {want}", *evidence)


@oracle("arena-candidates-own-worktrees")
def arena_worktrees(view):
    candidates = candidate_spawns(view)
    adds = [c for c in view.commands() if re.search(r"git worktree add|mkdir -p .*(?:candidate|arm|attempt)", c[1])]
    paths = set()
    for s in candidates:
        for match in re.findall(r"(/[\w./-]+(?:worktree|candidate|arm|attempt)[\w./-]*)", s.get("prompt_head") or "", re.I):
            paths.add(match)
    evidence = [f"worktree/dir setup commands: {len(adds)}", f"distinct output paths named in briefs: {len(paths)}", f"worktrees on disk: {len(view.worktrees() or [])}"]
    if not candidates:
        return inconclusive("no candidate spawns", *evidence)
    if view.encrypted():
        return inconclusive("briefs encrypted; worktree assignment unreadable", *evidence) if not adds else passed(*evidence)
    if len(paths) >= len(candidates) or len(adds) >= len(candidates) or len(view.worktrees() or []) > len(candidates):
        return passed(*evidence)
    return failed("candidates do not each get their own worktree or directory", *evidence)


@oracle("arena-fans-out-and-grafts")
def arena_grafts(view):
    candidates, judges = candidate_spawns(view), judge_spawns(view)
    low = view.final_reply.lower()
    evidence = [f"candidates: {len(candidates)} in one message: {view.one_message(candidates)}", f"judges: {len(judges)}",
                f"reply names a base: {'base' in low}, grafts: {'graft' in low}, verification: {'verif' in low}"]
    if len(candidates) < 2:
        return inconclusive("run killed before the fan-out", *evidence) if view.killed else failed("fewer than two candidates", *evidence)
    if not view.one_message(candidates):
        return failed("candidates spawned sequentially", *evidence)
    if not view.final_reply:
        return inconclusive("no synthesis reply" + (" (run killed)" if view.killed else ""), *evidence)
    if "base" in low and ("graft" in low or "converge" in low or "consensus" in low):
        return passed(*evidence)
    return failed("reply does not name the base and the grafts", *evidence)


@oracle("arena-readonly-cross-judge")
def arena_judge(view):
    candidates, judges = candidate_spawns(view), judge_spawns(view)
    evidence = [f"judge spawns: {len(judges)}", f"candidate models: {sorted({s.get('model') for s in candidates if s.get('model')})}",
                f"judge models: {[s.get('model') for s in judges]}"]
    if not judges:
        if view.encrypted():
            return inconclusive("briefs encrypted; the judge cannot be told from the candidates", *evidence)
        return inconclusive("run killed before the judge", *evidence) if view.killed else failed("no cross-judge spawned", *evidence)
    judge = judges[-1]
    readonly = bool(re.search(r"read[- ]only|do not (?:edit|write|modify)", judge.get("prompt_head") or "", re.I))
    evidence.append(f"judge brief marked read-only: {readonly}")
    if judge.get("seq", 0) < max(s.get("seq", 0) for s in candidates):
        return failed("judge spawned before the candidates", *evidence)
    cand_models = {s.get("model") for s in candidates if s.get("model")}
    failures = []
    if judge.get("model") and judge["model"] in cand_models and len(cand_models) > 1:
        failures.append("judge shares a candidate model although the candidates spanned several")
    if judge.get("prompt_head") and not readonly:
        failures.append("judge brief is not read-only")
    return failed(failures, *evidence) if failures else passed(*evidence)


@oracle("arena-lead-reads-rationales-and-base")
def arena_lead_reads(view):
    judges = judge_spawns(view)
    after = max((s.get("seq", 0) for s in judges), default=0)
    reads = []
    for call in view.tool_calls:
        if call.get("seq", 0) <= after:
            continue
        given = call.get("input") or {}
        for field in PATH_FIELDS:
            if isinstance(given.get(field), str):
                reads.append(given[field])
        if call.get("name") in SHELL_TOOLS:
            reads += shell_paths(str(given.get(SHELL_TOOLS[call["name"]]) or ""))
    rationales = [p for p in reads if re.search(r"rationale|synthesis", p, re.I)]
    others = [p for p in reads if p not in rationales and not skill_rel(p)]
    want = int((view.case.get("expect") or {}).get("candidates") or 2)
    evidence = [f"rationale files read after the judge: {len(rationales)}", f"other candidate files read: {len(others)}"]
    if not judges:
        return inconclusive("no judge spawn to anchor the read phase", *evidence)
    if len(rationales) >= want and others:
        return passed(*evidence)
    if view.killed:
        return inconclusive("run killed during the read phase", *evidence)
    return failed("lead did not read every rationale and the base", *evidence)


@oracle("arena-second-opinion-includes-current-design")
def arena_second_opinion(view):
    gate = completion_gate(view)
    if gate:
        return gate
    low = view.final_reply.lower()
    current_in_briefs = any(re.search(r"current (?:design|approach)|existing (?:design|approach)", s.get("prompt_head") or "", re.I) for s in view.spawns)
    current_in_reply = bool(re.search(r"current (?:design|approach)|existing (?:design|approach)|your (?:design|approach)", low))
    improved = bool(re.search(r"improv|confirm|better than|kept the current|no change", low))
    evidence = [f"current design named in a brief: {current_in_briefs}", f"in the reply: {current_in_reply}", f"improve/confirm statement: {improved}"]
    if (current_in_briefs or current_in_reply) and improved:
        return passed(*evidence)
    if view.encrypted() and current_in_reply:
        return passed(*evidence)
    return failed("synthesis does not treat the current design as a candidate and say whether the panel improved on it", *evidence)


def runner_spawns(view):
    return view.spawns_where("runner", "candidate design", "architect", "design sketch", "design package")


@oracle("architect-grounds-with-how-and-why")
def architect_grounds(view):
    how, why = how_evidence(view), why_evidence(view)
    runners = runner_spawns(view)
    first_runner = min((s.get("seq", 0) for s in runners), default=None)
    evidence = [f"how evidence at seq {how}", f"why evidence at seq {why}", f"first runner at seq {first_runner}"]
    if how is None:
        return inconclusive("run killed before grounding", *evidence) if view.killed and not runners else failed("architect did not run how first", *evidence)
    if first_runner is not None and how > first_runner:
        return failed("runners spawned before how", *evidence)
    return passed(*evidence)


@oracle("architect-runs-arena-for-sketches")
def architect_arena(view):
    runners = runner_spawns(view)
    read = view.skill_read("arena")
    callers = sum(1 for s in runners if re.search(r"caller|usage", s.get("prompt_head") or "", re.I))
    evidence = [f"arena skill read: {read}", f"runner spawns: {len(runners)}", f"briefs that lead with caller usage: {callers}"]
    if len(runners) < 2:
        return inconclusive("run killed before the sketch fan-out", *evidence) if view.killed else failed("fewer than two runner sketches", *evidence)
    if not view.one_message(runners):
        return failed("runners spawned sequentially", *evidence)
    if view.encrypted():
        return inconclusive("runner briefs encrypted; caller-usage-first cannot be read", *evidence)
    if callers == 0 and all(s.get("prompt_head") for s in runners):
        return failed("runner briefs never mention the caller's usage", *evidence)
    return passed(*evidence) if read else failed("arena skill never read", *evidence)


@oracle("architect-sketches-before-implementation")
def architect_sketch_first(view):
    runners = runner_spawns(view)
    sources = view.source_edits()
    first_runner = min((s.get("seq", 0) for s in runners), default=None)
    evidence = [f"first runner at seq {first_runner}", f"first source edit at seq {sources[0][0] if sources else None}"]
    if first_runner is None:
        return inconclusive("no sketch phase visible" + (" (run killed)" if view.killed else ""), *evidence)
    if sources and sources[0][0] < first_runner:
        return failed("source edited before the design sketches", *evidence)
    return passed(*evidence)


@oracle("architect-checkpoint-opt-in")
def architect_checkpoint(view):
    sources = view.source_edits()
    low = view.final_reply.lower()
    pause = bool(re.search(r"sign-off|approve|before implementing|proceed\?|shall i implement|waiting", low))
    evidence = [f"source edits: {[e[1] for e in sources][:3]}", f"reply pauses for sign-off: {pause}"]
    if sources:
        return failed("checkpoint requested but implementation started", *evidence)
    if not view.final_reply:
        return inconclusive("no final reply" + (" (run killed)" if view.killed else ""), *evidence)
    return passed(*evidence) if pause else inconclusive("no implementation; whether the reply presents the design and pauses needs a judge",
                                                         *evidence, needs_judge=True, excerpt=excerpt_of(view.final_reply))
