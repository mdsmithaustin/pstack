#!/usr/bin/env python3
"""Print the route, worklist, skill loads, and gates for one poteto-mode playbook.

Only routed playbooks accept risk facts. With no facts or override, their route
is pending. With all five facts, the script applies the routing policy in
references/routes.md. The same facts give the same route on every harness.
Steps and their outcome sentences come from the playbook file, which owns them. Gates, panels,
and the flags of code-changing playbooks come from routes.json beside the mode entry.

Use --step N to print the step's full text and the route's gates. For a routed
playbook, include --route with the route the plan printed. For other playbooks, --route is
optional with --step. A full plan rejects --route. A step rejects risk facts,
--user-route, --raise-to, --reason, and --json.

On the lightweight route, the step lists the skills it keeps and labels conditional
loads separately. For a code-changing playbook, a step that runs Opening a PR
includes the reminder to commit even when the push or PR is skipped.

Use --reason only with --raise-to. On a routed playbook, --raise-to requires
a nonblank reason.
Supply each risk fact, --user-route, --raise-to, --reason, --step, --route,
and --harness at most once. Arguments must be valid UTF-8.
On a usage error, the script writes one line to stderr and exits with status 2.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlsplit

MODE = Path(__file__).resolve().parents[1]
ROUTES = ("lightweight", "standard", "intensive")
LEVELS = ("low", "material", "unknown")
STEP = re.compile(r"^(\d+)\. (.*)$")
BOLD = re.compile(r"\*\*(.+?)\*\*")
LOAD = re.compile(r"call the Skill tool with `([a-z0-9-]+)`", re.I)
NAMED = re.compile(r"(?:`([a-z0-9-]+)`|\*\*([a-z0-9-]+)\*\*) skill")
SENTENCE_END = re.compile(r"(?<=[.!?])\s")
FULL_READ = "Read this playbook in full."
REPLY = "**Reply:**"
OPENS_WITH_CONDITION = re.compile(r"^\W*(If|When|Where|For|In|On the|Once|Unless|Otherwise|Only)\b")
WORD = re.compile(r"\bn/a\b|[^\W_]\w*(?:'\w+)?")
NO_CHECK = re.compile(r"\b(?:not|never|\w+n't)\s+(?:yet\s+|been\s+|really\s+)?(?:check|look|verif(?:y|ied)|test|inspect|review)(?:ed|s)?\b"
                      r"|\bskipped\s+(?:the\s+)?(?:check|look|verification|test|inspection|review)s?\b")
THIN_WORDS = frozenset("""ok okay fine none n/a na unknown low tbd yes no same trivial nothing not did didn't never check checked
unchecked verified unverified evidence applicable trust me to it is and file files line lines loc change changes changed insertion
insertions deletion deletions touched one two three four five six seven eight nine ten""".split())
SCRUTINY_REMOTE = ("Credit an existing independent review of the current revision. Or name human PR review as the scrutiny, "
                   "record the revision it must cover, and report delivery as pending review. Otherwise brief one `trail reviewer`.")
SCRUTINY_LOCAL = ("No pull request will open, so no PR review exists to credit. Brief one `trail reviewer`, or report the user's "
                  "review of the branch as pending.")
SCP_REMOTE = re.compile(r"^(?:[^/:]+@)?([^@/:]+):")
RUN_PR = re.compile(r"\bRun \*\*Opening a PR\*\*")
KEEP_COMMITS = "   still commit when the push or PR is skipped"
SURROGATE = re.compile("[\udc80-\udcff]")
WHEN_HOLDS = "   load only when the step's own condition holds: "
NO_CHANGE_ENDPOINT = ("what this playbook's Reply line names", "this playbook does not produce a code change")


class PlanParser(argparse.ArgumentParser):
    def error(self, message):
        message = " ".join(message.splitlines()).rstrip(".")
        self.exit(2, f"{self.prog}: error: {message}. Run {self.prog} --help for the flags.\n")


class Once(argparse.Action):
    """Refuse a repeated flag, so a later value cannot silently replace an earlier one."""

    given = False

    def __call__(self, parser, namespace, values, option_string=None):
        if self.given:
            parser.error(f"{option_string} was given more than once.")
        self.given = True
        setattr(namespace, self.dest, values)


def read_playbook(path):
    """Return (opening prose lines, [(number, text block)], reply line) as the worklist rule splits them."""
    prose, steps, current, reply, in_step = [], [], None, "", False
    for line in path.read_text(encoding="utf-8").split("\n"):
        match = STEP.match(line)
        if line.startswith(REPLY):
            reply = line.strip()
        elif match and not reply:
            current, in_step = [match.group(2)], True
            steps.append((int(match.group(1)), current))
        elif current is None:
            if line.strip() and not line.startswith("#"):
                prose.append(line)
        elif line.startswith("#"):
            in_step = False
        elif in_step and line[:1] in ("", " ", "\t") and not reply:
            current.append(line.strip())
    return prose, [(number, " ".join(part for part in block if part)) for number, block in steps], reply


def step_loads(text):
    always, conditional = [], []
    for sentence in SENTENCE_END.split(text):
        target = conditional if OPENS_WITH_CONDITION.match(sentence) else always
        target.extend(LOAD.findall(sentence))
    always = list(dict.fromkeys(always))
    return always, [skill for skill in dict.fromkeys(conditional) if skill not in always]


def step_text(path, wanted):
    """One step's lines as the playbook has them, sub-items included, or None when the step is absent."""
    block = None
    for line in path.read_text(encoding="utf-8").split("\n"):
        match = STEP.match(line)
        if match:
            if block is not None:
                break
            if int(match.group(1)) == wanted:
                block = [line]
        elif block is not None:
            if line[:1] not in ("", " ", "\t"):
                break
            block.append(line)
    return "\n".join(block).rstrip() if block else None


