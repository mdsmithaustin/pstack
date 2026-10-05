import json
import hashlib
import os
import platform
import pwd
import re
import shlex
import shutil
import stat
import subprocess
import sys
import uuid
from dataclasses import dataclass, replace
from functools import lru_cache
from pathlib import Path

import live

SKILLS_DIR = ".claude/skills"
PRIVATE_DIRS = (".claude/",)
SHARES_HOST_TMP = False

DEFAULT_EFFORT = "high"
SPAWN_TOOLS = ("Task", "Agent")
READ_COMMANDS = {"cat", "head", "tail", "sed", "awk", "less", "more", "nl", "bat", "wc", "grep", "rg",
                 "diff", "cmp", "jq", "python3", "python"}
SEPARATORS = {"&&", "||", ";", "|", "&"}
TASK_ID = re.compile(r"Task #?(\w+)")
ASSIGN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
VAR = re.compile(r"\$(?:\{([A-Za-z_][A-Za-z0-9_]*)\}|([A-Za-z_][A-Za-z0-9_]*))")
PERSONA_LINE = re.compile(r"^persona: ([\w-]+)[ \t]*$", re.M)
COMMAND_NAME = re.compile(r"<command-name>(/[^<]+)</command-name>")
COMMAND_ARGS = re.compile(r"<command-args>(.*?)</command-args>", re.S)


class IsolationUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class ClaudePaths:
    root: Path
    project: Path
    config: Path
    tmp: Path
    cache: Path
    xdg: Path
    transcripts: Path


@dataclass(frozen=True)
class HostRuntime:
    binary: Path
    version: str
    home: Path
    user: str
    read_files: tuple[Path, ...]
    read_trees: tuple[Path, ...]
    fingerprints: tuple[tuple[Path, str], ...]
    path_env: str
    shell: str


@dataclass(frozen=True)
class ClaudeState:
    paths: ClaudePaths
    runtime: HostRuntime
    identities: tuple[tuple[Path, int, int], ...]
    session: str
    records: tuple[dict, ...] = ()


@dataclass(frozen=True)
class ConfinedCommand:
    argv: tuple[str, ...]
    env: dict[str, str]
    session: str


CLAUDE_BINARY = Path("/Users/msmith1/.local/share/claude/versions/2.1.289")
CLAUDE_SHA256 = "03d66745e3bb69ec727d66023696f3820bc0a00a8a5ba725eb6706d0c67cbe69"
PYTHON_ROOT = Path("/Users/msmith1/.local/share/mise/installs/python/3.14.7")
NODE_ROOT = Path("/Users/msmith1/.local/share/mise/installs/node/24.20.0")
GIT_ROOT = Path("/Library/Developer/CommandLineTools")
RG_BINARY = Path("/Applications/ChatGPT.app/Contents/Resources/codex-cli/codex-path/rg")
PINNED_TOOLS = (
    (PYTHON_ROOT / "bin/python3.14", ("1bfa9a829d950ecd4870a3d7a6826eb57edb4aa93f69d07cd3bb21e9fcc6d439",)),
    (NODE_ROOT / "bin/node", ("9d050fd455b56426e25d4d603c7c501cbb2630348e836cf221dcce748e90588a",)),
    (RG_BINARY, ("ee0025a8dcfb3bef627328c5fb57b56967dcdfc3ed713e3825dfaba1da2e579a",)),
    (GIT_ROOT / "usr/bin/git", ("a73bf622a2e470d5d57a4b1d5aef1e8680e67278018d4858a2f93825b7d595c7",
                              "be4afb2b003904725826250de9fb76567bbacf82323457b5a1ec26706b66bcae")),
)
SYSTEM_TOOLS = tuple(Path("/bin") / n for n in ("sh", "bash", "zsh", "cat", "cp", "mv", "rm", "mkdir", "ls", "pwd", "chmod")) + tuple(
    Path("/usr/bin") / n for n in ("security", "uname", "sw_vers", "sed", "awk", "grep", "head", "tail", "wc", "find", "xargs", "env", "diff", "sort", "touch", "true", "false", "tee", "tr"))


def _open_dir(path):
    if not path.is_absolute() or ".." in path.parts:
        raise IsolationUnavailable(f"not an absolute owned directory: {path}")
    fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in path.parts[1:]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = child
        return fd
    except OSError as error:
        os.close(fd)
        raise IsolationUnavailable(f"unsafe directory: {path}") from error


