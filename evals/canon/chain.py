#!/usr/bin/env python3
"""Census of how far each screened run followed the poteto-mode chain.

The chain a /poteto-mode run is meant to follow:

  1. the invocation injects poteto-mode/SKILL.md
  2. the agent reads one playbook, the one the task matches
  3. it opens a worklist whose first items are that playbook's steps, verbatim
  4. it reads the principle leaf a decision needs before making the decision
  5. it delegates code-writing to a subagent whose brief names the data shape
  6. its reply cites only principles whose leaf it read

Each agent's trace is parsed into one list of Events (reads of mounted skill
files, workspace edits, spawns, worklist updates, messages, denials), and
every stage is computed from that list alone, so Claude and Codex runs are
measured by the same code.

  chain.py [ROOT ...] [--jsonl FILE] [--markdown]

A ROOT is a directory of screen.py --out dirs, or one such dir. Every run dir
under it (<out>/<agent>/<rule>/[<case>/]<arm>/runs/<case>/with_skill[/run-N]
holding trace.jsonl) becomes one JSON line.
"""
import argparse
import importlib.util
import json
import re
import shlex
import sys
from dataclasses import dataclass, field
from pathlib import Path

CANON = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("canon_screen", CANON / "screen.py")
screen = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(screen)

DEFAULT_ROOTS = (Path("/private/tmp/canon-entry"), Path("/private/tmp/canon-ws"), Path("/private/tmp/canon-screen"))
INDEX = "poteto-mode/SKILL.md"
PLAYBOOK = re.compile(r"^poteto-mode/playbooks/([\w-]+)\.md$")
PRINCIPLE_ENTRY = re.compile(r"\*\*(.+?)\*\* \(\*\*(principle-[a-z-]+)\*\*\)")

# The playbook each case's prompt asks for: add or change behavior is Feature,
# a behavior-preserving tidy, dedupe, deepen, or swap is Refactoring, a reported
# defect is Bug fix. None marks a case no bundled playbook owns (a spec review).
EXPECTED_PLAYBOOK = {
    "paid-articles": "feature", "hold-expiry": "feature", "session-lineage-usage": "feature",
    "session-stats-json": "feature", "shipment-tracking": "feature", "projects-dashboard": "feature",
    "billing-late-fees": "feature", "cart-quantity": "feature", "checkout-bdd": "feature",
    "checkout-rules": "feature", "register-email": "feature", "billing-pause": "feature",
    "sessions-by-label": "feature", "sessions-by-tag": "feature", "csv-export": "feature",
    "payroll-overtime": "feature", "cron-paused-reason": "feature", "order-line-items": "feature",
    "session-tree": "feature", "refund-window": "feature", "paylane-webhooks": "feature",
    "marketplace-subtotal": "feature", "free-shipping": "feature",
    "account-types": "refactoring", "harness-families": "refactoring", "invoice-customers": "refactoring",
    "subagent-routing-wrapper": "refactoring", "harness-names": "refactoring", "pricing-modules": "refactoring",
    "terminal-name": "refactoring", "invoice-credit-rounding": "refactoring",
    "payroll-invoice-rounding": "refactoring", "billing-cleanup": "refactoring", "delivery-dates": "refactoring",
    "textkit-exports": "refactoring", "textkit-tidy": "refactoring",
    "http-client-small": "refactoring", "http-client-swap": "refactoring",
    "member-coupon": "bug-fix", "orders-pagination": "bug-fix", "zero-price": "bug-fix",
    "withdrawal-story": None, "loyalty-points": None,
}

