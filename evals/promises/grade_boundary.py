import errno
import fcntl
import hashlib
import hmac
import json
import os
import platform
import shlex
import signal
import stat
import subprocess
import sys
import threading
import uuid
from dataclasses import dataclass
from pathlib import Path

HERE = Path(__file__).resolve().parent
PYTHON_ROOT = Path("/Users/msmith1/.local/share/mise/installs/python/3.14.7")
PYTHON = PYTHON_ROOT / "bin/python3.14"
GIT_ROOT = Path("/Library/Developer/CommandLineTools")
GIT = GIT_ROOT / "usr/bin/git"
PINS = ((PYTHON, ("1bfa9a829d950ecd4870a3d7a6826eb57edb4aa93f69d07cd3bb21e9fcc6d439",)),
        (GIT, ("a73bf622a2e470d5d57a4b1d5aef1e8680e67278018d4858a2f93825b7d595c7",
               "be4afb2b003904725826250de9fb76567bbacf82323457b5a1ec26706b66bcae")))
SYSTEM_FILES = tuple(Path(p) for p in ("/", "/dev/null", "/dev/random", "/dev/urandom",
    "/usr/share/icu/icudt78l.dat", "/private/var/db/timezone/zoneinfo/America/Denver",
    "/bin/sh", "/bin/bash", "/bin/cat", "/bin/sleep", "/usr/bin/env", "/usr/bin/true", "/usr/bin/false"))
SYSTEM_TREES = (Path("/System/Library"), Path("/usr/lib"), PYTHON_ROOT,
                GIT_ROOT / "usr/libexec/git-core", GIT_ROOT / "usr/share/git-core/templates")
SKILL_DIRS = (".claude/skills", ".agents/skills", ".hermes/skills", ".grok/skills", "skills")


class GradeRefused(RuntimeError):
    def __init__(self, reason, detail, run_id=None):
        self.receipt = {"run_id": run_id, "reason": reason, "detail": str(detail)}
        super().__init__(f"{reason}: {detail}")


class GradeAuthorization:
    """A handle issued by trusted setup or reviewed retention."""

    def __init__(self, *args, **kwargs):
        raise GradeRefused("unknown_authorization", "trusted controller issuance is required")


