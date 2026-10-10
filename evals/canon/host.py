#!/usr/bin/env python3
"""The host runner's entry wrapper. screen.py writes one shell script per
agent that execs

  host.py wrap --agent claude|codex [--workspace] [--token T --discovery D] -- TARGET ARG...

in the harness workspace. It links the mounted skill tree where the agent
finds project skills, starts the prompt with the invocation token, runs the
agent with session persistence back on, and moves the run's own session out of
the agent's store into a numbered slot under $CANON_HARVEST, laid out as the
sbx runner's harvest: transcripts/claude/<project>/<session>.jsonl or
transcripts/codex/sessions/YYYY/MM/DD/rollout-*.jsonl. With --workspace it also
checks out the commit $CANON_WORKSPACE describes before the agent starts and
writes the diff of what the agent changed after, as workspace.py documents.
Under --discovery it also registers the named agents (the personas, plus the
effort agents on Claude Code) as sbx_inside.py setup does, for a workspace run
keeps their files out of the harvest, and for Codex trusts the project with a
-c override, since the harness's --ignore-user-config skips the config file's
trust. For Claude it lists the linked managed pstack skills by name only,
as setup-pstack does for a user's pstack skills.

The harness turns persistence off, with --no-session-persistence for Claude
and --ephemeral for Codex, and removes its isolated CODEX_HOME when the run
ends, so without this wrapper a host run leaves no transcript and entry_state
cannot see the /poteto-mode expansion or the $poteto-mode injection. The
wrapper pins Claude's session id with --session-id and reads Codex's from the
stream's thread.started event, so it moves that one session and no other.

A timed-out run dies with the wrapper, since the harness kills the whole
process group, so collect never runs. The wrapper records the pinned session in the
slot before the agent starts, and screen.py's file_harvest calls recover on
each slot from the parent, which the kill does not reach, to finish the move.
Codex needs no recovery, since its store is the harness's temporary
CODEX_HOME, which the harness removes.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sbx_inside  # noqa: E402
import workspace  # noqa: E402

HARNESS = {agent: row["harness"] for agent, row in json.loads((Path(__file__).resolve().parent / "sbx.json").read_text())["agents"].items()}

PERSISTENCE_OFF = {"claude": "--no-session-persistence", "codex": "--ephemeral"}
# agent: (env var naming its home, default home, store under it, the dirs in
# the store that hold sessions, harvest path)
SESSION_STORES = {
    "claude": ("CLAUDE_CONFIG_DIR", ".claude", "projects", "*", "claude"),
    "codex": ("CODEX_HOME", ".codex", "sessions", "*/*/*", "codex/sessions"),
}


def session_store(agent):
    variable, default, store, _, _ = SESSION_STORES[agent]
    return Path(os.environ.get(variable, Path.home() / default)) / store


def session_dirs(agent, store):
    """The directories of the store that hold session files now: Claude's
    project dirs, Codex's day dirs."""
    return {path for path in store.glob(SESSION_STORES[agent][3]) if path.is_dir()}


def session_files(agent, store, session):
    """The files the agent wrote for one session and the delegates it spawned:
    Claude's transcript and its subagents directory under the project dir, or
    Codex's rollout and every rollout whose first session_meta names a moved
    thread as its parent_thread_id."""
    if agent == "claude":
        return sorted([*store.glob(f"*/{session}.jsonl"), *store.glob(f"*/{session}")])
    rollouts = {path: first_session_meta(path) for path in store.rglob("rollout-*.jsonl")}
    chosen = {path for path in rollouts if path.name.endswith(f"-{session}.jsonl")}
    threads = {session}
    while True:
        children = {path for path, meta in rollouts.items() if path not in chosen and meta.get("parent_thread_id") in threads}
        if not children:
            return sorted(chosen)
        chosen |= children
        threads |= {rollouts[path].get("id") for path in children} - {None}


def first_session_meta(rollout):
    """The payload of a rollout's first session_meta record, which names the
    thread and, for a delegate, its parent."""
    with rollout.open(errors="replace") as handle:
        for line in handle:
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(record, dict) and record.get("type") == "session_meta":
                return record.get("payload") or {}
    return {}


