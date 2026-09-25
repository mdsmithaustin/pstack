#!/usr/bin/env python3
"""Census of how far each screened run followed the poteto-mode chain.

The chain a /poteto-mode run is meant to follow:

  1. the invocation injects poteto-mode/SKILL.md
  2. the agent reads one playbook, the one the task matches
  3. it opens a worklist whose first items are that playbook's steps, verbatim,
     on a structured tool when one is offered, else in its progress messages
  4. it reads the principle leaf a decision needs before making the decision
  5. it delegates code-writing to a poteto-agent subagent whose brief names
     the data shape; a delegate a routed skill prescribes (Comment Sicko, how
     explorers, architect runners, ...) keeps the role that skill gives it
  6. its reply cites only principles whose leaf it read

Each agent's trace is parsed into one list of Events (reads of mounted skill
files, workspace edits, spawns, worklist updates, messages, denials), and
every stage is computed from that list alone, so Claude and Codex runs are
measured by the same code. When the run's harvest dir holds transcripts, each
delegate's own transcript is parsed the same way and its events are merged in
with actor "delegate", placed right after the spawn that started it.

  chain.py [ROOT ...] [--jsonl FILE] [--markdown]

A ROOT is a directory of screen.py --out dirs, or one such dir. Every run dir
under it (<out>/<agent>/<rule>/[<case>/]<arm>/runs/<case>/with_skill[/run-N]
holding trace.jsonl) becomes one JSON line. A Claude run whose harvest dir
holds raw-stream.jsonl is read from it: the sandbox wrapper keeps the agent's
whole stream there and hands the harness a copy with one result event.
"""
import argparse
import importlib.util
import json
import re
import shlex
import sys
from dataclasses import dataclass, field, replace
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
CLAUDE_WORKLIST_OFFERS = {"TodoWrite", "TaskCreate"}
CODEX_WORKLIST_TOOL = "update_plan"
CLAUDE_SPAWN_TOOLS = {"Agent", "Task"}
CODEX_SPAWN_TOOLS = {"spawn_agent", "spawn"}
SHELL_WRAPPER = re.compile(r"^/bin/(?:ba|z)?sh -lc ")
HEREDOC = re.compile(r"<<-?\s*(['\"]?)(\w+)\1[^\n]*\n.*?\n\s*\2\s*(?:\n|$)", re.DOTALL)
DATA_SHAPE = re.compile(r"data shape|organizing structure|principle-[a-z-]+|model[- ]the[- ]domain", re.IGNORECASE)
FOR_LOOP = re.compile(r"\bfor (\w+) in ([^;]+?);\s*do\s+(.+?);?\s*done\b")
WORKLIST_WORD = re.compile(r"\b(worklist|todo list|to-do list)\b", re.IGNORECASE)
LIST_ITEM = re.compile(r"^\s*(?:\d+[.)]|[-*•]|\[[ x]\])\s+")
WORKLIST_MARKER = "**Worklist.** Copy these items into your worklist before step 1."
STEP_POINTER = re.compile(r"\*\*([a-z][a-z0-9-]*)\*\*|`([a-z][a-z0-9-]*)`")
GENERIC_ROLES = {None, "default", "worker", "general-purpose"}
PERSONA_ROLE = "poteto-agent"
CODEX_BRIEFING_HEAD = "Pstack installed skill paths"
RAW_STREAM = "raw-stream.jsonl"

# The skill files a lead may review a pull request by, as the route each names.
# Any other poteto-mode playbook is a route under its own name.
REVIEW_ROUTES = {
    "poteto-mode/playbooks/investigation.md": "investigation",
    "interrogate/SKILL.md": "interrogate",
    "interrogate/references/code-quality-review.md": "interrogate/code-quality-review",
    "interrogate/references/reviewer-prompt.md": "interrogate/reviewer-prompt",
    "architect/references/design-red-flags.md": "architect-design-red-flags",
    "how/SKILL.md": "how",
}
PRINCIPLE_LEAF = re.compile(r"^(principle-[a-z-]+)/SKILL\.md$")
DIFF_PATH = re.compile(r"^diff --git a/.+? b/(.+)$", re.MULTILINE)
JUDGE_VERDICTS = (*screen.review.VERDICTS["positive"], *screen.review.VERDICTS["near-miss"])


def first_sentence(text):
    line = next(line for line in text.splitlines() if line.strip() and not line.startswith("#"))
    return " ".join(line.split(". ")[0].split())


def persona_line(role_id=PERSONA_ROLE):
    """The opening sentence of a named role's body, which every delivery
    route carries whole."""
    roles = json.loads((screen.REPO / "skills/pstack-harness/references/subagents/roles.json").read_text())
    return first_sentence(next(role["body"] for role in roles["roles"] if role["id"] == role_id))


PERSONA_LINE = persona_line()


def has_persona(text):
    return PERSONA_LINE in " ".join((text or "").split())


def template_line(path):
    """The sentence a brief built from a routed skill's prompt template
    carries: the first body sentence after the template's --- rule, else its
    first "You are" sentence, else its first sentence."""
    text = (screen.REPO / "skills" / path).read_text()
    head, rule, body = text.partition("\n---\n")
    if rule:
        return first_sentence(body)
    you = re.search(r"^You are[^\n]*", text, re.MULTILINE)
    return " ".join(you.group(0).split(". ")[0].split()) if you else first_sentence(text)


@dataclass(frozen=True)
class Prescribed:
    """A delegate a routed skill prescribes. A Codex 0.157 brief is
    encrypted, so path and reads are what its harvest shows."""
    skill: str
    name: str
    roles: tuple = ()
    line: str = None
    template: str = None
    mention: str = None
    named_by_path: bool = True

    def matches(self, role, brief, path=None, reads=()):
        flat = " ".join((brief or "").split())
        return ((role or "").lower().replace(" ", "-") in self.roles
                or bool(self.line and self.line in flat)
                or bool(self.template and (self.template in flat or self.template in reads))
                or bool(self.mention and re.search(self.mention, flat, re.IGNORECASE))
                or bool(self.named_by_path and path and re.search(rf"(?:^|/){re.escape(self.skill)}(?:[_-]|$)", path)))


