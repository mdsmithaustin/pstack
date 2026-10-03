"""Run guide-promise cases on a real harness, then grade the harvested trace."""

import argparse
import fcntl
import importlib
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tarfile
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
CASES = HERE / "cases"
FIXTURES = HERE / "fixtures"
HISTORIES = HERE / "histories"
WORKSPACE = "w"
ENTRY_PREFIX = re.compile(r"^/([a-z][a-z0-9-]*)\s*(.*)$", re.S)
HARNESSES = {
    "claude-code": "harnesses.claude_code",
    "codex": "harnesses.codex",
    "hermes": "harnesses.hermes",
    "grok": "harnesses.grok",
}
MEANINGS = ("eval", "evals", "evaluation", "judge", "experiment", "rubric", "score", "compare",
            "benchmark", "candidate", "arena", "promise", "promises", "oracle", "verdict")


@dataclass
class Run:
    root: Path
    harness: str
    case: dict
    skills_at: str
    timeout_s: int
    turns: list = field(default_factory=list)
    baseline: list = field(default_factory=list)

    @property
    def project(self):
        return self.root / WORKSPACE / self.case["fixture"]


def adapter(name):
    sys.path.insert(0, str(HERE))
    return importlib.import_module(HARNESSES[name])


def load_case(case_id):
    case = json.loads((CASES / case_id / "case.json").read_text(encoding="utf-8"))
    case["id"] = case_id
    return case


CHAT_ITEM = re.compile(r"^\s*(?:(?:\d+[.)]|[-*])\s+(.*)|(\[[ xX~>-]\]\s+.*))$")
CHAT_STATE_WORDS = {"completed": "completed", "complete": "completed", "done": "completed", "in progress": "in progress",
                    "in_progress": "in progress", "in-progress": "in progress", "pending": "pending", "not started": "pending"}
CHAT_MARKS = {"[x]": "completed", "[X]": "completed", "✅": "completed", "[~]": "in progress", "[>]": "in progress",
              "⏳": "in progress", "🔄": "in progress", "[ ]": "pending", "[-]": "skipped: marked"}
CHAT_EDGE_WORD = re.compile(r"^[\s*_(\[]*(completed?|done|in[ _-]progress|pending|not started)\b[\s*_)\]]*[.:,-]?"
                            r"|[\s(*_\[-]+(completed?|done|in[ _-]progress|pending|not started)[\s*_)\].]*$", re.I)
CHAT_SKIP = re.compile(r"\bskipped\b:?\s*(.*)", re.I)


def chat_state(body):
    for mark, state in CHAT_MARKS.items():
        if body.startswith(mark):
            return state
    skip = CHAT_SKIP.search(body)
    if skip:
        return f"skipped: {skip.group(1).strip().strip('*_').strip()}"
    if body.startswith("⏭"):
        return f"skipped: {body.lstrip('⏭️ ').strip()}"
    edge = CHAT_EDGE_WORD.search(body)
    if edge:
        return CHAT_STATE_WORDS[(edge.group(1) or edge.group(2)).lower()]
    return None


def chat_worklist(text):
    items = []
    for line in text.splitlines():
        match = CHAT_ITEM.match(line)
        if match:
            body = (match.group(1) or match.group(2)).strip()
            items.append({"text": body, "state": chat_state(body)})
    marked = sum(1 for i in items if i["state"])
    if len(items) < 2 or marked < max(2, (len(items) + 1) // 2):
        return None
    return [{**i, "state": i["state"] or "pending"} for i in items]


def timeout_for(case, harness):
    limits = case.get("timeout_s", 1800)
    if isinstance(limits, int):
        return limits
    return limits.get(harness, limits.get("default", 1800))


def execute(argv, cwd, env, timeout_s, stdout, stderr, stdin=None):
    started = time.monotonic()
    with open(stdout, "wb") as out, open(stderr, "wb") as err:
        proc = subprocess.Popen([str(a) for a in argv], cwd=cwd, env=env, stdout=out, stderr=err,
                                stdin=subprocess.DEVNULL if stdin is None else stdin, start_new_session=True)
        try:
            code, timed_out = proc.wait(timeout=timeout_s), False
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)
            code, timed_out = proc.wait(), True
    return {"argv": [str(a) for a in argv], "exit_code": code, "timed_out": timed_out,
            "duration_s": round(time.monotonic() - started, 1)}


