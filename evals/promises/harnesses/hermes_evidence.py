from __future__ import annotations

import hashlib
import json
import os
import re
import signal
import sqlite3
import stat
import struct
import subprocess
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

GATEWAY_CONTAINER = "hermes-default-gateway"
HERMES_BIN = "/opt/hermes/.venv/bin/hermes"
PYTHON_BIN = "/opt/hermes/.venv/bin/python"
USER_HERMES = Path.home() / ".hermes"
DOCKER_ENV_KEYS = ("PATH", "HOME", "DOCKER_HOST", "DOCKER_CONTEXT", "DOCKER_CONFIG")
TOOLSETS = ("delegation", "file", "skills", "terminal", "todo")
STATE_MEMBERS = ("state.db", "state.db-wal", "state.db-shm")
MAX_BYTES = 128 * 1024 * 1024
MAX_ENTRIES = 20000
MAX_ROWS = 50000
MAX_DEPTH = 64
INTEGRITY_FTS_COLUMNS = {
    "messages_fts_config": ("k", "v"),
    "messages_fts_trigram_config": ("k", "v"),
    "messages_fts_idx": ("segid", "term", "pgno"),
    "messages_fts_trigram_idx": ("segid", "term", "pgno"),
}
PRELOAD_CHECK = """
import json, sys
sys.path.insert(0, "/opt/hermes")
from agent.skill_commands import build_preloaded_skills_prompt
text, loaded, missing = build_preloaded_skills_prompt([sys.argv[1]])
print(json.dumps({"loaded": loaded, "missing": missing, "chars": len(text)}))
"""
CONFIG = """{model}agent:
  max_turns: 90
  reasoning_effort: high
terminal:
  backend: local
  cwd: {project}
  timeout: 300
skills:
  trusted_project_dirs:
    - {project}
delegation:
  max_concurrent_children: 4
  max_spawn_depth: 1
  subagent_auto_approve: true
  oneshot_max_children: 0
platform_toolsets:
  cli:
{toolsets}{tools}"""
EAGER_TOOLS = 'tools:\n  tool_search:\n    enabled: "off"\n'


@dataclass(frozen=True)
class FrozenArray:
    items: tuple


@dataclass(frozen=True)
class FrozenObject:
    items: tuple


def freeze(value):
    if isinstance(value, dict):
        return FrozenObject(tuple((k, freeze(v)) for k, v in value.items()))
    if isinstance(value, list):
        return FrozenArray(tuple(freeze(v) for v in value))
    if value is None or type(value) in (str, int, float, bool):
        return value
    raise ValueError("invalid JSON value")


def thaw(value):
    if isinstance(value, FrozenObject):
        return {k: thaw(v) for k, v in value.items}
    if isinstance(value, FrozenArray):
        return [thaw(v) for v in value.items]
    return value


@dataclass(frozen=True)
class RunBinding:
    run_id: str
    root: Path
    project: Path
    private_parent: Path


@dataclass(frozen=True)
class NativeSetup:
    image_override: str | None
    model_block: str
    entry: str | None
    preload_skills: tuple[str, ...]
    todo_eager: bool
    todo_tools: Literal["on", "off"]


@dataclass(frozen=True)
class NativeTurn:
    index: int
    arguments: tuple[str, ...]


@dataclass(frozen=True)
class CapturedTurn:
    index: int
    record: FrozenObject


@dataclass(frozen=True)
class WriterObservation:
    launch_index: int
    name: str
    container_id: str | None
    disposition: Literal["removed", "verified-absent", "unknown"]
    receipt_member: str


@dataclass(frozen=True)
class SourceStamp:
    device: int
    inode: int
    size: int
    mtime_ns: int
    ctime_ns: int
    link_count: int


@dataclass(frozen=True)
class PresentBytes:
    member: str
    size: int
    sha256: str
    source: SourceStamp


@dataclass(frozen=True)
class AbsentSidecar:
    member: str


@dataclass(frozen=True)
class DatabaseSet:
    main: PresentBytes
    wal: PresentBytes | AbsentSidecar
    shm: PresentBytes | AbsentSidecar


@dataclass(frozen=True)
class FixtureEntry:
    components: tuple[str, ...]
    kind: str


@dataclass(frozen=True)
class FixtureInventory:
    original_spelling: str
    entries: tuple[FixtureEntry, ...]


@dataclass(frozen=True)
class SessionRecords:
    session: FrozenObject
    messages: tuple[FrozenObject, ...]


@dataclass(frozen=True)
class Acquisition:
    run_id: str
    id: str
    provenance: str
    database: DatabaseSet
    writers: tuple[WriterObservation, ...]
    retained_members: tuple[str, ...]


@dataclass(frozen=True)
class CompleteEvidence:
    meta: FrozenObject
    turns: tuple[CapturedTurn, ...]
    acquisition: Acquisition
    sessions: tuple[SessionRecords, ...]
    fixture: FixtureInventory
    retained_paths: tuple[str, ...]


@dataclass(frozen=True)
class IncompleteEvidence:
    run_id: str
    acquisition_id: str
    reason: str
    detail: str
    meta: FrozenObject | None
    turns: tuple[CapturedTurn, ...]
    retained_paths: tuple[str, ...]


@dataclass(frozen=True)
class OwnedExport:
    destination: Path


@dataclass(frozen=True)
class RetainedPair:
    root: Path
    run_id: str
    acquisitions: tuple[str, ...]
    manifest_member: str = "pair.json"


@dataclass(frozen=True)
class ReplayBinding:
    pair_root: Path
    expected_run_id: str
    acquisition_id: str