def routed(skill, name, template):
    return Prescribed(skill, name, line=template_line(template), template=template)


PRESCRIBED = (
    Prescribed("no-comments", "comment-sicko", roles=("comment-sicko",), line=persona_line("comment-sicko"), named_by_path=False),
    routed("how", "explorer", "how/references/explorer-prompt.md"),
    routed("how", "explainer", "how/references/explainer-prompt.md"),
    routed("why", "investigator", "why/references/investigator-prompt.md"),
    routed("why", "synthesizer", "why/references/synthesizer-prompt.md"),
    routed("architect", "runner", "architect/references/runner-prompt.md"),
    routed("interrogate", "reviewer", "interrogate/references/reviewer-prompt.md"),
    routed("reflect", "judgment reviewer", "reflect/references/judgment-reviewer.md"),
    routed("reflect", "tooling reviewer", "reflect/references/tooling-reviewer.md"),
    routed("reflect", "divergent reviewer", "reflect/references/divergent-reviewer.md"),
    routed("reflect", "synthesizer", "reflect/references/synthesizer.md"),
    Prescribed("arena", "runner", mention=r"\barena/SKILL\.md\b|\barena (?:runner|candidate)s?\b"),
    Prescribed("swarm", "worker", mention=r"\bswarm/SKILL\.md\b|\bswarm (?:worker|reviewer)s?\b"),
)


def prescribed_by(role, brief, path=None, reads=()):
    """"<skill> <name>" of the routed-skill role a delegate holds, or None."""
    return next((f"{entry.skill} {entry.name}" for entry in PRESCRIBED if entry.matches(role, brief, path, reads)), None)


@dataclass(frozen=True)
class Event:
    """One thing a run did, in trace order. actor is "main" or "delegate".
    index is the lead trace line. A delegate's event takes its spawn's index
    and extends the spawn's sub with its own line in the child transcript."""
    index: int
    actor: str
    kind: str  # read, edit, spawn, wait, worklist, worklist-rejected, message, denied
    path: str = ""
    partial: bool = False
    text: str = ""
    sub: tuple = ()


def order(event):
    return (event.index, event.sub)


@dataclass
class Spawn:
    """The delegate one spawn event started, and whether it got the persona."""
    event: Event
    role: str = None
    persona: bool = False
    path: str = None
    code_writing: bool = False  # the delegate edited a workspace file, vs an explorer or design runner
    prescribed: str = None  # "<skill> <name>" when a routed skill prescribes its role
    reads: frozenset = frozenset()  # tree paths its own transcript read
    inline: list = field(default_factory=list)  # its events the lead stream already echoed


@dataclass
class Child:
    """One delegate transcript. link is the key its parent registered the
    spawn under: the Task tool_use id, or the Codex child thread id."""
    link: str
    events: list
    spawns: dict
    role: str = None
    persona: bool = False
    brief: str = ""
    path: str = None
    worklist_tool_offered: bool = None  # True when its rollout lists or calls update_plan


@dataclass
class Trace:
    events: list = field(default_factory=list)
    final: str = ""
    slash_commands: tuple = ()
    worklist_tool_offered: bool = None  # None when the trace neither lists tools nor calls one
    result_events: int = None  # Claude: one per turn the lead ended, the last being the answer
    spawns: dict = field(default_factory=dict)  # spawn key -> Spawn


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
    """A write that lands in the checkout: not a mounted skill file, inside cwd
    when the path is absolute and cwd is known, else not under /tmp or /dev.
    A sandbox cwd may itself sit under /tmp."""
    if not path or resolve(path, tree):
        return False
    if path.startswith("/") and cwd:
        return path.startswith(cwd.rstrip("/") + "/")
    return not path.startswith(("/tmp", "/private/tmp", "/dev"))


def json_records(lines):
    for index, line in enumerate(lines):
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(record, dict):
            yield index, record


def errored_tool_ids(records):
    ids = set()
    for _, record in records:
        content = (record.get("message") or {}).get("content") if record.get("type") == "user" else None
        for block in content if isinstance(content, list) else []:
            if isinstance(block, dict) and block.get("type") == "tool_result" and block.get("is_error"):
                ids.add(block.get("tool_use_id"))
    return ids


