"""Regenerate arms/playbook.patch and arms/skill.patch from arms/text/.

Usage: python3 make_arms.py

Each patch is a git diff against skills/ as rule.json's skills_at holds it,
with paths relative to skills/ (a/<skill>/...). The playbook arm adds
poteto-mode/playbooks/premortem.md and one router line after the Prototype
entry in poteto-mode/SKILL.md. The skill arm adds premortem/SKILL.md. Both
bodies come from arms/text/body.md, substituted for <body.md> in the wrappers.
"""
import json
import subprocess
import tempfile
from pathlib import Path

RULE = Path(__file__).resolve().parent
TEXT = RULE / "arms" / "text"
REPO = RULE.parents[3]
ANCHOR = "- **Prototype.**"


def git(*args, cwd):
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout


def with_body(name):
    return (TEXT / name).read_text(encoding="utf-8").replace("<body.md>\n", (TEXT / "body.md").read_text(encoding="utf-8"))


def routed(skill_md):
    lines = skill_md.split("\n")
    anchors = [index for index, line in enumerate(lines) if line.startswith(ANCHOR)]
    if len(anchors) != 1:
        raise SystemExit(f"expected one {ANCHOR!r} line in poteto-mode/SKILL.md, found {len(anchors)}")
    lines.insert(anchors[0] + 1, (TEXT / "router.md").read_text(encoding="utf-8").rstrip("\n"))
    return "\n".join(lines)


def write_patch(tree, name, files):
    git("checkout", "--", ".", cwd=tree)
    git("clean", "-fdq", cwd=tree)
    for path, body in files.items():
        (tree / path).parent.mkdir(parents=True, exist_ok=True)
        (tree / path).write_text(body, encoding="utf-8")
    git("add", "-A", cwd=tree)
    patch = git("diff", "--cached", "--no-color", "--no-ext-diff", cwd=tree)
    (RULE / "arms" / f"{name}.patch").write_text(patch, encoding="utf-8")
    git("reset", "-q", cwd=tree)
    print(f"arms/{name}.patch: {sorted(files)}")


def main():
    commit = json.loads((RULE / "rule.json").read_text())["skills_at"]
    with tempfile.TemporaryDirectory() as scratch:
        tree = Path(scratch)
        archive = subprocess.run(["git", "archive", commit, "skills"], cwd=REPO, check=True, capture_output=True).stdout
        subprocess.run(["tar", "-x", "--strip-components=1", "-C", scratch], input=archive, check=True)
        git("init", "-q", cwd=tree)
        git("add", "-A", cwd=tree)
        git("-c", "user.name=canon", "-c", "user.email=canon@example.com", "commit", "-qm", "skills", cwd=tree)
        skill_md = (tree / "poteto-mode" / "SKILL.md").read_text(encoding="utf-8")
        write_patch(tree, "playbook", {
            "poteto-mode/playbooks/premortem.md": with_body("playbook.md"),
            "poteto-mode/SKILL.md": routed(skill_md),
        })
        write_patch(tree, "skill", {"premortem/SKILL.md": with_body("skill.md")})


if __name__ == "__main__":
    main()