@dataclass
class _Root:
    path: Path
    fd: int
    device: int
    inode: int

    @classmethod
    def open(cls, path, identity=None, create=False):
        path = Path(path)
        if not path.is_absolute() or ".." in path.parts:
            raise GradeRefused("unsafe_path", path)
        fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
        flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        try:
            for part in path.parts[1:]:
                try:
                    child = os.open(part, flags, dir_fd=fd)
                except FileNotFoundError:
                    if not create:
                        raise
                    os.mkdir(part, 0o700, dir_fd=fd)
                    child = os.open(part, flags, dir_fd=fd)
                os.close(fd)
                fd = child
            info = os.fstat(fd)
            if identity is not None and [info.st_dev, info.st_ino] != identity:
                raise GradeRefused("root_replaced", path)
            return cls(path, fd, info.st_dev, info.st_ino)
        except OSError as error:
            os.close(fd)
            raise GradeRefused("unsafe_root", path) from error
        except BaseException:
            os.close(fd)
            raise

    def identity(self):
        return [self.device, self.inode]

    def verify(self):
        current = _Root.open(self.path, self.identity())
        current.close()

    def close(self):
        if self.fd >= 0:
            os.close(self.fd)
            self.fd = -1

    def __del__(self):
        self.close()

    def _parent(self, rel):
        rel = Path(rel)
        if rel.is_absolute() or ".." in rel.parts or not rel.parts:
            raise GradeRefused("unsafe_path", self.path / rel)
        fd = os.dup(self.fd)
        try:
            for part in rel.parts[:-1]:
                child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                os.close(fd)
                fd = child
            return fd, rel.name
        except OSError as error:
            os.close(fd)
            if error.errno == errno.ENOENT:
                raise FileNotFoundError(self.path / rel) from error
            raise GradeRefused("unsafe_link", self.path / rel) from error

    def info(self, rel):
        self.verify()
        if Path(rel) == Path("."):
            return os.fstat(self.fd)
        fd, name = self._parent(rel)
        try:
            info = os.stat(name, dir_fd=fd, follow_symlinks=False)
            if stat.S_ISLNK(info.st_mode) or (stat.S_ISREG(info.st_mode) and info.st_nlink != 1):
                raise GradeRefused("unsafe_link", self.path / rel)
            if not (stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode)):
                raise GradeRefused("unsafe_object", self.path / rel)
            return info
        except OSError as error:
            if error.errno == errno.ENOENT:
                raise FileNotFoundError(self.path / rel) from error
            raise GradeRefused("unsafe_link", self.path / rel) from error
        finally:
            os.close(fd)

    def read(self, rel):
        self.verify()
        parent, name = self._parent(rel)
        fd = None
        try:
            fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
            before = os.fstat(fd)
            if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
                raise GradeRefused("unsafe_object", self.path / rel)
            with os.fdopen(os.dup(fd), "rb") as stream:
                data = stream.read()
            after = os.fstat(fd)
            named = os.stat(name, dir_fd=parent, follow_symlinks=False)
            fields = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns, s.st_nlink)
            if fields(before) != fields(after) or fields(after) != fields(named):
                raise GradeRefused("input_changed", self.path / rel)
            self.verify()
            return data
        except OSError as error:
            if error.errno == errno.ENOENT:
                raise FileNotFoundError(self.path / rel) from error
            raise GradeRefused("unsafe_link", self.path / rel) from error
        finally:
            if fd is not None:
                os.close(fd)
            os.close(parent)

    def files(self, pattern="*", recursive=True, include_directories=False):
        self.verify()
        found = []

        def walk(fd, prefix):
            for name in os.listdir(fd):
                rel = prefix / name
                info = os.stat(name, dir_fd=fd, follow_symlinks=False)
                if stat.S_ISLNK(info.st_mode) or (stat.S_ISREG(info.st_mode) and info.st_nlink != 1):
                    raise GradeRefused("unsafe_link", self.path / rel)
                if stat.S_ISDIR(info.st_mode):
                    if include_directories and rel.match(pattern):
                        found.append(self.path / rel)
                    if recursive:
                        child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                        try:
                            walk(child, rel)
                        finally:
                            os.close(child)
                elif stat.S_ISREG(info.st_mode):
                    if rel.match(pattern):
                        found.append(self.path / rel)
                else:
                    raise GradeRefused("unsafe_object", self.path / rel)

        try:
            walk(self.fd, Path("."))
        except OSError as error:
            raise GradeRefused("unsafe_link", self.path) from error
        self.verify()
        return found

    def write(self, name, data):
        if Path(name).name != name:
            raise GradeRefused("output_unsafe", name)
        self.verify()
        try:
            if not stat.S_ISREG(self.info(name).st_mode):
                raise GradeRefused("output_unsafe", self.path / name)
        except FileNotFoundError:
            pass
        temporary = f".{name}-{uuid.uuid4().hex}"
        try:
            fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=self.fd)
            try:
                with os.fdopen(fd, "wb") as stream:
                    stream.write(data)
                    stream.flush()
                    os.fsync(stream.fileno())
                self.verify()
                try:
                    if not stat.S_ISREG(self.info(name).st_mode):
                        raise GradeRefused("output_unsafe", self.path / name)
                except FileNotFoundError:
                    pass
                os.rename(temporary, name, src_dir_fd=self.fd, dst_dir_fd=self.fd)
                os.fsync(self.fd)
            finally:
                try:
                    os.unlink(temporary, dir_fd=self.fd)
                except FileNotFoundError:
                    pass
        except OSError as error:
            raise GradeRefused("output_unsafe", self.path / name) from error


def _json(value):
    return (json.dumps(value, indent=1) + "\n").encode()


