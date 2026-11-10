#!/usr/bin/env python3
"""Print the route, worklist, skill loads, and gates for one poteto-mode playbook.

The lead supplies the playbook and five risk facts. This script applies the
routing policy, so the answer is the same on every model and harness. Steps and
their outcome sentences come from the playbook file, which owns them. Gates, panels,
and the flags of code-changing playbooks come from routes.json beside the mode entry.

With --step N it prints the full text of one step instead, for the moment that step starts.

Exit 2 means a usage error, such as an unknown playbook, a missing step, or a lowered route.
"""
import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

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
CONDITIONAL = re.compile(r"^\W*(If|When|Where|For|On the|Once|Unless|Otherwise|Only)\b")
THIN_EVIDENCE = {"ok", "okay", "fine", "none", "n/a", "na", "unknown", "low", "tbd", "yes", "no", "same", "trivial", "nothing"}
SCRUTINY_REMOTE = ("Credit an existing independent review of the current revision. Or name human PR review as the scrutiny, "
                   "record the revision it must cover, and report delivery as pending review. Otherwise brief one `trail reviewer`.")
SCRUTINY_LOCAL = ("No remote, so no PR review exists to credit. Brief one `trail reviewer`, or report the user's review of "
                  "the local branch as pending.")
NO_CHANGE_ENDPOINT = ("what this playbook's Reply line names", "this playbook does not produce a code change")


class Once(argparse.Action):
    """Refuse a repeated flag, so a later value cannot silently replace an earlier one."""

    def __call__(self, parser, namespace, values, option_string=None):
        if getattr(namespace, self.dest) is not None:
            parser.error(f"{option_string} was given more than once.")
        setattr(namespace, self.dest, values)


def read_playbook(path):
    """Return (opening prose lines, [(number, text block)], reply line) as the worklist rule splits them."""
    prose, steps, current, reply = [], [], None, ""
    for line in path.read_text(encoding="utf-8").split("\n"):
        match = STEP.match(line)
        if line.startswith(REPLY):
            reply = line.strip()
        elif match and not reply:
            current = [match.group(2)]
            steps.append((int(match.group(1)), current))
        elif current is None:
            if line.strip() and not line.startswith("#"):
                prose.append(line)
        elif line[:1] in ("", " ", "\t") and not reply:
            current.append(line.strip())
    return prose, [(number, " ".join(part for part in block if part)) for number, block in steps], reply


def step_loads(text):
    """Split a step's skill loads into those it always makes and those behind a condition in the same sentence."""
    always, conditional = [], []
    for sentence in SENTENCE_END.split(text):
        target = conditional if CONDITIONAL.match(sentence) else always
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
    tiered = manifest["playbooks"].get(args.playbook, {}).get("tiered", False)
    out = [f"{args.playbook} step {args.step}, from {display_path(path)}", ""]
    if tiered and args.route == "lightweight":
        out += ["Lightweight route: do this step's work yourself. Skip its sentences that delegate, spawn a subagent, or load a skill the plan did not list. Keep its outcome, its checks, and its commands.", ""]
    elif tiered and args.route == "standard":
        panels = ", ".join(f"`{name}`" for name in manifest["panels"])
        out += [f"Standard route: the panels ({panels}) stay unloaded. Where this step names one, compare the options yourself and record them.", ""]
    out += [text, "", regime(args.playbook, manifest), "Mark the item completed only with its evidence."]
    return "\n".join(out)


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
        if len(evidence.split()) < 2 or len(evidence) < 8 or evidence.lower().strip(".") in THIN_EVIDENCE:
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
    def git(*args):
        return subprocess.run(["git", "-C", str(project), *args], capture_output=True, text=True)

    try:
        inside = git("rev-parse", "--git-dir").returncode == 0
    except OSError:
        return "commits on a local branch once Git is available", "Git is not on PATH", False
    if not inside:
        return "commits on a first local branch after `git init`", "no Git repository", False
    if not git("remote").stdout.strip():
        return "commits on a local branch, with the branch and its diff command in the reply", "no remote", False
    if shutil.which("gh") or shutil.which("origin"):
        return "reviewable PR", "remote and a forge CLI found", True
    return "reviewable PR through a built-in PR tool, else a pushed branch named in the reply", "remote found, no forge CLI on PATH", True