def _digest(path):
    with path.open("rb") as file:
        return hashlib.file_digest(file, "sha256").hexdigest()


@lru_cache(maxsize=1)
def _host_runtime():
    account = pwd.getpwuid(os.getuid())
    if (platform.system(), platform.release(), platform.machine(), account.pw_dir, account.pw_name) != (
            "Darwin", "25.6.0", "arm64", "/Users/msmith1", "msmith1"):
        raise IsolationUnavailable("Claude filesystem isolation supports only the measured Darwin 25.6.0 arm64 runtime")
    home = Path(account.pw_dir)
    files = (CLAUDE_BINARY, *(p for p, _ in PINNED_TOOLS), *SYSTEM_TOOLS, GIT_ROOT / "usr/share/git-core/gitattributes", *(Path(p) for p in (
        "/", "/usr/share/icu/icudt78l.dat", "/dev/null", "/dev/random", "/dev/urandom", "/private/etc/hosts",
        "/private/var/run/resolv.conf", "/private/var/db/timezone/zoneinfo/America/Denver")))
    trees = (PYTHON_ROOT, NODE_ROOT, GIT_ROOT / "usr/libexec/git-core", GIT_ROOT / "usr/share/git-core/templates",
             Path("/System/Library"), Path("/usr/lib"), home / "Library/Keychains")
    pins = []
    for path, expected in ((CLAUDE_BINARY, (CLAUDE_SHA256,)), *PINNED_TOOLS):
        if path.is_symlink():
            raise IsolationUnavailable(f"unsupported executable: {path}")
        digest = _digest(path)
        if digest not in expected:
            raise IsolationUnavailable(f"unsupported executable: {path}")
        pins.append((path, digest))
    if not Path("/usr/bin/sandbox-exec").is_file() or any(not path.exists() for path in (*files, *trees)):
        raise IsolationUnavailable("measured Seatbelt runtime dependencies are missing")
    return HostRuntime(CLAUDE_BINARY, "2.1.289", home, account.pw_name, files, trees, tuple(pins),
                       f"{PYTHON_ROOT}/bin:{NODE_ROOT}/bin:{RG_BINARY.parent}:{GIT_ROOT}/usr/bin:/usr/bin:/bin", "/bin/bash")


def _bind_paths(run, runtime):
    root = Path(os.path.abspath(run.root))
    project = Path(os.path.abspath(run.project))
    if project.parent != root / live.WORKSPACE or project == project.parent:
        raise IsolationUnavailable("fixture escaped its owned workspace")
    paths = ClaudePaths(root, project, root / "claude-config", root / "tmp", root / "cache", root / "xdg", root / "transcripts")
    fd = _open_dir(root)
    os.close(fd)
    for path in (paths.config, paths.tmp, paths.cache, paths.xdg, paths.transcripts):
        path.mkdir(mode=0o700, exist_ok=True)
    identities = []
    for path in sorted({*project.parents, project, paths.config, paths.tmp, paths.cache, paths.xdg, paths.transcripts, *runtime.read_trees}):
        fd = _open_dir(path)
        identity = os.fstat(fd)
        os.close(fd)
        identities.append((path, identity.st_dev, identity.st_ino))
    state = ClaudeState(paths, runtime, tuple(identities), str(uuid.uuid4()))
    run._claude_state = state
    return state


def _validate(state):
    for path, device, inode in state.identities:
        fd = _open_dir(path)
        identity = os.fstat(fd)
        os.close(fd)
        if (identity.st_dev, identity.st_ino) != (device, inode):
            raise IsolationUnavailable(f"owned directory was replaced: {path}")
    for path, digest in state.runtime.fingerprints:
        if path.is_symlink() or _digest(path) != digest:
            raise IsolationUnavailable(f"supported executable changed: {path}")


def _state(run):
    try:
        state = run._claude_state
    except AttributeError as error:
        raise IsolationUnavailable("Claude run has no evaluator-owned preparation state") from error
    _validate(state)
    return state


def config_dir(run):
    return _state(run).paths.config


def store(run):
    return config_dir(run) / "projects"