def regime(playbook, manifest):
    """Which sentences of a step bind. Only outcome-first playbooks allow another route to the outcome."""
    always = "Every prohibition, authorization limit, and confidentiality rule in a step binds."
    if playbook in manifest["outcome_first"]:
        return ("Outcome-first playbook: each step's bold outcome and its defining sentence bind. The step's other sentences "
                "are a default route, and another route that reaches the outcome with evidence is fine. " + always)
    return "Follow each step of this playbook as written. A script or another agent may read its output. " + always


def playbook_path(playbook):
    path = MODE / "playbooks" / f"{playbook}.md"
    if not re.fullmatch(r"[a-z0-9-]+", playbook) or not path.is_file():
        known = sorted(found.stem for found in (MODE / "playbooks").glob("*.md"))
        raise SystemExit(f"plan.py: unknown playbook {playbook!r}. Known: {', '.join(known)}.")
    return path


def render_step(args, manifest):
    path = playbook_path(args.playbook)
    text = step_text(path, args.step)
    if text is None:
        raise SystemExit(f"plan.py: {args.playbook} has no step {args.step}.")
    entry = manifest["playbooks"].get(args.playbook, {})
    tiered = entry.get("tiered", False)
    if tiered and args.route is None:
        raise SystemExit(f"plan.py: {args.playbook} is routed, so --step needs --route with the route the plan printed.")
    joined = dict(read_playbook(path)[1])[args.step]
    out = [f"{args.playbook} step {args.step}, from {display_path(path)}", ""]
    if tiered and args.route == "lightweight":
        out += ["Lightweight route: do this step's work yourself. Skip its sentences that delegate the work or spawn a design panel, or load a skill the plan did not list. Keep its outcome, its checks, its commands, and the independent scrutiny the plan lists."]
        if LOAD.search(joined):
            loads, conditional, _ = route_loads(joined, "lightweight", tiered, manifest)
            out.append("Loads this route keeps from this step: " + (", ".join(f"`{s}`" for s in loads) or "none") + ".")
            if conditional:
                out.append(WHEN_HOLDS + ", ".join(conditional))
        out.append("")
    elif tiered and args.route == "standard":
        panels = ", ".join(f"`{name}`" for name in manifest["panels"])
        out += [f"Standard route: the panels ({panels}) stay unloaded. Where this step names one, compare the options yourself and record them.", ""]
    out += [text, *([KEEP_COMMITS] if entry.get("changes_code") and RUN_PR.search(joined) else []), ""]
    if args.harness != "claude-code":
        out += [harness_note(args.harness), ""]
    gates = route_gates(manifest, args.playbook, args.route if tiered else "standard")
    out += ["gates, which still bind:", *render_gates(gates, args.harness), ""]
    out += [regime(args.playbook, manifest), "Mark the item completed only with its evidence."]
    return "\n".join(out)