def display_path(path):
    """The playbook path as a lead can use it on any machine."""
    return "${PSTACK_SKILLS_ROOT}/" + path.relative_to(MODE.parent).as_posix()


def load_phrase(skill, harness):
    if harness == "claude-code":
        return f"Call the Skill tool with `{skill}`"
    return f'read "${{PSTACK_SKILLS_ROOT:?}}/{skill}/SKILL.md" in full'


def pending(args, path, prose, endpoint):
    """No facts yet: the worklist opens first, and the facts are its first item."""
    return {
        "playbook": args.playbook, "file": display_path(path), "full_read": False, "route": "pending", "regime": None,
        "route_source": "table", "route_reason": "no risk facts recorded yet", "tiered": True, "facts": {}, "warning": None,
        "opening": prose, "steps": [], "lightweight_worklist": None, "gates": [], "scrutiny": None, "reply": "", "reply_loads": [],
        "default_endpoint": endpoint[0], "default_endpoint_reason": endpoint[1],
    }


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
    if tiered:
        missing = [name for name in manifest["facts"] if getattr(args, name) is None]
        if args.user_route and args.raise_to:
            raise SystemExit("plan.py: pass --user-route or --raise-to, not both. The user's route wins, so tell the user why you would raise it.")
        if len(missing) == len(manifest["facts"]) and not args.user_route and not args.raise_to:
            return pending(args, path, prose, shown)
        if missing:
            raise SystemExit(f"plan.py: record all five facts, even when a route is named. Missing: {', '.join('--' + m for m in missing)}.")
        facts = {name: parse_fact(getattr(args, name)) for name in manifest["facts"]}
        table, why = table_route(facts)
        route, source = table, "table"
        if args.raise_to:
            if ROUTES.index(args.raise_to) < ROUTES.index(table):
                raise SystemExit(f"plan.py: the lead can raise the route, not lower it. The table gives {table}. Only the user lowers a route, with --user-route.")
            if not args.reason:
                raise SystemExit("plan.py: --raise-to needs --reason.")
            route, why, source = args.raise_to, args.reason, "lead"
        if args.user_route:
            route, source = args.user_route, "user"
            if ROUTES.index(route) < ROUTES.index(table):
                warning = (f"The user's route is below the table's, which gives {table} because {why}. "
                           "Tell the user which facts are not low before the first edit.")
            why = "the user set the route"
    else:
        route, why, source = "standard", "this playbook has one procedure", "fixed"
        if args.user_route or args.raise_to:
            warning = "This playbook has one procedure, so the requested route does not apply."

    panels, keeps = set(manifest["panels"]), set(manifest["lightweight_keeps"])
    skips = entry.get("lightweight_skips", {}) if route == "lightweight" else {}

    def allowed(skills):
        return [s for s in skills if not (tiered and s in panels and route != "intensive") and not (route == "lightweight" and s not in keeps)]

    planned = []
    for number, text in steps:
        always, conditional = step_loads(text)
        held = [s for s in always + conditional if tiered and s in panels and route != "intensive"]
        loads, conditional = allowed(always), allowed(conditional)
        named = [a or b for a, b in NAMED.findall(text)]
        uses = [] if route == "lightweight" else [s for s in dict.fromkeys(named)
                                                 if s not in loads + conditional + held and (MODE.parent / s / "SKILL.md").is_file()]
        planned.append({"number": number, "name": step_name(text), "outcome": outcome(text), "loads": loads,
                        "conditional": conditional, "uses": uses, "held_for_intensive": held, "skipped": skips.get(step_name(text))})

    gates = []
    for gate in manifest["gates"]:
        if gate["applies"] == "code" and not changes_code:
            continue
        when = gate["when"].get(route) or gate["when"]["all"]
        gates.append({"id": gate["id"], "skill": gate.get("skill"), "run": gate.get("run"), "when": when})
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
        return "\n".join(out)
    if plan["full_read"] and not plan["steps"]:
        out.append(f"Then: Read {plan['file']} in full. It has no numbered steps.")
    elif plan["lightweight_worklist"]:
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
                out.append("   load only when the step's own condition holds: " + ", ".join(maybe))
        for step in plan["steps"]:
            if step["skipped"]:
                out.append(f"   {step['name']}: `skipped: {step['skipped']}` only when that is true. Otherwise raise the route.")
    else:
        if plan["opening"]:
            out.append("   opening prose, kept with the first item: " + " ".join(plan["opening"]))
        if plan["full_read"]:
            out.append(f"Then: Read {plan['file']} in full. Its steps index the sections after them.")
        out.append("Then one item per step:")
        for step in plan["steps"]:
            out.append(f"{step['number']}. {step['outcome']}")
            if step["loads"]:
                out.append("   load: " + "; ".join(load_phrase(skill, harness) for skill in step["loads"]))
            if step["conditional"]:
                out.append("   load only when the step's own condition holds: " + ", ".join(step["conditional"]))
            if step["uses"]:
                out.append("   also uses, as the step's text says: " + ", ".join(step["uses"]))
            if step["held_for_intensive"]:
                out.append("   intensive only: " + ", ".join(step["held_for_intensive"])
                           + ". Compare the options yourself and record them. Raise the route when you cannot choose.")
    if plan["route"] == "lightweight":
        out.append("Lightweight means direct work by the lead, no panel, and no investigation or implementation delegate.")
        out.append("If new evidence makes a fact material or unknown, rerun this script and expand the worklist before further edits.")
    out.append("")
    out.append("gates:")
    for gate in plan["gates"]:
        action = load_phrase(gate["skill"], harness) if gate["skill"] else f"run `{gate['run']}`"
        out.append(f"- {gate['id']}: {action}, {gate['when']}.")
    if plan["scrutiny"]:
        out.append("")
        out.append("independent scrutiny: " + plan["scrutiny"])
    if plan["reply"]:
        out.append("")
        out.append("Last item, the reply. " + plan["reply"])
        if plan["reply_loads"]:
            out.append("   load: " + "; ".join(load_phrase(skill, harness) for skill in plan["reply_loads"]))
    out.append("")
    if plan["regime"]:
        out.append(plan["regime"])
    if plan["steps"]:
        route = f" --route {plan['route']}" if plan["tiered"] else ""
        out.append(f"When a step starts, print its full text: rerun this script as `{plan['playbook']} --step <number>{route}`.")
    out.append("Another review pass needs a named unresolved concern.")
    return "\n".join(out)


def main(argv=None):
    manifest = json.loads((MODE / "routes.json").read_text(encoding="utf-8"))
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter, allow_abbrev=False)
    parser.add_argument("playbook", help="Playbook id, such as feature or bug-fix")
    for name in manifest["facts"]:
        parser.add_argument(f"--{name}", metavar="LEVEL[:EVIDENCE]", action=Once,
                            help="low, material, or unknown, then a colon and one line saying what was checked")
    parser.add_argument("--user-route", choices=ROUTES, help="The route the user asked for, in either direction")
    parser.add_argument("--raise-to", choices=ROUTES, help="A higher route the lead chooses, with --reason")
    parser.add_argument("--reason", help="Why the lead raises the route")
    parser.add_argument("--step", type=int, metavar="N", help="Print the full text of step N and nothing else")
    parser.add_argument("--route", choices=ROUTES, help="With --step on a routed playbook, the route the plan printed")
    parser.add_argument("--harness", choices=("claude-code", "codex", "grok", "hermes", "other"), default="other")
    parser.add_argument("--project", type=Path, default=Path.cwd(), help="Repository to inspect for a remote")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
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