def claude_events(records, tree, cwd, failed, agents=(), actor=None):
    """(events, {tool_use id: Spawn}, {parent tool_use id: [events]}) of Claude
    assistant records. Without an actor, a record that carries
    parent_tool_use_id is a delegate's, echoed into the lead stream."""
    events, spawns, echoed = [], {}, {}
    for index, record in records:
        if record.get("type") != "assistant":
            continue
        parent = record.get("parent_tool_use_id")
        who = actor or ("delegate" if parent else "main")
        where = record.get("cwd") or cwd
        mine = []
        content = (record.get("message") or {}).get("content")
        for block in content if isinstance(content, list) else []:
            kind = block.get("type")
            if kind == "text" and block.get("text", "").strip():
                mine.append(Event(index, who, "message", text=block["text"]))
            if kind != "tool_use":
                continue
            name, data, use_id = block.get("name"), block.get("input") or {}, block.get("id")
            ok = use_id not in failed
            if name == "Read" and ok:
                path = resolve(data.get("file_path", ""), tree)
                if path:
                    lines_total = tree[path]
                    offset, limit = data.get("offset") or 0, data.get("limit")
                    partial = offset > 1 or (limit is not None and limit < lines_total - max(offset - 1, 0))
                    mine.append(Event(index, who, "read", path, partial))
            elif name == "Skill" and ok:
                path = resolve(f"{data.get('skill', '')}/SKILL.md", tree)
                if path:
                    mine.append(Event(index, who, "read", path))
            elif name == "Bash" and ok:
                reads, writes = shell_effects(data.get("command", ""), tree)
                mine += [Event(index, who, "read", path, partial) for path, partial in reads]
                mine += [Event(index, who, "edit", path) for path in writes if in_workspace(path, where, tree)]
            elif name in CLAUDE_EDIT_TOOLS and ok:
                path = data.get("file_path") or data.get("notebook_path") or ""
                if in_workspace(path, where, tree):
                    mine.append(Event(index, who, "edit", path))
            elif name in CLAUDE_WORKLIST_TOOLS:
                if name == "TodoWrite":
                    items = [todo.get("content", "") for todo in data.get("todos") or []]
                else:
                    items = [" ".join(part for part in (data.get("subject"), data.get("description")) if part)]
                mine.append(Event(index, who, "worklist" if ok else "worklist-rejected", text=item_lines(items)))
            elif name in CLAUDE_SPAWN_TOOLS:
                event = Event(index, who, "spawn", text=data.get("prompt", ""))
                mine.append(event)
                role = data.get("subagent_type")
                spawns[use_id] = Spawn(event, role, (role == PERSONA_ROLE and PERSONA_ROLE in agents) or has_persona(event.text))
        events += mine
        if parent and not actor:
            echoed.setdefault(parent, []).extend(mine)
    return events, spawns, echoed


def parse_claude(lines, tree):
    trace = Trace()
    denied_ids, cwd, agents = set(), "", ()
    records = list(json_records(lines))
    for index, record in records:
        if record.get("type") == "system" and record.get("subtype") == "init":
            cwd = record.get("cwd", "")
            trace.slash_commands = tuple(record.get("slash_commands") or ())
            tools = record.get("tools") or []
            trace.worklist_tool_offered = bool(CLAUDE_WORKLIST_OFFERS & set(tools))
            agents = tuple(record.get("agents") or ())
        if record.get("type") == "system" and record.get("subtype") == "permission_denied":
            denied_ids.add(record.get("tool_use_id"))
            trace.events.append(Event(index, "main", "denied", text=record.get("tool_name", "")))
    results = [record for _, record in records if record.get("type") == "result"]
    trace.result_events = len(results)
    if results:
        # A lead that ends a turn while a background delegate runs emits a
        # result each time; the last one is the answer.
        trace.final = results[-1].get("result") or ""
    events, trace.spawns, echoed = claude_events(records, tree, cwd, denied_ids | errored_tool_ids(records), agents)
    for key, inline in echoed.items():
        if key in trace.spawns:
            trace.spawns[key].inline = inline
    trace.events += events
    trace.events.sort(key=order)
    return trace


def parse_claude_child(lines, meta, tree):
    """One subagents/agent-<id>.jsonl and its meta.json. The first user
    record's content is the brief."""
    records = list(json_records(lines))
    brief = next(((record.get("message") or {}).get("content") for _, record in records if record.get("type") == "user"), "")
    if isinstance(brief, list):
        brief = "\n".join(block.get("text", "") for block in brief if isinstance(block, dict))
    cwd = next((record["cwd"] for _, record in records if record.get("cwd")), "")
    events, spawns, _ = claude_events(records, tree, cwd, errored_tool_ids(records), actor="delegate")
    role = meta.get("agentType")
    return Child(meta.get("toolUseId", ""), events, spawns, role, role == PERSONA_ROLE or has_persona(brief), brief or "")


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
            trace.worklist_tool_offered = True
            trace.events.append(Event(index, "main", "worklist", text=item_lines(entry.get("text", "") for entry in item.get("items") or [])))
        elif kind == "collab_tool_call":
            event = codex_collab(index, "main", item, trace.spawns)
            trace.events.append(event)
    return trace


def codex_collab(index, actor, item, spawns):
    """The event of one collab tool call. A spawn registers a Spawn under each
    thread it started, with the role when the item names one."""
    tool = item.get("tool", "")
    if tool not in CODEX_SPAWN_TOOLS:
        return Event(index, actor, "wait", text=tool)
    event = Event(index, actor, "spawn", text=item.get("prompt") or "")
    roles = {agent.get("thread_id"): agent.get("agent_role") for agent in item.get("receiver_agents") or []}
    for key in item.get("receiver_thread_ids") or [f"#{index}"]:
        spawns[key] = Spawn(event, roles.get(key), has_persona(event.text))
    return event


def item_text(content):
    return "\n".join(part.get("text", "") for part in content or [] if isinstance(part, dict))


def codex_command(argv):
    if isinstance(argv, list):
        return argv[2] if len(argv) >= 3 and argv[1] in ("-lc", "-c") else shlex.join(argv)
    return argv or ""


def file_change_paths(item):
    changes = item.get("changes") or []
    if isinstance(changes, dict):
        return list(changes)
    return [change.get("path", "") for change in changes if isinstance(change, dict)]


def item_lines(items):
    """Worklist items as text, one item per line."""
    return "\n".join(" ".join(item.split()) for item in items if item and item.strip())


def plan_text(arguments):
    try:
        plan = json.loads(arguments).get("plan") or []
    except (ValueError, AttributeError):
        return str(arguments)
    return item_lines(step.get("step", "") for step in plan if isinstance(step, dict))


def exec_plan_text(source):
    """The steps of a code-mode tools.update_plan({plan: [{step: "..."}]}) call."""
    steps = [match.group(2) for match in re.finditer(r"""\bstep["']?\s*:\s*(["'`])((?:\\.|(?!\1).)*)\1""", source)]
    return item_lines(steps) if steps else source


def lists_update_plan(payload):
    tools = payload.get("tools") if isinstance(payload, dict) else None
    return any(isinstance(tool, dict) and tool.get("name") == CODEX_WORKLIST_TOOL for tool in tools or [])