def route_gates(manifest, playbook, route):
    changes_code = manifest["playbooks"].get(playbook, {}).get("changes_code", False)
    gates = []
    for gate in manifest["gates"]:
        if gate["applies"] == "code" and not changes_code:
            continue
        if playbook not in gate.get("playbooks", [playbook]):
            continue
        if route == "lightweight" and gate["id"] not in manifest.get("lightweight_gates", [gate["id"]]):
            continue
        gates.append({"id": gate["id"], "skill": gate.get("skill"), "run": gate.get("run"), "when": gate_timing(gate, route)})
    return gates


def gate_timing(gate, route):
    return gate["when"].get(route) or gate["when"]["all"]


def render_gates(gates, harness):
    return [f"- {gate['id']}: {load_phrase(gate['skill'], harness) if gate['skill'] else 'run `' + gate['run'] + '`'}, {gate['when']}."
            for gate in gates]


def step_name(text):
    match = BOLD.match(text)
    if not match:
        return text.split(".")[0]
    return re.sub(r"\s*\(.*\)", "", match.group(1)).rstrip(". ")


def outcome(text):
    """The bold outcome and its defining sentence."""
    match = BOLD.match(text)
    if not match:
        return SENTENCE_END.split(text, 1)[0]
    rest = text[match.end():].lstrip()
    return (match.group(0) + " " + SENTENCE_END.split(rest, 1)[0]).strip()


def parse_fact(value):
    level, _, evidence = value.partition(":")
    level, evidence = level.strip(), " ".join(evidence.split())
    if level not in LEVELS:
        raise SystemExit(f"plan.py: a fact is one of {', '.join(LEVELS)}, optionally followed by :evidence. Got {value!r}.")
    if level == "low":
        if not evidence:
            return "unknown", "recorded low with no evidence, so treated as unknown"
        text = evidence.lower().replace("\u2019", "'")
        if (len(evidence.split()) < 2 or len(evidence) < 8 or NO_CHECK.search(text)
                or all(word.isdigit() or word in THIN_WORDS for word in WORD.findall(text))):
            return "unknown", f"recorded low, but {evidence!r} does not say what was checked, so treated as unknown"
    return level, evidence


def table_route(facts):
    """Unknown context is not low risk. Intensive needs harm that is unclear or hard to undo."""
    raised = [name for name, (level, _) in facts.items() if level != "low"]
    if not raised:
        return "lightweight", "all five facts are low with evidence"
    harm = facts["consequence"][0] != "low"
    unclear = facts["uncertainty"][0] != "low"
    stuck = facts["reversibility"][0] != "low"
    if harm and (unclear or stuck):
        return "intensive", "consequence is not low and " + ("uncertainty" if unclear else "reversibility") + " is not low"
    return "standard", "not low: " + ", ".join(raised)


def default_endpoint(project):
    """The default endpoint that references/routes.md's Endpoint table gives `project`."""
    try:
        local = subprocess.run(["git", "rev-parse", "--local-env-vars"], capture_output=True, text=True).stdout.split()
    except OSError:
        return "commits on a local branch once Git is available", "Git is not on PATH", False
    env = {name: value for name, value in os.environ.items() if name not in local}

    def git(*args):
        return subprocess.run(["git", "-C", str(project), *args], capture_output=True, text=True, env=env)

    if git("rev-parse", "--git-dir").returncode != 0:
        return "commits on a first local branch after `git init`", "no Git repository", False
    urls = [line.split("\t", 1)[1].rsplit(" (", 1)[0] for line in git("remote", "-v").stdout.splitlines() if line.endswith(" (push)")]
    if not urls:
        return "commits on a local branch, with the branch and its diff command in the reply", "no remote", False
    hosts = {remote_host(url) for url in urls} - {None}
    if hosts and shutil.which("origin"):
        return "reviewable PR", "a network remote and Origin found", True
    if shutil.which("gh") and hosts & gh_hosts():
        return "reviewable PR", "a remote on a host gh serves", True
    if "github.com" in hosts:
        return "reviewable PR through a built-in PR tool, else a pushed branch named in the reply", "GitHub remote, no forge CLI on PATH", True
    why = "no PR tool on PATH serves the remote's host" if hosts else "every remote is a local path, which takes no PR"
    return "a pushed branch, named in the reply", why, False


