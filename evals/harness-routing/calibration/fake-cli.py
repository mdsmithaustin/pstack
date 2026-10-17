#!/usr/bin/env python3
import json
import os
import subprocess
import sys
import time
from pathlib import Path

base = Path(__file__).resolve().parent
args = sys.argv[1:]
if args == ["--version"]:
    print("codex-cli recorded-boundary")
elif args[:2] == ["exec", "--help"]:
    print("--ignore-user-config --ignore-rules --ephemeral --json --sandbox --output-last-message")
elif "features" in args:
    for name in ("apps", "plugins", "multi_agent", "goals", "hooks", "skill_search", "in_app_local_automation"):
        print(name + " stable false")
    print("skip_host_skill_discovery under-development true")
else:
    stdin = sys.stdin.buffer.read()
    with (base / "calls.jsonl").open("a") as target:
        target.write(json.dumps({"argv": args, "cwd": os.getcwd(), "stdin": stdin.decode(), "environment_keys": sorted(os.environ)}) + "\n")
    mode = (base / "mode").read_text().strip() if (base / "mode").exists() else "normal"
    if mode == "failure":
        print("invocation failed", file=sys.stderr)
        raise SystemExit(17)
    if mode == "timeout":
        child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
        (base / "descendant.pid").write_text(str(child.pid))
        print('{"type":"turn.started"}', flush=True)
        print("partial stderr", file=sys.stderr, flush=True)
        time.sleep(120)
    command = "cat skills/pstack-harness/SKILL.md"
    output = Path("skills/pstack-harness/SKILL.md").read_text()
    if mode == "dispatch":
        command, output = "codex exec resume child", ""
    elif mode == "contamination":
        output += "parent-routing-criteria-6f82d1b9"
    records = [
        {"type": "item.completed", "item": {"id": "intro", "type": "agent_message", "text": "I will read the instructions before choosing."}},
        {"type": "item.started", "item": {"id": "read", "type": "command_execution", "command": command, "status": "in_progress"}},
        {"type": "item.completed", "item": {"id": "read", "type": "command_execution", "command": command, "aggregated_output": output, "exit_code": 0, "status": "completed"}},
        {"type": "item.completed", "item": {"id": "answer", "type": "agent_message", "text": "Prepared."}},
        {"type": "turn.completed", "usage": {"input_tokens": 10, "output_tokens": 2}}
    ]
    for record in records:
        print(json.dumps(record))
    Path(args[args.index("--output-last-message") + 1]).write_text("Prepared.\n")