def codex_role(meta):
    source = meta.get("source") if isinstance(meta.get("source"), dict) else {}
    spawned = (source.get("subagent") or {}).get("thread_spawn") or {}
    return meta.get("agent_role") or spawned.get("agent_role")


def codex_path(meta):
    source = meta.get("source") if isinstance(meta.get("source"), dict) else {}
    spawned = (source.get("subagent") or {}).get("thread_spawn") or {}
    return meta.get("agent_path") or spawned.get("agent_path")


def is_codex_child(meta):
    source = meta.get("source") if isinstance(meta.get("source"), dict) else {}
    return bool(meta.get("parent_thread_id")) or "subagent" in source


def parse_codex_rollout(lines, tree):
    """(session_meta payload, Child) of one Codex rollout. Only completed
    items count. Code-mode exec input repeats the commands and spawns that
    items record, so of it only update_plan calls are read.

    A forked child's rollout replays its parent thread's own history for
    context, which carries the parent's own session_meta record further down
    the file. Only the file's first session_meta is this rollout's own
    identity (thread_source, parent_thread_id, agent_role, agent_path), so
    later ones are ignored."""
    meta, events, spawns, brief, task, developer, offered = {}, [], {}, None, None, "", None
    for index, record in json_records(lines):
        payload = record.get("payload") or {}
        if lists_update_plan(payload):
            offered = True
        if record.get("type") == "session_meta":
            if not meta:
                meta = payload
        elif record.get("type") == "response_item":
            kind = payload.get("type")
            if kind == "message" and payload.get("role") == "developer" and not developer:
                developer = item_text(payload.get("content")).lstrip()
            elif kind == "agent_message" and task is None and payload.get("recipient") and payload.get("recipient") == codex_path(meta):
                # 0.157 hands a spawned child its task as a message addressed
                # to its path, under a header; an encrypted payload leaves
                # nothing after the header.
                task = item_text(payload.get("content")).partition("Payload:")[2].strip() or None
            elif kind == "function_call" and payload.get("name") == CODEX_WORKLIST_TOOL:
                offered = True
                events.append(Event(index, "delegate", "worklist", text=plan_text(payload.get("arguments", ""))))
            elif kind == "custom_tool_call" and f"tools.{CODEX_WORKLIST_TOOL}(" in str(payload.get("input", "")):
                offered = True
                events.append(Event(index, "delegate", "worklist", text=exec_plan_text(payload["input"])))
        elif record.get("type") == "event_msg" and payload.get("type") == "item_completed":
            item, cwd = payload.get("item") or {}, meta.get("cwd", "")
            kind = item.get("type")
            if kind == "UserMessage" and brief is None:
                brief = item_text(item.get("content"))
            elif kind == "AgentMessage":
                events.append(Event(index, "delegate", "message", text=item_text(item.get("content"))))
            elif kind == "CommandExecution":
                reads, writes = shell_effects(codex_command(item.get("command")), tree)
                events += [Event(index, "delegate", "read", path, partial) for path, partial in reads]
                if item.get("exit_code") == 0:
                    events += [Event(index, "delegate", "edit", path) for path in writes if in_workspace(path, cwd, tree)]
            elif kind == "FileChange" and item.get("status", "completed") == "completed":
                events += [Event(index, "delegate", "edit", path) for path in file_change_paths(item) if in_workspace(path, cwd, tree)]
            elif kind == "CollabAgentToolCall":
                events.append(codex_collab(index, "delegate", item, spawns))
    role = codex_role(meta)
    brief = task or brief
    persona = role == PERSONA_ROLE or developer.startswith(CODEX_BRIEFING_HEAD) or has_persona(brief)
    return meta, Child(meta.get("id", ""), events, spawns, role, persona, brief or "", codex_path(meta), offered)


def attach(trace, children):
    """Merge each child's events into trace right after the spawn that started
    it, a parent before its own children. A child whose spawn the trace never
    shows goes after the last event."""
    pending = list(children)
    while pending:
        ready = [child for child in pending if child.link in trace.spawns]
        if not ready:
            base_index = max((event.index for event in trace.events), default=-1) + 1
            ready = pending
            for offset, child in enumerate(ready):
                trace.spawns[child.link] = Spawn(Event(base_index + offset, "delegate", "spawn"))
        for child in ready:
            spawn = trace.spawns[child.link]
            echoed = {id(event) for event in spawn.inline}
            trace.events = [event for event in trace.events if id(event) not in echoed]
            spawn.inline = []
            if child.brief and not spawn.event.text:
                old = spawn.event
                new = replace(old, text=child.brief)
                if old in trace.events:
                    trace.events[trace.events.index(old)] = new
                for other in trace.spawns.values():
                    if other.event is old:
                        other.event = new
            spawn.role = spawn.role or child.role
            spawn.persona = spawn.persona or child.persona
            spawn.path = spawn.path or child.path
            spawn.code_writing = spawn.code_writing or any(event.kind == "edit" for event in child.events)
            spawn.reads = spawn.reads | {event.path for event in child.events if event.kind == "read"}
            base = spawn.event
            moved = {id(event): replace(event, index=base.index, sub=base.sub + (event.index,)) for event in child.events}
            trace.events += moved.values()
            for key, inner in child.spawns.items():
                inner.event = moved[id(inner.event)]
                trace.spawns[key] = inner
        done = {id(child) for child in ready}
        pending = [child for child in pending if id(child) not in done]
    trace.events.sort(key=order)
    return trace


def harvest_dir(run_path):
    """<work>/runs/<run> maps to <work>/harvest/<run>, as workspace_diff in
    oracles/shared.py maps it."""
    run_path = Path(run_path)
    runs = next((parent for parent in run_path.parents if parent.name == "runs"), None)
    return runs.parent / "harvest" / run_path.relative_to(runs) if runs else None


