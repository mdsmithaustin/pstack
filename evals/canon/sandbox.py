#!/usr/bin/env python3
"""Sandboxed workspace runs: every answer runs inside its own Docker sandbox.

`screen.py run --runner sbx` points the harness at `sandbox.py wrap` instead of
workspace.py wrap. For each run the wrapper checks out the pinned commit in
the harness workspace as before, makes that checkout a self-contained git
repo, and creates one sandbox from it with `sbx create --clone`, so the agent
works on an in-sandbox clone and never on host files. It copies the mounted
skills and the overlay in, registers the poteto-agent persona the way a user
install does, links the project's test dependencies from a pinned template,
runs the agent with every tool and no permission prompts inside the sandbox,
and copies the workspace diff, the agent's session transcripts (every
delegate's included), and the sandbox's network log back out. The sandbox is
removed when the run ends. A Claude run's stream reaches the harness with only
its last result event, and its full stream is kept as raw-stream.jsonl.

  sandbox.py deps --agent A --repo R [--commit C]       build the dependency template for R at C
  sandbox.py probe --agent A [--repo R --commit C]      list the tools a run offers, at no model cost
  sandbox.py wrap --agent A [--token T --discovery D] -- ARG...   the harness entry wrapper
  sandbox.py gc                                          remove sandboxes a killed run left behind

sbx.json pins the per-agent kit, the dependency sync per repo, the uv version,
and the network each phase may reach. Auth never enters a file here: sbx's
proxy adds the stored credentials to model API requests.
"""
import argparse
import contextlib
import hashlib
import io
import json
import os
import secrets
import signal
import subprocess
import sys
import tarfile
import tempfile
import time
from pathlib import Path

CANON = Path(__file__).resolve().parent
sys.path.insert(0, str(CANON))
import workspace  # noqa: E402

CONFIG = json.loads((CANON / "sbx.json").read_text())
PREFIX = "canon-"
PAYLOAD = "/tmp/canon-payload"
LAST_MESSAGE = "/tmp/canon-last-message.txt"
DEPS_ROOT = "/opt/canon-deps"
# The stand-in answers inside the sandbox; CANON_SBX_STANDIN names it on the host.
STANDIN = "/tmp/canon-standin"
# Time the wrapper keeps for itself inside the harness timeout: harvest and teardown.
RESERVE_S = 120
# Flags a Claude run gets inside the sandbox. -p hides the task tools unless
# TodoWrite is allowed by name, and the sandbox's MCP gateway is not part of
# the task.
CLAUDE_FLAGS = ("--setting-sources", "project", "--permission-mode", "bypassPermissions",
                "--strict-mcp-config", "--allowedTools", "TodoWrite")
CODEX_FLAGS = ("-c", "mcp_servers.mcp-gateway.enabled=false")


class SandboxError(Exception):
    pass


def sbx(*args, input=None, capture=True, check=True):
    proc = subprocess.run(["sbx", *map(str, args)], input=input, capture_output=capture,
                          stdin=subprocess.DEVNULL if input is None else None)
    if check and proc.returncode != 0:
        detail = (proc.stderr or b"").decode(errors="replace").strip()[-600:] if capture else ""
        raise SandboxError(f"sbx {' '.join(map(str, args[:2]))} failed ({proc.returncode}): {detail}")
    return proc