READ_VERBS = {"cat", "nl", "less", "more", "bat", "awk", "head", "tail", "sed"}
TRIM_VERBS = {"head", "tail"}
WRITE_VERBS = {"tee", "rm", "mv", "cp", "touch", "apply_patch"}
CLAUDE_EDIT_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}
CLAUDE_WORKLIST_TOOLS = {"TodoWrite", "TaskCreate", "TaskUpdate"}
CLAUDE_SPAWN_TOOLS = {"Agent", "Task"}
CODEX_SPAWN_TOOLS = {"spawn_agent", "spawn"}
SHELL_WRAPPER = re.compile(r"^/bin/(?:ba|z)?sh -lc ")
HEREDOC = re.compile(r"<<-?\s*(['\"]?)(\w+)\1[^\n]*\n.*?\n\s*\2\s*(?:\n|$)", re.DOTALL)
DATA_SHAPE = re.compile(r"data shape|organizing structure|principle-[a-z-]+|model[- ]the[- ]domain", re.IGNORECASE)
FOR_LOOP = re.compile(r"\bfor (\w+) in ([^;]+?);\s*do\s+(.+?);?\s*done\b")
WORKLIST_WORD = re.compile(r"\b(worklist|todo list|to-do list)\b", re.IGNORECASE)


@dataclass(frozen=True)
class Event:
    """One thing a run did, in trace order. actor is "main" or "delegate"."""
    index: int
    actor: str
    kind: str  # read, edit, spawn, wait, worklist, message, denied
    path: str = ""
    partial: bool = False
    text: str = ""


@dataclass
class Trace:
    events: list = field(default_factory=list)
    final: str = ""
    slash_commands: tuple = ()
    worklist_tool_offered: bool = None  # None when the trace does not list tools


def md_lines(text):
    return text.count("\n") + (0 if text.endswith("\n") or not text else 1)


def resolve(token, tree, cwd=""):
    """The tree path a shell or tool path names, or None. Paths may sit under
    any mount (skills/pstack, .claude/skills, .agents/skills, an absolute cwd),
    so the longest suffix that is a tree file wins."""
    token = token.strip("'\"`")
    if cwd and not token.startswith("/"):
        token = f"{cwd.rstrip('/')}/{token}"
    parts = [part for part in token.split("/") if part and part != "."]
    for start in range(len(parts)):
        candidate = "/".join(parts[start:])
        if candidate in tree:
            return candidate
    return None


def sed_is_partial(tokens, lines):
    if "-n" not in tokens and not any(token.startswith("-n") for token in tokens):
        return False
    for token in tokens:
        match = re.fullmatch(r"'?(\d+)(?:,(\d+|\$))?p'?", token)
        if match:
            start, end = int(match.group(1)), match.group(2)
            if end is None:
                return True
            return start > 1 or (end != "$" and int(end) < lines)
    return True


def unquoted_newlines_to_semicolons(command):
    out, quote = [], None
    for char in command:
        if quote:
            quote = None if char == quote else quote
        elif char in "'\"":
            quote = char
        elif char == "\n":
            char = ";"
        out.append(char)
    return "".join(out)


def expand_loop(match):
    """`for n in a b; do cat $n/SKILL.md; done` as one statement per word."""
    name, words, body = match.groups()
    variable = re.compile(rf"\$(?:{name}\b|\{{{name}\}})")
    return "; ".join(variable.sub(word, body) for word in words.split())