def attach_transcripts(trace, agent, transcripts, tree, lead_lines=()):
    """Merge every delegate transcript under a harvest transcripts/ dir. For
    Codex, the lead's own rollout supplies its update_plan calls when the exec
    stream shows no todo_list item; they sort after the stream's last line."""
    children = []
    if agent == "claude":
        for path in sorted((transcripts / "claude").glob("*/*/subagents/agent-*.jsonl")):
            meta_path = path.with_name(path.name.removesuffix(".jsonl") + ".meta.json")
            meta = json.loads(meta_path.read_text()) if meta_path.is_file() else {}
            children.append(parse_claude_child(path.read_text(errors="replace").splitlines(), meta, tree))
        return attach(trace, children)
    lead = None
    for path in sorted((transcripts / "codex" / "sessions").rglob("rollout-*.jsonl")):
        meta, child = parse_codex_rollout(path.read_text(errors="replace").splitlines(), tree)
        if is_codex_child(meta):
            children.append(child)
        else:
            lead = child
    if lead and lead.worklist_tool_offered:
        trace.worklist_tool_offered = True
    if lead and not any(event.kind == "worklist" and event.actor == "main" for event in trace.events):
        trace.events += [replace(event, index=len(lead_lines), actor="main", sub=(event.index,)) for event in lead.events if event.kind == "worklist"]
    return attach(trace, children)


def normalize(text):
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"[*`_]", "", text).lower()
    return re.sub(r"\s+", " ", text).strip()


def step_lines(text):
    """The playbook's lines without the checklist a Worklist marker opens. The
    checklist restates the numbered steps below it, one line each, so its
    lines are no steps of their own."""
    lines = text.splitlines()
    if WORKLIST_MARKER not in lines:
        return lines
    start = lines.index(WORKLIST_MARKER)
    end = start + 1
    while end < len(lines) and (not lines[end].strip() or re.match(r"^\d+\.\s", lines[end])):
        end += 1
    return lines[:start] + lines[end:]


def playbook_steps(text):
    """The first sentence of each top-level numbered step, normalized."""
    steps = []
    for line in step_lines(text):
        match = re.match(r"^\d+\.\s+(.*)", line)
        if match:
            sentence = normalize(match.group(1))
            head = re.split(r"(?<=\.)\s", sentence, maxsplit=1)[0]
            steps.append(head.rstrip("."))
    return steps


@dataclass(frozen=True)
class Step:
    """One numbered playbook step as a worklist item must keep it: its
    identity (the bold heading it opens with, else its first clause) and the
    skills it points at (bold or backticked skill names)."""
    identity: str
    pointers: tuple


def first_clause(text, words=5):
    """The opening clause, cut at its first punctuation mark and at five
    words, so a paraphrase of the rest of the clause still names the step."""
    clause = re.split(r"[.,;:(]\s|[.,;:(]$|\s[-–]\s", text + " ", maxsplit=1)[0]
    return " ".join(clause.split()[:words])


def step_specs(text, skill_names):
    """The Steps of a playbook. A step runs from its numbered line through the
    indented lines under it; its identity comes from the numbered line."""
    blocks = []
    for line in step_lines(text):
        match = re.match(r"^\d+\.\s+(.*)", line)
        if match:
            blocks.append([match.group(1)])
        elif blocks and blocks[-1] is not None and line.startswith((" ", "\t")) and line.strip():
            blocks[-1].append(line.strip())
        elif blocks and line.strip():
            blocks.append(None)
    steps = []
    for block in filter(None, blocks):
        heading = re.match(r"\*\*([^*]+?)[.:]\*\*", block[0])
        identity = normalize(heading.group(1)) if heading else first_clause(normalize(block[0]))
        pointers = []
        for pair in STEP_POINTER.findall(" ".join(block)):
            name = pair[0] or pair[1]
            if (name in skill_names or f"principle-{name}" in skill_names) and name not in pointers:
                pointers.append(name)
        steps.append(Step(identity, tuple(pointers)))
    return steps


def message_items(text):
    """The list items of a message: each numbered or bulleted line with the
    lines that continue it. A message with no list is one item."""
    items = []
    for line in text.splitlines():
        if LIST_ITEM.match(line):
            items.append(LIST_ITEM.sub("", line, count=1))
        elif items and line.strip():
            items[-1] += " " + line.strip()
    return items or [text]


def valid_carrier(carrier, tool_offered, tool_rejected):
    """The pstack-harness worklist contract: a structured tool when one is
    offered, else progress messages, which also take over after a rejected
    tool call."""
    message_allowed = tool_offered is not True or tool_rejected
    return carrier == "tool" or (carrier == "message" and message_allowed)


def has_name(text, name):
    """Whether text names a skill, bare or by its principle- directory name."""
    return re.search(rf"(?<![\w-])(?:principle-)?{re.escape(name)}(?![\w-])", text) is not None


def step_fidelity(steps, items):
    """Per step: whether an item keeps its identity, and which of its pointers
    that item keeps. A step no item names keeps none of its pointers."""
    items = [normalize(item) for item in items]
    report = []
    for number, step in enumerate(steps, 1):
        item = next((item for item in items if step.identity and step.identity in item), None)
        kept = [name for name in step.pointers if item is not None and has_name(item, name)]
        report.append({"step": number, "identity": step.identity, "listed": item is not None,
                       "pointers": list(step.pointers), "kept": kept})
    return report


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