def _copy_tree(source, destination):
    root = _Root.open(source)
    try:
        destination.mkdir(parents=True, mode=0o700)
        for path in root.files():
            rel = path.relative_to(root.path)
            target = destination / rel
            target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            target.write_bytes(root.read(rel))
    finally:
        root.close()


def read_file(path):
    root = _Root.open(path.parent)
    try:
        return root.read(path.name)
    finally:
        root.close()


def copy_file(source, target):
    data = read_file(source)
    root = _Root.open(target.parent, create=True)
    try:
        root.write(target.name, data)
    finally:
        root.close()
    return data


def _snapshot(path):
    root = _Root.open(path)
    try:
        return {"path": str(root.path), "identity": root.identity()}
    finally:
        root.close()


def _copy_skill_inputs(source, destination):
    root = _Root.open(source)
    try:
        paths = [Path("poteto-mode/SKILL.md")]
        try:
            playbooks = _Root.open(root.path / "poteto-mode/playbooks")
        except GradeRefused:
            try:
                root.info("poteto-mode/playbooks")
            except FileNotFoundError:
                playbooks = None
            else:
                raise
        if playbooks:
            try:
                paths.extend(path.relative_to(root.path) for path in playbooks.files("*.md", recursive=False, include_directories=True))
            finally:
                playbooks.close()
        destination.mkdir(parents=True, mode=0o700)
        for rel in paths:
            target = destination / rel
            target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            target.write_bytes(root.read(rel))
    finally:
        root.close()


def _controller_path(out):
    out = Path(out).resolve()
    return out.parent / f".{out.name}-grade-controller"


class _Controller:
    def __init__(self, out, create=False):
        path = _controller_path(out)
        if create:
            try:
                path.mkdir(mode=0o700)
            except FileExistsError:
                pass
        self.root = _Root.open(path)
        info = os.fstat(self.root.fd)
        if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
            raise GradeRefused("unknown_authorization", "controller directory is not private")
        fcntl.flock(self.root.fd, fcntl.LOCK_EX)
        try:
            try:
                key = self.root.read("key.json")
            except FileNotFoundError:
                if not create:
                    raise GradeRefused("unknown_authorization", "controller has no issuer key")
                key = _json({"identity": self.root.identity(), "key": os.urandom(32).hex()})
                self.root.write("key.json", key)
        finally:
            fcntl.flock(self.root.fd, fcntl.LOCK_UN)
        issuer = json.loads(key)
        if issuer["identity"] != self.root.identity():
            raise GradeRefused("unknown_authorization", "controller directory was relocated")
        self.key = bytes.fromhex(issuer["key"])

    def save(self, state):
        payload = _json(state)
        self.root.write(f"{state['id']}.json", _json({"payload": state,
            "signature": hmac.digest(self.key, payload, "sha256").hex()}))

    def load(self, run_id):
        if not re_id(run_id):
            raise GradeRefused("unknown_authorization", "a registered run ID is required")
        try:
            envelope = json.loads(self.root.read(f"{run_id}.json"))
            state = envelope["payload"]
            signature = hmac.digest(self.key, _json(state), "sha256").hex()
            if not hmac.compare_digest(signature, envelope["signature"]) or state["id"] != run_id:
                raise GradeRefused("unknown_authorization", "authorization signature does not match")
        except (FileNotFoundError, ValueError, KeyError, TypeError) as error:
            raise GradeRefused("unknown_authorization", run_id) from error
        handle = object.__new__(GradeAuthorization)
        handle._controller = self
        handle._id = run_id
        return handle, state

    def issue(self, run_root, project, case, record, *, allocations=(), worktrees=(), output=None, original_project=None):
        if record["case"] != case["id"]:
            raise GradeRefused("input_changed", "record case differs from controller case")
        if record.get("project", str(Path(run_root) / "project")) != str(original_project or project):
            raise GradeRefused("input_changed", "record project differs from controller authority")
        writable = [Path(project), *(Path(p) for p in worktrees), *(Path(p) for p in allocations)]
        if any(Path(run_root).is_relative_to(p) for p in writable):
            raise GradeRefused("unsafe_root", "raw run storage overlaps candidate writable roots")
        if self.root.path.is_relative_to(Path(run_root)) or any(self.root.path.is_relative_to(p) for p in writable):
            raise GradeRefused("unsafe_root", "controller state overlaps candidate storage")
        if any(Path(output or run_root).is_relative_to(p) for p in writable):
            raise GradeRefused("output_unsafe", "output overlaps candidate writable roots")
        run_id = uuid.uuid4().hex
        private = self.root.path / run_id
        private.mkdir(mode=0o700)
        _copy_tree(HERE / "cases" / case["id"], private / "references" / "cases" / case["id"])
        if case.get("history"):
            _copy_tree(HERE / "histories" / case["history"], private / "references" / "histories" / case["history"])
        else:
            (private / "references" / "histories").mkdir(mode=0o700)
        _copy_skill_inputs(HERE.parents[1] / "skills", private / "fallback" / "skills")
        (private / "code").mkdir(mode=0o700)
        source = _Root.open(HERE)
        try:
            for name in ("grade_boundary.py", "oracles.py"):
                (private / "code" / name).write_bytes(source.read(name))
        finally:
            source.close()
        project = Path(project)
        try:
            project_state = _snapshot(project)
        except GradeRefused as error:
            if not project.exists() and not project.is_symlink():
                project_state = {"path": str(project), "identity": None}
            else:
                raise error
        git_directory = None
        if project_state["identity"] is not None:
            project_root = _Root.open(project)
            try:
                try:
                    git_info = project_root.info(".git")
                    if stat.S_ISDIR(git_info.st_mode):
                        git_directory = _snapshot(project / ".git")
                    else:
                        raise GradeRefused("unapproved_git", "linked primary project needs reviewed common Git authority")
                except FileNotFoundError:
                    pass
            finally:
                project_root.close()
        state = {"id": run_id, "run": _snapshot(run_root), "project": project_state,
                 "output": _snapshot(output or run_root), "allocations": [_snapshot(p) for p in allocations],
                 "worktrees": [_snapshot(p) for p in worktrees], "git": git_directory,
                 "private": _snapshot(private), "case": case, "record": record, "sealed": False}
        self.save(state)
        return self.load(run_id)[0]


