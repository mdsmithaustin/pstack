#!/usr/bin/env python3
"""Print the route, worklist, skill loads, and gates for one poteto-mode playbook.

The lead supplies the playbook and five risk facts. This script applies the
routing policy, so the answer is the same on every model and harness. Steps and
their outcome sentences come from the playbook file. Gates and playbook flags
come from routes.json beside the mode entry.

Exit 2 means a usage error, such as an unknown playbook or a lowered route.
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
SENTENCE_END = re.compile(r"(?<=[.!?])\s")
FULL_READ = "Read this playbook in full."


def read_playbook(path):
    """Return (opening prose lines, [(number, text block)]) as the worklist rule splits them."""
    prose, steps, current = [], [], None
    for line in path.read_text(encoding="utf-8").split("\n"):
        match = STEP.match(line)
        if match:
            current = [match.group(2)]
            steps.append((int(match.group(1)), current))
        elif current is None:
            if line.strip() and not line.startswith("#"):
                prose.append(line)
        elif line[:1] not in ("", " ", "\t"):
            break
        else:
            current.append(line.strip())
    return prose, [(number, " ".join(part for part in block if part)) for number, block in steps]


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
    level, evidence = level.strip(), evidence.strip()
    if level not in LEVELS:
        raise SystemExit(f"plan.py: a fact is one of {', '.join(LEVELS)}, optionally followed by :evidence. Got {value!r}.")
    if level == "low" and not evidence:
        return "unknown", "recorded low with no evidence, so treated as unknown"
    return level, evidence


def merge_second_opinion(facts, path):
    """A second opinion can raise a fact from low. It never lowers one. A bad file changes nothing."""
    try:
        answer = json.loads(Path(path).read_text(encoding="utf-8"))
        levels = answer["levels"]
        if answer.get("status") != "answered" or set(levels) != set(facts) or any(v not in LEVELS for v in levels.values()):
            raise ValueError("not an answered second opinion")
    except (OSError, ValueError, KeyError, TypeError) as error:
        return facts, f"second opinion ignored: {error}"
    raised = []
    merged = dict(facts)
    for name, (level, evidence) in facts.items():
        if level == "low" and levels[name] != "low":
            merged[name] = (levels[name], f"second opinion from {answer.get('cli', 'a CLI')} raised this from low. {evidence}".strip())
            raised.append(name)
    return merged, "second opinion raised: " + ", ".join(raised) if raised else "second opinion raised nothing"


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

    if git("rev-parse", "--git-dir").returncode != 0:
        return "commits on a first local branch after `git init`", "no Git repository", False
    if not git("remote").stdout.strip():
        return "commits on a local branch, with the branch and its diff command in the reply", "no remote", False
    if shutil.which("gh") or shutil.which("origin"):
        return "reviewable PR", "remote and a forge CLI found", True
    return "reviewable PR through a built-in PR tool, else a pushed branch named in the reply", "remote found, no forge CLI on PATH", True


def load_phrase(skill, harness):
    if harness == "claude-code":
        return f"Call the Skill tool with `{skill}`"
    return f'read "${{PSTACK_SKILLS_ROOT:?}}/{skill}/SKILL.md" in full'


def pending(args, path, prose):
    """No facts yet: the worklist opens first, and the facts are its first item."""
    endpoint, endpoint_why, _ = default_endpoint(args.project)
    return {
        "playbook": args.playbook, "file": str(path), "full_read": False, "route": "pending",
        "route_source": "table", "route_reason": "no risk facts recorded yet", "tiered": True, "facts": {}, "second_opinion": None,
        "opening": prose, "steps": [], "lightweight_worklist": None, "gates": [], "scrutiny": None,
        "default_endpoint": endpoint, "default_endpoint_reason": endpoint_why,
    }


def build(args, manifest):
    entry = manifest["playbooks"].get(args.playbook)
    if entry is None:
        raise SystemExit(f"plan.py: unknown playbook {args.playbook!r}. Known: {', '.join(sorted(manifest['playbooks']))}.")
    path = MODE / entry["file"]
    prose, steps = read_playbook(path)
    tiered = entry.get("tiered", False)
    facts, second = {}, None
    if tiered:
        missing = [name for name in manifest["facts"] if getattr(args, name) is None]
        if len(missing) == len(manifest["facts"]) and not args.user_route and not args.raise_to:
            return pending(args, path, prose)
        facts = {name: parse_fact(getattr(args, name) or "unknown") for name in manifest["facts"]}
        if args.second_opinion:
            facts, second = merge_second_opinion(facts, args.second_opinion)
        route, why = table_route(facts)
        source = "table"
        if args.raise_to:
            if ROUTES.index(args.raise_to) < ROUTES.index(route):
                raise SystemExit(f"plan.py: the lead can raise the route, not lower it. The table gives {route}. Only the user lowers a route, with --user-route.")
            if not args.reason:
                raise SystemExit("plan.py: --raise-to needs --reason.")
            route, why, source = args.raise_to, args.reason, "lead"
        if args.user_route:
            route, why, source = args.user_route, "the user set the route", "user"
    else:
        route, why, source = "standard", "this playbook has one procedure", "fixed"

    panels, keeps = set(manifest["panels"]), set(manifest["lightweight_keeps"])
    skips = entry.get("lightweight_skips", {}) if route == "lightweight" else {}
    planned = []
    for number, text in steps:
        name = step_name(text)
        loads, held = [], []
        for skill in dict.fromkeys(LOAD.findall(text)):
            if skill in panels and route != "intensive" and tiered:
                held.append(skill)
            elif route == "lightweight" and skill not in keeps and skill != "pstack-harness":
                continue
            elif route == "lightweight" and skill == "pstack-harness":
                continue
            else:
                loads.append(skill)
        planned.append({"number": number, "name": name, "outcome": outcome(text), "loads": loads,
                        "held_for_intensive": held, "skipped": skips.get(name)})

    endpoint, endpoint_why, has_remote = default_endpoint(args.project)
    changes_code = entry.get("changes_code", False)
    gates = []
    for gate in manifest["gates"]:
        if gate["applies"] == "code" and not changes_code:
            continue
        when = gate["when"].get(route) or gate["when"]["all"]
        gates.append({"id": gate["id"], "skill": gate.get("skill"), "run": gate.get("run"), "when": when})
    scrutiny = None
    if changes_code:
        scrutiny = ("Credit an existing independent review of the current revision, or leave human PR review pending at delivery. "
                    "Otherwise brief one `trail reviewer`." if has_remote else
                    "No remote, so no PR review exists to credit. Brief one `trail reviewer`, or report the user's review of the local branch as pending.")
    return {
        "playbook": args.playbook, "file": str(path), "full_read": any(line.startswith(FULL_READ) for line in prose),
        "route": route, "route_source": source, "route_reason": why, "tiered": tiered,
        "facts": {name: {"level": level, "evidence": evidence} for name, (level, evidence) in facts.items()},
        "second_opinion": second, "opening": prose, "steps": planned,
        "lightweight_worklist": entry.get("lightweight_worklist") if route == "lightweight" else None,
        "gates": gates, "scrutiny": scrutiny,
        "default_endpoint": endpoint, "default_endpoint_reason": endpoint_why,
    }


def render(plan, harness):
    out = [f"playbook: {plan['playbook']} ({plan['file']})"]
    out.append(f"route: {plan['route']} ({plan['route_source']}: {plan['route_reason']})")
    for name, fact in plan["facts"].items():
        out.append(f"  {name}: {fact['level']}" + (f" ({fact['evidence']})" if fact["evidence"] else ""))
    if plan["second_opinion"]:
        out.append(f"  {plan['second_opinion']}")
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
    if plan["full_read"]:
        out.append(f"Then: Read {plan['file']} in full. It has no numbered steps.")
    elif plan["lightweight_worklist"]:
        by_name = {step["name"]: step for step in plan["steps"]}
        out.append("Then these tracked outcomes:")
        for index, item in enumerate(plan["lightweight_worklist"], 1):
            covered = [by_name[name] for name in item["covers"] if name in by_name]
            out.append(f"{index}. {item['item']}. Outcomes: " + " ".join(step["outcome"] for step in covered))
            loads = [skill for step in covered for skill in step["loads"]]
            if loads:
                out.append("   load: " + "; ".join(load_phrase(skill, harness) for skill in loads))
        for step in plan["steps"]:
            if step["skipped"]:
                out.append(f"   {step['name']}: `skipped: {step['skipped']}` only when that is true. Otherwise raise the route.")
    else:
        if plan["opening"]:
            out.append("   opening prose, kept with the first item: " + " ".join(plan["opening"]))
        out.append("Then one item per step:")
        for step in plan["steps"]:
            out.append(f"{step['number']}. {step['outcome']}")
            if step["loads"]:
                out.append("   load: " + "; ".join(load_phrase(skill, harness) for skill in step["loads"]))
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
    out.append("")
    out.append("Read each step's full text in the playbook when its turn comes. Another review pass needs a named unresolved concern.")
    return "\n".join(out)


def main(argv=None):
    manifest = json.loads((MODE / "routes.json").read_text(encoding="utf-8"))
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("playbook", help="Playbook id, such as feature or bug-fix")
    for name in manifest["facts"]:
        parser.add_argument(f"--{name}", metavar="LEVEL[:EVIDENCE]",
                            help="low, material, or unknown, then a colon and one line of evidence")
    parser.add_argument("--user-route", choices=ROUTES, help="The route the user asked for, in either direction")
    parser.add_argument("--raise-to", choices=ROUTES, help="A higher route the lead chooses, with --reason")
    parser.add_argument("--reason", help="Why the lead raises the route")
    parser.add_argument("--second-opinion", type=Path, help="Answer file from second-opinion.py. It can only raise a fact")
    parser.add_argument("--harness", choices=("claude-code", "codex", "grok", "hermes", "other"), default="other")
    parser.add_argument("--project", type=Path, default=Path.cwd(), help="Repository to inspect for a remote")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
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