def split_shell(command):
    """[[stage tokens, ...] per pipeline], split only at unquoted operators,
    with heredoc bodies dropped. Operators stay out of the stage tokens except
    redirects, which stay where they are."""
    if SHELL_WRAPPER.match(command):
        body = SHELL_WRAPPER.sub("", command, count=1)
        try:
            command = shlex.split(body)[0]
        except (ValueError, IndexError):
            command = body.strip("'\"")
    command = FOR_LOOP.sub(expand_loop, unquoted_newlines_to_semicolons(HEREDOC.sub("\n", command)))
    lexer = shlex.shlex(command, posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    try:
        tokens = list(lexer)
    except ValueError:
        tokens = command.split()
    pipelines, stages, stage = [], [], []
    for token in tokens + [";"]:
        if token in (";", "&&", "||", "&", "|", "(", ")", ";;", "|&"):
            while stage and re.match(r"^\w+=", stage[0]):
                stage = stage[1:]
            if stage:
                stages.append(stage)
            stage = []
            if token != "|" and stages:
                pipelines.append(stages)
                stages = []
        else:
            stage.append(token)
    return pipelines


def shell_effects(command, tree):
    """(reads, writes) of one shell command: reads as (tree path, partial),
    writes as the paths a redirect, sed -i, or a write verb names. Search
    commands (rg, grep, find, ls, wc) read nothing."""
    reads, writes, cwd = [], [], ""
    for stages in split_shell(command):
        first = stages[0]
        if first[0] == "cd" and len(first) > 1:
            cwd = first[1]
            continue
        trimmed_later = any(stage[0] in TRIM_VERBS or (stage[0] == "sed" and "-n" in stage) for stage in stages[1:])
        for tokens in stages:
            for at, token in enumerate(tokens[:-1]):
                if token in (">", ">>") and tokens[at + 1] != "/dev/null":
                    writes.append(tokens[at + 1])
            words = [token for at, token in enumerate(tokens) if token not in (">", ">>", ">&", "<") and (at == 0 or tokens[at - 1] not in (">", ">>", ">&", "<"))]
            if not words:
                continue
            verb = words[0].rsplit("/", 1)[-1]
            options = [word for word in words[1:] if word.startswith("-")]
            if verb in ("sed", "perl") and any(option.startswith(("-i", "-pi")) for option in options):
                writes.append(words[-1])
                continue
            if verb in WRITE_VERBS:
                writes += [word for word in words[1:] if not word.startswith("-")]
                continue
            if verb not in READ_VERBS:
                continue
            for word in words[1:]:
                path = resolve(word, tree, cwd)
                if path is None:
                    continue
                partial = verb in TRIM_VERBS or trimmed_later or (verb == "sed" and sed_is_partial(words, tree[path]))
                reads.append((path, partial))
    return reads, writes


def in_workspace(path, cwd, tree):
    """A write that lands in the checkout: not a mounted skill file, not /tmp
    or /dev, and inside cwd when the path is absolute and cwd is known."""
    if not path or resolve(path, tree) or path.startswith(("/tmp", "/private/tmp", "/dev")):
        return False
    if path.startswith("/") and cwd:
        return path.startswith(cwd.rstrip("/") + "/")
    return True


def parse_claude(lines, tree):
    trace = Trace()
    denied_ids, errored_ids, cwd = set(), set(), ""
    records = []
    for index, line in enumerate(lines):
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        records.append((index, record))
        if record.get("type") == "system" and record.get("subtype") == "init":
            cwd = record.get("cwd", "")
            trace.slash_commands = tuple(record.get("slash_commands") or ())
            tools = record.get("tools") or []
            trace.worklist_tool_offered = bool(CLAUDE_WORKLIST_TOOLS & set(tools))
        if record.get("type") == "system" and record.get("subtype") == "permission_denied":
            denied_ids.add(record.get("tool_use_id"))
            trace.events.append(Event(index, "main", "denied", text=record.get("tool_name", "")))
        if record.get("type") == "user":
            for block in (record.get("message") or {}).get("content") or []:
                if isinstance(block, dict) and block.get("type") == "tool_result" and block.get("is_error"):
                    errored_ids.add(block.get("tool_use_id"))
        if record.get("type") == "result":
            trace.final = record.get("result") or ""
    for index, record in records:
        if record.get("type") != "assistant":
            continue
        actor = "delegate" if record.get("parent_tool_use_id") else "main"
        for block in (record.get("message") or {}).get("content") or []:
            kind = block.get("type")
            if kind == "text" and block.get("text", "").strip():
                trace.events.append(Event(index, actor, "message", text=block["text"]))
            if kind != "tool_use":
                continue
            name, data, use_id = block.get("name"), block.get("input") or {}, block.get("id")
            failed = use_id in denied_ids or use_id in errored_ids
            if name == "Read" and not failed:
                path = resolve(data.get("file_path", ""), tree)
                if path:
                    lines_total = tree[path]
                    offset, limit = data.get("offset") or 0, data.get("limit")
                    partial = offset > 1 or (limit is not None and limit < lines_total - max(offset - 1, 0))
                    trace.events.append(Event(index, actor, "read", path, partial))
            elif name == "Skill" and not failed:
                path = resolve(f"{data.get('skill', '')}/SKILL.md", tree)
                if path:
                    trace.events.append(Event(index, actor, "read", path))
            elif name == "Bash" and not failed:
                reads, writes = shell_effects(data.get("command", ""), tree)
                trace.events += [Event(index, actor, "read", path, partial) for path, partial in reads]
                trace.events += [Event(index, actor, "edit", path) for path in writes if in_workspace(path, cwd, tree)]
            elif name in CLAUDE_EDIT_TOOLS and not failed:
                path = data.get("file_path") or data.get("notebook_path") or ""
                if in_workspace(path, cwd, tree):
                    trace.events.append(Event(index, actor, "edit", path))
            elif name in CLAUDE_WORKLIST_TOOLS:
                items = [todo.get("content", "") for todo in data.get("todos") or []] or [data.get("subject", ""), data.get("description", "")]
                trace.events.append(Event(index, actor, "worklist", text="\n".join(item for item in items if item)))
            elif name in CLAUDE_SPAWN_TOOLS:
                trace.events.append(Event(index, actor, "spawn", text=data.get("prompt", "")))
    trace.events.sort(key=lambda event: event.index)
    return trace


def parse_codex(lines, tree, cwd=""):
    """Codex exec --json. Only item.completed items count. A delegate's own
    items run on another thread that this stream never shows."""
    trace = Trace()
    for index, line in enumerate(lines):
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        item = record.get("item") or {}
        if record.get("type") != "item.completed":
            continue
        kind = item.get("type")
        if kind == "agent_message":
            trace.events.append(Event(index, "main", "message", text=item.get("text", "")))
            trace.final = item.get("text", "")
        elif kind == "command_execution":
            reads, writes = shell_effects(item.get("command", ""), tree)
            trace.events += [Event(index, "main", "read", path, partial) for path, partial in reads]
            if item.get("exit_code") == 0:
                trace.events += [Event(index, "main", "edit", path) for path in writes if in_workspace(path, cwd, tree)]
        elif kind == "file_change" and item.get("status") == "completed":
            for change in item.get("changes") or []:
                if in_workspace(change.get("path", ""), cwd, tree):
                    trace.events.append(Event(index, "main", "edit", change["path"]))
        elif kind == "todo_list":
            trace.events.append(Event(index, "main", "worklist", text="\n".join(entry.get("text", "") for entry in item.get("items") or [])))
        elif kind == "collab_tool_call":
            tool = item.get("tool", "")
            trace.events.append(Event(index, "main", "spawn" if tool in CODEX_SPAWN_TOOLS else "wait", text=item.get("prompt") or tool))
    return trace


def normalize(text):
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"[*`_]", "", text).lower()
    return re.sub(r"\s+", " ", text).strip()