def re_id(value):
    return isinstance(value, str) and len(value) == 32 and all(c in "0123456789abcdef" for c in value)


def _lookup(out, run_id):
    return _Controller(out).load(run_id)[0]


def _before_turns(run):
    _runtime()
    record = {"harness": run.harness, "case": run.case["id"], "skills_at": run.skills_at,
              "project": str(run.project), "timeout_s": run.timeout_s, "turns": [], "baseline": run.baseline}
    controller = _Controller(run.root.parent, create=True)
    return controller.issue(run.root, run.project, run.case, record, allocations=(run.project.parent,))


def _write_record(handle, record):
    _, state = handle._controller.load(handle._id)
    expected = {k: v for k, v in state["record"].items() if k != "turns"}
    if {k: v for k, v in record.items() if k != "turns"} != expected:
        raise GradeRefused("input_changed", "trusted run metadata changed", handle._id)
    root = _Root.open(state["run"]["path"], state["run"]["identity"])
    try:
        root.write("run.json", _json(record))
    finally:
        root.close()


def _seal(handle, record, trace, *, write=True):
    _, state = handle._controller.load(handle._id)
    if {k: v for k, v in record.items() if k != "turns"} != {k: v for k, v in state["record"].items() if k != "turns"}:
        raise GradeRefused("input_changed", "record conflicts with pre-turn controller metadata", handle._id)
    if write:
        _write_record(handle, record)
    state["record"] = record
    state["trace"] = trace
    if "x_turns" in trace:
        turns = record.get("turns", [])
        expected = [turns]
        if record["harness"] in ("codex", "grok"):
            expected.append([{k: t.get(k) for k in ("index", "session_id", "argv", "exit_code", "timed_out", "duration_s")}
                             for t in turns])
        observed = json.dumps(trace["x_turns"], sort_keys=True)
        if all(observed != json.dumps(value, sort_keys=True) for value in expected):
            raise GradeRefused("input_changed", "x_turns conflicts with sealed metadata", handle._id)
    if "x_baseline" in trace and trace["x_baseline"] != record.get("baseline"):
        raise GradeRefused("input_changed", "x_baseline conflicts with sealed metadata", handle._id)
    root = _Root.open(state["run"]["path"], state["run"]["identity"])
    try:
        if write:
            root.write("trace.json", _json(trace))
        state["raw_digests"] = {name: hashlib.sha256(root.read(name)).hexdigest() for name in ("run.json", "trace.json")}
        if json.loads(root.read("run.json")) != record or json.loads(root.read("trace.json")) != trace:
            raise GradeRefused("input_changed", "raw inputs differ from controller inputs", handle._id)
    finally:
        root.close()
    state["sealed"] = True
    handle._controller.save(state)