def keep_session(agent, command):
    """command without the harness flag that turns persistence off, and the
    session id the run will have: a fresh uuid Claude is told to use, or None
    for Codex, whose stream names its thread."""
    kept = [arg for arg in command if arg != PERSISTENCE_OFF[agent]]
    if agent == "claude":
        session = str(uuid.uuid4())
        return [*kept, "--session-id", session], session
    return kept, None


def run_agent(command, prompt, stdout=None):
    """Run the agent on prompt, forwarding its stdout line by line, and return
    (its exit code, the thread id a Codex stream announces, or None)."""
    stdout = sys.stdout.buffer if stdout is None else stdout
    thread = None
    with tempfile.TemporaryFile() as stdin:
        stdin.write(prompt)
        stdin.seek(0)
        with subprocess.Popen(command, stdin=stdin, stdout=subprocess.PIPE) as process:
            for line in process.stdout:
                stdout.write(line)
                stdout.flush()
                if thread is None:
                    thread = announced_thread(line)
    return process.returncode, thread


def announced_thread(line):
    try:
        record = json.loads(line)
    except json.JSONDecodeError:
        return None
    return record.get("thread_id") if isinstance(record, dict) and record.get("type") == "thread.started" else None


def collect(agent, session, slot, before):
    """Move the run's own session out of the agent's store into
    slot/transcripts, laid out as the sbx runner's harvest, and record in
    slot/session.json which session it was and what moved. A session dir the
    run made (before holds the store's session dirs from before the agent
    started) goes too once no file is left in it."""
    store = session_store(agent)
    moved = []
    for path in session_files(agent, store, session) if session else ():
        destination = slot / "transcripts" / SESSION_STORES[agent][4] / path.relative_to(store)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(path), str(destination))
        moved.append(destination.relative_to(slot).as_posix())
        if path.parent not in before and path.parent != store and not any(child.is_file() for child in path.parent.rglob("*")):
            shutil.rmtree(path.parent)
    record_session(slot, agent, session, moved)
    return moved


def record_session(slot, agent, session, moved=None):
    """Write slot/session.json: which session the run has, pinned before the
    agent starts, and what moved once collected. A record without transcripts
    marks a wrapper the harness killed before it could collect."""
    record = {"agent": agent, "session": session}
    if moved is not None:
        record["transcripts"] = moved
    (slot / "session.json").write_text(json.dumps(record, indent=2) + "\n")


def recover(slot):
    """Collect a killed wrapper's pinned session from outside it, into the
    slot it pinned. Nothing moves for a slot already collected or never
    pinned, and no store dir is removed, since what existed before the run
    is unknown here."""
    path = slot / "session.json"
    if not path.is_file():
        return []
    record = json.loads(path.read_text())
    if "transcripts" in record:
        return []
    agent = record["agent"]
    return collect(agent, record["session"], slot, session_dirs(agent, session_store(agent)))


def link(root, discovery):
    """Link the mounted skill tree at root/discovery, for a pasted-project case
    whose workspace is not a repo."""
    target = root / discovery
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.is_symlink():
        target.unlink()
    target.symlink_to(os.path.relpath(root / workspace.TREE, target.parent))


def codex_config(command, root, writable, trusted):
    """command with the config Codex needs in its cwd, as -c overrides after
    exec, since the harness's --ignore-user-config skips $CODEX_HOME/config.toml.
    A workspace run (writable) adds root/.git to the workspace-write roots,
    because the sandbox keeps .git read-only inside a writable root, which fails
    `git worktree add` and `git commit` for an agent that delegates. A trusted
    project loads the personas registered under root/.codex/agents."""
    settings = []
    if writable:
        settings.append(f"sandbox_workspace_write.writable_roots={json.dumps([str(root / '.git')])}")
    if trusted:
        settings.append(f"projects={{{json.dumps(str(root))}={{trust_level=\"trusted\"}}}}")
    if "exec" not in command or not settings:
        return command
    at = command.index("exec") + 1
    return [*command[:at], *(arg for setting in settings for arg in ("-c", setting)), *command[at:]]