def playbook_steps(text):
    """The first sentence of each top-level numbered step, normalized."""
    steps = []
    for line in text.splitlines():
        match = re.match(r"^\d+\.\s+(.*)", line)
        if match:
            sentence = normalize(match.group(1))
            head = re.split(r"(?<=\.)\s", sentence, maxsplit=1)[0]
            steps.append(head.rstrip("."))
    return steps


def principle_index(index_text):
    """{slug: title} from the Principles section of poteto-mode/SKILL.md."""
    return {slug: title for title, slug in PRINCIPLE_ENTRY.findall(index_text)}


def cited_principles(text, principles):
    cited = []
    for slug, title in principles.items():
        bare = slug.removeprefix("principle-")
        pattern = rf"(?<![\w-])(?:{re.escape(slug)}|{re.escape(bare)}|{re.escape(title)})(?![\w-])"
        if re.search(pattern, text, re.IGNORECASE):
            cited.append(slug)
    return cited


def stages(trace, *, case, owner, injected, playbook_texts, principles, workspace):
    """Every chain stage of one run, from its events."""
    main = [event for event in trace.events if event.actor == "main"]
    reads = [event for event in trace.events if event.kind == "read"]
    main_reads = [event for event in main if event.kind == "read"]
    first_read = {}
    for event in main_reads:
        first_read.setdefault(event.path, event)
    playbooks = []
    for event in main_reads:
        match = PLAYBOOK.match(event.path)
        if match and match.group(1) not in playbooks:
            playbooks.append(match.group(1))
    expected = EXPECTED_PLAYBOOK.get(case, "unknown")
    matched = expected if expected in playbooks else (playbooks[0] if playbooks else None)

    edits = [event for event in trace.events if event.kind == "edit"]
    first_edit = edits[0].index if edits else None
    if owner == INDEX and injected:
        owner_at, owner_full = -1, True
    else:
        event = first_read.get(owner)
        owner_at, owner_full = (event.index, not event.partial) if event else (None, False)

    tool_lists = [event.text for event in main if event.kind == "worklist"]
    finals = {trace.final.strip()}
    text_lists = [event.text for event in main if event.kind == "message" and WORKLIST_WORD.search(event.text) and event.text.strip() not in finals]
    blob = normalize("\n".join(tool_lists or text_lists))
    steps = playbook_steps(playbook_texts.get(matched, "")) if matched else []
    def share(keys):
        return (round(sum(key in blob for key in keys) / len(keys), 2) if blob else 0.0) if keys else None
    verbatim = share(steps)
    echoed = share([" ".join(step.split()[:4]) for step in steps])

    spawns = [event for event in main if event.kind == "spawn"]
    waits = [event for event in main if event.kind == "wait"]
    cited = cited_principles(trace.final, principles)
    unread = [slug for slug in cited if f"{slug}/SKILL.md" not in first_read]
    return {
        "playbook_read": playbooks,
        "playbook_expected": expected,
        "playbook_matched": expected is not None and expected != "unknown" and playbooks == [expected],
        "worklist": {
            "tool_offered": trace.worklist_tool_offered,
            "tool_called": bool(tool_lists),
            "text_list": bool(text_lists) and not tool_lists,
            "verbatim_fraction": verbatim,
            "echoed_fraction": echoed,
        },
        "leaf_reads": [
            {"path": event.path, "index": event.index, "actor": event.actor, "partial": event.partial}
            for event in reads if not PLAYBOOK.match(event.path) and event.path != INDEX
        ],
        "index_read": INDEX in first_read,
        "owner": owner,
        "owner_read": owner_at is not None,
        "owner_read_full": owner_full,
        "first_edit": first_edit,
        "leaf_before_first_edit": None if first_edit is None or not workspace else owner_at is not None and owner_at < first_edit,
        "delegation": {
            "spawns": len(spawns),
            "waits": len(waits),
            "delegated": bool(spawns or waits),
            "brief_names_shape": any(DATA_SHAPE.search(event.text or "") for event in spawns) if spawns and any(event.text for event in spawns) else None,
            "delegate_reads": sorted({event.path for event in reads if event.actor == "delegate"}),
        },
        "citations": {"cited": cited, "unread": unread, "only_read": (not unread) if cited else None},
        "tools_denied": sum(event.kind == "denied" for event in trace.events),
    }