def _authorize_fixture(root, project, case, record, trace, *, worktrees=(), output=None):
    controller = _Controller(Path(root).parent, create=True)
    handle = controller.issue(root, project, case, record, worktrees=worktrees, output=output)
    _seal(handle, record, trace)
    return handle


def _authorize_retained(out, root, *, project, original_project, output, case, worktrees=()):
    raw = _Root.open(root)
    try:
        record = json.loads(raw.read("run.json"))
        trace = json.loads(raw.read("trace.json"))
        prior = raw.read("verdict.json")
    finally:
        raw.close()
    if record.get("project", str(Path(root) / "project")) != str(original_project):
        raise GradeRefused("input_changed", "record does not match the reviewed original mapping")
    if Path(output).resolve() == Path(root).resolve():
        raise GradeRefused("output_unsafe", "retained grades need a separate diagnostic directory")
    controller = _Controller(out, create=True)
    handle = controller.issue(root, project, case, record, worktrees=worktrees, output=output, original_project=original_project)
    _seal(handle, record, trace, write=False)
    _, state = controller.load(handle._id)
    state["prior_verdict_digest"] = hashlib.sha256(prior).hexdigest()
    controller.save(state)
    return handle


def _runtime():
    if (platform.system(), platform.release(), platform.machine()) != ("Darwin", "25.6.0", "arm64"):
        raise GradeRefused("boundary_unavailable", "only the reviewed Darwin 25.6.0 arm64 runtime is supported")
    for path, expected in PINS:
        if path.is_symlink() or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() not in expected:
            raise GradeRefused("boundary_unavailable", f"runtime fingerprint changed: {path}")
    if not Path("/usr/bin/sandbox-exec").is_file() or any(not p.exists() for p in (*SYSTEM_FILES, *SYSTEM_TREES)):
        raise GradeRefused("boundary_unavailable", "reviewed native runtime files are unavailable")


def _git_path(text, base):
    if "\x00" in text:
        raise GradeRefused("unapproved_git", "worktree path contains a NUL byte")
    path = Path(text.strip())
    return Path(os.path.abspath(path if path.is_absolute() else base / path))