def remote_host(url):
    """Git reads a colon before the first slash as scp-like host:path, not as a local path."""
    if "://" in url:
        try:
            parts = urlsplit(url)
            host = None if parts.scheme == "file" else parts.hostname
        except ValueError:
            return None
        ssh = parts.scheme in ("ssh", "git+ssh", "ssh+git")
    else:
        match = SCP_REMOTE.match(url)
        host, ssh = (match.group(1).lower() if match else None), True
    if host and ssh:
        host = ssh_hostname(host)
    return "github.com" if host and (host == "github.com" or host.endswith(".github.com")) else host


def ssh_hostname(alias):
    """Resolve an ssh alias as gh does, with `ssh -G`, which prints the evaluated config and connects to nothing."""
    if alias.startswith("-"):
        return alias
    try:
        done = subprocess.run(["ssh", "-G", alias], capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        return alias
    found = re.search(r"^hostname (\S+)$", done.stdout, re.M)
    return found.group(1).lower() if found else alias


def gh_hosts():
    """The hosts gh serves, from the hosts.yml in the config folder gh's own lookup order finds."""
    if os.environ.get("GH_CONFIG_DIR"):
        folder = Path(os.environ["GH_CONFIG_DIR"])
    elif os.environ.get("XDG_CONFIG_HOME"):
        folder = Path(os.environ["XDG_CONFIG_HOME"]) / "gh"
    elif os.name == "nt" and os.environ.get("AppData"):
        folder = Path(os.environ["AppData"]) / "GitHub CLI"
    else:
        folder = Path.home() / ".config" / "gh"
    try:
        text = (folder / "hosts.yml").read_text(encoding="utf-8", errors="replace")
    except OSError:
        text = ""
    keys = re.findall(r"^( *)([^\s#]\S*?)[ \t]*:(?=[ \t]|$)", text, re.M)
    named = {key.strip("'\"").lower() for indent, key in keys if indent == keys[0][0]}
    return {"github.com", os.environ.get("GH_HOST", "github.com").lower(), *named}


def display_path(path):
    """The playbook path as a lead can use it on any machine."""
    return "${PSTACK_SKILLS_ROOT}/" + path.relative_to(MODE.parent).as_posix()


def load_phrase(skill, harness):
    if harness == "claude-code":
        return f"Call the Skill tool with `{skill}`"
    return f'read "${{PSTACK_SKILLS_ROOT:?}}/{skill}/SKILL.md" in full'


def harness_note(harness):
    return f"On this harness, \"Call the Skill tool with `<name>`\" means: {load_phrase('<name>', harness)}."


def raise_the_route(source):
    return "ask the user to raise the route" if source == "user" else "raise the route"


def pending(args, manifest, path, prose, endpoint):
    """No facts yet: the worklist opens first, and the facts are its first item. The gates of the lightest route bind already."""
    return {
        "playbook": args.playbook, "file": display_path(path), "full_read": False, "route": "pending", "regime": None,
        "route_source": "table", "route_reason": "no risk facts recorded yet", "tiered": True, "facts": {}, "warning": None,
        "opening": prose, "steps": [], "lightweight_worklist": None, "gates": route_gates(manifest, args.playbook, "lightweight"),
        "scrutiny": None, "reply": "", "reply_loads": [],
        "default_endpoint": endpoint[0], "default_endpoint_reason": endpoint[1],
    }


def route_loads(text, route, tiered, manifest):
    panels, keeps = set(manifest["panels"]), set(manifest["lightweight_keeps"])
    always, conditional = step_loads(text)
    held = [s for s in always + conditional if tiered and s in panels and route != "intensive"]

    def allowed(skills):
        return [s for s in skills if not (tiered and s in panels and route != "intensive") and not (route == "lightweight" and s not in keeps)]

    return allowed(always), allowed(conditional), held


def build(args, manifest, endpoint=None):
    """Build the plan. `endpoint` fixes the repository lookup, so a measurement does not depend on the machine."""
    path = playbook_path(args.playbook)
    entry = manifest["playbooks"].get(args.playbook, {})
    prose, steps, reply = read_playbook(path)
    tiered = entry.get("tiered", False)
    changes_code = entry.get("changes_code", False)
    found = endpoint or default_endpoint(args.project)
    shown = found[:2] if changes_code else NO_CHANGE_ENDPOINT
    facts, warning = {}, None
    if args.reason is not None and not args.raise_to:
        raise SystemExit("plan.py: --reason goes with --raise-to. Drop it, or raise the route.")
    if tiered:
        missing = [name for name in manifest["facts"] if getattr(args, name) is None]
        if args.user_route and args.raise_to:
            raise SystemExit("plan.py: pass --user-route or --raise-to, not both. The user's route wins, so tell the user why you would raise it.")
        if len(missing) == len(manifest["facts"]) and not args.user_route and not args.raise_to:
            return pending(args, manifest, path, prose, shown)
        if missing:
            raise SystemExit(f"plan.py: record all five facts, even when a route is named. Missing: {', '.join('--' + m for m in missing)}.")
        facts = {name: parse_fact(getattr(args, name)) for name in manifest["facts"]}
        table, why = table_route(facts)
        route, source = table, "table"
        if args.raise_to:
            if ROUTES.index(args.raise_to) < ROUTES.index(table):
                raise SystemExit(f"plan.py: the lead can raise the route, not lower it. The table gives {table}. Only the user lowers a route, with --user-route.")
            if not (args.reason or "").strip():
                raise SystemExit("plan.py: --raise-to needs --reason.")
            route, why, source = args.raise_to, args.reason, "lead"
        if args.user_route:
            route, source = args.user_route, "user"
            if ROUTES.index(route) < ROUTES.index(table):
                warning = (f"The user's route is below the table's, which gives {table} because {why}. "
                           "Tell the user which facts are not low before the first edit.")
            why = "the user set the route"
    else:
        given = [f"--{name}" for name in manifest["facts"] if getattr(args, name) is not None]
        if given:
            raise SystemExit(f"plan.py: {args.playbook} has one procedure, so it takes no risk facts. Drop {', '.join(given)}.")
        route, why, source = "standard", "this playbook has one procedure", "fixed"
        if args.user_route or args.raise_to:
            warning = "This playbook has one procedure, so the requested route does not apply."

    skips = entry.get("lightweight_skips", {}) if route == "lightweight" else {}
    planned = []
    for number, text in steps:
        loads, conditional, held = route_loads(text, route, tiered, manifest)
        named = [a or b for a, b in NAMED.findall(text)]
        uses = [] if route == "lightweight" else [s for s in dict.fromkeys(named) if s not in loads + conditional + held]
        planned.append({"number": number, "name": step_name(text), "outcome": outcome(text), "loads": loads,
                        "conditional": conditional, "uses": uses, "held_for_intensive": held, "skipped": skips.get(step_name(text)),
                        "runs_pr": changes_code and bool(RUN_PR.search(text))})

    gates = route_gates(manifest, args.playbook, route)
    return {
        "playbook": args.playbook, "file": display_path(path), "full_read": any(line.startswith(FULL_READ) for line in prose),
        "regime": regime(args.playbook, manifest),
        "route": route, "route_source": source, "route_reason": why, "tiered": tiered, "warning": warning,
        "facts": {name: {"level": level, "evidence": evidence} for name, (level, evidence) in facts.items()},
        "opening": prose, "steps": planned,
        "lightweight_worklist": entry.get("lightweight_worklist") if route == "lightweight" else None,
        "gates": gates, "scrutiny": (SCRUTINY_REMOTE if found[2] else SCRUTINY_LOCAL) if changes_code else None,
        "reply": reply, "reply_loads": LOAD.findall(reply),
        "default_endpoint": shown[0], "default_endpoint_reason": shown[1],
    }


def render(plan, harness):
    out = [f"playbook: {plan['playbook']} ({plan['file']})"]
    out.append(f"route: {plan['route']} ({plan['route_source']}: {plan['route_reason']})")
    for name, fact in plan["facts"].items():
        out.append(f"  {name}: {fact['level']}" + (f" ({fact['evidence']})" if fact["evidence"] else ""))
    if plan["warning"]:
        out.append(f"warning: {plan['warning']}")
    out.append("")
    out.append("This output is not the worklist. Create the worklist in your carrier now from the items below, in this order. Keep one in progress.")
    out.append(f"First item: `{plan['playbook']} playbook opening`. Record these fields in it:")
    out.append(f"   playbook: {plan['file']}")
    out.append("   start commit: the output of `git rev-parse HEAD`, or `no commits`")
    out.append(f"   route: {plan['route']} ({plan['route_source']})")
    out.append(f"   endpoint: the user's stated endpoint, else {plan['default_endpoint']} ({plan['default_endpoint_reason']})")
    out.append("   budget: what would make you change approach, such as two failed attempts on one premise")
    if plan["route"] == "pending":
        out.append("Then: Record the five risk facts with evidence, as references/routes.md defines them. Change no file before this item closes.")
        out.append("Then: Rerun this script with the facts, and replace this item with the items it prints.")
        out += ["", "gates, which bind before the facts are recorded, at the lightest route's times:", *render_gates(plan["gates"], harness)]
        return "\n".join(out)
    if plan["full_read"] and not plan["steps"]:
        out.append(f"Then: Read {plan['file']} in full. It has no numbered steps.")
    elif plan["opening"]:
        out.append("   opening prose, kept with the first item: " + " ".join(plan["opening"]))
    if plan["lightweight_worklist"]:
        by_name = {step["name"]: step for step in plan["steps"]}
        out.append("Then these tracked outcomes:")
        for index, item in enumerate(plan["lightweight_worklist"], 1):
            covered = [by_name[name] for name in item["covers"] if name in by_name]
            numbers = ", ".join(str(step["number"]) for step in covered)
            out.append(f"{index}. {item['item']} (steps {numbers}). Outcomes: " + " ".join(step["outcome"] for step in covered))
            loads = [skill for step in covered for skill in step["loads"]]
            if loads:
                out.append("   load: " + "; ".join(load_phrase(skill, harness) for skill in loads))
            maybe = [skill for step in covered for skill in step["conditional"]]
            if maybe:
                out.append(WHEN_HOLDS + ", ".join(maybe))
            if any(step["runs_pr"] for step in covered):
                out.append(KEEP_COMMITS)
        for step in plan["steps"]:
            if step["skipped"]:
                out.append(f"   {step['name']}: `skipped: {step['skipped']}` only when that is true. Otherwise {raise_the_route(plan['route_source'])}.")
    elif plan["steps"]:
        if plan["full_read"]:
            out.append(f"Then: Read {plan['file']} in full. Its steps index the sections after them.")
        out.append("Then one item per step:")
        for step in plan["steps"]:
            out.append(f"{step['number']}. {step['outcome']}")
            if step["runs_pr"]:
                out.append(KEEP_COMMITS)
            if step["loads"]:
                out.append("   load: " + "; ".join(load_phrase(skill, harness) for skill in step["loads"]))
            if step["conditional"]:
                out.append(WHEN_HOLDS + ", ".join(step["conditional"]))
            if step["uses"]:
                out.append("   also uses, as the step's text says: " + ", ".join(step["uses"]))
            if step["held_for_intensive"]:
                out.append("   intensive only: " + ", ".join(step["held_for_intensive"])
                           + f". Compare the options yourself and record them. {raise_the_route(plan['route_source']).capitalize()} when you cannot choose.")
    if plan["route"] == "lightweight":
        out.append("Lightweight means direct work by the lead, no panel, and no investigation or implementation delegate.")
        out.append("If new evidence makes a fact material or unknown, rerun this script and expand the worklist before further edits.")
    out.append("")
    out.append("gates:")
    out += render_gates(plan["gates"], harness)
    if plan["scrutiny"]:
        out.append("")
        out.append("independent scrutiny: " + plan["scrutiny"])
    if plan["reply"]:
        out.append("")
        out.append("Last item, the reply. " + plan["reply"])
        if plan["reply_loads"]:
            out.append("   load: " + "; ".join(load_phrase(skill, harness) for skill in plan["reply_loads"]))
    if harness != "claude-code" and "call the skill tool" in "\n".join(out).lower():
        out += ["", harness_note(harness)]
    out.append("")
    if plan["regime"]:
        out.append(plan["regime"])
    if plan["steps"]:
        route = f" --route {plan['route']}" if plan["tiered"] else ""
        out.append(f"When a step starts, print its full text: rerun this script as `{plan['playbook']} --step <number>{route}`.")
        if plan["lightweight_worklist"]:
            out.append("Item numbers are not step numbers: when an item starts, print each step number in its parentheses.")
    out.append("Another review pass needs a named unresolved concern.")
    return "\n".join(out)


def directory(value):
    if not Path(value).is_dir():
        raise argparse.ArgumentTypeError(f"{value!r} is not an existing directory")
    return Path(value)


def main(argv=None):
    manifest = json.loads((MODE / "routes.json").read_text(encoding="utf-8"))
    parser = PlanParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter, allow_abbrev=False)
    parser.add_argument("playbook", help="Playbook id, such as feature or bug-fix")
    for name in manifest["facts"]:
        parser.add_argument(f"--{name}", metavar="LEVEL[:EVIDENCE]", action=Once,
                            help="low, material, or unknown, then a colon and one line saying what was checked")
    parser.add_argument("--user-route", choices=ROUTES, action=Once, help="The route the user asked for, in either direction")
    parser.add_argument("--raise-to", choices=ROUTES, action=Once, help="A higher route the lead chooses, with --reason")
    parser.add_argument("--reason", action=Once, help="Why the lead raises the route")
    parser.add_argument("--step", type=int, metavar="N", action=Once, help="Print the full text of step N and the route's gates")
    parser.add_argument("--route", choices=ROUTES, action=Once, help="With --step on a routed playbook, the route the plan printed")
    parser.add_argument("--harness", choices=("claude-code", "codex", "grok", "hermes", "other"), default="other", action=Once)
    parser.add_argument("--project", type=directory, action=Once, help="Repository to inspect for a remote (default: the current directory)")
    parser.add_argument("--json", action="store_true")
    argv = sys.argv[1:] if argv is None else argv
    undecodable = next((arg for arg in argv if SURROGATE.search(arg)), None)
    if undecodable is not None:
        print(f"plan.py: {undecodable!r} is not valid UTF-8.", file=sys.stderr)
        return 2
    args = parser.parse_args(argv)
    if args.step is None and args.route:
        parser.error("--route goes with --step. The full plan takes the risk facts and chooses the route.")
    if args.step is not None:
        plan_only = [f"--{name.replace('_', '-')}" for name in (*manifest["facts"], "user_route", "raise_to", "reason")
                     if getattr(args, name) is not None]
        if args.json:
            plan_only.append("--json")
        if plan_only:
            parser.error(f"--step prints one step of a plan already made. Drop {', '.join(plan_only)}.")
    elif args.project is None:
        try:
            args.project = Path.cwd()
        except FileNotFoundError:
            parser.error("the current directory no longer exists, so pass --project.")
    try:
        if args.step is not None:
            print(render_step(args, manifest))
            return 0
        plan = build(args, manifest)
    except SystemExit as error:
        if isinstance(error.code, str):
            print(error.code, file=sys.stderr)
            return 2
        raise
    print(json.dumps(plan, indent=2) if args.json else render(plan, args.harness))
    return 0


if __name__ == "__main__":
    sys.exit(main())
