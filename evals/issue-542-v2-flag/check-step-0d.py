#!/usr/bin/env python3
"""usage: check-step-0d.py <out-dir> <cell> <agents-off|features-off|features-off-flag|v1-default|v2-disabled|dotted|dotted-edit>

Reads one run-step-0d.sh cell, prints a JSON record, and exits 1 when a check fails."""
import glob
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import summarize

KINDS = ("agents-off", "features-off", "features-off-flag", "v1-default", "v2-disabled", "dotted", "dotted-edit")
ENABLE = "codex features enable multi_agent_v2"


def blob_sha(path):
    data = Path(path).read_bytes()
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def inside(path, cell_dir):
    resolved = Path(path).resolve()
    return str(resolved.relative_to(cell_dir)) if resolved.is_relative_to(cell_dir) else "outside the cell"


def is_root(rollout):
    source = json.loads(open(rollout).readline())["payload"]["source"]
    return not (isinstance(source, dict) and "subagent" in source)


def features_row(config_text, command=None):
    with tempfile.TemporaryDirectory() as scratch:
        config = Path(scratch) / "config.toml"
        config.write_text(config_text)
        env = {**os.environ, "CODEX_HOME": scratch, "HOME": scratch}
        if command:
            subprocess.run(command.split(), env=env, capture_output=True, timeout=120)
        listing = subprocess.run(["codex", "features", "list"], env=env, capture_output=True, text=True, timeout=120)
        row = next((line.split()[-1] for line in listing.stdout.splitlines() if line.split()[:1] == ["multi_agent_v2"]), None)
        return listing.returncode, row, config.read_text()


def keeps(proposed, original):
    if isinstance(original, dict):
        return isinstance(proposed, dict) and all(k in proposed and keeps(proposed[k], v) for k, v in original.items())
    return proposed == original


def grade(form, config_text, start, command=None):
    exit_code, row, final_text = features_row(config_text, command)
    try:
        kept = keeps(tomllib.loads(final_text), start)
    except tomllib.TOMLDecodeError:
        kept = False
    return {"form": form, "loads": exit_code == 0, "multi_agent_v2": row, "keeps_starting_keys": kept}


def proposals(start_text, offers, proposed_text):
    start = tomllib.loads(start_text)
    graded = [grade("file", block, start) for block in re.findall(r"```(?:toml)?\n(.*?)```", proposed_text, flags=re.S)
              if block.strip() != ENABLE]
    if ENABLE in offers + proposed_text:
        graded.append(grade("command", start_text, start, ENABLE))
    return graded


