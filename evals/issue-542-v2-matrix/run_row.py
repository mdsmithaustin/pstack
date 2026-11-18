#!/usr/bin/env python3
"""Run one row of the multi_agent_v2 spawn matrix in a private CODEX_HOME.

    run_row.py ROW --root DIR [--timeout SECONDS]

DIR is a fresh directory. The run builds the `shop` fixture and installs this checkout's skills into it, so the user's
`~/.codex` config is never read or written. Only `auth.json` is copied from the user's login.
"""

import argparse
import contextlib
import json
import os
import shutil
import signal
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

import fixture

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
ROWS = json.loads((HERE / "rows.json").read_text())
LEAD_MODEL = "gpt-6.1-sol"
LEAD_EFFORT = "high"
CLEANUP_SIGNALS = (signal.SIGINT, signal.SIGTERM, signal.SIGHUP, signal.SIGQUIT)
ENV_KEPT = ("PATH", "LANG", "LC_ALL", "LC_CTYPE", "TERM", "USER", "LOGNAME", "SHELL", "TZ", "SSL_CERT_FILE",
            "SSL_CERT_DIR", "HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY", "http_proxy", "https_proxy", "no_proxy")


def install_skills(dest):
    archive = subprocess.run(["git", "-C", str(REPO), "archive", "--format=tar", "HEAD", "skills"],
                             check=True, capture_output=True).stdout
    with tempfile.TemporaryFile() as tmp:
        tmp.write(archive)
        tmp.seek(0)
        with tarfile.open(fileobj=tmp) as tar:
            members = [m for m in tar.getmembers() if "/" in m.name]
            for member in members:
                member.name = member.name.split("/", 1)[1]
            dest.mkdir(parents=True, exist_ok=True)
            tar.extractall(dest, members=members, filter="tar")


def prepare(root):
    for name in ("home", "codex-home", "tmp", "transcripts"):
        (root / name).mkdir(exist_ok=True)
    project = root / "project"
    fixture.build(project)
    install_skills(project / ".agents" / "skills")
    shutil.copy(HERE / "models.md", project / ".agents" / "pstack-models.md")
    script = project / ".agents" / "skills" / "pstack-harness" / "scripts" / "subagents.py"
    installed = subprocess.run([sys.executable, str(script), "install", "--harness", "codex", "--project", str(project)],
                               check=True, capture_output=True, text=True).stdout
    (root / "personas-install.json").write_text(installed)
    exclude = project / ".git" / "info" / "exclude"
    exclude.write_text(exclude.read_text() + ".agents/\n.codex/\n")
    return project


def repository_roots():
    listing = subprocess.run(["git", "-C", str(REPO), "worktree", "list", "--porcelain", "-z"], check=True,
                             stdout=subprocess.PIPE, text=True).stdout
    return [REPO, *(Path(field.removeprefix("worktree ")) for field in listing.split("\0") if field.startswith("worktree "))]


def inside_repository(root):
    real = root.resolve()
    tops = [top for top in repository_roots() if top.exists()]
    return any(ancestor.exists() and any(ancestor.samefile(top) for top in tops) for ancestor in (real, *real.parents))


@contextlib.contextmanager
def private_login(source, dest):
    def stop(signum, frame):
        for number in CLEANUP_SIGNALS:
            signal.signal(number, signal.SIG_IGN)
        raise SystemExit(128 + signum)

    previous = {number: signal.signal(number, stop) for number in CLEANUP_SIGNALS}
    try:
        dest.unlink(missing_ok=True)
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
        with os.fdopen(os.open(dest, flags, 0o600), "wb") as out:
            os.fchmod(out.fileno(), 0o600)
            out.write(source.read_bytes())
        yield
    finally:
        try:
            dest.unlink(missing_ok=True)
        finally:
            for number, handler in previous.items():
                signal.signal(number, handler)


def env_for(root):
    env = {k: os.environ[k] for k in ENV_KEPT if k in os.environ}
    env.update(HOME=str(root / "home"), CODEX_HOME=str(root / "codex-home"), TMPDIR=str(root / "tmp"))
    return env


def flags(root, project, model, effort, v2_flag):
    trusted = json.dumps(str(project))
    roots = json.dumps([str(project / ".git"), str(root / "tmp")])
    return ["--disable", "apps", "-c", f'model="{model}"', "-c", f'model_reasoning_effort="{effort}"',
            "-c", 'approval_policy="never"', "-c", 'sandbox_mode="workspace-write"',
            *(["-c", "features.multi_agent_v2=true"] if v2_flag else []),
            "-c", f'projects={{{trusted}={{trust_level="trusted"}}}}',
            "-c", f"sandbox_workspace_write.writable_roots={roots}",
            "-c", "sandbox_workspace_write.exclude_slash_tmp=true",
            "-c", "sandbox_workspace_write.exclude_tmpdir_env_var=true"]


def thread_id(stream):
    for line in stream.read_text(errors="replace").splitlines():
        try:
            record = json.loads(line)
        except ValueError:
            continue
        if record.get("type") == "thread.started":
            return record["thread_id"]


def login_source():
    return Path.home() / ".codex" / "auth.json"


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("row", choices=sorted(ROWS))
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--timeout", type=int, default=3000)
    args = parser.parse_args()
    if inside_repository(args.root):
        parser.error(f"--root {args.root} resolves inside the repository; choose a directory outside it")
    if args.root.exists() and not args.root.is_dir():
        parser.error(f"--root {args.root} exists and is not a directory")
    if (args.root / "codex-home").is_symlink():
        parser.error(f"{args.root / 'codex-home'} is a symlink; remove it or choose a fresh --root")
    if args.timeout < 1:
        parser.error("--timeout must be at least 1 second")
    if not login_source().is_file():
        parser.error(f"no Codex login at {login_source()}")
    return args


def main():
    args = parse_args()
    root = args.root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    row = ROWS[args.row]
    model = row.get("model", LEAD_MODEL)
    project = prepare(root)
    env = env_for(root)
    session = None
    turns = []
    with private_login(login_source(), root / "codex-home" / "auth.json"):
        for index, prompt in enumerate(row["turns"]):
            stream, errors, last = (root / "transcripts" / f"turn-{index}.{ext}" for ext in ("jsonl", "err", "last-message.txt"))
            resume = ["resume"] if index else []
            tail = ["--json", "-o", str(last), "--", *([session] if index else []), prompt]
            argv = ["codex", "exec", *resume, *flags(root, project, model, LEAD_EFFORT, row.get("v2_flag", True)), *tail]
            with open(stream, "wb") as out, open(errors, "wb") as err:
                try:
                    code = subprocess.run(argv, cwd=project, env=env, stdin=subprocess.DEVNULL, stdout=out, stderr=err,
                                          timeout=args.timeout).returncode
                except subprocess.TimeoutExpired:
                    code = "timeout"
            session = session or thread_id(stream)
            turns.append({"index": index, "exit": code, "session": session})
            if code != 0:
                break
    (root / "run.json").write_text(json.dumps({"row": args.row, "model": model, "effort": LEAD_EFFORT, "v2_flag": row.get("v2_flag", True), "prompts": row["turns"], "skills_at":
        subprocess.run(["git", "-C", str(REPO), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip(),
        "turns": turns}, indent=1) + "\n")
    print(json.dumps(turns))


if __name__ == "__main__":
    main()