@dataclass(frozen=True)
class RunDir:
    out: Path
    agent: str
    rule: str
    case: str
    arm: str
    path: Path
    legacy: bool


def locate(trace_path):
    """The run a trace.jsonl belongs to, from its path. A dir made before rules
    had cases has no case level above the arm."""
    parts = trace_path.parent.parts
    at = len(parts) - 1 - parts[::-1].index("runs")
    arm, case = parts[at - 1], parts[at + 1]
    if arm not in screen.ARMS:
        return None
    cased = parts[at - 2] == case and (Path(*parts[:at - 4]) / "arms").is_dir()
    if cased:
        return RunDir(Path(*parts[:at - 4]), parts[at - 4], parts[at - 3], case, arm, trace_path.parent, False)
    rule = parts[at - 2]
    return RunDir(Path(*parts[:at - 3]), parts[at - 3], rule, screen.LEGACY_CASES.get(rule, case), arm, trace_path.parent, True)


def arm_tree(run):
    """{tree path: line count} and the root it was read from."""
    build_path = run.out / "arms" / run.rule / "build.json"
    build_info = json.loads(build_path.read_text()) if build_path.is_file() else {}
    tree_dir = build_info.get("tree_dir", "skills")
    base = run.out / "arms" / run.rule / (run.arm if run.legacy else f"{run.case}/{run.arm}") / tree_dir
    files = {path.relative_to(base).as_posix(): path for path in base.rglob("*.md")} if base.is_dir() else {}
    return build_info, files