def wrap(argv, stdin=sys.stdin.buffer, stdout=None):
    split = argv.index("--")
    options, command = argv[:split], argv[split + 1:]
    agent = options[options.index("--agent") + 1]
    token = options[options.index("--token") + 1] if "--token" in options else None
    discovery = options[options.index("--discovery") + 1] if "--discovery" in options else None
    slot = workspace.next_slot(Path(os.environ["CANON_HARVEST"]))
    root = Path.cwd()
    checkout = Checkout(root, slot, agent) if "--workspace" in options else None
    personas = []
    if checkout:
        if not checkout.materialize(discovery):
            return workspace.REFUSED
        personas = checkout.record.get("agents")
    elif discovery:
        link(root, discovery)
        personas = sbx_inside.register_agents(root, {"discovery": discovery, "harness": HARNESS[agent]})
    prompt = stdin.read()
    if token:
        prompt = token.encode() + b" " + prompt
    command, session = keep_session(agent, command)
    if agent == "codex":
        command = codex_config(command, root, bool(checkout), bool(personas))
    elif discovery:
        command = workspace.name_only_settings(command, root / workspace.TREE)
    before = session_dirs(agent, session_store(agent))
    record_session(slot, agent, session)
    code, thread = run_agent(command, prompt, stdout)
    try:
        collect(agent, session or thread, slot, before)
    finally:
        if checkout:
            checkout.harvest(code)
    return code


class Checkout:
    """A workspace case's checkout in the agent's cwd: materialized from the
    arm's workspace.json before the agent runs, its diff harvested after, with
    the record of both in the slot's workspace.json."""

    def __init__(self, root, slot, agent):
        self.root, self.slot, self.agent = root, slot, agent
        self.arm = Path(os.environ["CANON_WORKSPACE"])
        self.spec = json.loads((self.arm / "workspace.json").read_text())
        self.review = workspace.arm_review(self.arm, self.spec)
        self.record = {"expected_tree": self.spec["tree"]}

    def save(self):
        (self.slot / "workspace.json").write_text(json.dumps(self.record, indent=2) + "\n")

    def materialize(self, discovery):
        """True when the checkout has the tree the build recorded, else the
        record names the error and the agent must not start."""
        started = time.monotonic()
        try:
            self.record["tree"] = workspace.materialize(self.root, Path(self.spec["mirror"]), self.spec["commit"],
                                                        workspace.read_files(self.arm / "overlay"), self.review, self.spec.get("history", False))
            if self.record["tree"] != self.spec["tree"]:
                raise workspace.WorkspaceError(f"materialized tree {self.record['tree']} is not the recorded {self.spec['tree']}")
            if self.review:
                self.record["refs"] = workspace.check_refs(self.root, self.spec)
            if discovery:
                workspace.expose(self.root, discovery)
                self.record["agents"] = sbx_inside.register_agents(self.root, {"discovery": discovery, "harness": HARNESS[self.agent]})
                workspace.exclude(self.root, self.record["agents"])
                tree = workspace.snapshot(self.root, "HEAD")
                if tree != self.spec["tree"]:
                    raise workspace.WorkspaceError(f"sandbox tree {tree} is not the recorded {self.spec['tree']}")
        except workspace.WorkspaceError as exc:
            self.record["error"] = str(exc)
            self.save()
            print(f"workspace: {exc}", file=sys.stderr)
            return False
        self.record["materialize_s"] = round(time.monotonic() - started, 2)
        self.save()
        return True

    def harvest(self, agent_rc):
        self.record["agent_rc"] = agent_rc
        started = time.monotonic()
        try:
            diff = workspace.harvest(self.root, self.record["tree"])
            (self.slot / "workspace.diff").write_bytes(diff)
            self.record["diff_bytes"] = len(diff)
        except workspace.WorkspaceError as exc:
            self.record["error"] = f"harvest: {exc}"
        if self.review:
            self.record.update(workspace.head_state(self.root))
        self.record["harvest_s"] = round(time.monotonic() - started, 2)
        self.record["workspace_bytes"] = workspace.disk_bytes(self.root)
        self.save()


def main(argv):
    if argv[:1] == ["wrap"] and "--agent" in argv and "--" in argv:
        return wrap(argv[1:])
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except workspace.WorkspaceError as exc:
        print(f"workspace: {exc}", file=sys.stderr)
        sys.exit(1)