class Sandbox:
    def __init__(self, name):
        self.name = name

    @classmethod
    def create(cls, name, kit, path=None, template=None, deny=()):
        args = ["create", "--skills", "off", "--name", name, "-q"]
        if path is not None:
            args.append("--clone")
        if template:
            args += ["-t", template]
        for host in deny:
            args += ["--deny-network", host]
        sbx(*args, kit, *([path] if path is not None else []))
        return cls(name)

    def exec_args(self, argv, workdir=None, env=None, interactive=False, user=None):
        args = ["exec"]
        if interactive:
            args.append("-i")
        if workdir:
            args += ["-w", workdir]
        if user:
            args += ["-u", user]
        for key, value in (env or {}).items():
            args += ["-e", f"{key}={value}"]
        return [*args, self.name, *argv]

    def exec(self, *argv, workdir=None, env=None, input=None, capture=True, check=True, user=None):
        return sbx(*self.exec_args(argv, workdir, env, input is not None, user), input=input, capture=capture, check=check)

    def exec_stdout(self, *argv, workdir=None, env=None, stdin=None):
        """Run argv with stdin from an open file and stderr passed through.
        Returns the Popen; the caller reads its stdout line by line."""
        return subprocess.Popen(["sbx", *map(str, self.exec_args(argv, workdir, env, stdin is not None))],
                                stdin=stdin if stdin is not None else subprocess.DEVNULL, stdout=subprocess.PIPE)

    def put(self, local, remote):
        sbx("cp", local, f"{self.name}:{remote}")

    def get(self, remote, local):
        sbx("cp", f"{self.name}:{remote}", local)

    def unpack(self, local_tar, directory):
        """Copy a tar in and extract it to directory, owned by the agent user.
        sbx cp writes as root, so root unpacks and removes the tar."""
        self.put(local_tar, f"{directory}.tar")
        self.exec("sh", "-c", f"rm -rf {directory} && mkdir -p {directory} && tar -xf {directory}.tar -C {directory} "
                              f"&& rm {directory}.tar && chown -R agent:agent {directory}", user="root")

    def allow(self, hosts):
        sbx("policy", "allow", "network", "--sandbox", self.name, ",".join(hosts))

    def policy(self):
        """{"allow": [...], "deny": [...]} network resources that apply to this sandbox."""
        rules = _json_or_text(sbx("policy", "ls", self.name, "--wide", "--json", check=False).stdout)
        summary = {"allow": [], "deny": []}
        for rule in (rules or {}).get("rules", []) if isinstance(rules, dict) else []:
            if rule.get("resource_type") == "network" and rule.get("status", "active") == "active":
                summary.setdefault(rule.get("decision"), []).extend(rule.get("resources") or [])
        return {decision: sorted(set(hosts)) for decision, hosts in summary.items()}

    def reachable(self, hosts):
        """{host: True/False} as the sandbox's policy authorizer decides it."""
        decisions = {}
        for host in hosts:
            proc = sbx("policy", "check", "network", "--sandbox", self.name, host, "--json", check=False)
            answer = _json_or_text(proc.stdout)
            decisions[host] = answer.get("allowed", answer.get("decision") == "allow") if isinstance(answer, dict) else None
        return decisions

    def network_log(self):
        proc = sbx("policy", "log", self.name, "--json", check=False)
        return _json_or_text(proc.stdout)

    def remove(self):
        sbx("rm", "--force", self.name, check=False)


def _json_or_text(data):
    text = (data or b"").decode(errors="replace")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


def sandboxes():
    return [box["name"] for box in json.loads(sbx("ls", "--json").stdout).get("sandboxes") or []]


def templates():
    """{"repository:tag": row} of the templates in the sandbox runtime's store."""
    listing = json.loads(sbx("template", "ls", "--json").stdout)
    rows = listing if isinstance(listing, list) else next((value for value in listing.values() if isinstance(value, list)), [])
    return {f"{row['repository'].rsplit('/', 1)[-1]}:{row['tag']}": row for row in rows}


@contextlib.contextmanager
def timed(timings, key):
    started = time.monotonic()
    try:
        yield
    finally:
        timings[key] = round(time.monotonic() - started, 2)


def config_digest(*parts):
    return hashlib.sha256(json.dumps(parts, sort_keys=True).encode()).hexdigest()[:12]


def deps_tag(agent, repo, commit):
    """The template name for agent, repo, and commit, versioned by every
    setting that changes what the build installs."""
    spec = {key: value for key, value in CONFIG["repos"][repo].items() if key in ("python", "sync", "env")}
    return f"canon-deps-{agent}-{repo}-{commit[:12]}:{config_digest(CONFIG['uv'], spec, CONFIG['agents'][agent]['kit'], CONFIG['agents'][agent].get('cli'))}"


def deps_env(repo):
    spec = CONFIG["repos"][repo]
    return {
        "UV_PROJECT_ENVIRONMENT": f"{DEPS_ROOT}/{repo}/venv",
        "UV_CACHE_DIR": f"{DEPS_ROOT}/uv-cache",
        "UV_PYTHON_INSTALL_DIR": f"{DEPS_ROOT}/python",
        "UV_PYTHON": spec["python"],
        "UV_PYTHON_DOWNLOADS": "never",
        "UV_OFFLINE": "1",
        **spec.get("env", {}),
    }