def prepare(run):
    state = _bind_paths(run, _host_runtime())
    script = state.paths.project / SKILLS_DIR / "pstack-harness/scripts/subagents.py"
    done = subprocess.run([sys.executable, str(script), "install", "--harness", "claude-code",
                           "--project", str(state.paths.project)], capture_output=True, text=True)
    (state.paths.root / "agents-install.json").write_text(done.stdout)
    report = json.loads(done.stdout or "{}")
    rows = [*report.get("roles", []), *report.get("efforts", [])]
    if done.returncode or report.get("payload") != "ready" or not rows or any(r["native_file"] != "current" for r in rows):
        raise RuntimeError(f"persona registration failed: {done.stdout}{done.stderr}")
    (state.paths.project / ".claude/settings.json").write_text(json.dumps({"attribution": {"commit": "", "pr": ""}}) + "\n")
    _validate(state)
    profile = _policy(state, 0)
    done = subprocess.run(["/usr/bin/sandbox-exec", "-p", profile, "/usr/bin/true"], cwd=state.paths.project,
                          env=child_env(run), capture_output=True, timeout=10)
    if done.returncode:
        raise IsolationUnavailable(f"Seatbelt policy preflight failed: {done.stderr.decode(errors='replace')}")


def child_env(run):
    state = _state(run)
    paths, runtime = state.paths, state.runtime
    env = {"HOME": str(runtime.home), "USER": runtime.user, "LOGNAME": runtime.user, "SHELL": runtime.shell,
           "PATH": runtime.path_env, "LANG": "en_US.UTF-8", "TERM": "dumb", "CLAUDE_CONFIG_DIR": str(paths.config),
           "CLAUDE_SECURESTORAGE_CONFIG_DIR": "", "TMPDIR": str(paths.tmp), "TMP": str(paths.tmp), "TEMP": str(paths.tmp),
           "CLAUDE_CODE_TMPDIR": str(paths.tmp), "XDG_RUNTIME_DIR": str(paths.tmp), "XDG_CACHE_HOME": str(paths.cache),
           "XDG_CONFIG_HOME": str(paths.xdg / "config"), "XDG_DATA_HOME": str(paths.xdg / "data"), "XDG_STATE_HOME": str(paths.xdg / "state"),
           "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_NOSYSTEM": "1", "PIP_CACHE_DIR": str(paths.cache / "pip"),
           "NPM_CONFIG_CACHE": str(paths.cache / "npm")}
    if run.case.get("env", {}).get("todo_tools"):
        env["CLAUDE_CODE_ENABLE_TODO_TOOLS"] = "1"
    return env


def _policy(state, index):
    paths, runtime = state.paths, state.runtime
    literal = lambda p: f"(literal {json.dumps(str(p), ensure_ascii=False)})"
    subtree = lambda p: f"(subpath {json.dumps(str(p), ensure_ascii=False)})"
    writes = (paths.project, paths.config, paths.tmp, paths.cache, paths.xdg)
    ancestors = {parent for p in (*runtime.read_files, *runtime.read_trees, *writes) for parent in p.parents}
    ancestors.update(Path(p) for p in ("/etc", "/var", "/tmp", "/private/etc/resolv.conf", "/private/etc/localtime"))
    ancestors.update((paths.root / f"stream-{index}.jsonl", paths.root / f"stderr-{index}.txt"))
    rules = ["(version 1)", "(allow default)", "(deny file-read*)", "(deny file-write*)",
             "(allow file-read* " + " ".join(map(literal, runtime.read_files)) + ")",
             "(allow file-read* " + " ".join(map(subtree, runtime.read_trees)) + ")",
             "(allow file-read* file-write* " + " ".join(map(subtree, writes)) + ")",
             "(allow file-read-metadata " + " ".join(map(literal, sorted(ancestors))) + ")",
             '(allow file-write* (literal "/dev/null") (subpath "/dev/fd"))',
             "(deny file-write-unlink " + " ".join(map(literal, writes)) + ")"]
    return "\n".join(rules)


def _command(run, text, index):
    state = _state(run)
    if index != len(state.records):
        raise IsolationUnavailable("Claude turns must follow evaluator-owned session order")
    skill, rest = live.split_entry(run.case, text, index)
    prompt = f"/{skill} {rest}".rstrip() if skill else text
    pin = ["--session-id" if index == 0 else "--resume", state.session]
    argv = ["/usr/bin/sandbox-exec", "-p", _policy(state, index), str(state.runtime.binary),
            "-p", "--output-format", "stream-json", "--verbose", "--setting-sources", "project",
            "--strict-mcp-config", "--mcp-config", '{"mcpServers":{}}', "--permission-mode", "bypassPermissions", *pin]
    effort = run.case.get("effort", DEFAULT_EFFORT)
    if effort:
        argv += ["--effort", effort]
    if run.case.get("model"):
        argv += ["--model", run.case["model"]]
    argv.append(prompt)
    return ConfinedCommand(tuple(argv), child_env(run), state.session)


