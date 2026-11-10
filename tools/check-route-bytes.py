#!/usr/bin/env python3
"""Report the instruction bytes each playbook route asks the lead to load, under a budget that only tightens.

A route's load is the files its plan names: the mode entry and its always-read references,
the playbook, the skills its steps load, and the skills its gates run. plan.py supplies the
steps and gates, so this follows the same manifest the lead follows. Counts are UTF-8 source
bytes. They are not provider tokens, and they exclude files a step reads only on a condition.

  check-route-bytes.py            check every route against tools/route-byte-budgets.json
  check-route-bytes.py --report   print each route's bytes and files
  check-route-bytes.py --update   rewrite the budgets to the current bytes

--update refuses to raise a budget unless --allow-raise is passed for a reviewed exception.
Exit 0: every route is within budget. Exit 1: a route is over, or has no budget.
"""
import argparse
import importlib.util
import json
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


def load_plan(root):
    spec = importlib.util.spec_from_file_location("pstack_plan", root / "skills/poteto-mode/scripts/plan.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def route_files(root, plan_module, manifest, playbook, route):
    entry = manifest["playbooks"][playbook]
    levels = {name: None for name in manifest["facts"]}
    if entry.get("tiered"):
        levels = {name: LOW for name in manifest["facts"]} | FACTS[route]
    plan = plan_module.build(plan_module.argparse.Namespace(
        playbook=playbook, user_route=None, raise_to=None, reason=None, second_opinion=None, harness="other", project=root, **levels,
    ), manifest)
    files = list(ALWAYS) + [f"skills/poteto-mode/{entry['file']}"]
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
    return list(dict.fromkeys(files))


def measure(root):
    manifest = json.loads((root / "skills/poteto-mode/routes.json").read_text(encoding="utf-8"))
    plan_module = load_plan(root)
    report = {}
    for playbook, entry in sorted(manifest["playbooks"].items()):
        for route in (manifest["routes"] if entry.get("tiered") else ["standard"]):
            files = route_files(root, plan_module, manifest, playbook, route)
            sizes = {name: len((root / name).read_bytes()) for name in files}
            key = f"{playbook}:{route}" if entry.get("tiered") else playbook
            report[key] = {"bytes": sum(sizes.values()), "files": sizes}
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--budgets", type=Path, default=BUDGETS)
    parser.add_argument("--report", action="store_true")
    parser.add_argument("--update", action="store_true")
    parser.add_argument("--allow-raise", action="store_true")
    args = parser.parse_args(argv)
    report = measure(args.root)
    current = {key: value["bytes"] for key, value in report.items()}
    if args.report:
        for key, value in report.items():
            print(f"{value['bytes']:>7}  {key}  ({len(value['files'])} files)")
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
