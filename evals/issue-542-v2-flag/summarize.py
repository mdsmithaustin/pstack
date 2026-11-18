#!/usr/bin/env python3
"""usage: summarize.py <out-dir> <cell> > <cell>.json"""
import glob
import json
import re
import sys
from pathlib import Path


def tools(items, namespace=""):
    for item in items:
        if item.get("type") == "namespace":
            yield from tools(item["tools"], item["name"])
        else:
            yield namespace, item


def top_level_keys(text):
    text = re.sub(r'"(?:[^"\\]|\\.)*"|\'(?:[^\'\\]|\\.)*\'|`(?:[^`\\]|\\.)*`', '""', text)
    keys, depth, token = [], 0, ""
    for ch in text:
        if ch in "{[(":
            depth += 1
        elif ch in "}])":
            depth -= 1
        if depth == 1 and (ch.isalnum() or ch == "_"):
            token += ch
        else:
            if depth == 1 and ch in ":?" and token:
                keys.append(token)
            token = ""
    return keys


def object_after(text, marker):
    start = text.find(marker)
    if start < 0:
        return None
    start = text.index("{", start)
    depth = 0
    for i in range(start, len(text)):
        depth += {"{": 1, "}": -1}.get(text[i], 0)
        if depth == 0:
            return text[start : i + 1]
    return None


def main(out, cell):
    cell_dir = Path(out) / cell
    root, children = None, []
    for path in sorted(glob.glob(str(cell_dir / "home/sessions/**/*.jsonl"), recursive=True)):
        records = [json.loads(line) for line in open(path)]
        source = records[0]["payload"]["source"]
        if isinstance(source, dict) and "subagent" in source:
            children.append((source["subagent"]["thread_spawn"], records))
        else:
            root = records
    if root is None:
        return {"cell": cell, "error": "no root rollout"}

    v2_tool, deferred, v1_params, calls = None, [], None, []
    for record in root:
        payload = record["payload"]
        kind = payload.get("type")
        if kind == "additional_tools":
            for namespace, tool in tools(payload["tools"]):
                if tool.get("name") == "spawn_agent":
                    schema = tool.get("parameters", {})
                    v2_tool = {
                        "namespace": namespace,
                        "parameters": sorted(schema.get("properties", {})),
                        "required": sorted(schema.get("required", [])),
                    }
        elif kind == "message" and payload.get("role") == "developer":
            for part in payload.get("content", []):
                deferred += re.findall(r"^- (multi_agent\w*): ", part.get("text", ""), re.M)
        elif kind == "function_call" and payload.get("name") == "spawn_agent":
            args = json.loads(payload["arguments"])
            args.pop("message", None)
            calls.append({"path": "function_call", **args})
        elif kind == "custom_tool_call":
            for match in re.finditer(r"tools\.(\w*spawn_agent)\(", payload.get("input", "")):
                literal = object_after(payload["input"][match.start():], "(")
                if literal:
                    calls.append({"path": "exec:" + match.group(1), "keys": sorted(set(top_level_keys(literal)) - {"message"})})
        elif kind == "custom_tool_call_output":
            for part in payload.get("output", []) if isinstance(payload.get("output"), list) else []:
                text = part.get("text", "").replace("\\n", "\n").replace('\\"', '"')
                literal = object_after(text, "multi_agent_v1__spawn_agent(args:")
                if literal:
                    v1_params = sorted(set(top_level_keys(literal)))

    contexts = [r["payload"] for r in root if r["type"] == "turn_context"]
    child_runs = []
    for spawn, records in children:
        own = [r["payload"] for r in records if r["type"] == "turn_context"][-1]
        child_runs.append({"agent_path": spawn["agent_path"], "model": own["model"], "effort": own["effort"]})

    exec_lines = [json.loads(line) for line in open(cell_dir / "exec.jsonl") if line.strip()]
    last_reply = [e["item"]["text"] for e in exec_lines if e["type"] == "item.completed" and e["item"]["type"] == "agent_message"][-1:]
    features = {}
    for line in (cell_dir / "features.txt").read_text().splitlines():
        parts = line.split()
        if parts and parts[0] in ("multi_agent", "multi_agent_v2"):
            features[parts[0]] = parts[-1]
    return {
        "cell": cell,
        "root_model": contexts[0]["model"],
        "root_effort": contexts[0]["effort"],
        "features": features,
        "config_toml": (cell_dir / "config.toml").read_text(),
        "v2_tool": v2_tool,
        "deferred": sorted(set(deferred)),
        "v1_tool_params": v1_params,
        "spawn_calls": calls,
        "children": child_runs,
        "child_answer_reached_root": bool(last_reply) and last_reply[0].strip().endswith("PONG"),
    }


if __name__ == "__main__":
    print(json.dumps(main(sys.argv[1], sys.argv[2]), indent=2, sort_keys=True))