def stages(trace, *, case, owner, injected, playbook_texts, principles, workspace, skill_names=()):
    """Every chain stage of one run, from its events. skill_names are the
    mounted skills a playbook step may point at."""
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
        owner_at, owner_full = (-1, ()), True
    else:
        event = first_read.get(owner)
        owner_at, owner_full = (order(event), not event.partial) if event else (None, False)

    tool_lists = [event.text for event in main if event.kind == "worklist"]
    rejected = any(event.kind == "worklist-rejected" for event in main)
    specs = step_specs(playbook_texts.get(matched, ""), set(skill_names)) if matched else []
    finals = {trace.final.strip()}

    def names_steps(text):
        flat = normalize(text)
        return sum(bool(spec.identity) and spec.identity in flat for spec in specs) >= 2

    text_lists = [event.text for event in main if event.kind == "message" and event.text.strip() not in finals
                  and (WORKLIST_WORD.search(event.text) or names_steps(event.text))]
    carrier = "tool" if tool_lists else "message" if text_lists else "none"
    items = ([line for text in tool_lists for line in text.splitlines()] if tool_lists
             else [item for text in text_lists for item in message_items(text)])
    fidelity = step_fidelity(specs, items)
    pointer_total = sum(len(step["pointers"]) for step in fidelity)
    blob = normalize("\n".join(tool_lists or text_lists))
    steps = playbook_steps(playbook_texts.get(matched, "")) if matched else []
    def share(keys):
        return (round(sum(key in blob for key in keys) / len(keys), 2) if blob else 0.0) if keys else None
    verbatim = share(steps)
    echoed = share([" ".join(step.split()[:4]) for step in steps])

    spawns = [event for event in main if event.kind == "spawn"]
    waits = [event for event in main if event.kind == "wait"]
    by_event = {id(spawn.event): spawn for spawn in trace.spawns.values()}
    briefed = [by_event.get(id(event)) or Spawn(event) for event in spawns]
    if not spawns and trace.spawns:
        # Codex's own stream never shows a real spawn call, only a `wait` on
        # one (codex_collab), so the whole delegate census comes from the
        # harvested child rollouts attach() folded into trace.spawns.
        briefed = list(trace.spawns.values())
    for spawn in briefed:
        spawn.prescribed = prescribed_by(spawn.role, spawn.event.text, spawn.path, spawn.reads)
    helpers = [spawn for spawn in briefed if not spawn.prescribed]
    implementers = [spawn for spawn in helpers if spawn.code_writing]
    census = {}
    for spawn in briefed:
        counts = census.setdefault(spawn.role or "(none)", dict.fromkeys(("spawns", "code_writing", "prescribed", "persona", "implementation_misses"), 0))
        counts["spawns"] += 1
        counts["code_writing"] += spawn.code_writing
        counts["prescribed"] += bool(spawn.prescribed)
        counts["persona"] += spawn.persona
        counts["implementation_misses"] += spawn in implementers and not spawn.persona
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
            "carrier": carrier,
            "tool_rejected": rejected,
            "valid_carrier": valid_carrier(carrier, trace.worklist_tool_offered, rejected),
            "steps": fidelity,
            "steps_listed": sum(step["listed"] for step in fidelity) if fidelity else None,
            "steps_total": len(fidelity) if fidelity else None,
            "pointer_fraction": round(sum(len(step["kept"]) for step in fidelity) / pointer_total, 2) if pointer_total else None,
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
        "leaf_before_first_edit": None if first_edit is None or not workspace else owner_at is not None and owner_at < order(edits[0]),
        "delegation": {
            "spawns": len(briefed),
            "waits": len(waits),
            "delegated": bool(briefed or waits),
            "brief_names_shape": any(DATA_SHAPE.search(spawn.event.text or "") for spawn in briefed) if briefed and any(spawn.event.text for spawn in briefed) else None,
            "delegate_reads": sorted({event.path for event in reads if event.actor == "delegate"}),
        },
        "delegate_edits": sorted({event.path for event in edits if event.actor == "delegate"}),
        "delegate_census": [
            {"role": spawn.role, "path": spawn.path, "code_writing": spawn.code_writing, "persona": spawn.persona, "prescribed": spawn.prescribed}
            for spawn in briefed
        ],
        "role_census": census,
        "implementation_delegate_persona": {
            "spawns": len(implementers),
            "with_persona": sum(spawn.persona for spawn in implementers),
            "misses": [spawn.role for spawn in implementers if not spawn.persona],
        },
        "helper_persona": {
            "spawns": len(helpers),
            "with_persona": sum(spawn.persona for spawn in helpers),
        },
        "citations": {"cited": cited, "unread": unread, "only_read": (not unread) if cited else None},
        "tools_denied": sum(event.kind == "denied" for event in trace.events),
        "result_events": trace.result_events,
        "worklist_tool": {
            "offered": True if trace.worklist_tool_offered is None and tool_lists else trace.worklist_tool_offered,
            "called": bool(tool_lists),
            "calls": len(tool_lists),
        },
        "delegate_persona": {
            "spawns": len(briefed),
            "with_persona": sum(spawn.persona for spawn in briefed),
            "roles": [spawn.role for spawn in briefed],
        },
    }


def review_route(path):
    playbook = PLAYBOOK.match(path)
    return REVIEW_ROUTES.get(path) or (playbook.group(1) if playbook else None)


