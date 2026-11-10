#!/usr/bin/env python3
"""Report the bytes each playbook route places in the lead's context, under a budget that only tightens.

Context is what the lead reads: Markdown instructions and the text a script prints. A script's
own source is not context. It is maintenance surface, which --surface reports separately and
which no budget here limits.

A route's context is:
- the mode entry and its always-read references,
- the playbook, and the references its steps tell the lead to read, open, follow, or apply,
- the skills its steps load or name, and the skills its gates run,
- the plan that plan.py prints for it.

plan.py supplies the steps and gates, so this follows the same manifest the lead follows. Counts
are UTF-8 bytes, not provider tokens. Linked references are followed one hop from the playbook.
A reference inside a loaded skill is not followed, so the figure is a floor for a route that
reads deeper.

  check-route-bytes.py            check every route against tools/route-byte-budgets.json
  check-route-bytes.py --report   print each route's bytes, split into Markdown and plan output
  check-route-bytes.py --surface  print the script and test bytes that support the suite
  check-route-bytes.py --update   rewrite the budgets to the current bytes

--update refuses to raise a budget unless --allow-raise is passed for a reviewed exception.
Exit 0: every route is within budget. Exit 1: a route is over, or has no budget.
"""
import argparse
import importlib.util
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUDGETS = Path(__file__).with_name("route-byte-budgets.json")
ALWAYS = [
    "skills/poteto-mode/SKILL.md",
    "skills/poteto-mode/references/task-triggers.md",
    "skills/poteto-mode/references/writing.md",
    "skills/pstack-harness/SKILL.md",
    "skills/pstack-harness/references/worklist.md",
]
LOW = "low:evidence"
FACTS = {
    "lightweight": {},
    "standard": {"reach": "material:evidence"},
    "intensive": {"consequence": "material:evidence", "uncertainty": "material:evidence"},
}
OPT_IN_GATES = {"recap"}
LINK = re.compile(r"\[[^\]]*\]\(([^)#\s]+\.md)(?:#[^)]*)?\)")
READ_VERB = re.compile(r"\b(read|open|opens|follow|apply|continue in)\b", re.I)
PLAYBOOK_PATH = re.compile(r"`(playbooks/[a-z-]+\.md)`")
CONDITIONAL = re.compile(r"^\W*(If|When|Where|For|On the|Otherwise|Only)\b")
RUN_PR = re.compile(r"\bRun \*\*Opening a PR\*\*")
SENTENCE = re.compile(r"(?<=[.!?])\s+")
SURFACE_SUFFIXES = {".py", ".ts", ".mjs", ".sh"}


def linked_reads(root, playbook_file):
    """References one hop from the playbook that an unconditional sentence tells the lead to read or run.

    A sentence that opens with a condition, such as "If" or "For a", names a read the route may not make,
    so it is left out and the figure stays a floor. Only files under skills/ count. Repository documents
    such as PORTING.md are written for maintainers, not loaded by a route.
    """
    path = root / playbook_file
    found = []
    for sentence in SENTENCE.split(path.read_text(encoding="utf-8")):
        if CONDITIONAL.match(sentence.strip()):
            continue
        targets = []
        if READ_VERB.search(sentence):
            targets += [path.parent / link for link in LINK.findall(sentence)]
            targets += [root / "skills/poteto-mode" / name for name in PLAYBOOK_PATH.findall(sentence)]
        if RUN_PR.search(sentence):
            targets.append(root / "skills/poteto-mode/playbooks/opening-a-pr.md")
        for target in targets:
            target = target.resolve()
            if target.is_file() and target != path.resolve() and (root / "skills").resolve() in target.parents:
                found.append(target.relative_to(root.resolve()).as_posix())
    return list(dict.fromkeys(found))


def surface(root):
    """Script and test files that support the suite. They cost maintenance, not context."""
    groups = {"skill scripts": [root / "skills"], "tools": [root / "tools"], "tests": [root / "tests"]}
    report = {}
    for name, tops in groups.items():
        files = [p for top in tops for p in top.rglob("*")
                 if p.is_file() and p.suffix in SURFACE_SUFFIXES and "node_modules" not in p.parts]
        report[name] = {"files": len(files), "bytes": sum(p.stat().st_size for p in files)}
    return report


