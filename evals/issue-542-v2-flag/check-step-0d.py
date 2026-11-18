#!/usr/bin/env python3
"""usage: check-step-0d.py <out-dir> <cell> <agents-off|features-off|features-off-flag>

Reads one run-step-0d.sh cell, prints a JSON record, and exits 1 when a check fails."""
import glob
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import summarize

FIRST_OFFER = {"agents-off": r"\[agents\]", "features-off": None, "features-off-flag": r"multi_agent_v2"}


def main(out, cell, kind):
    cell_dir = Path(out) / cell
    base = summarize.main(out, cell)
    rollout = glob.glob(str(cell_dir / "home/sessions/**/*.jsonl"), recursive=True)[0]
    reads = []
    for line in open(rollout):
        payload = json.loads(line)["payload"]
        if payload.get("type") in ("function_call", "custom_tool_call"):
            reads += re.findall(r"[^\s\"']*setup-pstack/SKILL\.md", payload.get("arguments", "") + payload.get("input", ""))
    branch_copy = str(cell_dir / "home/skills/setup-pstack/SKILL.md")
    events = [json.loads(line) for line in open(cell_dir / "exec.jsonl") if line.strip()]
    reply = [e["item"]["text"] for e in events if e["type"] == "item.completed" and e["item"]["type"] == "agent_message"][-1]
    offers = re.split(r"^#+\s*OFFERS\s*$", reply, flags=re.M)[-1]
    items = re.findall(r"^\s*\d+\.\s+(.*)$", offers, re.M)
    first = FIRST_OFFER[kind]
    checks = {
        "no spawn_agent tool in the rollout": base["v2_tool"] is None and not base["deferred"],
        "read the branch copy of setup-pstack": reads.count(branch_copy) >= 1 and all(r == branch_copy for r in reads),
        "offers section has items": bool(items),
        "never offers multi_agent = true": not re.search(r"multi_agent\b(?!_v2)\s*(=\s*true|enable)|enable multi_agent\b(?!_v2)", offers),
        "offers multi_agent_v2": kind == "agents-off" or any("multi_agent_v2" in item for item in items),
    }
    if first:
        checks["first offer matches"] = bool(items) and bool(re.search(first, items[0]))
    return {"cell": cell, "kind": kind, "features": base["features"], "config_toml": base["config_toml"],
            "skill_reads": reads, "offers": items, "reply": reply, "checks": checks}


if __name__ == "__main__":
    record = main(*sys.argv[1:4])
    text = json.dumps(record, indent=2, sort_keys=True)
    print(text.replace(str(Path(sys.argv[1]) / sys.argv[2] / "home"), "$CODEX_HOME").replace(str(Path.home()), "$HOME"))
    sys.exit(0 if all(record["checks"].values()) else 1)