def turn(run, text, index):
    command = _command(run, text, index)
    state = _state(run)
    stream, stderr = state.paths.root / f"stream-{index}.jsonl", state.paths.root / f"stderr-{index}.txt"
    for path in (stream, stderr):
        if path.exists() or path.is_symlink():
            raise IsolationUnavailable(f"evaluator output already exists: {path}")
    record = live.execute(command.argv, state.paths.project, command.env, run.timeout_s, stream, stderr)
    record = {**record, "session_id": command.session, "index": index, "stream": str(stream), "stderr": str(stderr)}
    run._claude_state = replace(state, records=(*state.records, record.copy()))
    _validate(state)
    return record


def _read_file(fd, name):
    source = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
    try:
        before = os.fstat(source)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
            raise IsolationUnavailable(f"unsafe evidence file: {name}")
        data = bytearray()
        while part := os.read(source, 1024 * 1024):
            data.extend(part)
        after = os.fstat(source)
        named = os.stat(name, dir_fd=fd, follow_symlinks=False)
        stamp = lambda row: (row.st_dev, row.st_ino, row.st_size, row.st_mtime_ns, row.st_ctime_ns, row.st_nlink)
        if stamp(before) != stamp(after) or stamp(after) != stamp(named):
            raise IsolationUnavailable(f"evidence changed during collection: {name}")
        return bytes(data)
    finally:
        os.close(source)


def _tree(fd, prefix=Path()):
    before = os.fstat(fd)
    found = {}
    for name in sorted(os.listdir(fd)):
        row = os.stat(name, dir_fd=fd, follow_symlinks=False)
        relative = prefix / name
        if stat.S_ISDIR(row.st_mode):
            child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            try:
                opened = os.fstat(child)
                if (row.st_dev, row.st_ino) != (opened.st_dev, opened.st_ino):
                    raise IsolationUnavailable(f"evidence directory replaced: {relative}")
                found.update(_tree(child, relative))
                named = os.stat(name, dir_fd=fd, follow_symlinks=False)
                if (opened.st_dev, opened.st_ino) != (named.st_dev, named.st_ino):
                    raise IsolationUnavailable(f"evidence directory replaced: {relative}")
            finally:
                os.close(child)
        elif stat.S_ISREG(row.st_mode):
            found[relative] = _read_file(fd, name)
        else:
            raise IsolationUnavailable(f"linked or special evidence: {relative}")
    after = os.fstat(fd)
    if (before.st_mtime_ns, before.st_ctime_ns) != (after.st_mtime_ns, after.st_ctime_ns):
        raise IsolationUnavailable(f"evidence directory changed during collection: {prefix}")
    return found


