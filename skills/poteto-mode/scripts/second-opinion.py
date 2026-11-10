#!/usr/bin/env python3
"""Ask a configured CLI to rate the five risk facts again, as a check on the lead's own answers.

Off by default. A repository turns it on with a file named `.agents/pstack-second-opinion`
that holds one word, `codex` or `claude`. The call is tool-less, ephemeral, and read-only.
It sends the task summary and the evidence the lead recorded, and asks for one level per fact.

The answer can only raise a fact. Pass the output file to plan.py with --second-opinion.
Each run first removes an earlier answer at --out, so a stale file is never reused.
Any failure prints an `unavailable` result and exits 1, and the table's own route stands.
This call never chooses the route. plan.py does, from the merged facts.

Exit 0: an answer was written. Exit 1: unavailable. Exit 2: usage error. Exit 3: switched off.
"""
import argparse
import json
import os
import signal
import subprocess
import sys
from pathlib import Path

FACTS = ("consequence", "reach", "uncertainty", "complexity", "reversibility")
LEVELS = ("low", "material", "unknown")
SWITCH = Path(".agents") / "pstack-second-opinion"
PROMPT = """You are checking a risk assessment for a code change. Use only the text below. Use no tools.
For each fact, answer `low` only when the evidence shows it. Answer `material` when the evidence shows real risk.
Answer `unknown` when the evidence does not settle it. Unknown context is not low risk.

Facts: consequence (data loss, permissions, incorrect results, compatibility, user-visible disruption),
reach (shared callers, public interfaces, dependencies), uncertainty (unclear requirements, unfamiliar
code, weak tests, contested design), complexity (repeated changes, growing conditionals, recurring repairs),
reversibility (failure visibility, rollback, whether recovery preserves data).

Reply with one JSON object and nothing else, with exactly these keys: consequence, reach, uncertainty,
complexity, reversibility. Each value is "low", "material", or "unknown".

PACKET:
"""


class Unavailable(Exception):
    pass


def capture(argv, prompt, workspace, timeout):
    with subprocess.Popen(argv, cwd=workspace, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          text=True, encoding="utf-8", start_new_session=True) as process:
        try:
            stdout, _ = process.communicate(prompt, timeout=timeout)
            return process.returncode, stdout
        except subprocess.TimeoutExpired as error:
            raise Unavailable("the CLI timed out") from error
        finally:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait()


def command(cli, executable, workspace, timeout):
    """The same restrictions as evals/bot-triage/compare.py: no tools, no MCP, no hooks, no persistence."""
    if cli == "claude":
        return [executable, "-p", "--safe-mode", "--tools", "", "--strict-mcp-config", "--mcp-config", '{"mcpServers":{}}',
                "--no-session-persistence", "--output-format", "json", "--disable-slash-commands", "--no-chrome",
                "--settings", json.dumps({"disableAllHooks": True})]
    code, stdout = capture([executable, "mcp", "list", "--json"], "", workspace, min(30, timeout))
    if code:
        raise Unavailable("cannot list the configured Codex MCP servers")
    servers = json.loads(stdout)
    if not isinstance(servers, list):
        raise Unavailable("the Codex MCP list is not a list")
    disabled = []
    for server in servers:
        if not isinstance(server, dict) or not isinstance(server.get("name"), str) or not server["name"]:
            raise Unavailable("a Codex MCP server has no name")
        settings = "enabled=false"
        transport = server.get("transport")
        if isinstance(transport, dict) and transport.get("type") == "stdio":
            settings += ',command="/usr/bin/false"'
        disabled.append(f"{json.dumps(server['name'])}={{{settings}}}")
    overrides = [
        'approval_policy="never"', 'web_search="disabled"', "project_doc_max_bytes=0", "notify=[]", 'developer_instructions=""',
        "features.shell_tool=false", "features.hooks=false", "features.plugin_hooks=false", "features.plugins=false",
        "features.apps=false", "features.multi_agent=false", "features.multi_agent_v2=false", "features.goals=false",
        "features.memories=false", "features.skip_host_skill_discovery=true", "features.view_image=false",
        "features.image_generation=false", "features.in_app_browser=false", "suppress_unstable_features_warning=true",
        "mcp_servers={" + ",".join(disabled) + "}",
    ]
    return [executable, "exec", "--ephemeral", "--sandbox", "read-only", "--json", "--skip-git-repo-check", "--color", "never",
            *[value for setting in overrides for value in ("-c", setting)], "-"]


def final_text(cli, stdout):
    if cli == "claude":
        record = json.loads(stdout)
        if not isinstance(record, dict) or record.get("is_error") or record.get("type") != "result":
            raise Unavailable("Claude did not return a successful result")
        return record["result"]
    final, completed = None, False
    for line in filter(None, stdout.split("\n")):
        event = json.loads(line)
        if not isinstance(event, dict) or event.get("type") in {"error", "turn.failed"}:
            raise Unavailable("Codex reported a failed turn")
        item = event.get("item")
        if item is not None:
            if not isinstance(item, dict) or item.get("type") not in {"agent_message", "reasoning", "error"}:
                raise Unavailable("Codex ran a tool, so the answer is not a tool-less judgment")
            if event.get("type") == "item.completed" and item.get("type") == "agent_message":
                final = item.get("text")
        completed = completed or event.get("type") == "turn.completed"
    if not completed or not isinstance(final, str):
        raise Unavailable("Codex did not complete with an answer")
    return final


def parse_levels(text):
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`").removeprefix("json").strip()
    answer = json.loads(text)
    if not isinstance(answer, dict) or set(answer) != set(FACTS) or any(answer[name] not in LEVELS for name in FACTS):
        raise Unavailable("the answer is not one level for each of the five facts")
    return answer


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--task", required=True, help="One or two sentences on the change")
    for name in FACTS:
        parser.add_argument(f"--{name}", required=True, metavar="LEVEL[:EVIDENCE]")
    parser.add_argument("--evidence-file", type=Path, help="Output of risk-facts.py to include in the packet")
    parser.add_argument("--project", type=Path, default=Path.cwd())
    parser.add_argument("--executable", help="A trusted CLI path. Default: the CLI's name on PATH")
    parser.add_argument("--timeout", type=float, default=180)
    parser.add_argument("--out", type=Path, required=True, help="Where to write the answer for plan.py")
    args = parser.parse_args(argv)
    args.out.unlink(missing_ok=True)
    switch = args.project / SWITCH
    cli = switch.read_text(encoding="utf-8").strip() if switch.is_file() else ""
    if cli not in ("codex", "claude"):
        print(json.dumps({"status": "off", "reason": f"{SWITCH} does not name codex or claude"}))
        return 3
    packet = {"task": args.task, "recorded": {name: getattr(args, name) for name in FACTS}}
    if args.evidence_file:
        packet["evidence"] = args.evidence_file.read_text(encoding="utf-8")[:20000]
    try:
        argv_cli = command(cli, args.executable or cli, args.project, args.timeout)
        code, stdout = capture(argv_cli, PROMPT + json.dumps(packet, indent=1), args.project, args.timeout)
        if code:
            raise Unavailable(f"the CLI exited {code}")
        levels = parse_levels(final_text(cli, stdout))
    except (Unavailable, OSError, ValueError, KeyError) as error:
        print(json.dumps({"status": "unavailable", "reason": str(error)}))
        return 1
    args.out.write_text(json.dumps({"status": "answered", "cli": cli, "levels": levels}, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({"status": "answered", "cli": cli, "levels": levels}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