@dataclass(frozen=True)
class LegacyReplayBinding:
    root: Path
    original_fixture_spelling: str
    fixture_components: tuple[str, ...]
    source_kind: Literal["native-profile", "legacy-copied"]
    evaluator_offline_assertion: str


class EvidenceRefused(RuntimeError):
    def __init__(self, reason, detail):
        super().__init__(detail)
        self.reason = reason


class RetentionUnavailable(RuntimeError):
    pass


@dataclass
class _Directory:
    path: Path
    fd: int
    parent: int | None
    name: str
    identity: tuple[int, int]


def _identity(info):
    return info.st_dev, info.st_ino


def _stamp(info):
    return SourceStamp(info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns, info.st_nlink)


def _components(path):
    value = str(path)
    parts = value.split("/")
    if not value or value.startswith("/") or any(p in ("", ".", "..") for p in parts):
        raise EvidenceRefused("path-refused", f"invalid member {value!r}")
    return tuple(parts)


def _name(value):
    if len(_components(value)) != 1:
        raise EvidenceRefused("path-refused", f"single member name required: {value!r}")


def _session_id(data):
    for line in data.decode("utf-8", "replace").splitlines():
        if line.startswith("{"):
            try:
                event = json.loads(line)
            except ValueError:
                continue
            if isinstance(event, dict) and event.get("type") in ("system", "result"):
                sid = event.get("session_id")
                if isinstance(sid, str) and sid:
                    return sid
        elif line.startswith("session_id: ") and line[12:].strip():
            return line[12:].strip()
    return None