def review_stage(trace, review, census, diff, after, judged):
    """How the lead reviewed the pull request on review["branch"]: the review
    skill files it read, in order, the principle leaves each actor read, its
    delegates, whether the run changed the PR (diff is the harvested
    workspace.diff, None when none was harvested; after is workspace.json),
    and the judge's verdict."""
    route_reads = []
    for event in trace.events:
        name = review_route(event.path) if event.actor == "main" and event.kind == "read" else None
        if name and name not in [read["route"] for read in route_reads]:
            route_reads.append({"route": name, "index": event.index})
    route = [read["route"] for read in route_reads]
    leaves = {"lead": [], "delegate": []}
    for event in trace.events:
        leaf = PRINCIPLE_LEAF.match(event.path) if event.kind == "read" else None
        actor = "lead" if event.actor == "main" else "delegate"
        if leaf and leaf.group(1) not in leaves[actor]:
            leaves[actor].append(leaf.group(1))
    head = after.get("head_after")
    return {
        "branch": review["branch"],
        "route": route,
        "primary": route[0] if route else "none",
        "route_reads": route_reads,
        "principle_leaves": leaves,
        "delegated": {"delegated": bool(census), "spawns": len(census),
                      "roles": [entry["prescribed"] or entry["role"] for entry in census]},
        "pr_modified": None if diff is None else bool(diff.strip()),
        "pr_paths": sorted(set(DIFF_PATH.findall(diff or ""))),
        "head_moved": None if head is None else head != review.get("refs", {}).get(review["branch"]),
        "verdict": judged,
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
    cased = parts[at - 2] == case and (Path(*parts[:at - 4]) / "arms").is_dir()
    if cased:
        out, rule = Path(*parts[:at - 4]), parts[at - 3]
        build = out / "arms" / rule / "build.json"
        if arm not in (json.loads(build.read_text()).get("arms", screen.ARMS) if build.is_file() else screen.ARMS):
            return None
        return RunDir(out, parts[at - 4], rule, case, arm, trace_path.parent, False)
    if arm not in screen.ARMS:
        return None
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


def work_dir(run):
    return run.out / run.agent / run.rule / (run.arm if run.legacy else f"{run.case}/{run.arm}")


def verdict_for(run, run_number):
    grade = work_dir(run) / "grade.json"
    if not grade.is_file():
        return "UNGRADED"
    regraded = grade.with_name("regrade.json")
    if regraded.is_file():
        row = next((row for row in json.loads(regraded.read_text())["results"] if row["run"] == run_number), None)
        if row:
            return row["verdict"]
    results = json.loads(grade.read_text()).get("results", [])
    for result in results:
        if Path(result.get("run_base", "")).resolve() == run.path.resolve():
            return screen.verdict(result)[0]
    for result in results:
        if result.get("run_number") == run_number:
            return screen.verdict(result)[0]
    return "UNGRADED"


def judge_for(run, run_number):
    """The judge's combined verdict and calibration of one run, or None."""
    judge = work_dir(run) / "judge.json"
    if not judge.is_file():
        return None
    row = next((row for row in json.loads(judge.read_text()).get("results", []) if row.get("run") == run_number), None)
    return {"combined": row.get("combined"), "calibrated": row.get("calibrated")} if row else None


def injection(run, agent, entry, trace):
    """True when the entry wrapper prefixed the invocation, so the index text
    reached the agent without a file read. Claude also has to list the skill
    among its slash commands for the token to expand."""
    if entry != screen.ENTRY_SKILL:
        return False
    token = screen.ENTRY_INVOCATION[agent][0]
    wrappers = [run.out / "entry" / name for name in (agent, f"{agent}-workspace", f"{agent}-sbx")]
    prefixed = any(path.is_file() and re.search(rf"(?<![\w$/.-]){re.escape(token)}(?![\w-])", path.read_text()) for path in wrappers)
    if agent == "claude":
        return prefixed and screen.ENTRY_SKILL in trace.slash_commands
    return prefixed


def rule_owner(rule, build_info, arm=None):
    """The file the rule patches. An arm of an N-arm rule owns the first file
    its own patch changes; current, which changes none, keeps the rule's target."""
    changed = build_info.get("arm_changes", {}).get(arm)
    if changed:
        return changed[0]
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
    harvest = harvest_dir(run.path)
    raw = harvest / RAW_STREAM if harvest and run.agent == "claude" else None
    lines = (raw if raw and raw.is_file() else trace_path).read_text(errors="replace").splitlines()
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
    if harvest and (harvest / "transcripts").is_dir():
        attach_transcripts(trace, run.agent, harvest / "transcripts", tree, lines)
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
    skill_names = {path.split("/")[0] for path in files if path.count("/") == 1 and path.endswith("/SKILL.md")}
    record.update(stages(trace, case=run.case, owner=rule_owner(run.rule, build_info, run.arm), injected=injected,
                         playbook_texts=playbook_texts, principles=principles, workspace=workspace, skill_names=skill_names))
    review = build_info.get("cases", {}).get(run.case, {}).get("review")
    record["review"] = None
    if review:
        diff = harvest / "workspace.diff" if harvest else None
        after = harvest / "workspace.json" if harvest else None
        record["review"] = review_stage(
            trace, review, record["delegate_census"],
            diff.read_text(errors="replace") if diff and diff.is_file() else None,
            json.loads(after.read_text()) if after and after.is_file() else {},
            judge_for(run, run_number))
    return record


def walk(roots):
    for root in roots:
        if root.is_dir():
            yield from sorted(path for path in root.rglob("trace.jsonl") if "with_skill" in path.parts)


def rate(rows, test, fraction=False):
    """hits/runs, or for a fraction stage the mean over runs that have one."""
    counted = [row for row in rows if test(row) is not None]
    if not counted:
        return "n/a"
    if fraction:
        return f"{sum(test(row) for row in counted) / len(counted):.2f} over {len(counted)}"
    return f"{sum(bool(test(row)) for row in counted)}/{len(counted)}"


def role_census(rows):
    """{role: role_census counts summed over rows}."""
    total = {}
    for row in rows:
        for role, counts in row["role_census"].items():
            into = total.setdefault(role, dict.fromkeys(counts, 0))
            for key, value in counts.items():
                into[key] += value
    return dict(sorted(total.items()))


STAGES = {
    "injected": lambda row: row["injected"],
    "one playbook, the expected one": lambda row: row["playbook_matched"] if row["playbook_expected"] not in (None, "unknown") else None,
    "any playbook read": lambda row: bool(row["playbook_read"]),
    "worklist tool offered": lambda row: row["worklist"]["tool_offered"],
    "worklist carried by a tool": lambda row: row["worklist"]["carrier"] == "tool",
    "worklist carried in messages": lambda row: row["worklist"]["carrier"] == "message",
    "worklist present via a valid carrier": lambda row: row["worklist"]["valid_carrier"],
    "every playbook step listed": lambda row: None if row["worklist"]["steps_total"] is None else row["worklist"]["steps_listed"] == row["worklist"]["steps_total"],
    "step pointers preserved (fraction)": lambda row: row["worklist"]["pointer_fraction"],
    "owner file read or injected": lambda row: row["owner_read"],
    "owner read in full": lambda row: row["owner_read_full"],
    "owner read before first edit": lambda row: row["leaf_before_first_edit"],
    "delegated": lambda row: row["delegation"]["delegated"],
    "brief says data shape or names a principle": lambda row: row["delegation"]["brief_names_shape"],
    "cited any principle": lambda row: bool(row["citations"]["cited"]),
    "cited only read leaves": lambda row: row["citations"]["only_read"],
    "delegate outside a routed skill got the poteto-agent briefing": lambda row: (
        row["helper_persona"]["with_persona"] == row["helper_persona"]["spawns"] if row["helper_persona"]["spawns"] else None
    ),
    "implementation delegate ran as poteto-agent": lambda row: (
        row["implementation_delegate_persona"]["with_persona"] == row["implementation_delegate_persona"]["spawns"]
        if row["implementation_delegate_persona"]["spawns"] else None
    ),
}
FRACTION_STAGES = {"step pointers preserved (fraction)"}
REVIEW_STAGES = {
    "read an interrogate reference": lambda row: any(name.startswith("interrogate/") for name in row["review"]["route"]),
    "read a principle leaf": lambda row: any(row["review"]["principle_leaves"].values()),
    "delegated": lambda row: row["review"]["delegated"]["delegated"],
    "pr modified": lambda row: row["review"]["pr_modified"],
    "head moved": lambda row: row["review"]["head_moved"],
}


def review_markdown(rows, agents):
    """Per agent over review runs: primary route counts, the review stages,
    delegate roles, and primary route by the judge's combined verdict."""
    out = ["Review cases. The route is the review skill files the lead read, in order; the primary route is the first.", ""]
    for agent in agents:
        mine = [row for row in rows if row["agent"] == agent and row["review"]]
        if not mine:
            continue
        primaries = sorted({row["review"]["primary"] for row in mine})
        roles = {}
        for row in mine:
            for role in row["review"]["delegated"]["roles"]:
                roles[role or "(none)"] = roles.get(role or "(none)", 0) + 1
        out += [f"{agent} review ({len(mine)} runs)", "", "| stage | runs |", "|---|---|"]
        out += [f"| primary route {name} | {rate(mine, lambda row, name=name: row['review']['primary'] == name)} |" for name in primaries]
        out += [f"| {name} | {rate(mine, test)} |" for name, test in REVIEW_STAGES.items()]
        out += [f"| delegate roles | {', '.join(f'{role} {count}' for role, count in sorted(roles.items())) or '-'} |", ""]
        out += ["| primary route | " + " | ".join(JUDGE_VERDICTS) + " | unjudged |", "|---|" + "---|" * (len(JUDGE_VERDICTS) + 1)]
        for name in primaries:
            combined = [(row["review"]["verdict"] or {}).get("combined") for row in mine if row["review"]["primary"] == name]
            combined = [verdict if verdict in JUDGE_VERDICTS else None for verdict in combined]
            out.append(f"| {name} | " + " | ".join(str(combined.count(verdict)) for verdict in (*JUDGE_VERDICTS, None)) + " |")
        out.append("")
    return out


def markdown(rows):
    """Stage rates per agent over poteto-mode entry runs, which mount the whole
    tree. A single-skill entry mounts no playbooks, so its runs are only counted."""
    skipped = len([row for row in rows if row["entry"] != screen.ENTRY_SKILL])
    rows = [row for row in rows if row["entry"] == screen.ENTRY_SKILL]
    agents = sorted({row["agent"] for row in rows})
    out = ["| stage | " + " | ".join(agents) + " |", "|---|" + "---|" * len(agents)]
    out.append("| runs | " + " | ".join(str(sum(row["agent"] == agent for row in rows)) for agent in agents) + " |")
    for name, test in STAGES.items():
        out.append(f"| {name} | " + " | ".join(rate([row for row in rows if row["agent"] == agent], test, name in FRACTION_STAGES) for agent in agents) + " |")
    out += ["", f"{skipped} single-skill entry run(s) left out.", "", "Delegates per role. Prescribed means a routed skill gives the role; "
            "an implementation miss is a code-writing delegate outside a routed skill that did not run as poteto-agent.", ""]
    for agent in agents:
        census = role_census([row for row in rows if row["agent"] == agent])
        out += [f"{agent}", "", "| role | spawns | code-writing | prescribed | poteto-agent | implementation misses |", "|---|---|---|---|---|---|"]
        out += [f"| {role} | {counts['spawns']} | {counts['code_writing']} | {counts['prescribed']} | {counts['persona']} | {counts['implementation_misses']} |"
                for role, counts in census.items()]
        out.append("")
    workspace = [row for row in rows if row["workspace"] and row["verdict"] in ("PASS", "FAIL")]
    out += ["Workspace cases, graded runs only. Each cell is stage hits over runs with that verdict.", ""]
    for agent in agents:
        mine = [row for row in workspace if row["agent"] == agent]
        out += [f"{agent} ({len(mine)} runs)", "", "| stage | PASS | FAIL |", "|---|---|---|"]
        for name, test in STAGES.items():
            out.append(f"| {name} | " + " | ".join(rate([row for row in mine if row["verdict"] == verdict], test, name in FRACTION_STAGES) for verdict in ("PASS", "FAIL")) + " |")
        out.append("")
    if any(row.get("review") for row in rows):
        out += review_markdown(rows, agents)
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