def _approved_trees(state):
    project = state["project"]
    if project["identity"] is None:
        if Path(project["path"]).exists() or Path(project["path"]).is_symlink():
            raise GradeRefused("input_changed", "authorized absent project appeared")
        return []
    approved = {project["path"]: project, **{r["path"]: r for r in state["worktrees"]}}
    allocations = [_Root.open(r["path"], r["identity"]) for r in state["allocations"]]
    git = state["git"]
    if git is None and state["worktrees"]:
        raise GradeRefused("unapproved_git", "worktrees require a bound common Git directory")
    common = _Root.open(git["path"], git["identity"]) if git else None
    try:
        if common:
            try:
                registry = _Root.open(common.path / "worktrees")
            except GradeRefused:
                if (common.path / "worktrees").exists() or (common.path / "worktrees").is_symlink():
                    raise
                registry = None
            if registry:
                try:
                    for pointer in registry.files("gitdir"):
                        path = _git_path(registry.read(pointer.relative_to(registry.path)).decode(), registry.path).parent
                        if str(path) not in approved:
                            allocation = next((r for r in allocations if path.is_relative_to(r.path)), None)
                            if allocation is None:
                                raise GradeRefused("unapproved_worktree", path)
                            approved[str(path)] = _snapshot(path)
                finally:
                    registry.close()
        for root in approved.values():
            opened = _Root.open(root["path"], root["identity"])
            try:
                opened.files()
                if root == project or not common:
                    continue
                pointer = opened.read(".git").decode()
                if not pointer.startswith("gitdir: "):
                    raise GradeRefused("unapproved_git", opened.path)
                directory = _git_path(pointer[8:], opened.path)
                if not directory.is_relative_to(common.path / "worktrees"):
                    raise GradeRefused("unapproved_git", directory)
                rel = directory.relative_to(common.path)
                if _git_path(common.read(rel / "commondir").decode(), directory) != common.path:
                    raise GradeRefused("unapproved_git", "worktree common directory differs")
                if _git_path(common.read(rel / "gitdir").decode(), directory) != opened.path / ".git":
                    raise GradeRefused("unapproved_git", "worktree reverse pointer differs")
            finally:
                opened.close()
        return list(approved.values())
    except FileNotFoundError as error:
        raise GradeRefused("unapproved_git", f"missing worktree metadata: {error}") from error
    except UnicodeDecodeError as error:
        raise GradeRefused("unapproved_git", f"invalid UTF-8 worktree metadata: {error}") from error
    finally:
        if common:
            common.close()
        for root in allocations:
            root.close()


def _policy(reads, writes):
    literal = lambda p: f"(literal {json.dumps(str(p))})"
    subtree = lambda p: f"(subpath {json.dumps(str(p))})"
    files = (*SYSTEM_FILES, GIT)
    trees = (*SYSTEM_TREES, *reads, *writes)
    ancestors = {parent for p in (*files, *trees) for parent in p.parents}
    ancestors.update(Path(p) for p in ("/tmp", "/var", "/etc", "/private/etc/localtime"))
    return "\n".join(("(version 1)", "(allow default)", "(deny file-read*)", "(deny file-write*)",
        "(allow file-read* " + " ".join(map(literal, files)) + ")",
        "(allow file-read* " + " ".join(map(subtree, trees)) + ")",
        "(allow file-write* " + " ".join(map(subtree, writes)) + ")",
        "(allow file-read* " + " ".join(map(literal, sorted(ancestors))) + ")",
        '(allow file-write* (literal "/dev/null") (subpath "/dev/fd"))',
        "(deny file-write-unlink " + " ".join(map(literal, (*writes, *ancestors))) + ")"))


class _Environment:
    def __init__(self, roots, trees, skills, scratch, absent):
        self.roots = sorted([_Root.open(r["path"], r["identity"]) for r in roots], key=lambda r: len(str(r.path)), reverse=True)
        self.trees = {r["path"] for r in trees}
        self.skills = Path(skills)
        self.scratch = Path(scratch)
        self.absent = Path(absent) if absent else None

    def bound(self, path):
        path = Path(path)
        if ".." in path.parts:
            raise GradeRefused("unsafe_path", path)
        for root in self.roots:
            if path.is_relative_to(root.path):
                return root, path.relative_to(root.path)
        raise GradeRefused("unapproved_path", path)

    def read_bytes(self, path):
        root, rel = self.bound(path)
        return root.read(rel)

    def read_text(self, path, encoding="utf-8", errors="strict"):
        return self.read_bytes(path).decode(encoding, errors)

    def exists(self, path, kind=None):
        if self.absent is not None and Path(path).is_relative_to(self.absent):
            return False
        root, rel = self.bound(path)
        try:
            info = root.info(rel)
            return (stat.S_ISREG(info.st_mode) if kind == "file" else stat.S_ISDIR(info.st_mode) if kind == "dir" else True)
        except FileNotFoundError:
            return False

    def files(self, path, pattern, recursive=False):
        root, rel = self.bound(path)
        if not self.exists(path, "dir"):
            return []
        child = _Root.open(root.path / rel)
        try:
            return child.files(pattern, recursive=recursive, include_directories=True)
        finally:
            child.close()

    def git(self, path, args, *, text=True):
        if str(path) not in self.trees:
            raise GradeRefused("unapproved_worktree", path)
        return subprocess.run([str(GIT), "-C", str(path), *args], capture_output=True, text=text)

    def worktrees(self, paths):
        for path in paths:
            if path not in self.trees:
                raise GradeRefused("unapproved_worktree", path)
        return paths

    def check(self, path, command, timeout):
        if str(path) not in self.trees:
            raise GradeRefused("unapproved_worktree", path)
        proc = subprocess.Popen(shlex.split(command), cwd=path, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                text=True, start_new_session=True)
        try:
            stdout, stderr = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            if proc.poll() is None:
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            proc.wait()
            raise
        return subprocess.CompletedProcess(proc.args, proc.returncode, stdout, stderr)