def load_plan(root):
    spec = importlib.util.spec_from_file_location("pstack_plan", root / "skills/poteto-mode/scripts/plan.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def route_files(root, plan_module, manifest, playbook, route):
    entry = manifest["playbooks"].get(playbook, {})
    levels = {name: None for name in manifest["facts"]}
    if entry.get("tiered"):
        levels = {name: LOW for name in manifest["facts"]} | FACTS[route]
    plan = plan_module.build(plan_module.argparse.Namespace(
        playbook=playbook, user_route=None, raise_to=None, reason=None, second_opinion=None, harness="other", project=root, **levels,
    ), manifest)
    playbook_file = f"skills/poteto-mode/playbooks/{playbook}.md"
    linked = linked_reads(root, playbook_file)
    if plan["route"] == "lightweight":
        linked = [name for name in linked if not name.endswith("references/delegation.md")]
    files = list(ALWAYS) + [playbook_file] + linked
    if entry.get("tiered"):
        files.append("skills/poteto-mode/references/routes.md")
    if entry.get("changes_code"):
        files.append("skills/poteto-mode/references/review-lens.md")
        files.append("skills/poteto-mode/playbooks/opening-a-pr.md")
        if plan["route"] != "lightweight":
            files.append("skills/poteto-mode/references/delegation.md")
    skills = [skill for step in plan["steps"] for skill in step["loads"] + step["uses"]]
    skills += [gate["skill"] for gate in plan["gates"] if gate["skill"] and gate["id"] not in OPT_IN_GATES]
    files += [f"skills/{skill}/SKILL.md" for skill in skills]
    return list(dict.fromkeys(files)), len(plan_module.render(plan, "other").encode("utf-8"))


def measure(root):
    manifest = json.loads((root / "skills/poteto-mode/routes.json").read_text(encoding="utf-8"))
    plan_module = load_plan(root)
    report = {}
    for playbook in sorted(path.stem for path in (root / "skills/poteto-mode/playbooks").glob("*.md")):
        entry = manifest["playbooks"].get(playbook, {})
        for route in (manifest["routes"] if entry.get("tiered") else ["standard"]):
            files, plan_output = route_files(root, plan_module, manifest, playbook, route)
            sizes = {name: len((root / name).read_bytes()) for name in files}
            key = f"{playbook}:{route}" if entry.get("tiered") else playbook
            report[key] = {"bytes": sum(sizes.values()) + plan_output, "markdown": sum(sizes.values()),
                           "plan_output": plan_output, "files": sizes}
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--budgets", type=Path, default=BUDGETS)
    parser.add_argument("--report", action="store_true")
    parser.add_argument("--surface", action="store_true")
    parser.add_argument("--update", action="store_true")
    parser.add_argument("--allow-raise", action="store_true")
    args = parser.parse_args(argv)
    if args.surface:
        for name, value in surface(args.root).items():
            print(f"{value['bytes']:>8}  {name}  ({value['files']} files)")
        print("Maintenance surface. None of it is placed in the lead's context, and no budget here limits it.")
        return 0
    report = measure(args.root)
    current = {key: value["bytes"] for key, value in report.items()}
    if args.report:
        for key, value in report.items():
            print(f"{value['bytes']:>7}  {key}  (Markdown {value['markdown']} in {len(value['files'])} files, plan output {value['plan_output']})")
        return 0
    budgets = json.loads(args.budgets.read_text(encoding="utf-8")) if args.budgets.is_file() else {}
    if args.update:
        raised = sorted(key for key, size in current.items() if key in budgets and size > budgets[key])
        if raised and not args.allow_raise:
            print(f"FAIL route bytes: --update would raise {', '.join(raised)}. Cut the load, or pass --allow-raise after review.")
            return 1
        args.budgets.write_text(json.dumps(current, indent=1, sort_keys=True) + "\n", encoding="utf-8")
        print(f"Wrote {args.budgets.name} for {len(current)} routes.")
        return 0
    failed = False
    for key, size in current.items():
        if key not in budgets:
            print(f"FAIL route bytes: {key} has no budget. Run --update.")
            failed = True
        elif size > budgets[key]:
            print(f"FAIL route bytes: {key} loads {size} bytes, above its budget of {budgets[key]}. Run --report.")
            failed = True
    if not failed:
        print(f"PASS route bytes: {len(current)} routes within budget.")
    return int(failed)


if __name__ == "__main__":
    sys.exit(main())
