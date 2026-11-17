#!/usr/bin/env python3
"""Print the matrix table for the extracts named on the command line."""

import json
import sys
from pathlib import Path


def cell(spawns, key):
    values = []
    for s in spawns:
        if s["style"] == "child":
            continue
        value = s[key] if key != "fork" else (f"{s['fork_field']}={json.dumps(s['fork_value'])}" if s["fork_field"] else "unset")
        if value not in values:
            values.append(value)
    return ", ".join(values) or "none"


def line(s):
    ran = "/".join(f"{m}@{e}" for m, e in s["child_contexts"] or [])
    if s["style"] == "child":
        return f"child {s['agent_type']} ran {ran}"
    asked = f"{s['args_model']}@{s['args_effort']}" if s["args_model"] else "no model or effort"
    return f"{s['matches_role'] or s['agent_type']}: asked {asked}" + (f", child ran {ran}" if s["child_contexts"] else "")


def observed(spawns):
    return "; ".join(line(s) for s in spawns) or "none"


def resolved(extract):
    return "; ".join(f"{a['role']} {a['model']}@{a['effort']}" for a in extract["resolved"])


def main(paths):
    print("| Row | Lead | `multi_agent_v2` flag | Spawns | Fork field and value | Agent types | Resolved (fixture config) | Observed per spawn | Result |")
    print("|---|---|---|---|---|---|---|---|---|")
    for path in paths:
        e = json.loads(Path(path).read_text())
        s = e["spawns"]
        lead = "/".join(f"{m}@{x}" for m, x in e["lead_contexts"])
        print(f"| {e['row']} | {lead} | {'on' if e['v2_flag'] else 'off'} | {len(s)} | {cell(s, 'fork')} | {cell(s, 'agent_type')} "
              f"| {resolved(e)} | {observed(s)} | {e['verdict']} |")


if __name__ == "__main__":
    main(sys.argv[1:])
