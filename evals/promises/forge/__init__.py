"""Provision an offline GitHub forge inside a live case's project, under .git/forge/."""

import json
import shlex
import shutil
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _ids(state):
    for pr in state["prs"]:
        for item in pr["reviews"] + pr["comments"]:
            yield item["id"]
        for thread in pr["threads"]:
            for comment in thread["comments"]:
                yield comment["id"]


def _pr(raw, user, head_oid, base_oid, created):
    pr = {"title": "", "body": "", "base": "main", "author": user, "draft": False, "state": "OPEN", "labels": [],
          "reviewRequests": [], "checks": [], "reviews": [], "threads": [], "comments": [], "createdAt": created,
          "mergedAt": None, "closedAt": None, "mergeCommit": None, "autoMergeRequest": None, **raw}
    pr["headRefOid"], pr["baseRefOid"] = head_oid, base_oid
    for review in pr["reviews"]:
        review.setdefault("submittedAt", created)
        if review.get("commit") == "head":
            review["commit"] = head_oid
    for thread in pr["threads"]:
        thread.setdefault("isResolved", False)
        thread.setdefault("isOutdated", False)
        for comment in thread["comments"]:
            comment.setdefault("createdAt", created)
    for comment in pr["comments"]:
        comment.setdefault("createdAt", created)
    return pr


def provision(project: Path, spec: dict, spec_dir: Path, run_git) -> None:
    forge = project / ".git" / "forge"
    (forge / "bin").mkdir(parents=True)
    (forge / "ci").mkdir()
    for source, name in (("gh", "gh"), ("forge-ssh", "forge-ssh"), ("forge-ssh", "ssh")):
        shutil.copy(HERE / source, forge / "bin" / name)
        (forge / "bin" / name).chmod(0o755)
    run_git(forge, "init", "-q", "--bare", "-b", "main", "remote.git")
    user = spec.get("user", "dev")
    state = {"repo": spec["repo"], "user": user, "protected": [], "ci": spec.get("ci"), "next_number": 1,
             "next_id": 1000, "next_run_id": 18000000001, "prs": [], "issues": [], "runs": {}}
    state_path = forge / "state.json"
    state_path.write_text(json.dumps(state, indent=1), encoding="utf-8")

    run_git(project, "remote", "add", "origin", f"git@github.com:{spec['repo']}.git")
    run_git(project, "config", "core.sshCommand", shlex.quote(str(forge / "bin" / "forge-ssh")))
    run_git(project, "config", "ssh.variant", "simple")
    if spec.get("push"):
        run_git(project, "push", "-q", "-u", "origin", *spec["push"])
        if "main" in spec["push"]:
            run_git(project, "remote", "set-head", "origin", "main")
    hook = forge / "remote.git" / "hooks" / "pre-receive"
    shutil.copy(HERE / "pre-receive", hook)
    hook.chmod(0o755)

    def tip(branch):
        return run_git(forge / "remote.git", "rev-parse", "--verify", f"refs/heads/{branch}",
                       capture_output=True, text=True).stdout.strip()

    state["protected"] = list(spec.get("protected", []))
    if spec.get("state"):
        canned = json.loads((spec_dir / spec["state"]).read_text(encoding="utf-8"))
        created = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        state["prs"] = [_pr(raw, user, tip(raw["head"]), tip(raw.get("base", "main")), created)
                        for raw in canned.get("prs", [])]
        numbers = [pr["number"] for pr in state["prs"]]
        state["next_number"] = max([canned.get("next_number", 1), *(n + 1 for n in numbers)])
        state["next_id"] = max([state["next_id"], *(int(i) + 1 for i in _ids(state))])
    state_path.write_text(json.dumps(state, indent=1), encoding="utf-8")
    (forge / "calls.jsonl").write_text("", encoding="utf-8")
    (forge / "pushes.jsonl").write_text("", encoding="utf-8")