def _snapshot(state):
    _validate(state)
    source = state.paths.config / "projects"
    fd = _open_dir(source)
    source_identity = os.fstat(fd)
    evidence = {}
    try:
        leads = []
        for slug in sorted(os.listdir(fd)):
            row = os.stat(slug, dir_fd=fd, follow_symlinks=False)
            if not stat.S_ISDIR(row.st_mode):
                raise IsolationUnavailable(f"unsafe native project directory: {slug}")
            child = os.open(slug, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            try:
                opened = os.fstat(child)
                if (opened.st_dev, opened.st_ino) != (row.st_dev, row.st_ino):
                    raise IsolationUnavailable(f"native project directory replaced: {slug}")
                names = os.listdir(child)
                lead = f"{state.session}.jsonl"
                if lead not in names:
                    continue
                leads.append(slug)
                evidence[Path(slug) / lead] = _read_file(child, lead)
                if state.session in names:
                    session_fd = os.open(state.session, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=child)
                    try:
                        evidence.update(_tree(session_fd, Path(slug) / state.session))
                    finally:
                        os.close(session_fd)
                named = os.stat(slug, dir_fd=fd, follow_symlinks=False)
                after = os.fstat(child)
                if (opened.st_dev, opened.st_ino, opened.st_mtime_ns, opened.st_ctime_ns) != (
                        named.st_dev, named.st_ino, after.st_mtime_ns, after.st_ctime_ns):
                    raise IsolationUnavailable(f"native project directory changed: {slug}")
            finally:
                os.close(child)
        if len(leads) != 1:
            raise IsolationUnavailable(f"expected one native lead transcript, found {len(leads)}")
        after = os.fstat(fd)
        named = _open_dir(source)
        try:
            current = os.fstat(named)
            if (source_identity.st_dev, source_identity.st_ino, source_identity.st_mtime_ns, source_identity.st_ctime_ns) != (
                    current.st_dev, current.st_ino, after.st_mtime_ns, after.st_ctime_ns):
                raise IsolationUnavailable("native projects root changed during collection")
        finally:
            os.close(named)
    except OSError as error:
        raise IsolationUnavailable("unsafe native session evidence") from error
    finally:
        os.close(fd)
    _validate(state)
    digest = hashlib.sha256()
    for path, data in sorted(evidence.items()):
        digest.update(str(path).encode() + b"\0" + hashlib.sha256(data).digest())
    snapshot = state.paths.transcripts / f"snapshot-{len(state.records):04d}-{digest.hexdigest()}"
    if snapshot.exists():
        fd = _open_dir(snapshot)
        try:
            if _tree(fd) != evidence:
                raise IsolationUnavailable("retained snapshot was changed")
        finally:
            os.close(fd)
    else:
        stage = state.paths.transcripts / f".stage-{uuid.uuid4()}"
        stage.mkdir(mode=0o700)
        try:
            for path, data in evidence.items():
                target = stage / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
            _validate(state)
            stage.rename(snapshot)
        except BaseException:
            shutil.rmtree(stage)
            raise
    return snapshot, evidence


def _evidence(run, session):
    state = getattr(run, "_claude_state", None)
    if state is not None:
        return _snapshot(_state(run))
    root = Path(os.path.abspath(run.root)) / "transcripts"
    fd = _open_dir(root)
    try:
        snapshots = [name for name in os.listdir(fd) if re.fullmatch(rf"snapshot-{len(run.turns):04d}-[0-9a-f]{{64}}", name)]
        if len(snapshots) > 1:
            raise IsolationUnavailable("retained snapshot selection is ambiguous")
        if snapshots:
            root = root / snapshots[0]
            child = os.open(snapshots[0], os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            try:
                all_files = _tree(child)
            finally:
                os.close(child)
        else:
            all_files = _tree(fd)
    finally:
        os.close(fd)
    leads = [p for p in all_files if p.name == f"{session}.jsonl" and len(p.parts) == 2]
    if len(leads) != 1:
        raise IsolationUnavailable(f"expected one retained lead transcript, found {len(leads)}")
    lead = leads[0]
    return root, {p: data for p, data in all_files.items() if p == lead or p.is_relative_to(lead.with_suffix(""))}


def _stream_rows(root, index):
    fd = _open_dir(Path(os.path.abspath(root)))
    try:
        try:
            data = _read_file(fd, f"stream-{index}.jsonl")
        except FileNotFoundError:
            return []
        return _jsonl(data)
    finally:
        os.close(fd)


def _jsonl(data):
    rows = []
    for line in data.decode(errors="replace").split("\n"):
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def load_jsonl(path):
    return _jsonl(Path(path).read_bytes())


def blocks(entry):
    content = entry.get("message", {}).get("content")
    if isinstance(content, str):
        return [{"type": "text", "text": content}]
    return content or []


def result_text(block):
    content = block.get("content")
    if isinstance(content, list):
        return "\n".join(part.get("text", "") for part in content if isinstance(part, dict))
    return content or ""


def shell_reads(command, cwd):
    try:
        lexer = shlex.shlex(command, posix=True, punctuation_chars=";&|")
        lexer.whitespace_split = True
        tokens = list(lexer)
    except ValueError:
        return []
    segments, current = [], []
    for token in tokens:
        if token in SEPARATORS or set(token) <= set(";&|"):
            segments.append(current)
            current = []
        else:
            current.append(token)
    segments.append(current)
    here, found, names = Path(cwd), [], {}
    for segment in segments:
        while segment and ASSIGN.match(segment[0]):
            key, value = segment.pop(0).split("=", 1)
            names[key] = value
        if segment and segment[0] == "export":
            for token in segment[1:]:
                if ASSIGN.match(token):
                    key, value = token.split("=", 1)
                    names[key] = value
            continue
        segment = [VAR.sub(lambda m: names.get(m.group(1) or m.group(2), m.group(0)), token) for token in segment]
        if not segment:
            continue
        name = Path(segment[0]).name
        if name == "cd" and len(segment) > 1:
            here = Path(os.path.normpath(here / segment[1]))
            continue
        if name not in READ_COMMANDS:
            continue
        for arg in segment[1:]:
            if not arg or arg[0] in "-<>":
                continue
            path = Path(arg) if arg.startswith("/") else here / arg
            found.append(os.path.normpath(path))
    return found


def files_read(rows, cwd):
    paths = []
    for entry in rows:
        if entry.get("type") != "assistant":
            continue
        for block in blocks(entry):
            if block.get("type") != "tool_use":
                continue
            given = block.get("input", {})
            if block["name"] == "Read" and given.get("file_path"):
                path = Path(given["file_path"])
                paths.append(os.path.normpath(path if path.is_absolute() else Path(cwd) / path))
            elif block["name"] == "Bash" and given.get("command"):
                paths.extend(shell_reads(given["command"], entry.get("cwd") or cwd))
    return list(dict.fromkeys(paths))


def prompt_text(entry):
    text = "\n".join(b.get("text", "") for b in blocks(entry) if b.get("type") == "text")
    name = COMMAND_NAME.search(text)
    if not name:
        return text
    args = COMMAND_ARGS.search(text)
    return f"{name.group(1)} {args.group(1) if args else ''}".strip()


def is_prompt(entry):
    if entry.get("type") != "user" or entry.get("isMeta") or entry.get("isSidechain"):
        return False
    parts = blocks(entry)
    if not parts or any(p.get("type") == "tool_result" for p in parts):
        return False
    text = prompt_text(entry).strip()
    return bool(text) and not text.startswith(("<task-notification", "<system-reminder", "[Request interrupted"))


def tag_turns(rows):
    turn, seen, tagged = 0, False, []
    for entry in rows:
        if is_prompt(entry):
            turn += seen
            seen = True
        tagged.append((turn, entry))
    return tagged


def lead_events(rows):
    events = []
    names = {}

    def add(turn, event):
        events.append({"seq": len(events), "turn": turn, **event})

    for turn, entry in tag_turns(rows):
        kind = entry.get("type")
        if kind not in ("assistant", "user"):
            continue
        if is_prompt(entry):
            add(turn, {"kind": "user", "text": prompt_text(entry)})
            continue
        if entry.get("isMeta"):
            continue
        for block in blocks(entry):
            if block.get("type") == "tool_use":
                names[block["id"]] = block["name"]
                add(turn, {"kind": "tool_call", "name": block["name"], "input": block.get("input", {}), "id": block["id"]})
            elif block.get("type") == "tool_result":
                add(turn, {"kind": "tool_result", "name": names.get(block.get("tool_use_id"), "?"),
                           "ok": not block.get("is_error", False), "output_head": result_text(block)[:400],
                           "id": block.get("tool_use_id")})
            elif block.get("type") == "text" and kind == "assistant" and block.get("text", "").strip():
                add(turn, {"kind": "text", "text": block["text"]})
    return events


def native_worklist(events):
    tasks, order, snapshots = {}, [], []
    results = {e["id"]: e for e in events if e["kind"] == "tool_result"}
    for event in events:
        if event["kind"] != "tool_call":
            continue
        name, given = event["name"], event["input"]
        if name == "TodoWrite":
            items = [{"text": t.get("content", ""), "state": t.get("status", "pending").replace("_", " ")}
                     for t in given.get("todos", [])]
            snapshots.append({"seq": event["seq"], "turn": event["turn"], "carrier": name, "items": items})
            continue
        if name == "TaskCreate":
            match = TASK_ID.search(results.get(event["id"], {}).get("output_head", ""))
            task_id = match.group(1) if match else f"?{len(order) + 1}"
            tasks[task_id] = {"text": given.get("subject") or given.get("description", ""), "state": "pending"}
            order.append(task_id)
        elif name == "TaskUpdate":
            task_id = str(given.get("taskId"))
            task = tasks.setdefault(task_id, {"text": "?", "state": "pending"})
            if task_id not in order:
                order.append(task_id)
            if given.get("subject"):
                task["text"] = given["subject"]
            if given.get("status"):
                status = given["status"].replace("_", " ")
                task["state"] = "skipped: deleted" if status == "deleted" else status
            note = (given.get("description") or "").strip()
            if note.lower().startswith("skipped"):
                task["state"] = "skipped: " + note.split(":", 1)[-1].strip()[:200]
        else:
            continue
        snapshots.append({"seq": event["seq"], "turn": event["turn"], "carrier": name, "items": [dict(tasks[t]) for t in order]})
    return snapshots


def text_worklist(events):
    return [{"seq": e["seq"], "turn": e["turn"], "carrier": "text", "items": items}
            for e in events if e["kind"] == "text" and (items := live.chat_worklist(e["text"]))]

def observed(rows):
    assistants = [e for e in rows if e.get("type") == "assistant"]
    return {"models": sorted({e.get("message", {}).get("model") for e in assistants} - {None, "<synthetic>"}),
            "efforts": sorted({e.get("perTurnEffort") or e.get("effort") for e in assistants} - {None})}


def first_reply(rows):
    for entry in rows:
        if entry.get("type") == "assistant":
            for block in blocks(entry):
                if block.get("type") == "text" and block.get("text", "").strip():
                    return block["text"]
    return None


def spawns(events, session_dir, evidence):
    metas = {}
    for path, contents in sorted(evidence.items()):
        if path.parent.name != "subagents" or not path.name.endswith(".meta.json"):
            continue
        data = json.loads(contents)
        if data.get("toolUseId") in metas:
            raise IsolationUnavailable("duplicate native child metadata")
        metas[data.get("toolUseId")] = (data, session_dir / "subagents" / path.name, path)
    found = []
    for event in events:
        if event["kind"] != "tool_call" or event["name"] not in SPAWN_TOOLS:
            continue
        given = event["input"]
        meta, meta_path, relative = metas.get(event["id"], ({}, None, None))
        agent_type = given.get("subagent_type") or meta.get("agentType")
        effort = agent_type.removeprefix("pstack-effort-") if agent_type and agent_type.startswith("pstack-effort-") else None
        prompt = given.get("prompt", "")
        persona = agent_type if agent_type and not effort else None
        if effort:
            persona = next((p for p in ("poteto-agent", "comment-sicko") if p in prompt[:2000]), None)
        transcript = Path(str(meta_path).removesuffix(".meta.json") + ".jsonl") if meta_path else None
        child_path = Path(str(relative).removesuffix(".meta.json") + ".jsonl") if relative else None
        child = _jsonl(evidence[child_path]) if child_path in evidence else None
        reply = first_reply(child) if child else None
        line = PERSONA_LINE.search(reply or "")
        found.append({"seq": event["seq"], "turn": event["turn"], "tool": event["name"], "subagent_type": agent_type, "persona": persona,
                      "model": given.get("model") or meta.get("model"), "effort": effort, "prompt_head": prompt[:300],
                      "transcript": str(transcript) if transcript else None,
                      "observed": observed(child) if child else None,
                      "x_child_first_reply": reply[:200] if reply else None,
                      "x_persona_line": line.group(1) if line else None})
    return found


def entry_state(entry_skill, init, rows):
    if not entry_skill:
        return "not-observed"
    if init and entry_skill not in (init.get("skills") or []) and entry_skill not in (init.get("slash_commands") or []):
        return "not-registered"
    for entry in rows:
        for block in blocks(entry) if entry.get("type") == "user" else []:
            if f"<command-name>/{entry_skill}</command-name>" in (block.get("text", "") if block.get("type") == "text" else ""):
                return "injected"
        for block in blocks(entry) if entry.get("type") == "assistant" else []:
            if block.get("type") == "tool_use" and block["name"] == "Skill" and block.get("input", {}).get("skill", "").lstrip("/") == entry_skill:
                return "injected"
    return "not-observed"


def injected_base(rows):
    for entry in rows:
        if entry.get("type") == "user" and entry.get("isMeta"):
            for block in blocks(entry):
                match = re.match(r"Base directory for this skill: (\S+)", block.get("text", ""))
                if match:
                    return match.group(1)
    return None


def host_skill_hits(contents):
    roots = [str(Path.home() / ".claude/skills"), str(Path.home() / ".agents/skills")]
    return sorted({root for data in contents for root in roots if root in data.decode(errors="replace")})


def harvest(run):
    prepared = getattr(run, "_claude_state", None)
    turns = prepared.records if prepared is not None else run.turns
    session = prepared.session if prepared is not None else turns[0]["session_id"] if turns else None
    if session is not None and str(uuid.UUID(session)) != session:
        raise IsolationUnavailable("invalid native session identity")
    transcripts, evidence = _evidence(run, session) if session else (run.root / "transcripts", {})
    main = next((p for p in evidence if p.name == f"{session}.jsonl"), None)
    main_paths = [transcripts / main] if main else []
    rows = _jsonl(evidence[main]) if main else []
    session_dir = main_paths[0].with_suffix("") if main else run.root / "missing"
    delegates = sorted(p for p in evidence if p.parent.name == "subagents" and p.suffix == ".jsonl")
    delegate_paths = [transcripts / p for p in delegates]
    cwd = str(prepared.paths.project if prepared else run.project)

    streams = [_stream_rows(prepared.paths.root if prepared else run.root, i) for i in range(len(turns))]
    init = next((e for s in streams for e in s if e.get("subtype") == "init"), {})
    results = [next((e for e in reversed(s) if e.get("type") == "result"), {}) for s in streams]
    events = lead_events(rows)
    reads_by = {"lead": files_read(rows, cwd)}
    for path in delegates:
        reads_by[path.stem] = files_read(_jsonl(evidence[path]), cwd)
    state = entry_state(run.case.get("entry"), init, rows)
    if state == "not-observed" and any(p.endswith(f"/{run.case.get('entry')}/SKILL.md") for p in reads_by["lead"]):
        state = "read"
    tagged = tag_turns(rows)
    turn_entries = []
    for i in range(len(turns)):
        skill, _ = live.split_entry(run.case, run.case["turns"][i], i)
        if skill:
            turn_entries.append({"turn": i, "skill": skill,
                                 "entry": entry_state(skill, init, [e for t, e in tagged if t == i])})
    final = results[-1].get("result") if results else None
    if final is None:
        final = next((e["text"] for e in reversed(events) if e["kind"] == "text"), "")
    spawn_rows = spawns(events, session_dir, evidence)
    argvs = [t["argv"] for t in turns]
    requested = next((a[i + 1] for a in argvs[:1] for i, v in enumerate(a) if v == "--effort"), None)
    return {
        "harness": "claude-code",
        "cli_version": init.get("claude_code_version"),
        "model": init.get("model"),
        "effort": ",".join(observed(rows)["efforts"]) or requested,
        "argv": argvs[0] if argvs else [],
        "cwd": cwd,
        "exit_code": turns[-1]["exit_code"] if turns else None,
        "duration_s": round(sum(t["duration_s"] for t in turns), 1),
        "entry": state,
        "events": events,
        "files_read": list(dict.fromkeys(p for paths in reads_by.values() for p in paths)),
        "worklist": sorted(native_worklist(lead_events(rows)) + text_worklist(events), key=lambda s: s["seq"]),
        "spawns": spawn_rows,
        "final_reply": final,
        "transcript_paths": [str(p) for p in [*main_paths, *delegate_paths]],
        "x_session_id": session,
        "x_argvs": argvs,
        "x_turn_exit_codes": [t["exit_code"] for t in turns],
        "x_timed_out": any(t["timed_out"] for t in turns),
        "x_effort_requested": requested,
        "x_todo_tools": "on" if run.case.get("env", {}).get("todo_tools") else "off",
        "x_turn_entries": turn_entries,
        "x_entry_base_dir": injected_base(rows),
        "x_files_read_by": reads_by,
        "x_cost_usd": round(sum(r.get("total_cost_usd") or 0 for r in results), 4),
        "x_deferred_tools": next((e["attachment"].get("addedNames") for e in rows if e.get("type") == "attachment"
                                  and e["attachment"].get("type") == "deferred_tools_delta"), None),
        "x_init_tools": init.get("tools"),
        "x_host_skill_hits": host_skill_hits(evidence.values()),
        "x_evidence_snapshot": str(transcripts),
        "x_evidence_complete": bool(turns) and all(not t["timed_out"] and t["exit_code"] == 0 for t in turns)
            and all(r.get("subtype") == "success" for r in results)
            and all(s["observed"] is not None for s in spawn_rows)
            and not any(e["kind"] == "tool_call" and e["input"].get("run_in_background") for e in events),
    }