class HermesEvidence:
    @classmethod
    def bind(cls, binding: RunBinding, timeout_s: int):
        owner = cls()
        owner.binding = binding
        owner.timeout_s = timeout_s
        owner._dirs = []
        owner._catalog = {}
        owner._turns = ()
        owner._writers = ()
        owner._attempts = []
        owner._meta = None
        owner._provenance = "native-stopped"
        owner._replay_error = None
        owner._source = None
        owner._capture_index = 0
        owner._profile = None
        owner._setup_files = []
        try:
            if not binding.run_id or not binding.project.is_relative_to(binding.root):
                raise EvidenceRefused("path-refused", "fixture must be inside the bound run")
            if binding.private_parent.is_relative_to(binding.root):
                raise EvidenceRefused("path-refused", "private evidence must be outside the run mount")
            owner._root = owner._absolute(binding.root)
            owner._fixture_components = binding.project.relative_to(binding.root).parts
            owner._fixture = owner._walk(owner._root, owner._fixture_components)
            parent = owner._absolute(binding.private_parent)
            owner._private = owner._mkdir(parent, "hermes-evidence-" + uuid.uuid4().hex)
            owner.private_root = owner._private.path
            owner._captures = owner._mkdir(owner._private, "captures")
            owner._acquisitions = owner._mkdir(owner._private, "acquisitions")
            owner._save("binding.json", {"run_id": binding.run_id, "root": str(binding.root),
                        "project": str(binding.project), "fixture_components": owner._fixture_components})
            return owner
        except BaseException:
            owner.close()
            raise

    def _absolute(self, path):
        path = Path(path)
        if not path.is_absolute() or ".." in path.parts:
            raise EvidenceRefused("path-refused", f"absolute evaluator path required: {path}")
        fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        directory = _Directory(Path("/"), fd, None, "", _identity(os.fstat(fd)))
        self._dirs.append(directory)
        return self._walk(directory, path.parts[1:], same_device=False)

    def _walk(self, directory, parts, same_device=True):
        for name in parts:
            _name(name)
            cached = next((d for d in self._dirs if d.parent == directory.fd and d.name == name), None)
            if cached is not None:
                info = os.stat(name, dir_fd=directory.fd, follow_symlinks=False)
                if not stat.S_ISDIR(info.st_mode) or _identity(info) != cached.identity:
                    raise EvidenceRefused("identity-changed", f"replaced directory: {cached.path}")
                directory = cached
                continue
            info = os.stat(name, dir_fd=directory.fd, follow_symlinks=False)
            if not stat.S_ISDIR(info.st_mode) or (same_device and info.st_dev != directory.identity[0]):
                raise EvidenceRefused("path-refused", f"directory refused: {directory.path / name}")
            fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory.fd)
            if _identity(info) != _identity(os.fstat(fd)):
                os.close(fd)
                raise EvidenceRefused("identity-changed", f"directory changed: {name}")
            directory = _Directory(directory.path / name, fd, directory.fd, name, _identity(info))
            self._dirs.append(directory)
        return directory

    def _mkdir(self, parent, name):
        _name(name)
        os.mkdir(name, mode=0o700, dir_fd=parent.fd)
        return self._walk(parent, (name,))

    def _check(self, private_only=False):
        for directory in self._dirs:
            if private_only and not (directory.path.is_relative_to(self.private_root) or self.private_root.is_relative_to(directory.path)):
                continue
            if _identity(os.fstat(directory.fd)) != directory.identity:
                raise EvidenceRefused("identity-changed", f"detached directory: {directory.path}")
            if directory.parent is not None:
                info = os.stat(directory.name, dir_fd=directory.parent, follow_symlinks=False)
                if not stat.S_ISDIR(info.st_mode) or _identity(info) != directory.identity:
                    raise EvidenceRefused("identity-changed", f"replaced directory: {directory.path}")
        if private_only:
            return
        for directory, name, identity in self._setup_files:
            info = os.stat(name, dir_fd=directory.fd, follow_symlinks=False)
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or _identity(info) != identity:
                raise EvidenceRefused("identity-changed", f"prepared entry replaced: {name}")
        if any(w.disposition == "unknown" for w in self._writers):
            raise EvidenceRefused("termination-unknown", "an earlier native writer has unknown termination")

    def _open(self, directory, name):
        _name(name)
        info = os.stat(name, dir_fd=directory.fd, follow_symlinks=False)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_dev != directory.identity[0]:
            raise EvidenceRefused("path-refused", f"regular single-link file required: {directory.path / name}")
        if info.st_size > MAX_BYTES:
            raise EvidenceRefused("resource-limit", f"file exceeds byte limit: {name}")
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory.fd)
        if _stamp(os.fstat(fd)) != _stamp(info):
            os.close(fd)
            raise EvidenceRefused("identity-changed", f"file changed before open: {name}")
        return fd, _stamp(info)

    def _bytes(self, directory, name):
        fd, stamp = self._open(directory, name)
        try:
            data = self._read_fd(fd)
            if _stamp(os.fstat(fd)) != stamp:
                raise EvidenceRefused("source-changed", f"file changed during read: {name}")
            return data
        finally:
            os.close(fd)

    @staticmethod
    def _read_fd(fd):
        os.lseek(fd, 0, os.SEEK_SET)
        chunks, count = [], 0
        while chunk := os.read(fd, 1024 * 1024):
            count += len(chunk)
            if count > MAX_BYTES:
                raise EvidenceRefused("resource-limit", "byte limit exceeded")
            chunks.append(chunk)
        return b"".join(chunks)

    def _write(self, directory, name, data):
        _name(name)
        fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory.fd)
        with os.fdopen(fd, "wb") as output:
            output.write(data)
            output.flush()
            os.fsync(output.fileno())
        if directory.path.is_relative_to(self.private_root):
            member = str((directory.path / name).relative_to(self.private_root))
            self._catalog[member] = {"size": len(data), "sha256": hashlib.sha256(data).hexdigest()}

    def _save(self, member, value):
        parts = _components(member)
        directory = self._walk(self._private, parts[:-1])
        self._write(directory, parts[-1], (json.dumps(value, indent=2) + "\n").encode())

    def _capture(self, argv, timeout_s):
        self._check(private_only=True)
        index = self._capture_index
        self._capture_index += 1
        prefix = f"captures/{index:04d}"
        handles = []
        started = time.monotonic()
        try:
            for suffix in ("stdout", "stderr"):
                fd = os.open(f"{index:04d}.{suffix}", os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                             0o600, dir_fd=self._captures.fd)
                handles.append(os.fdopen(fd, "w+b"))
            try:
                process = subprocess.Popen([str(a) for a in argv], cwd=self.private_root,
                    env={k: os.environ[k] for k in DOCKER_ENV_KEYS if k in os.environ},
                    stdout=handles[0], stderr=handles[1], stdin=subprocess.DEVNULL, start_new_session=True)
                try:
                    code, timed_out = process.wait(timeout=timeout_s), False
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    code, timed_out = process.wait(), True
            except OSError as exc:
                handles[1].write(str(exc).encode())
                code, timed_out = 127, False
        finally:
            for handle in handles:
                handle.flush()
                handle.close()
            for suffix in ("stdout", "stderr"):
                name = f"{index:04d}.{suffix}"
                try:
                    data = self._bytes(self._captures, name)
                except FileNotFoundError:
                    continue
                self._catalog[f"captures/{name}"] = {"size": len(data), "sha256": hashlib.sha256(data).hexdigest()}
        record = {"argv": [str(a) for a in argv], "exit_code": code, "timed_out": timed_out,
                  "duration_s": round(time.monotonic() - started, 1),
                  "stream": str(self.private_root / (prefix + ".stdout")),
                  "stderr": str(self.private_root / (prefix + ".stderr"))}
        self._save(prefix + ".json", record)
        return record, self._bytes(self._captures, f"{index:04d}.stdout"), self._bytes(self._captures, f"{index:04d}.stderr")

    def _native(self, tag, entrypoint, args, timeout_s):
        self._check()
        index = len(self._writers)
        name = f"pstack-hermes-{uuid.uuid4().hex}-{tag}"
        receipt = f"writer-{index:04d}.json"
        writer = WriterObservation(index, name, None, "unknown", receipt)
        self._save(f"launch-{index:04d}.json", asdict(writer))
        self._writers += (writer,)
        root, project = self.binding.root, self.binding.project
        profile = root / "hroot/profiles/probe"
        env = {"HOME": root / "home", "HERMES_HOME": profile, "TERMINAL_CWD": project,
               "HERMES_WRITE_SAFE_ROOT": f"{project}:{profile / 'cache'}", "TMPDIR": root / "tmp"}
        flags = [v for k, value in env.items() for v in ("-e", f"{k}={value}")]
        argv = ["docker", "run", "--pull=never", "--rm", "-i", "--init", "--name", name, "--entrypoint", entrypoint,
                "-v", f"{root}:{root}", "-v", f"{USER_HERMES / 'auth.json'}:{root / 'hroot/auth.json'}:ro",
                *flags, "-w", str(project), self._image, *args]
        try:
            record, stdout, stderr = self._capture(argv, timeout_s)
        finally:
            rm, _, _ = self._capture(["docker", "rm", "-f", name], 30)
            inspect, state, _ = self._capture(["docker", "container", "ls", "-a", "--no-trunc", "--filter", f"name=^/{name}$", "--format", "{{.ID}}"], 30)
            ids = state.decode("utf-8", "replace").split()
            disposition = "removed" if rm["exit_code"] == 0 and inspect["exit_code"] == 0 and not ids else (
                "verified-absent" if inspect["exit_code"] == 0 and not ids else "unknown")
            writer = WriterObservation(index, name, ids[0] if len(ids) == 1 else None, disposition, receipt)
            self._writers = self._writers[:-1] + (writer,)
            self._save(receipt, {**asdict(writer), "removal": rm, "inspection": inspect})
        self._check()
        return record, stdout, stderr

    def prepare(self, setup: NativeSetup):
        self._check()
        if self._meta is not None:
            raise EvidenceRefused("invalid-meta", "owner is already prepared")
        for components in (("hroot",), ("hroot", "profiles"), ("hroot", "profiles", "probe"), ("home",), ("tmp",)):
            parent = self._walk(self._root, components[:-1])
            try:
                os.mkdir(components[-1], 0o700, dir_fd=parent.fd)
            except FileExistsError:
                pass
            created = self._walk(parent, (components[-1],))
            if components == ("hroot", "profiles", "probe"):
                self._profile = created
        hroot = self._walk(self._root, ("hroot",))
        self._write(self._profile, ".no-bundled-skills", b"")
        self._write(hroot, "auth.json", b"")
        self._write(self._profile, "config.yaml", CONFIG.format(model=setup.model_block, project=self.binding.project,
             toolsets="".join(f"    - {t}\n" for t in TOOLSETS if setup.todo_tools != "off" or t != "todo"),
             tools=EAGER_TOOLS if setup.todo_eager else "").encode())
        self._setup_files = [(d, name, _identity(os.stat(name, dir_fd=d.fd, follow_symlinks=False)))
                             for d, name in ((self._profile, "config.yaml"), (self._profile, ".no-bundled-skills"), (hroot, "auth.json"))]
        if setup.image_override:
            argv = ["docker", "image", "inspect", setup.image_override, "--format", "{{.Id}}"]
        else:
            argv = ["docker", "inspect", GATEWAY_CONTAINER, "--format", "{{.Image}}"]
        record, output, error = self._capture(argv, 30)
        image = output.decode("utf-8", "replace").strip()
        if record["exit_code"] or not re.fullmatch(r"sha256:[a-f0-9]{64}", image):
            raise RuntimeError(f"no local Hermes image: {error.decode('utf-8', 'replace')[-300:]}")
        self._image = image
        preloads = {}
        for skill in setup.preload_skills:
            record, output, error = self._native("preload", PYTHON_BIN, ["-c", PRELOAD_CHECK, skill], 120)
            if record["exit_code"]:
                raise RuntimeError(f"docker run preload exited {record['exit_code']}: {error.decode('utf-8', 'replace')[-300:]}")
            check = json.loads(output.decode("utf-8", "replace").splitlines()[-1])
            if not isinstance(check, dict) or not all(isinstance(check.get(k), list) for k in ("loaded", "missing")):
                raise EvidenceRefused("invalid-meta", "invalid preload response")
            preloads[skill] = check
        record, output, error = self._native("version", HERMES_BIN, ["--version"], 120)
        if record["exit_code"]:
            raise RuntimeError(f"docker run version exited {record['exit_code']}: {error.decode('utf-8', 'replace')[-300:]}")
        version = output.decode("utf-8", "replace").strip()
        meta = {"image": image, "cli_version": version.splitlines()[0] if version else None,
                "entry": setup.entry, "preload": preloads.get(setup.entry, {}), "preloads": preloads,
                "todo_eager": setup.todo_eager, "todo_tools": setup.todo_tools}
        self._meta = _prepared(meta)
        self._save("meta.json", meta)

    @property
    def first_session(self):
        return next((thaw(t.record)["session_id"] for t in self._turns if thaw(t.record).get("session_id")), None)

    def turn(self, command: NativeTurn):
        self._check()
        if self._meta is None or command.index != len(self._turns):
            raise EvidenceRefused("invalid-meta", "turn must follow preparation and earlier captured turns")
        args = list(command.arguments)
        if "--resume" in args:
            raise EvidenceRefused("invalid-meta", "resume belongs to the evidence owner")
        if command.index:
            if not self.first_session:
                raise RuntimeError(f"turn {command.index} cannot resume: no earlier turn reported a Hermes session id")
            args += ["--resume", self.first_session]
        record, output, _ = self._native(f"turn{command.index}", HERMES_BIN, args, self.timeout_s)
        record.update(hermes_argv=["hermes", *args], image=self._image, session_id=_session_id(output))
        self._turns += (CapturedTurn(command.index, freeze(record)),)
        self._save(f"turn-{command.index:04d}.json", record)
        return thaw(self._turns[-1].record)

    def _inventory(self):
        entries = []
        def visit(directory, prefix):
            if len(prefix) > MAX_DEPTH:
                raise EvidenceRefused("resource-limit", "fixture depth limit exceeded")
            for name in sorted(os.listdir(directory.fd)):
                if len(entries) >= MAX_ENTRIES:
                    raise EvidenceRefused("resource-limit", "fixture inventory limit exceeded")
                info = os.stat(name, dir_fd=directory.fd, follow_symlinks=False)
                kind = "symlink" if stat.S_ISLNK(info.st_mode) else "directory" if stat.S_ISDIR(info.st_mode) else (
                    "regular" if stat.S_ISREG(info.st_mode) and info.st_nlink == 1 else
                    "hardlink" if stat.S_ISREG(info.st_mode) else "special")
                if info.st_dev != directory.identity[0]:
                    kind = "unavailable"
                parts = prefix + (name,)
                entries.append(FixtureEntry(parts, kind))
                if kind == "directory":
                    visit(self._walk(directory, (name,)), parts)
        visit(self._fixture, ())
        return FixtureInventory(self._original_fixture, tuple(entries))

    @property
    def _original_fixture(self):
        return getattr(self, "_fixture_spelling", str(self.binding.project))

    def read(self):
        aid = uuid.uuid4().hex
        attempt = self._mkdir(self._acquisitions, aid)
        self._attempts.append(aid)
        raw = self._mkdir(attempt, "raw")
        work = self._mkdir(attempt, "work")
        opened, receipts = {}, []
        reason = None
        try:
            self._check()
            if self._replay_error:
                raise EvidenceRefused("pair-incomplete", self._replay_error)
            if self._meta is None:
                raise EvidenceRefused("invalid-meta", "no captured prepared metadata")
            source = self._source or self._profile
            if source is None:
                raise EvidenceRefused("missing-state", "no bound native profile")
            for member in STATE_MEMBERS:
                try:
                    opened[member] = self._open(source, member)
                except FileNotFoundError:
                    if member == "state.db":
                        raise EvidenceRefused("missing-state", "native main database is absent")
                    receipts.append(AbsentSidecar(member))
            for member, (fd, stamp) in opened.items():
                data = self._read_fd(fd)
                if _stamp(os.fstat(fd)) != stamp:
                    raise EvidenceRefused("source-changed", f"native file changed: {member}")
                self._write(raw, member, data)
                receipts.append(PresentBytes(member, len(data), hashlib.sha256(data).hexdigest(), stamp))
                if member != "state.db-shm":
                    self._write(work, member, data)
            by_name = {r.member: r for r in receipts}
            database = DatabaseSet(*(by_name[m] for m in STATE_MEMBERS))
            self._save(f"acquisitions/{aid}/database.json", asdict(database))
            if "state.db-wal" in opened:
                self._validate_wal(self._bytes(raw, "state.db"), self._bytes(raw, "state.db-wal"))
            sessions = self._decode(work)
            roots = tuple(dict.fromkeys(thaw(t.record).get("session_id") for t in self._turns if thaw(t.record).get("session_id")))
            ids = {thaw(s.session)["id"] for s in sessions}
            populated = {thaw(s.session)["id"] for s in sessions if s.messages}
            if not roots or any(s not in ids or s not in populated for s in roots):
                raise EvidenceRefused("missing-root", "captured root session is absent from native records")
            inventory = self._inventory()
            for receipt in receipts:
                if isinstance(receipt, PresentBytes):
                    fd, stamp = opened[receipt.member]
                    if (_stamp(os.fstat(fd)) != stamp or hashlib.sha256(self._read_fd(fd)).hexdigest() != receipt.sha256
                            or hashlib.sha256(self._bytes(raw, receipt.member)).hexdigest() != receipt.sha256
                            or _stamp(os.stat(receipt.member, dir_fd=source.fd, follow_symlinks=False)) != stamp):
                        raise EvidenceRefused("source-changed", f"evidence changed: {receipt.member}")
            for receipt in receipts:
                if isinstance(receipt, AbsentSidecar):
                    try:
                        os.stat(receipt.member, dir_fd=source.fd, follow_symlinks=False)
                    except FileNotFoundError:
                        continue
                    raise EvidenceRefused("source-changed", f"sidecar appeared: {receipt.member}")
            self._check()
            acquisition = Acquisition(self.binding.run_id, aid, self._provenance, database, self._writers,
                                      tuple(k for k in self._catalog if k.startswith(f"acquisitions/{aid}/")))
            result = CompleteEvidence(self._meta, self._turns, acquisition, sessions, inventory, ())
        except (OSError, ValueError, sqlite3.Error, EvidenceRefused, RecursionError) as exc:
            reason = exc.reason if isinstance(exc, EvidenceRefused) else "decode-failed"
            result = IncompleteEvidence(self.binding.run_id, aid, reason, f"{type(exc).__name__}: {exc}", self._meta, self._turns, ())
        finally:
            for fd, _ in opened.values():
                os.close(fd)
            self._collect_work(work)
        self._save(f"acquisitions/{aid}/result.json", {"id": aid, "provenance": self._provenance, "reason": reason,
                     "detail": result.detail if isinstance(result, IncompleteEvidence) else None,
                     "members": [asdict(r) for r in receipts]})
        from dataclasses import replace
        return replace(result, retained_paths=tuple(str(self.private_root / k) for k in self._catalog))

    def _collect_work(self, work):
        for name in os.listdir(work.fd):
            data = self._bytes(work, name)
            member = str((work.path / name).relative_to(self.private_root))
            self._catalog[member] = {"size": len(data), "sha256": hashlib.sha256(data).hexdigest()}
        prefix = str(work.path.relative_to(self.private_root)) + "/"
        for member in tuple(self._catalog):
            if member.startswith(prefix) and member[len(prefix):] not in os.listdir(work.fd):
                del self._catalog[member]

    @staticmethod
    def _validate_wal(main, wal):
        if not wal:
            return
        if len(wal) < 32 or len(main) < 100 or main[:16] != b"SQLite format 3\x00":
            raise EvidenceRefused("decode-failed", "invalid WAL or database header")
        magic, version, page = struct.unpack(">III", wal[:12])
        db_page = int.from_bytes(main[16:18], "big")
        db_page = 65536 if db_page == 1 else db_page
        if magic not in (0x377f0682, 0x377f0683) or version != 3007000 or page != db_page or (len(wal) - 32) % (page + 24):
            raise EvidenceRefused("decode-failed", "WAL header or frame length is invalid")
        order = "<" if magic == 0x377f0682 else ">"
        def checksum(data, sums):
            words = struct.unpack(order + "I" * (len(data) // 4), data)
            a, b = sums
            for i in range(0, len(words), 2):
                a = (a + words[i] + b) & 0xffffffff
                b = (b + words[i + 1] + a) & 0xffffffff
            return a, b
        sums = checksum(wal[:24], (0, 0))
        if sums != struct.unpack(">II", wal[24:32]):
            raise EvidenceRefused("decode-failed", "WAL header checksum mismatch")
        for offset in range(32, len(wal), page + 24):
            frame = wal[offset:offset + page + 24]
            sums = checksum(frame[:8] + frame[24:], sums)
            if frame[8:16] != wal[16:24] or sums != struct.unpack(">II", frame[16:24]):
                raise EvidenceRefused("decode-failed", "WAL frame checksum mismatch")

    def _decode(self, work):
        con = sqlite3.connect((work.path / "state.db").as_uri() + "?mode=rw", uri=True)
        try:
            if not all(callable(getattr(con, name, None)) for name in ("enable_load_extension", "setlimit", "set_authorizer", "set_progress_handler")):
                raise EvidenceRefused("decode-failed", "required SQLite restrictions are unavailable")
            con.enable_load_extension(False)
            con.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, 2 * 1024 * 1024)
            con.setlimit(sqlite3.SQLITE_LIMIT_COLUMN, 100)
            budget = 2000
            def progress():
                nonlocal budget
                budget -= 1
                return budget <= 0
            con.set_progress_handler(progress, 1000)
            con.set_authorizer(self._authorize_integrity)
            if con.execute("PRAGMA quick_check").fetchall() != [("ok",)]:
                raise EvidenceRefused("decode-failed", "database integrity check failed")
            con.set_authorizer(self._authorize)
            con.row_factory = sqlite3.Row
            sessions = [dict(r) for r in con.execute("SELECT * FROM sessions ORDER BY started_at LIMIT ?", (MAX_ROWS + 1,))]
            messages = [dict(r) for r in con.execute("SELECT * FROM messages ORDER BY id LIMIT ?", (MAX_ROWS + 1,))]
            if len(sessions) > MAX_ROWS or len(messages) > MAX_ROWS:
                raise EvidenceRefused("resource-limit", "native row limit exceeded")
            grouped = {}
            for message in messages:
                required = ("id", "session_id", "role", "content", "tool_calls", "tool_call_id", "tool_name")
                if any(k not in message for k in required) or type(message["id"]) is not int or not isinstance(message["session_id"], str):
                    raise EvidenceRefused("decode-failed", "invalid native message row")
                if message["role"] not in ("user", "assistant", "tool", "system") or any(message[k] is not None and not isinstance(message[k], str) for k in required[3:]):
                    raise EvidenceRefused("decode-failed", "invalid native message values")
                if message["tool_calls"]:
                    calls = json.loads(message["tool_calls"])
                    if not isinstance(calls, list):
                        raise EvidenceRefused("decode-failed", "tool_calls must be an array")
                    for call in calls:
                        if not isinstance(call, dict) or not isinstance(call.get("function"), dict):
                            raise EvidenceRefused("decode-failed", "invalid native tool call")
                        fn = call["function"]
                        args = json.loads(fn.get("arguments") or "{}")
                        if not isinstance(args, dict) or not isinstance(fn.get("name"), str):
                            raise EvidenceRefused("decode-failed", "invalid native tool arguments")
                grouped.setdefault(message["session_id"], []).append(freeze({key: message[key] for key in required}))
            records, ids = [], set()
            for session in sessions:
                required = ("id", "parent_session_id", "model_config", "started_at", "model", "cwd")
                if any(k not in session for k in required) or not isinstance(session["id"], str) or session["id"] in ids:
                    raise EvidenceRefused("decode-failed", "invalid or duplicate native session")
                ids.add(session["id"])
                if type(session["started_at"]) not in (int, float) or any(session[k] is not None and not isinstance(session[k], str) for k in ("parent_session_id", "model", "cwd")):
                    raise EvidenceRefused("decode-failed", "invalid native session values")
                config = json.loads(session["model_config"] or "{}")
                if not isinstance(config, dict) or (config.get("reasoning_config") is not None and not isinstance(config["reasoning_config"], dict)):
                    raise EvidenceRefused("decode-failed", "model_config must be an object")
                session["model_config"] = config
                session["delegate_from"] = session["parent_session_id"] or config.get("_delegate_from")
                usage_fields = ("api_call_count", "input_tokens", "output_tokens", "cache_read_tokens")
                for key in usage_fields:
                    if session.get(key) is not None and type(session[key]) is not int:
                        raise EvidenceRefused("decode-failed", "invalid native usage counter")
                session = {key: session[key] for key in (*required, *usage_fields, "delegate_from") if key in session}
                records.append(SessionRecords(freeze(session), tuple(grouped.get(session["id"], ()))))
            return tuple(records)
        finally:
            con.close()

    @staticmethod
    def _authorize_integrity(action, first, second, database, trigger):
        allowed = action == sqlite3.SQLITE_SELECT or (
            action == sqlite3.SQLITE_READ and database == "main" and second in INTEGRITY_FTS_COLUMNS.get(first, ())) or (
            action == sqlite3.SQLITE_PRAGMA and second is None and (
                first == "quick_check" and database in (None, "main") or
                first == "data_version" and database == "main"))
        return sqlite3.SQLITE_OK if allowed and trigger is None else sqlite3.SQLITE_DENY

    @staticmethod
    def _authorize(action, first, second, database, trigger):
        allowed = action == sqlite3.SQLITE_SELECT or (
            action == sqlite3.SQLITE_READ and database == "main" and first in ("sessions", "messages")) or (
            action == sqlite3.SQLITE_PRAGMA and first == "quick_check" and second is None)
        return sqlite3.SQLITE_OK if allowed and trigger is None else sqlite3.SQLITE_DENY

    def close(self):
        for directory in reversed(getattr(self, "_dirs", ())):
            os.close(directory.fd)
        self._dirs = []

    def _tree(self, directory, prefix=()):
        files, directories = [], []
        def visit(current, parts):
            if len(parts) > MAX_DEPTH:
                raise EvidenceRefused("resource-limit", "export depth limit exceeded")
            for name in sorted(os.listdir(current.fd)):
                if len(files) + len(directories) >= MAX_ENTRIES:
                    raise EvidenceRefused("resource-limit", "export entry limit exceeded")
                member = parts + (name,)
                info = os.stat(name, dir_fd=current.fd, follow_symlinks=False)
                if stat.S_ISDIR(info.st_mode):
                    child = self._walk(current, (name,))
                    directories.append(member)
                    visit(child, member)
                else:
                    fd, stamp = self._open(current, name)
                    os.close(fd)
                    files.append((member, current, name, stamp))
        visit(directory, prefix)
        return files, directories

    def retain_pair(self, export: OwnedExport):
        try:
            self._check()
            destination = export.destination
            if destination.is_relative_to(self.binding.root) or destination.is_relative_to(self.private_root):
                raise EvidenceRefused("path-refused", "pair destination must be outside the run and private evidence")
            parent = self._absolute(destination.parent)
            pair = self._mkdir(parent, destination.name)
            run_dest = self._mkdir(pair, "run")
            evidence_dest = self._mkdir(pair, "hermes-evidence")
            files, directories = self._tree(self._root)
            for parts in directories:
                self._mkdir(self._walk(run_dest, parts[:-1]), parts[-1])
            catalog = {}
            for parts, source, name, stamp in files:
                data = self._bytes(source, name)
                if _stamp(os.stat(name, dir_fd=source.fd, follow_symlinks=False)) != stamp:
                    raise EvidenceRefused("source-changed", f"export source changed: {parts}")
                self._write(self._walk(run_dest, parts[:-1]), parts[-1], data)
                catalog["run/" + "/".join(parts)] = {"size": len(data), "sha256": hashlib.sha256(data).hexdigest()}
            evidence_dirs = {parts[:i] for member in self._catalog for parts in [_components(member)] for i in range(1, len(parts))}
            for parts in sorted(evidence_dirs, key=lambda p: (len(p), p)):
                self._mkdir(self._walk(evidence_dest, parts[:-1]), parts[-1])
            for member, expected in self._catalog.items():
                parts = _components(member)
                data = self._bytes(self._walk(self._private, parts[:-1]), parts[-1])
                if {"size": len(data), "sha256": hashlib.sha256(data).hexdigest()} != expected:
                    raise EvidenceRefused("source-changed", f"private catalog changed: {member}")
                self._write(self._walk(evidence_dest, parts[:-1]), parts[-1], data)
                catalog["hermes-evidence/" + member] = expected
            self._check()
            manifest = {"schema_version": 1, "run_id": self.binding.run_id,
                "original_root": str(self.binding.root), "original_fixture": self._original_fixture,
                "fixture_components": self._fixture_components, "acquisitions": self._attempts,
                "turn_members": [f"turn-{t.index:04d}.json" for t in self._turns],
                "members": catalog, "directories": ["run", "hermes-evidence", *("run/" + "/".join(p) for p in directories),
                                                      *("hermes-evidence/" + "/".join(p) for p in sorted(evidence_dirs))],
                "absent_run_records": [name for name in ("run.json", "trace.json", "verdict.json") if "run/" + name not in catalog]}
            self._write(pair, "pair.json", (json.dumps(manifest, indent=2) + "\n").encode())
            return RetainedPair(destination, self.binding.run_id, tuple(self._attempts))
        except (OSError, ValueError, EvidenceRefused) as exc:
            raise RetentionUnavailable(f"Hermes pair export failed; private evidence remains at {self.private_root}: {exc}") from exc

    @classmethod
    def replay(cls, binding: ReplayBinding, private_parent: Path):
        reader = cls()
        reader._dirs = []
        try:
            pair = reader._absolute(binding.pair_root)
            manifest = json.loads(reader._bytes(pair, "pair.json"), object_pairs_hook=_unique_object)
            if manifest["schema_version"] != 1 or manifest["run_id"] != binding.expected_run_id:
                raise EvidenceRefused("pair-incomplete", "pair identity does not match replay binding")
            if len(set(manifest["acquisitions"])) != len(manifest["acquisitions"]) or len(set(manifest["directories"])) != len(manifest["directories"]):
                raise EvidenceRefused("pair-incomplete", "duplicate pair member")
            if binding.acquisition_id not in manifest["acquisitions"]:
                raise EvidenceRefused("pair-incomplete", "requested acquisition is not cataloged")
            _components(binding.acquisition_id)
            components = tuple(manifest["fixture_components"])
            _components("/".join(components))
            owner = cls.bind(RunBinding(binding.expected_run_id, binding.pair_root / "run",
                                       binding.pair_root / "run" / Path(*components), private_parent), 1)
            owner._fixture_spelling = manifest["original_fixture"]
            owner._provenance = "pair-offline"
            try:
                expected_members = manifest["members"]
                for member, expected in expected_members.items():
                    parts = _components(member)
                    if parts[0] not in ("run", "hermes-evidence"):
                        raise EvidenceRefused("pair-incomplete", "unknown pair namespace")
                    data = reader._bytes(reader._walk(pair, parts[:-1]), parts[-1])
                    if {"size": len(data), "sha256": hashlib.sha256(data).hexdigest()} != expected:
                        raise EvidenceRefused("pair-incomplete", f"catalog mismatch: {member}")
                files, directories = reader._tree(pair)
                if {"/".join(p) for p, _, _, _ in files} != set(expected_members) | {"pair.json"}:
                    raise EvidenceRefused("pair-incomplete", "pair membership mismatch")
                if {"/".join(p) for p in directories} != set(manifest["directories"]):
                    raise EvidenceRefused("pair-incomplete", "pair directory membership mismatch")
                for member, expected in expected_members.items():
                    parts = _components(member)
                    if parts[0] != "hermes-evidence":
                        continue
                    relative = parts[1:]
                    if relative == ("binding.json",):
                        relative = ("imported-binding-" + uuid.uuid4().hex + ".json",)
                    target = owner._private
                    for name in relative[:-1]:
                        try:
                            target = owner._mkdir(target, name)
                        except FileExistsError:
                            target = owner._walk(target, (name,))
                    data = reader._bytes(reader._walk(pair, parts[:-1]), parts[-1])
                    if {"size": len(data), "sha256": hashlib.sha256(data).hexdigest()} != expected:
                        raise EvidenceRefused("pair-incomplete", f"catalog changed during import: {member}")
                    owner._write(target, relative[-1], data)
                owner._attempts = list(manifest["acquisitions"])
                evidence = owner._private
                owner._meta = _prepared(json.loads(owner._bytes(evidence, "meta.json")))
                owner._turns = tuple(CapturedTurn(i, freeze(json.loads(owner._bytes(evidence, name))))
                                    for i, name in enumerate(manifest["turn_members"]))
                owner._source = owner._walk(evidence, ("acquisitions", binding.acquisition_id, "raw"))
                result_dir = owner._walk(evidence, ("acquisitions", binding.acquisition_id))
                receipt = json.loads(owner._bytes(result_dir, "result.json"))
                if receipt["reason"] is not None:
                    raise EvidenceRefused("pair-incomplete", f"selected acquisition is incomplete: {receipt['reason']}")
                owner._save("replay-" + uuid.uuid4().hex + ".json", {"run_id": binding.expected_run_id, "acquisition_id": binding.acquisition_id,
                                           "pair_root": str(binding.pair_root), "provenance": owner._provenance})
            except (OSError, ValueError, KeyError, TypeError, EvidenceRefused) as exc:
                owner._replay_error = str(exc)
            return owner
        finally:
            reader.close()

    @classmethod
    def replay_legacy(cls, binding: LegacyReplayBinding, private_parent: Path):
        if not binding.evaluator_offline_assertion or binding.source_kind not in ("native-profile", "legacy-copied"):
            raise EvidenceRefused("invalid-meta", "legacy replay requires an explicit source kind and no-writer assertion")
        _components("/".join(binding.fixture_components))
        owner = cls.bind(RunBinding(uuid.uuid4().hex, binding.root, binding.root / Path(*binding.fixture_components), private_parent), 1)
        owner._fixture_spelling = binding.original_fixture_spelling
        owner._provenance = "legacy-offline"
        try:
            meta = json.loads(owner._bytes(owner._root, "hermes.json"))
            record = json.loads(owner._bytes(owner._root, "run.json"))
            if not isinstance(meta, dict) or not all(k in meta for k in ("image", "cli_version", "entry", "preload", "todo_eager")):
                raise EvidenceRefused("invalid-meta", "legacy metadata is incomplete")
            owner._meta = _prepared(meta)
            owner._save("meta.json", meta)
            streams = owner._walk(owner._root, ("transcripts",))
            for index, turn in enumerate(record["turns"]):
                data = owner._bytes(streams, f"turn-{index}.stream.jsonl")
                err = owner._bytes(streams, f"turn-{index}.stderr.txt")
                owner._write(owner._captures, f"legacy-{index}.stdout", data)
                owner._write(owner._captures, f"legacy-{index}.stderr", err)
                detached = {k: turn.get(k) for k in ("argv", "hermes_argv", "exit_code", "duration_s", "timed_out")}
                detached.update(session_id=_session_id(data), stream=str(owner.private_root / "captures" / f"legacy-{index}.stdout"),
                                stderr=str(owner.private_root / "captures" / f"legacy-{index}.stderr"))
                owner._turns += (CapturedTurn(index, freeze(detached)),)
                owner._save(f"turn-{index:04d}.json", detached)
            owner._source = owner._walk(owner._root, ("hroot", "profiles", "probe") if binding.source_kind == "native-profile" else ("transcripts",))
            owner._save("legacy.json", {"source_kind": binding.source_kind, "assertion": binding.evaluator_offline_assertion,
                                       "provenance": "legacy-offline", "historical_termination": "unverified"})
        except (OSError, ValueError, TypeError, KeyError, EvidenceRefused) as exc:
            owner._replay_error = str(exc)
        return owner


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _prepared(meta):
    if not isinstance(meta, dict) or any(k not in meta for k in ("image", "cli_version", "entry", "preload", "todo_eager")):
        raise EvidenceRefused("invalid-meta", "prepared metadata is incomplete")
    if not isinstance(meta["image"], str) or any(meta[k] is not None and not isinstance(meta[k], str) for k in ("cli_version", "entry")):
        raise EvidenceRefused("invalid-meta", "prepared identity fields are invalid")
    if not isinstance(meta["preload"], dict) or not isinstance(meta.get("preloads", {}), dict) or type(meta["todo_eager"]) is not bool or meta.get("todo_tools", "on") not in ("on", "off"):
        raise EvidenceRefused("invalid-meta", "prepared tool metadata is invalid")
    for check in [meta["preload"], *meta.get("preloads", {}).values()]:
        if not isinstance(check, dict) or any(not isinstance(check.get(k, []), list) for k in ("loaded", "missing")):
            raise EvidenceRefused("invalid-meta", "prepared preload response is invalid")
    return freeze(meta)