def records_dir():
    path = workspace.cache_root() / "sbx"
    path.mkdir(parents=True, exist_ok=True)
    return path


def build_deps(agent, repo, commit):
    """Snapshot a sandbox that holds repo's locked test dependencies as a
    template. The venv, the uv cache, and the interpreter live under
    /opt/canon-deps, outside any workspace. The source copy used to sync is
    deleted before the snapshot, and so are the agent's credential files, which
    the kit writes again when a sandbox is created from the template."""
    spec, kit = CONFIG["repos"][repo], CONFIG["agents"][agent]["kit"]
    mirror = workspace.fetch(repo, commit)
    tag = deps_tag(agent, repo, commit)
    name = f"{PREFIX}deps-{agent}-{repo}-{secrets.token_hex(3)}"
    record = {"tag": tag, "agent": agent, "repo": repo, "commit": commit, "uv": CONFIG["uv"], "python": spec["python"],
              "sync": spec["sync"], "network": CONFIG["build_network"], "timings": {}}
    timings = record["timings"]
    with tempfile.TemporaryDirectory() as directory:
        source = Path(directory) / "src.tar"
        source.write_bytes(workspace.git("--git-dir", str(mirror), "archive", "--format=tar", commit))
        box = None
        try:
            with timed(timings, "create_s"):
                box = Sandbox.create(name, kit)
            box.allow(CONFIG["build_network"])
            box.exec("sh", "-c", f"mkdir -p {DEPS_ROOT}/{repo}/src && chown -R agent:agent {DEPS_ROOT}", user="root")
            box.put(source, f"{DEPS_ROOT}/{repo}/src.tar")
            env = {key: value for key, value in deps_env(repo).items() if key not in ("UV_OFFLINE", "UV_PYTHON_DOWNLOADS")}
            steps = [
                ["tar", "-xf", f"{DEPS_ROOT}/{repo}/src.tar", "-C", f"{DEPS_ROOT}/{repo}/src"],
                ["uv", "tool", "install", "--force", f"uv=={CONFIG['uv']}"],
                ["uv", "python", "install", spec["python"]],
                ["sh", "-c", f"cd {DEPS_ROOT}/{repo}/src && uv sync {' '.join(spec['sync'])}"],
            ]
            cli = CONFIG["agents"][agent].get("cli")
            if cli:
                with timed(timings, "cli_s"):
                    proc = box.exec("npm", "install", "-g", cli, user="root", check=False)
                if proc.returncode != 0:
                    raise SandboxError(f"npm install -g {cli} failed: {proc.stderr.decode(errors='replace')[-800:]}")
                record["cli"] = cli
            for key, step in zip(("extract_s", "uv_s", "python_s", "sync_s"), steps):
                with timed(timings, key):
                    proc = box.exec(*step, env=env, check=False)
                if proc.returncode != 0:
                    raise SandboxError(f"{' '.join(step)} failed: {proc.stderr.decode(errors='replace')[-800:]}")
            versions = box.exec("sh", "-c", "uv --version; claude --version 2>/dev/null; codex --version 2>/dev/null; "
                                f"du -sm {DEPS_ROOT}/{repo}/venv {DEPS_ROOT}/uv-cache {DEPS_ROOT}/python", env=env).stdout.decode()
            record["versions_and_sizes"] = versions.strip().splitlines()
            box.exec("sh", "-c", f"rm -rf {DEPS_ROOT}/{repo}/src {DEPS_ROOT}/{repo}/src.tar "
                                 "$HOME/.claude/.credentials.json $HOME/.codex/auth.json")
            record["network_log"] = box.network_log()
            with timed(timings, "save_s"):
                sbx("stop", name)
                sbx("template", "save", name, tag)
            record["template_bytes"] = templates()[tag]["size"]
        finally:
            if box is not None:
                with timed(timings, "destroy_s"):
                    box.remove()
    (records_dir() / f"{tag.replace(':', '@')}.json").write_text(json.dumps(record, indent=2) + "\n")
    return record