def verdict_for(run, run_number):
    grade = run.out / run.agent / run.rule / (run.arm if run.legacy else f"{run.case}/{run.arm}") / "grade.json"
    if not grade.is_file():
        return "UNGRADED"
    results = json.loads(grade.read_text()).get("results", [])
    for result in results:
        if Path(result.get("run_base", "")).resolve() == run.path.resolve():
            return screen.verdict(result)[0]
    for result in results:
        if result.get("run_number") == run_number:
            return screen.verdict(result)[0]
    return "UNGRADED"


def injection(run, agent, entry, trace):
    """True when the entry wrapper prefixed the invocation, so the index text
    reached the agent without a file read. Claude also has to list the skill
    among its slash commands for the token to expand."""
    if entry != screen.ENTRY_SKILL:
        return False
    token = screen.ENTRY_INVOCATION[agent][0]
    wrappers = [run.out / "entry" / name for name in (agent, f"{agent}-workspace")]
    prefixed = any(path.is_file() and re.search(rf"(?<![\w$/.-]){re.escape(token)}(?![\w-])", path.read_text()) for path in wrappers)
    if agent == "claude":
        return prefixed and screen.ENTRY_SKILL in trace.slash_commands
    return prefixed


def rule_owner(rule, build_info):
    if build_info.get("target"):
        return build_info["target"]
    patch = screen.RULES / rule / "rule.patch"
    return screen.parse_patch(patch.read_text())[0] if patch.is_file() else None


def analyze(trace_path, principles):
    run = locate(trace_path)
    if run is None:
        return None
    build_info, files = arm_tree(run)
    tree = {path: md_lines(source.read_text(errors="replace")) for path, source in files.items()}
    lines = trace_path.read_text(errors="replace").splitlines()
    run_number = int(run.path.name.removeprefix("run-")) if run.path.name.startswith("run-") else 1
    entry = build_info.get("entry", "skill")
    if run.agent == "claude":
        trace = parse_claude(lines, tree)
    else:
        environment = run.path / "environment.json"
        cwd = ""
        if environment.is_file():
            cwd = str(json.loads(environment.read_text()).get("cwd") or "")
        trace = parse_codex(lines, tree, cwd if cwd.startswith("/") else "")
    output = run.path / "output.md"
    if output.is_file():
        trace.final = output.read_text(errors="replace") + "\n" + trace.final
    injected = injection(run, run.agent, entry, trace)
    playbook_texts = {PLAYBOOK.match(path).group(1): source.read_text(errors="replace") for path, source in files.items() if PLAYBOOK.match(path)}
    workspace = "workspace" in build_info.get("cases", {}).get(run.case, {})
    record = {
        "agent": run.agent, "rule": run.rule, "case": run.case, "arm": run.arm, "run": run_number,
        "out": str(run.out), "verdict": verdict_for(run, run_number), "entry": entry,
        "workspace": workspace,
        "injected": injected,
    }
    record.update(stages(trace, case=run.case, owner=rule_owner(run.rule, build_info), injected=injected,
                         playbook_texts=playbook_texts, principles=principles, workspace=workspace))
    return record


def walk(roots):
    for root in roots:
        if root.is_dir():
            yield from sorted(path for path in root.rglob("trace.jsonl") if "with_skill" in path.parts)


def rate(rows, test):
    counted = [row for row in rows if test(row) is not None]
    hits = sum(bool(test(row)) for row in counted)
    return f"{hits}/{len(counted)}" if counted else "n/a"