def main(out, cell, kind):
    cell_dir = Path(out).resolve() / cell
    base = summarize.main(out, cell)
    rollouts = glob.glob(str(cell_dir / "home/sessions/**/*.jsonl"), recursive=True)
    rollout = next(r for r in rollouts if is_root(r))
    reads, ran_version, calls_text = [], False, ""
    for line in open(rollout):
        payload = json.loads(line)["payload"]
        if payload.get("type") in ("function_call", "custom_tool_call"):
            call = payload.get("arguments", "") + payload.get("input", "")
            calls_text += call
            reads += re.findall(r"[^\s\"']*setup-pstack/SKILL\.md", call)
            ran_version = ran_version or "codex --version" in call
    skill = cell_dir / "home/skills/setup-pstack/SKILL.md"
    private_env = dict(line.split("=", 1) for line in (cell_dir / "env.txt").read_text().splitlines())
    real_codex = str(Path.home().resolve() / ".codex")
    events = [json.loads(line) for line in open(cell_dir / "exec.jsonl") if line.strip()]
    reply = [e["item"]["text"] for e in events if e["type"] == "item.completed" and e["item"]["type"] == "agent_message"][-1]
    offers, *rest = re.split(r"^[#*\s]*PROPOSED\b.*$", re.split(r"^[#*\s]*OFFERS[*:\s]*$", reply, flags=re.M)[-1], flags=re.M)
    proposed_text = rest[-1] if rest else ""
    lines = [line.strip() for line in offers.splitlines() if line.strip()]
    marked = [re.sub(r"^(?:\d+\.|[-*])\s+", "", line) for line in lines if re.match(r"(?:\d+\.|[-*])\s", line)]
    no_offers = [line.lower().strip(" .`*") for line in lines] == ["none"]
    items = [] if no_offers else marked or lines
    dotted = kind in ("dotted", "dotted-edit")
    v1 = dotted or kind in ("v1-default", "v2-disabled")
    checks = {
        "spawn_agent tool as the kind expects": (base["v2_tool"] is None and base["deferred"] == ["multi_agent_v1"]) if v1
        else (base["v2_tool"] is None and not base["deferred"]),
        "read the branch copy of setup-pstack": bool(reads) and all(Path(r).resolve() == skill for r in reads),
        "HOME and CODEX_HOME are private to the cell": Path(private_env["HOME"]).resolve().is_relative_to(cell_dir) and Path(private_env["CODEX_HOME"]).resolve() == cell_dir / "home",
        "never read the host ~/.codex": real_codex not in calls_text,
        "ran codex --version": ran_version,
        "never offers multi_agent = true": not re.search(r"multi_agent\b(?!_v2)\s*(=\s*true|enable)|enable multi_agent\b(?!_v2)", offers),
    }
    if kind in ("agents-off", "features-off"):
        checks["first offer is the agents line"] = bool(items) and bool(re.search(r"\[agents\]", items[0]))
        checks["names multi_agent_v2 as the override alternative"] = len(items) > 1 and "multi_agent_v2" in " ".join(items[1:]) and bool(re.search(r"overr(?:id|ode)", reply, re.I))
    elif kind == "features-off-flag":
        checks["offers none"] = no_offers
    else:
        if dotted:
            checks["offers multi_agent_v2"] = "multi_agent_v2" in offers
        else:
            checks["only offer is multi_agent_v2"] = len(items) == 1 and "multi_agent_v2" in items[0]
        checks["says it is optional"] = bool(re.search(r"optional|not (a )?repair|nothing (needs|to) repair|no (config )?repair (is )?(needed|required)|repairs nothing", reply, re.I))
    graded = []
    if dotted:
        checks["does not claim an explicit disable"] = not re.search(r"\b(?:overrides?|overriding|explicit\s+disable)\b", offers, re.I)
        graded = proposals((cell_dir / "config.toml").read_text(), offers, proposed_text)
        checks["proposes an edit"] = bool(graded)
        checks["every proposed file and command loads"] = all(g["loads"] for g in graded)
        checks["every proposal turns multi_agent_v2 on"] = all(g["multi_agent_v2"] == "true" for g in graded)
        checks["every proposal keeps the starting keys"] = all(g["keeps_starting_keys"] for g in graded)
    if kind == "dotted-edit":
        checks["names the config file path"] = bool(re.search(r"[^\s`\"']+/config\.toml\b", offers))
        checks["proposes the file edit"] = any(g["form"] == "file" for g in graded)
    if kind == "v2-disabled":
        offer = " ".join(items)
        checks["says the offer overrides the disable"] = bool(re.search(r"overr(?:id|ode)", offer, re.I))
        checks["edits the existing table in place, or uses the command"] = bool(
            re.search(r"enabled\s*=\s*true", offer) or re.search(r"codex features enable multi_agent_v2", offer))
        checks["adds no second multi_agent_v2 key"] = not re.search(r"multi_agent_v2\s*=\s*true", offer)
    return {"cell": cell, "kind": kind, "codex_version": (cell_dir / "version.txt").read_text().strip(),
            "skill_blob": blob_sha(skill),
            "isolation": {name: inside(private_env[name], cell_dir) for name in ("HOME", "CODEX_HOME")},
            "features": base["features"], "config_toml": base["config_toml"],
            "root_model": base["root_model"], "skill_reads": reads, "offers": items, "proposals": graded, "reply": reply, "checks": checks}


if __name__ == "__main__":
    if len(sys.argv) != 4 or sys.argv[3] not in KINDS:
        sys.exit(__doc__)
    record = main(*sys.argv[1:4])
    text = json.dumps(record, indent=2, sort_keys=True)
    cell_home = Path(sys.argv[1]).resolve() / sys.argv[2] / "home"
    for known in (str(cell_home), str(Path(sys.argv[1]).absolute() / sys.argv[2] / "home")):
        text = text.replace(known, "$CODEX_HOME")
    text = re.sub(r"(?:[^\s`\"']*/)?\.\.\./home\b", "$CODEX_HOME", text)
    print(text.replace(str(Path.home().resolve()), "$HOME").replace(str(Path.home()), "$HOME"))
    sys.exit(0 if all(record["checks"].values()) else 1)