def self_contained(root):
    """The clone inside the sandbox cannot follow alternates to the host's
    mirror, so copy the objects the checkout needs into the repo itself."""
    workspace.git("repack", "-a", "-d", "-q", cwd=root)
    alternates = Path(root) / ".git" / "objects" / "info" / "alternates"
    if alternates.exists():
        alternates.unlink()


def agent_command(agent, argv):
    """The harness's argv, rewritten for inside the sandbox. Returns (argv, the
    host path the harness reads Codex's last message from, or None)."""
    if agent == "claude":
        return ["claude", *[arg for arg in argv if arg != "--no-session-persistence"], *CLAUDE_FLAGS], None
    rewritten, last_message, skip = ["codex"], None, False
    for index, arg in enumerate(argv):
        if skip:
            skip = False
            continue
        if arg in ("--ephemeral", "--ignore-user-config"):
            continue
        if arg == "--sandbox":
            rewritten += ["--sandbox", "danger-full-access"]
            skip = True
        elif arg == "--output-last-message":
            last_message = argv[index + 1]
            rewritten += [arg, LAST_MESSAGE]
            skip = True
        else:
            rewritten.append(arg)
    if rewritten[-1:] == ["-"]:
        return [*rewritten[:-1], *CODEX_FLAGS, "-"], last_message
    return [*rewritten, *CODEX_FLAGS], last_message


def is_result(line):
    try:
        event = json.loads(line)
    except ValueError:
        return False
    return isinstance(event, dict) and event.get("type") == "result"


def last_result_only(lines):
    """The lines in order, without every result event but the last. The
    harness takes exactly one result from a Claude stream, and a lead that
    waits on a background delegate ends a turn, with a result, each time."""
    held = []
    for line in lines:
        if is_result(line):
            yield from held[1:]
            held = [line]
        elif held:
            held.append(line)
        else:
            yield line
    yield from held


def stream_claude(box, command, prompt_path, raw_path, out, **options):
    """Run Claude in the sandbox, keep its whole stream in raw_path, and write
    the stream with one result event to out. Returns the exit code."""
    with open(prompt_path, "rb") as stdin, open(raw_path, "wb") as raw:
        proc = box.exec_stdout(*command, stdin=stdin, **options)

        def lines():
            for line in proc.stdout:
                raw.write(line)
                yield line

        try:
            for line in last_result_only(lines()):
                out.write(line)
                out.flush()
            return proc.wait()
        except BaseException:
            proc.kill()
            proc.wait()
            raise
        finally:
            proc.stdout.close()


def pack(directory, files):
    """A tar of {archive path: local path or bytes}."""
    target = Path(directory) / f"payload-{secrets.token_hex(4)}.tar"
    with tarfile.open(target, "w") as archive:
        for name, source in files.items():
            if isinstance(source, bytes):
                info = tarfile.TarInfo(name)
                info.size = len(source)
                info.mode = 0o644
                archive.addfile(info, fileobj=io.BytesIO(source))
            else:
                archive.add(source, arcname=name)
    return target


def manifest(agent, root, spec, discovery):
    conf = CONFIG["agents"][agent]
    tree = "skills/pstack" if discovery else "skills"
    record = {"agent": agent, "root": str(root), "commit": spec["commit"], "expected_tree": spec["tree"], "tree": tree,
              "discovery": discovery, "harness": conf["harness"] if discovery else None, "transcripts": conf["transcripts"],
              "deps": None}
    if spec["repo"] in CONFIG["repos"]:
        record["deps"] = {"env": deps_env(spec["repo"]), "sync": CONFIG["repos"][spec["repo"]]["sync"]}
    return record


def standin(agent_argv, root):
    """The offline stand-in's argv inside the sandbox, after its plan is made
    on the host (it needs screen.py to pick a sample)."""
    host = Path(os.environ["CANON_SBX_STANDIN"])
    plan = subprocess.run([sys.executable, str(host), "plan"], cwd=root, capture_output=True, check=True).stdout
    return host, plan, ["python3", f"{STANDIN}/agent", f"{STANDIN}/plan.json", *agent_argv]