def install_tree(ref, dest):
    dest.mkdir(parents=True, exist_ok=True)
    archive = subprocess.run(["git", "-C", str(ROOT), "archive", "--format=tar", ref, "skills"],
                             check=True, capture_output=True).stdout
    with tempfile.TemporaryFile() as tmp:
        tmp.write(archive)
        tmp.seek(0)
        with tarfile.open(fileobj=tmp) as tar:
            for member in tar.getmembers():
                member.name = member.name.split("/", 1)[1] if "/" in member.name else ""
            tar.extractall(dest, members=[m for m in tar.getmembers() if m.name], filter="tar")


GIT_ISOLATION = {"GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}
GIT_IDENTITY = ["-c", "user.name=dev", "-c", "user.email=dev@example.com", "-c", "commit.gpgsign=false", "-c", "core.hooksPath=/dev/null"]


def git_run(dest, *args, **kwargs):
    return subprocess.run(["git", "-C", str(dest), *GIT_IDENTITY, *args], check=True,
                          env={**os.environ, **GIT_ISOLATION}, **kwargs)


def make_project(case, dest):
    shutil.copytree(FIXTURES / case["fixture"], dest, copy_function=shutil.copy)
    git_run(dest, "init", "-q", "-b", "main")
    git_run(dest, "add", "-A")
    git_run(dest, "commit", "-qm", case.get("commit_message", "initial import"))
    for step in history_steps(case):
        if step.get("branch"):
            exists = subprocess.run(["git", "-C", str(dest), "rev-parse", "--verify", "--quiet", f"refs/heads/{step['branch']}"],
                                    capture_output=True).returncode == 0
            git_run(dest, "checkout", "-q", *([] if exists else ["-b"]), step["branch"])
        shutil.copytree(step["path"], dest, dirs_exist_ok=True, copy_function=shutil.copy)
        for rel in step.get("delete", []):
            (dest / rel).unlink()
        if step.get("commit", True):
            git_run(dest, "add", "-A")
            git_run(dest, "commit", "-q", "--allow-empty", "-F", "-", input=step["message"], text=True)


def baseline(project):
    """Every commit make_project wrote, root first and the checked-out head last, recorded before any turn so an agent's amend or rebase cannot move them."""
    head = git_run(project, "rev-parse", "HEAD", capture_output=True, text=True).stdout.strip()
    commits = git_run(project, "rev-list", "--reverse", "--topo-order", "--branches", capture_output=True, text=True).stdout.split()
    return [c for c in commits if c != head] + [head]


def history_steps(case):
    name = case.get("history")
    if not name:
        return []
    folder = HISTORIES / name
    spec = json.loads((folder / "steps.json").read_text(encoding="utf-8"))
    if spec.get("fixture") != case["fixture"]:
        raise ValueError(f"history {name} is for fixture {spec.get('fixture')}, case uses {case['fixture']}")
    return [{**step, "path": folder / step["dir"]} for step in spec["steps"]]


def split_entry(case, text, index):
    if index == 0 and case.get("entry"):
        return case["entry"], text
    match = ENTRY_PREFIX.match(text)
    if match and (ROOT / "skills" / match.group(1) / "SKILL.md").is_file():
        return match.group(1), match.group(2)
    return None, text


def fixture_lock(fixture):
    """Agents write literal /tmp paths named after the project, so one fixture runs once at a time per host."""
    handle = open(Path(tempfile.gettempdir()) / f"pstack-live-{fixture}.lock", "w")
    fcntl.flock(handle, fcntl.LOCK_EX)
    return handle


def run_case(harness, case_id, skills_at, out, index):
    case = load_case(case_id)
    if case.get("deferred") or case.get("kind", "live") != "live":
        raise SystemExit(f"{case_id} does not run live: kind {case.get('kind', 'live')}, deferred {case.get('deferred')}")
    module = adapter(harness)
    root = Path(tempfile.mkdtemp(prefix=f"{case['fixture']}-", dir=out)).resolve()
    commit = subprocess.run(["git", "-C", str(ROOT), "rev-parse", skills_at],
                            check=True, capture_output=True, text=True).stdout.strip()
    run = Run(root, harness, case, commit, timeout_for(case, harness))
    run.project.parent.mkdir(parents=True)
    make_project(case, run.project)
    run.baseline = baseline(run.project)
    install_tree(run.skills_at, run.project / module.SKILLS_DIR)
    exclude = run.project / ".git" / "info" / "exclude"
    exclude.write_text(exclude.read_text() + "".join(f"{d}\n" for d in module.PRIVATE_DIRS))
    module.prepare(run)
    lock = fixture_lock(case["fixture"]) if module.SHARES_HOST_TMP and case.get("tmp_lock", True) else None
    try:
        for i, text in enumerate(case["turns"]):
            record = module.turn(run, text, i)
            run.turns.append(record)
            (root / "run.json").write_text(json.dumps(meta(run), indent=1) + "\n")
    finally:
        if lock:
            lock.close()
    trace = module.harvest(run)
    (root / "trace.json").write_text(json.dumps(trace, indent=1) + "\n")
    verdict = grade(root)
    print(json.dumps({"run": str(root), "case": case_id, "harness": harness, "n": index,
                      "verdicts": {p: v["verdict"] for p, v in verdict["promises"].items()}}))
    return root


def meta(run):
    return {"harness": run.harness, "case": run.case["id"], "skills_at": run.skills_at, "project": str(run.project),
            "timeout_s": run.timeout_s, "turns": run.turns, "baseline": run.baseline}


def grade(root):
    import oracles
    root = Path(root)
    record = json.loads((root / "run.json").read_text())
    case = load_case(record["case"])
    trace = json.loads((root / "trace.json").read_text())
    trace.setdefault("x_turns", record.get("turns", []))
    trace.setdefault("x_baseline", record.get("baseline"))
    verdict = {"case": case["id"], "harness": record["harness"], "skills_at": record["skills_at"],
               "promises": {pid: oracles.check(pid, trace, case, Path(record.get("project", root / "project")))
                            for pid in case["promises"]}}
    (root / "verdict.json").write_text(json.dumps(verdict, indent=1) + "\n")
    return verdict


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--harness", required=True, choices=sorted(HARNESSES))
    r.add_argument("--case", required=True, action="append")
    r.add_argument("--runs", type=int, default=1)
    r.add_argument("--skills-at", default="HEAD")
    r.add_argument("--out", default=str(Path(tempfile.gettempdir()) / "pstack-live"))
    g = sub.add_parser("grade")
    g.add_argument("runs", nargs="+")
    p = sub.add_parser("report")
    p.add_argument("out")
    p.add_argument("--upstream")
    p.add_argument("--upstream-ref")
    args = parser.parse_args(argv)
    if args.cmd == "run":
        out = Path(args.out)
        out.mkdir(parents=True, exist_ok=True)
        for case_id in args.case:
            for n in range(args.runs):
                run_case(args.harness, case_id, args.skills_at, out, n)
        return 0
    if args.cmd == "grade":
        for root in args.runs:
            print(json.dumps(grade(root)))
        return 0
    import ledger
    import report
    with ledger.upstream_tree(args.upstream, args.upstream_ref) as upstream:
        print(report.render(Path(args.out), upstream))
    return 0


if __name__ == "__main__":
    sys.exit(main())
