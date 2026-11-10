#!/usr/bin/env python3
"""Record that a gate ran against a tree, and check whether that evidence is still current.

A gate is any named check, such as cleanup, documentation, or scrutiny. `record` stores the
gate's result with the Git tree it examined. `check` compares that tree with the current one
and lists the paths that changed since. Evidence for an unchanged tree stays valid, so the
gate does not repeat. Use it only for a gate whose whole input is the tree. A gate that also
reads a reply, a PR body, or a baseline commit has inputs this record does not hold. Records live under the repository's Git directory and are never committed.

By default the tree is the working tree: tracked changes plus untracked files that Git does
not ignore. Pass --tree <commit-or-tree> to bind to committed content, such as HEAD.

Exit 0: recorded, or the evidence is current. Exit 1: the evidence is missing, stale, or a
recorded failure. Exit 2: usage error, or not a Git repository.
"""
import argparse
import datetime
import json
import os
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path

LOCK_WAIT_SECONDS = 20
LOCK_STALE_SECONDS = 120


class GateError(Exception):
    pass


def git(project, *args, env=None):
    done = subprocess.run(["git", "-C", str(project), *args], capture_output=True, text=True, env=env)
    if done.returncode != 0:
        raise GateError(done.stderr.strip() or f"git {' '.join(args)} failed")
    return done.stdout.strip()


def worktree_tree(project):
    """The tree of tracked and unignored untracked content, built in a scratch index."""
    with tempfile.TemporaryDirectory() as scratch:
        env = {**os.environ, "GIT_INDEX_FILE": str(Path(scratch) / "index")}
        try:
            git(project, "read-tree", "HEAD", env=env)
        except GateError:
            pass
        git(project, "add", "--all", env=env)
        return git(project, "write-tree", env=env)


def resolve_tree(project, treeish):
    return git(project, "rev-parse", f"{treeish}^{{tree}}") if treeish else worktree_tree(project)


def store_path(project):
    return Path(git(project, "rev-parse", "--path-format=absolute", "--git-common-dir")) / "pstack" / "gates.json"


@contextmanager
def locked(path):
    """Hold the store for one read-modify-write. Linked worktrees share the store, so they share the lock."""
    lock = path.with_suffix(".lock")
    lock.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + LOCK_WAIT_SECONDS
    while True:
        try:
            lock.mkdir()
            break
        except FileExistsError:
            try:
                if time.time() - lock.stat().st_mtime > LOCK_STALE_SECONDS:
                    lock.rmdir()
                    continue
            except OSError:
                continue
            if time.monotonic() > deadline:
                raise GateError(f"another gate record holds {lock}. Retry, or remove it if no gate.py is running.")
            time.sleep(0.05)
    try:
        yield
    finally:
        try:
            lock.rmdir()
        except OSError:
            pass


def load(path):
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def record(args):
    path = store_path(args.project)
    tree = resolve_tree(args.project, args.tree)
    with locked(path):
        records = load(path)
        records[args.gate] = {
            "tree": tree,
            "result": args.result,
            "note": args.note or "",
            "recorded_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        }
        scratch = path.with_name(f"{path.name}.{os.getpid()}.tmp")
        scratch.write_text(json.dumps(records, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        scratch.replace(path)
    print(f"recorded {args.gate}: {args.result} at tree {tree}")
    return 0


def check(args):
    entry = load(store_path(args.project)).get(args.gate)
    if entry is None:
        print(f"missing {args.gate}: no evidence recorded. Run the gate, then record it.")
        return 1
    tree = resolve_tree(args.project, args.tree)
    if entry["tree"] != tree:
        changed = git(args.project, "diff", "--name-only", entry["tree"], tree).splitlines()
        print(f"stale {args.gate}: recorded at tree {entry['tree']}, current tree {tree}. Recheck these paths:")
        for name in changed:
            print(f"  {name}")
        return 1
    if entry["result"] != "pass":
        print(f"failed {args.gate}: the recorded result for this tree is {entry['result']}. {entry['note']}".rstrip())
        return 1
    print(f"current {args.gate}: pass at tree {tree}. {entry['note']}".rstrip())
    return 0


def listing(args):
    records = load(store_path(args.project))
    tree = resolve_tree(args.project, args.tree)
    for gate, entry in sorted(records.items()):
        state = "current" if entry["tree"] == tree else "stale"
        print(f"{gate}: {entry['result']} ({state})")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--project", type=Path, default=Path.cwd(), help="Repository to inspect")
    parser.add_argument("--tree", help="Commit or tree to bind to, such as HEAD. Default: the working tree")
    actions = parser.add_subparsers(dest="action", required=True)
    rec = actions.add_parser("record", help="Store a gate result for the tree")
    rec.add_argument("gate")
    rec.add_argument("--result", choices=("pass", "fail"), default="pass")
    rec.add_argument("--note", help="Where the evidence is, or what failed")
    chk = actions.add_parser("check", help="Say whether a gate's evidence still describes the tree")
    chk.add_argument("gate")
    actions.add_parser("list", help="List every recorded gate and whether it is current")
    args = parser.parse_args(argv)
    try:
        return {"record": record, "check": check, "list": listing}[args.action](args)
    except GateError as error:
        print(f"gate.py: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