def wrap(argv, stdin=sys.stdin.buffer):
    split = argv.index("--")
    options, harness_argv = argv[:split], argv[split + 1:]

    def option(flag):
        return options[options.index(flag) + 1] if flag in options else None

    agent, token, discovery = option("--agent"), option("--token"), option("--discovery")
    prompt = stdin.read()
    if not prompt.strip():
        raise SandboxError("the harness sent an empty prompt")
    if token:
        prompt = token.encode() + b" " + prompt
    arm = Path(os.environ["CANON_WORKSPACE"])
    spec = json.loads((arm / "workspace.json").read_text())
    slot = workspace.next_slot(Path(os.environ["CANON_HARVEST"]))
    record = {"runner": "sbx", "expected_tree": spec["tree"], "timings": {}}
    timings = record["timings"]
    root = Path.cwd()
    box = None

    def save():
        (slot / "workspace.json").write_text(json.dumps(record, indent=2) + "\n")

    def interrupted(signum, frame):
        raise SandboxError(f"interrupted by signal {signum}")

    previous = signal.signal(signal.SIGTERM, interrupted)
    try:
        with tempfile.TemporaryDirectory() as directory:
            with timed(timings, "materialize_s"):
                record["host_tree"] = workspace.materialize(root, Path(spec["mirror"]), spec["commit"], workspace.read_files(arm / "overlay"))
                if record["host_tree"] != spec["tree"]:
                    raise workspace.WorkspaceError(f"materialized tree {record['host_tree']} is not the recorded {spec['tree']}")
                self_contained(root)
            inside = manifest(agent, root, spec, discovery)
            files = {"manifest.json": json.dumps(inside).encode(), "sbx_inside.py": CANON / "sbx_inside.py",
                     "workspace.py": CANON / "workspace.py", "skills": root / "skills", "overlay": arm / "overlay"}
            payload = pack(directory, files)
            tools = pack(directory, {name: files[name] for name in ("manifest.json", "sbx_inside.py", "workspace.py")})
            template = None
            if inside["deps"]:
                template = deps_tag(agent, spec["repo"], spec["commit"])
                if template not in templates():
                    raise SandboxError(f"no dependency template {template}; build it with "
                                       f"`python3 evals/canon/sandbox.py deps --agent {agent} --repo {spec['repo']} --commit {spec['commit']}`")
            record["template"] = template
            name = f"{PREFIX}{agent}-{secrets.token_hex(4)}"
            record["sandbox"] = name
            with timed(timings, "create_s"):
                box = Sandbox.create(name, CONFIG["agents"][agent]["kit"], root, template, CONFIG["run_deny_network"])
            with timed(timings, "setup_s"):
                box.unpack(payload, PAYLOAD)
                proc = box.exec("python3", f"{PAYLOAD}/sbx_inside.py", "setup", f"{PAYLOAD}/manifest.json", check=False)
                record["setup"] = _json_or_text(proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else b"")
                box.exec("rm", "-rf", PAYLOAD)
                if proc.returncode != 0:
                    raise workspace.WorkspaceError(f"sandbox setup: {record['setup']} {proc.stderr.decode(errors='replace')[-400:]}")
                record["tree"] = record["setup"]["tree"]
                record["versions"] = box.exec("sh", "-c", "claude --version 2>/dev/null; codex --version 2>/dev/null; uv --version").stdout.decode().split("\n")[:3]
            record["policy"] = box.policy()
            record["reachable"] = box.reachable([*CONFIG["agents"][agent]["api"], *CONFIG["run_deny_network"]])
            save()
            command, last_message = agent_command(agent, harness_argv)
            if os.environ.get("CANON_SBX_STANDIN"):
                host, plan, command = standin(command, root)
                box.unpack(pack(directory, {"agent": host, "plan.json": plan}), STANDIN)
            budget = int(os.environ.get("CANON_TIMEOUT_S", workspace.TIMEOUT_S)) - RESERVE_S
            env = inside["deps"]["env"] if inside["deps"] else {}
            record["command"] = command
            record["prompt_bytes"] = len(prompt)
            timed_command = ("timeout", "--kill-after=30", str(max(budget, 60)), *command)
            with timed(timings, "agent_s"):
                if agent == "claude":
                    prompt_path = Path(directory) / "prompt.txt"
                    prompt_path.write_bytes(prompt)
                    record["agent_rc"] = stream_claude(box, timed_command, prompt_path, slot / "raw-stream.jsonl", sys.stdout.buffer,
                                                       workdir=str(root), env=env)
                else:
                    record["agent_rc"] = box.exec(*timed_command, workdir=str(root), env=env, input=prompt, capture=False, check=False).returncode
            if os.environ.get("CANON_SBX_STANDIN"):
                box.exec("rm", "-rf", STANDIN)
            with timed(timings, "harvest_s"):
                box.unpack(tools, PAYLOAD)
                proc = box.exec("python3", f"{PAYLOAD}/sbx_inside.py", "harvest", f"{PAYLOAD}/manifest.json", "/tmp/canon-out", check=False)
                if proc.returncode != 0:
                    raise SandboxError(f"sandbox harvest failed: {proc.stdout.decode(errors='replace')[-400:]}")
                box.get("/tmp/canon-out.tar", Path(directory) / "out.tar")
                with tarfile.open(Path(directory) / "out.tar") as archive:
                    archive.extractall(slot, filter="data")
                record.update(json.loads((slot / "inside.json").read_text()))
                (slot / "inside.json").unlink()
                if last_message:
                    box.get(LAST_MESSAGE, last_message)
            (slot / "network-log.json").write_text(json.dumps(box.network_log(), indent=2) + "\n")
    except (workspace.WorkspaceError, SandboxError, subprocess.CalledProcessError) as exc:
        record["error"] = str(exc)
        print(f"sandbox: {exc}", file=sys.stderr)
        record.setdefault("agent_rc", workspace.REFUSED)
    finally:
        signal.signal(signal.SIGTERM, previous)
        if box is not None:
            with timed(timings, "destroy_s"):
                box.remove()
        save()
    return record["agent_rc"] if "error" not in record else workspace.REFUSED