STAGES = {
    "injected": lambda row: row["injected"],
    "one playbook, the expected one": lambda row: row["playbook_matched"] if row["playbook_expected"] not in (None, "unknown") else None,
    "any playbook read": lambda row: bool(row["playbook_read"]),
    "worklist tool offered": lambda row: row["worklist"]["tool_offered"],
    "worklist tool called": lambda row: row["worklist"]["tool_called"],
    "worklist in message text": lambda row: row["worklist"]["text_list"],
    "worklist half verbatim or more": lambda row: None if row["worklist"]["verbatim_fraction"] is None else row["worklist"]["verbatim_fraction"] >= 0.5,
    "worklist echoes half the steps' opening words": lambda row: None if row["worklist"]["echoed_fraction"] is None else row["worklist"]["echoed_fraction"] >= 0.5,
    "owner file read or injected": lambda row: row["owner_read"],
    "owner read in full": lambda row: row["owner_read_full"],
    "owner read before first edit": lambda row: row["leaf_before_first_edit"],
    "delegated": lambda row: row["delegation"]["delegated"],
    "brief says data shape or names a principle": lambda row: row["delegation"]["brief_names_shape"],
    "cited any principle": lambda row: bool(row["citations"]["cited"]),
    "cited only read leaves": lambda row: row["citations"]["only_read"],
}


def markdown(rows):
    """Stage rates per agent over poteto-mode entry runs, which mount the whole
    tree. A single-skill entry mounts no playbooks, so its runs are only counted."""
    skipped = len([row for row in rows if row["entry"] != screen.ENTRY_SKILL])
    rows = [row for row in rows if row["entry"] == screen.ENTRY_SKILL]
    agents = sorted({row["agent"] for row in rows})
    out = ["| stage | " + " | ".join(agents) + " |", "|---|" + "---|" * len(agents)]
    out.append("| runs | " + " | ".join(str(sum(row["agent"] == agent for row in rows)) for agent in agents) + " |")
    for name, test in STAGES.items():
        out.append(f"| {name} | " + " | ".join(rate([row for row in rows if row["agent"] == agent], test) for agent in agents) + " |")
    workspace = [row for row in rows if row["workspace"] and row["verdict"] in ("PASS", "FAIL")]
    out += ["", f"{skipped} single-skill entry run(s) left out.", "", "Workspace cases, graded runs only. Each cell is stage hits over runs with that verdict.", ""]
    for agent in agents:
        mine = [row for row in workspace if row["agent"] == agent]
        out += [f"{agent} ({len(mine)} runs)", "", "| stage | PASS | FAIL |", "|---|---|---|"]
        for name, test in STAGES.items():
            out.append(f"| {name} | " + " | ".join(rate([row for row in mine if row["verdict"] == verdict], test) for verdict in ("PASS", "FAIL")) + " |")
        out.append("")
    return "\n".join(out)


def table(rows):
    lines = [f"{'agent':6} {'rule':30} {'case':26} {'arm':8} run {'verdict':8} inj playbooks            wl   owner edit<  deleg cited/unread denied"]
    for row in rows:
        worklist = row["worklist"]["verbatim_fraction"]
        lines.append(
            f"{row['agent']:6} {row['rule']:30.30} {row['case']:26.26} {row['arm']:8} {row['run']:<3} {row['verdict']:8} "
            f"{'y' if row['injected'] else '-':3} {','.join(row['playbook_read']) or '-':20.20} "
            f"{'-' if worklist is None else worklist:<4} {'y' if row['owner_read'] else '-':5} "
            f"{'-' if row['leaf_before_first_edit'] is None else 'y' if row['leaf_before_first_edit'] else 'n':5} "
            f"{row['delegation']['spawns']}/{row['delegation']['waits']:<4} "
            f"{len(row['citations']['cited'])}/{len(row['citations']['unread']):<10} {row['tools_denied']}"
        )
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("roots", nargs="*", type=Path, default=list(DEFAULT_ROOTS))
    parser.add_argument("--jsonl", type=Path, help="write one JSON line per run here")
    parser.add_argument("--markdown", action="store_true", help="print per-agent stage rates and the workspace cross-tab")
    args = parser.parse_args(argv)
    principles = principle_index((screen.REPO / "skills" / INDEX).read_text())
    rows = [row for row in (analyze(path, principles) for path in walk(args.roots)) if row]
    if args.jsonl:
        args.jsonl.write_text("".join(json.dumps(row) + "\n" for row in rows))
    print(markdown(rows) if args.markdown else table(rows))
    return 0


if __name__ == "__main__":
    sys.exit(main())