def grade(authorization):
    """Return the existing verdict for one controller-issued authorization."""
    if not isinstance(authorization, GradeAuthorization) or not hasattr(authorization, "_controller"):
        raise GradeRefused("unknown_authorization", "path-based grading is not authorized")
    controller = authorization._controller
    _, state = controller.load(authorization._id)
    run_id = state["id"]
    attempt = controller.root.path / run_id / uuid.uuid4().hex
    attempt.mkdir(mode=0o700)
    output = None
    try:
        _runtime()
        if not state["sealed"]:
            raise GradeRefused("input_changed", "run inputs are not sealed")
        raw = _Root.open(state["run"]["path"], state["run"]["identity"])
        try:
            for name, expected in state["raw_digests"].items():
                if hashlib.sha256(raw.read(name)).hexdigest() != expected:
                    raise GradeRefused("input_changed", name)
            if "prior_verdict_digest" in state and hashlib.sha256(raw.read("verdict.json")).hexdigest() != state["prior_verdict_digest"]:
                raise GradeRefused("input_changed", "retained raw verdict changed")
        except FileNotFoundError as error:
            raise GradeRefused("input_changed", error) from error
        finally:
            raw.close()
        output = _Root.open(state["output"]["path"], state["output"]["identity"])
        try:
            output.info("verdict.json")
        except FileNotFoundError:
            pass
        trees = _approved_trees(state)
        private = _Root.open(state["private"]["path"], state["private"]["identity"])
        try:
            for name in ("code", "references", "fallback"):
                protected = _Root.open(private.path / name)
                try:
                    protected.files()
                finally:
                    protected.close()
            private.verify()
        finally:
            private.close()
        skills = Path(state["private"]["path"]) / "fallback" / "skills"
        if state["project"]["identity"] is not None:
            project = _Root.open(state["project"]["path"], state["project"]["identity"])
            try:
                for sub in SKILL_DIRS:
                    try:
                        present = stat.S_ISREG(project.info(Path(sub) / "poteto-mode" / "SKILL.md").st_mode)
                    except FileNotFoundError:
                        present = False
                    if present:
                        skills = attempt / "installed" / "skills"
                        _copy_skill_inputs(project.path / sub, skills)
                        break
            finally:
                project.close()
        scratch = attempt / "scratch"
        scratch.mkdir(mode=0o700)
        roots = [*trees, _snapshot(Path(state["private"]["path"]) / "references"), _snapshot(skills)]
        config = {"invocation": uuid.uuid4().hex, "case": state["case"], "record": state["record"],
                  "trace": state["trace"], "project": state["project"]["path"], "roots": roots, "trees": trees,
                  "skills": str(skills), "references": str(Path(state["private"]["path"]) / "references"),
                  "scratch": str(scratch)}
        profile = _policy([Path(state["private"]["path"]) / "code", Path(config["references"]), skills],
                          [*(Path(r["path"]) for r in trees), scratch])
        (attempt / "profile.sb").write_text(profile)
        env = {"PATH": f"{PYTHON_ROOT}/bin:{GIT_ROOT}/usr/bin:/usr/bin:/bin", "HOME": str(scratch),
               "TMPDIR": str(scratch), "LANG": "en_US.UTF-8", "GIT_CONFIG_GLOBAL": "/dev/null",
               "GIT_CONFIG_NOSYSTEM": "1", "PYTHONDONTWRITEBYTECODE": "1"}
        read_fd, write_fd = os.pipe()
        chunks = []

        def read_result():
            with os.fdopen(read_fd, "rb") as stream:
                chunks.append(stream.read())

        reader = threading.Thread(target=read_result)
        reader.start()
        try:
            proc = subprocess.Popen(["/usr/bin/sandbox-exec", "-p", profile, str(PYTHON), "-I", "-B",
                str(Path(state["private"]["path"]) / "code" / "grade_boundary.py"), "--worker", str(write_fd)],
                cwd=scratch, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                pass_fds=(write_fd,), start_new_session=True)
        except OSError as error:
            raise GradeRefused("boundary_unavailable", f"native worker launch failed: {error}") from error
        finally:
            os.close(write_fd)
        stdout, stderr = proc.communicate(_json(config))
        reader.join()
        (attempt / "worker.stdout").write_bytes(stdout)
        (attempt / "worker.stderr").write_bytes(stderr)
        (attempt / "worker.result").write_bytes(b"".join(chunks))
        if proc.returncode:
            raise GradeRefused("boundary_unavailable", f"worker exited {proc.returncode}; logs: {attempt}")
        try:
            result = json.loads(b"".join(chunks))
        except ValueError as error:
            raise GradeRefused("boundary_unavailable", f"missing worker result; logs: {attempt}") from error
        if result.get("invocation") != config["invocation"]:
            raise GradeRefused("boundary_unavailable", "worker result belongs to another invocation")
        if "refusal" in result:
            receipt = result["refusal"]
            raise GradeRefused(receipt["reason"], receipt["detail"])
        verdict = result["verdict"]
        expected = {"case": state["case"]["id"], "harness": state["record"]["harness"], "skills_at": state["record"]["skills_at"]}
        if any(verdict.get(k) != v for k, v in expected.items()) or set(verdict["promises"]) != set(state["case"]["promises"]):
            raise GradeRefused("boundary_unavailable", "worker result does not match the authorized case")
        output.write("verdict.json", _json(verdict))
        return verdict
    except GradeRefused as refusal:
        refusal.receipt["run_id"] = run_id
        refusal.receipt["attempt"] = str(attempt)
        (attempt / "refusal.json").write_bytes(_json(refusal.receipt))
        raise
    finally:
        if output:
            output.close()


def _worker(result_fd):
    os.set_inheritable(result_fd, False)
    config = json.load(sys.stdin)
    result = {"invocation": config["invocation"]}
    try:
        sys.path.insert(0, str(HERE))
        import oracles
        oracles._IO = _Environment(config["roots"], config["trees"], config["skills"], config["scratch"],
                                   config["project"] if not config["trees"] else None)
        oracles.HERE = Path(config["references"])
        oracles.HISTORIES = oracles.HERE / "histories"
        trace = config["trace"]
        record = config["record"]
        trace.setdefault("x_turns", record.get("turns", []))
        trace.setdefault("x_baseline", record.get("baseline"))
        case = config["case"]
        result["verdict"] = {"case": case["id"], "harness": record["harness"], "skills_at": record["skills_at"],
            "promises": {pid: oracles.check(pid, trace, case, Path(config["project"])) for pid in case["promises"]}}
    except GradeRefused as refusal:
        result["refusal"] = refusal.receipt
    with os.fdopen(result_fd, "wb") as stream:
        stream.write(_json(result))


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--worker":
        _worker(int(sys.argv[2]))
    else:
        raise SystemExit("use live.py grade with a registered run ID")