def probe(agent, repo=None, commit=None):
    """Create a run-shaped sandbox with the tracked skills mounted and the
    persona registered, then ask the agent for its tool list without a model
    call: Claude with a model name that does not exist prints its init event
    and stops; Codex is pointed at a local server that records the request it
    would send and answers 400."""
    import screen  # noqa: PLC0415

    conf = CONFIG["agents"][agent]
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory) / "probe"
        if repo:
            spec = workspace.Spec(repo, commit, {})
            checkout, tree = workspace.reference_checkout(spec)
            mirror = workspace.require_mirror(spec)
        for path, data in screen.tracked("skills").items():
            (root / "skills" / "pstack" / path).parent.mkdir(parents=True, exist_ok=True)
            (root / "skills" / "pstack" / path).write_bytes(data)
        if repo:
            tree = workspace.materialize(root, mirror, commit, {})
        else:
            (root / "README.md").parent.mkdir(parents=True, exist_ok=True)
            (root / "README.md").write_text("probe\n")
            workspace.git("init", "-q", "--template=", cwd=root)
            workspace.exclude(root, ["skills"])
            workspace.git("add", "README.md", cwd=root)
            workspace.git("-c", "user.name=probe", "-c", "user.email=probe@example.com", "commit", "-q", "-m", "probe", cwd=root)
            commit = workspace.git("rev-parse", "HEAD", cwd=root).decode().strip()
            tree = workspace.snapshot(root, commit)
        self_contained(root)
        spec = {"repo": repo or "probe", "commit": commit, "tree": tree}
        inside = manifest(agent, root, spec, conf["discovery"])
        (Path(directory) / "empty").mkdir()
        payload = pack(directory, {"manifest.json": json.dumps(inside).encode(), "sbx_inside.py": CANON / "sbx_inside.py",
                                   "workspace.py": CANON / "workspace.py", "skills": root / "skills", "overlay": Path(directory) / "empty"})
        box = None
        try:
            template = deps_tag(agent, repo, commit) if inside["deps"] else None
            box = Sandbox.create(f"{PREFIX}probe-{agent}-{secrets.token_hex(3)}", conf["kit"], root, template, CONFIG["run_deny_network"])
            box.unpack(payload, PAYLOAD)
            setup = box.exec("python3", f"{PAYLOAD}/sbx_inside.py", "setup", f"{PAYLOAD}/manifest.json", check=False)
            report = {"setup": _json_or_text(setup.stdout.strip().splitlines()[-1]) if setup.stdout.strip() else setup.stderr.decode()}
            env = inside["deps"]["env"] if inside["deps"] else {}
            if inside["deps"]:
                package = CONFIG["repos"][repo]["package"]
                check = box.exec("sh", "-c", f"uv run --frozen python -c 'import {package}, pytest; print({package}.__file__, pytest.__version__)' "
                                 "&& uv run --frozen pytest --collect-only -q -p no:cacheprovider tests 2>&1 | tail -n 1",
                                 workdir=str(root), env=env, check=False)
                report["deps_check"] = (check.stdout + check.stderr).decode(errors="replace").strip().splitlines()[-3:]
            if agent == "claude":
                command, _ = agent_command("claude", ["-p", "--output-format", "stream-json", "--verbose", "--no-session-persistence",
                                                      "--model", "canon-no-such-model"])
                out = box.exec(*command, workdir=str(root), env=env, input=b"/poteto-mode reply ok", check=False).stdout.decode()
                init = next(json.loads(line) for line in out.splitlines() if '"subtype":"init"' in line.replace(" ", ""))
                report.update({key: init.get(key) for key in ("claude_code_version", "permissionMode", "tools", "agents")})
                report["poteto-mode listed"] = "poteto-mode" in (init.get("slash_commands") or [])
            else:
                command, _ = agent_command("codex", ["exec", "--json", "--skip-git-repo-check", "--sandbox", "workspace-write",
                                                     "--model", "canon-no-such-model", "--ephemeral", "--ignore-user-config", "-"])
                box.exec("sh", "-c", f"nohup python3 {PAYLOAD}/sbx_inside.py capture 8765 /tmp/canon-capture.jsonl >/dev/null 2>&1 &")
                time.sleep(1)
                provider = ('model_providers.canon={name="canon",base_url="http://127.0.0.1:8765/v1",'
                            'wire_api="responses",requires_openai_auth=false}')
                command = [*command[:-1], "-c", provider, "-c", "model_provider=canon", "-c", "request_max_retries=0",
                           "-c", "stream_max_retries=0", "-"]
                box.exec(*command, workdir=str(root), env=env, input=b"$poteto-mode reply ok", check=False)
                body = json.loads(json.loads(box.exec("head", "-n", "1", "/tmp/canon-capture.jsonl").stdout)["body"])
                names = []
                for tool in body.get("tools") or []:
                    names.append(tool.get("name") or tool.get("type"))
                    names += [f"{tool.get('name')}.{inner.get('name')}" for inner in tool.get("tools") or []]
                text = json.dumps(body)
                report.update({"codex_version": box.exec("codex", "--version").stdout.decode().strip(), "tools": names,
                               "poteto-agent role offered": "poteto-agent:" in text,
                               "poteto-mode injected": "name: poteto-mode" in json.dumps(body.get("input"))})
            report["policy"] = box.policy()
            report["reachable"] = box.reachable([*conf["api"], *CONFIG["run_deny_network"]])
            return report
        finally:
            if box is not None:
                box.remove()


def gc():
    removed = [name for name in sandboxes() if name.startswith(PREFIX)]
    for name in removed:
        Sandbox(name).remove()
    return removed


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ["wrap"]:
        return wrap(argv[1:])
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("deps")
    p.add_argument("--agent", choices=sorted(CONFIG["agents"]), required=True)
    p.add_argument("--repo", choices=sorted(CONFIG["repos"]), required=True)
    p.add_argument("--commit", required=True)
    p = sub.add_parser("probe")
    p.add_argument("--agent", choices=sorted(CONFIG["agents"]), required=True)
    p.add_argument("--repo", choices=sorted(CONFIG["repos"]))
    p.add_argument("--commit")
    sub.add_parser("gc")
    args = parser.parse_args(argv)
    try:
        if args.command == "deps":
            print(json.dumps(build_deps(args.agent, args.repo, args.commit), indent=2))
        elif args.command == "probe":
            print(json.dumps(probe(args.agent, args.repo, args.commit), indent=2))
        else:
            print(json.dumps(gc()))
    except (SandboxError, workspace.WorkspaceError) as exc:
        print(f"sandbox: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
