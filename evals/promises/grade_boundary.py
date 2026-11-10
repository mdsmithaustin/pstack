import errno
import fcntl
import hashlib
import hmac
import json
import os
import platform
import pwd
import re
import shlex
import shutil
import signal
import stat
import subprocess
import tempfile
import sys
import threading
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

HERE = Path(__file__).resolve().parent
_HOST_ACCOUNT = pwd.getpwuid(os.getuid())
PYTHON_ROOT = Path(_HOST_ACCOUNT.pw_dir) / ".local/share/mise/installs/python/3.14.7"
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

RELAY_CASE = "feature-recovery-obligations-run"
RELAY_POLICY = ("poteto-mode/SKILL.md", "poteto-mode/playbooks/feature.md",
                "poteto-mode/references/task-triggers.md", "poteto-mode/references/review-lens.md")
RELAY_DIFF = ("diff --full-index --binary --no-ext-diff --no-textconv --no-renames --no-color "
              "--no-prefix --diff-algorithm=myers --no-indent-heuristic --unified=10000")
RELAY_READ = re.compile(
    r'(?:// @exec: \{[ \t]*"max_output_tokens":[ \t]*[1-9][0-9]{0,5}[ \t]*\}[ \t]*\r?\n)?'
    r'text\(await tools\.exec_command\(\{\s*cmd:\s*("(?:[^"\\]|\\.)*"),\s*'
    r'workdir:\s*("(?:[^"\\]|\\.)*"),\s*max_output_tokens:\s*20000\s*\}\)\);?'
)
RELAY_FINDINGS = {
    "preserved_shaped": "Did the native work open against the actual baseline and use history and preserved behavior to shape the data before edits?",
    "full_route_planned": "Did the native work choose the full route before implementation, record the throughput checkpoint and follow the appropriate delegation decision?",
    "designed": "Before implementation, did the native work compare suitable alternatives or record a supported single-design skip?",
    "specified_built": "Did the native work settle acceptance before implementation and show paired passing integrated and strict baseline test results on the delivery?",
    "native_cli_proof": "Did the native work verify the real CLI and observe recovery effects on the delivery?",
    "spec_scrutiny": "Which read-only native report covered the matching bytes, and did it verify the original spec and resolve any competing or open findings?",
    "structural_scrutiny": "Which read-only native report covered the matching bytes, and did it resolve structure against the review lens and recorded history decision?",
    "landed_published": "Did the native work identify the committed delivery and account for publication and any departures?",
}


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

    def remove(self, rel):
        """Delete the directory at rel without following a link on the way to it or inside it. Absent is done."""
        self.verify()
        try:
            parent, name = self._parent(rel)
        except FileNotFoundError:
            return
        try:
            info = os.stat(name, dir_fd=parent, follow_symlinks=False)
            if not stat.S_ISDIR(info.st_mode):
                raise GradeRefused("unsafe_link" if stat.S_ISLNK(info.st_mode) else "unsafe_object", self.path / rel)
            shutil.rmtree(name, dir_fd=parent)
        except FileNotFoundError:
            pass
        except OSError as error:
            raise GradeRefused("unsafe_link", self.path / rel) from error
        finally:
            os.close(parent)

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


def write_file(target, data):
    root = _Root.open(target.parent, create=True)
    try:
        root.write(target.name, data)
    finally:
        root.close()


def copy_file(source, target):
    data = read_file(source)
    write_file(target, data)
    return data


def create_file(path):
    root = _Root.open(path.parent)
    try:
        fd = os.open(path.name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=root.fd)
    except OSError as error:
        raise GradeRefused("output_unsafe", path) from error
    finally:
        root.close()
    return os.fdopen(fd, "wb")


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
        for name in os.listdir(root.fd):
            try:
                directory = stat.S_ISDIR(root.info(name).st_mode)
            except (GradeRefused, FileNotFoundError):
                continue
            if directory:
                (destination / name).mkdir(exist_ok=True, mode=0o700)
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
        for name in dict.fromkeys((case["id"], case.get("references", case["id"]))):
            _copy_tree(HERE / "cases" / name, private / "references" / "cases" / name)
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
        if case["id"] == RELAY_CASE and record["harness"] == "codex":
            try:
                state["relay_start"] = _relay_start(state, private)
            except (ValueError, FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
                raise GradeRefused("input_changed", f"Relay inputs could not be pinned at admission: {error}", run_id) from error
        self.save(state)
        return self.load(run_id)[0]


def _sha(value):
    return hashlib.sha256(value).hexdigest()


def _relay_digest(value):
    return _sha(json.dumps(value, sort_keys=True, separators=(",", ":")).encode())


def _relay_policy(state, private):
    installed = _Root.open(Path(state["project"]["path"]) / ".agents/skills")
    protected = private / "references/relay-policy"
    try:
        for name in RELAY_POLICY:
            target = protected / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(installed.read(name))
    finally:
        installed.close()
    return {name: _sha(read_file(protected / name)) for name in RELAY_POLICY}


@contextmanager
def _relay_objects(state, private):
    common = _Root.open(state["git"]["path"], state["git"]["identity"])
    try:
        with tempfile.TemporaryDirectory(dir=private) as directory:
            db = Path(directory)
            env = {"HOME": str(db), "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_NOSYSTEM": "1",
                   "PATH": "/usr/bin:/bin", "LANG": "C"}
            argv = [str(GIT), "--no-replace-objects", "--git-dir", str(db)]
            subprocess.run([*argv, "init", "--quiet", "--bare", "--template="], check=True,
                           cwd=db, env=env, capture_output=True, timeout=10)
            total = 0
            for source in common.files():
                rel = source.relative_to(common.path).as_posix()
                if not rel.startswith("objects/"):
                    continue
                if rel in ("objects/info/alternates", "objects/info/http-alternates") or rel.endswith(".promisor"):
                    raise GradeRefused("unapproved_git", "the Relay delivery uses indirect Git objects")
                if not re.fullmatch(r"objects/(?:[0-9a-f]{2}/[0-9a-f]{38}|pack/pack-[0-9a-f]{40}\.(?:idx|pack))", rel):
                    continue
                total += common.info(rel).st_size
                if total > 16 * 1024 * 1024:
                    raise ValueError("the Relay object input exceeds the case limit")
                target = db / rel
                target.parent.mkdir(exist_ok=True)
                target.write_bytes(common.read(rel))
            profile = _policy([], [db])

            def git(*args):
                return subprocess.run(["/usr/bin/sandbox-exec", "-p", profile, *argv, *args], check=True,
                                      cwd=db, env=env, capture_output=True, timeout=10).stdout

            yield git
    finally:
        common.close()


def _relay_manifest(git, revision, destination=None):
    manifest = {}
    for row in git("ls-tree", "-rz", "--full-tree", revision).split(b"\0")[:-1]:
        info, path = row.split(b"\t", 1)
        mode, kind, oid = info.decode("ascii").split()
        name = path.decode("utf-8")
        rel = Path(name)
        if (kind != "blob" or mode not in ("100644", "100755") or rel.is_absolute()
                or rel.as_posix() != name or any(part in (".", "..", ".git") for part in rel.parts)):
            raise ValueError(f"unsupported Relay delivery entry {name!r}")
        data = git("cat-file", "blob", oid)
        if destination:
            target = destination / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("xb") as stream:
                stream.write(data)
            target.chmod(0o755 if mode == "100755" else 0o644)
        manifest[name] = [mode, _sha(data)]
    return manifest


def _delivery_claim(reply):
    if not isinstance(reply, str):
        raise ValueError("the final reply is not text")
    claims = set()
    for line in reply.splitlines():
        line = line.strip()
        if not re.match(r"Delivery(?:\s|$)", line):
            continue
        claim = re.fullmatch(r"Delivery (refs/heads/\S+) ([0-9a-fA-F]{40})", line)
        if claim is None:
            raise ValueError("malformed Delivery line in the final reply")
        ref, sha = claim.groups()
        claims.add((ref, sha.lower()))
    if not claims:
        raise ValueError("no delivery branch and commit in the final reply")
    if len(claims) > 1:
        raise ValueError("conflicting delivery declarations in the final reply")
    return claims.pop()


def _relay_checkout(state, trees, ref, sha):
    common = _Root.open(state["git"]["path"], state["git"]["identity"])
    try:
        selected = []
        for tree in trees:
            path = Path(tree["path"])
            root = _Root.open(path, tree["identity"])
            try:
                if tree == state["project"]:
                    head = common.read("HEAD")
                else:
                    pointer = root.read(".git").decode()
                    gitdir = _git_path(pointer[8:], path).relative_to(common.path)
                    head = common.read(gitdir / "HEAD")
                if head == f"ref: {ref}\n".encode():
                    selected.append(str(path))
            finally:
                root.close()
        if len(selected) != 1:
            raise ValueError("the delivery branch does not name one admitted checkout")
        try:
            resolved = common.read(ref).strip()
        except FileNotFoundError:
            try:
                packed = common.read("packed-refs").splitlines()
            except FileNotFoundError:
                packed = []
            resolved = next((line.split(b" ", 1)[0] for line in packed if line.endswith(b" " + ref.encode())), b"")
        if resolved != sha.encode("ascii"):
            raise ValueError("the delivery commit does not match the checkout HEAD")
        return selected[0]
    finally:
        common.close()


def _relay_start(state, private):
    baseline = (state["record"].get("baseline") or [None])[-1]
    if not isinstance(baseline, str) or not re.fullmatch(r"[0-9a-f]{40}", baseline) or not state["git"]:
        raise ValueError("the Relay baseline commit was not available at admission")
    with _relay_objects(state, private) as git:
        if git("cat-file", "-t", baseline) != b"commit\n":
            raise ValueError("the admitted Relay baseline is not a commit")
        git("fsck", "--strict", "--no-reflogs", baseline)
        tree = _relay_manifest(git, baseline)
    return {"baseline": baseline, "baseline_digest": _relay_digest(tree), "policy": _relay_policy(state, private),
            "probe": _sha(read_file(private / "references/cases" / RELAY_CASE / "held_out.py"))}


def _relay_reviewer_edits(review, project, checkout, cwd, manifest):
    from oracles import EDIT_TOOLS, View

    actions = []
    for event in review["actions"]:
        if event.get("name") in EDIT_TOOLS and event["kind"] == "tool_call":
            args = event.get("input") or {}
            patch = args.get("code") or args.get("raw")
            if isinstance(patch, str):
                event = {**event, "input": {**args, "patch": patch}}
        actions.append(event)
    view = View({"events": actions}, {}, None)
    calls = {call["seq"]: call for call in view.tool_calls}
    edits = []
    roots = (project, Path(checkout), cwd)
    for seq, path, _ in view.edits():
        call = calls[seq]
        native_change = (call.get("name") == "FileChange"
                         and (call.get("input") or {}).get("status") == "completed")
        if not native_change and not (view.results_for(call) or {}).get("ok"):
            continue
        if path == "?":
            edits.append(path)
            continue
        directory = Path((call.get("input") or {}).get("cwd") or review["cwd"] or cwd)
        full = Path(os.path.normpath(directory / path))
        if any(full.is_relative_to(root) and full.relative_to(root).as_posix() in manifest for root in roots):
            edits.append(str(full))
    return edits


def _relay_review(state, base, sha, tree, diff, checkout, manifest, capture):
    turns = state["record"].get("turns") or []
    if not capture or not turns or not turns[-1].get("session_id") or turns[-1]["session_id"] != capture[0]:
        return [], [], [], {"matched": 0, "competing": 0}
    argv = turns[-1].get("argv") or []
    root = Path(state["run"]["path"])
    project = Path(state["project"]["path"])
    required = ('approval_policy="never"', 'sandbox_mode="workspace-write"',
                "sandbox_workspace_write.exclude_slash_tmp=true",
                "sandbox_workspace_write.exclude_tmpdir_env_var=true",
                "sandbox_workspace_write.writable_roots=" + json.dumps([str(project / ".git"), str(root / "tmp")], ensure_ascii=False))
    settings = argv[:argv.index("--")] if "--" in argv else []
    if any([v for v in settings if v.startswith(entry.split("=")[0] + "=")] != [entry] for entry in required):
        return [], [], [], {"matched": 0, "competing": 0}
    if any(v in settings for v in ("--dangerously-bypass-approvals-and-sandbox", "--sandbox", "-s", "--full-auto")):
        return [], [], [], {"matched": 0, "competing": 0}

    matches, competing = [], []
    command_prefix = f"git {RELAY_DIFF} {base} "
    for review in capture[1]:
        record = {k: v for k, v in review.items() if k not in ("reads", "read_calls")}
        attempts, exact = [], []
        for action in review["read_calls"]:
            call = RELAY_READ.fullmatch(action["input"].strip())
            if not call:
                continue
            command, cwd = map(json.loads, call.groups())
            if not command.startswith(command_prefix):
                continue
            attempt = {"command": command, "cwd": cwd, "call": action["call"], "matches_delivery": False}
            attempts.append(attempt)
            reads = [read for read in review["reads"] if read["call"] == action["call"]]
            if len(reads) != 1:
                attempt["availability"] = "unpaired"
                continue
            read = reads[0]
            output = read["output"].encode()
            attempt.update(result=read["result"], exit_code=read["exit_code"], diff_sha256=_sha(output))
            path = Path(cwd)
            admitted = ".." not in path.parts and any(path.is_relative_to(allowed) for allowed in (project.parent, root / "tmp"))
            if (admitted and read["exit_code"] == 0 and output == diff
                    and command[len(command_prefix):] in (sha, tree)):
                attempt["matches_delivery"] = True
                exact.append(attempt)
        record["read_attempts"] = attempts if len(attempts) <= 8 else attempts[:4] + attempts[-4:]
        record["omitted_read_attempts"] = max(0, len(attempts) - 8)
        if not exact or review["incomplete"]:
            competing.append(record)
            continue
        selected = exact[-1]
        edits = _relay_reviewer_edits(review, project, checkout, Path(selected["cwd"]), manifest)
        if edits:
            record["reviewer_edits"] = edits
            competing.append(record)
            continue
        record.update({key: selected[key] for key in ("call", "result", "command", "diff_sha256")})
        matches.append(record)
    return matches[:4], competing[:4], capture[2], {
        "matched": max(0, len(matches) - 4), "competing": max(0, len(competing) - 4)}


def _seal_relay(state, capture):
    private = Path(state["private"]["path"])
    start = state["relay_start"]
    try:
        ref, sha = _delivery_claim(state["trace"].get("final_reply"))
        checkout = _relay_checkout(state, _approved_trees(state), ref, sha)
        base = start["baseline"]
        image = private / "references/relay-delivery"
        with _relay_objects(state, private) as git:
            git("fsck", "--strict", "--no-reflogs", base, sha)
            baseline = _relay_manifest(git, base)
            if _relay_digest(baseline) != start["baseline_digest"]:
                raise GradeRefused("input_changed", "Relay baseline bytes changed")
            git("merge-base", "--is-ancestor", base, sha)
            tree = git("rev-parse", sha + "^{tree}").decode("ascii").strip()
            diff = git(*shlex.split(RELAY_DIFF), base, sha)
            if not diff:
                return {"reason": "the declared Relay commit does not change the fixture"}
            image.mkdir()
            manifest = _relay_manifest(git, sha, image)
        review, competing, lead_evidence, omissions = _relay_review(
            state, base, sha, tree, diff, checkout, baseline.keys() | manifest.keys(), capture)
        return {"checkout": checkout, "ref": ref, "commit": sha,
                "tree_digest": _relay_digest(manifest), "review": review, "competing_reviews": competing,
                "review_omissions": omissions, "lead_evidence": lead_evidence}
    except (ValueError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
        return {"reason": f"the Relay delivery could not be pinned: {error}"}


def _verify_relay(state, trees):
    relay = state.get("relay")
    if relay is None:
        return
    private = Path(state["private"]["path"]) / "references"
    for name, expected in state["relay_start"]["policy"].items():
        if _sha(read_file(private / "relay-policy" / name)) != expected:
            raise GradeRefused("input_changed", f"Relay policy changed: {name}")
    if _sha(read_file(private / "cases" / RELAY_CASE / "held_out.py")) != state["relay_start"]["probe"]:
        raise GradeRefused("input_changed", "the protected Relay probe changed")
    if "reason" in relay:
        return
    try:
        if _relay_checkout(state, trees, relay["ref"], relay["commit"]) != relay["checkout"]:
            raise ValueError("the admitted Relay checkout changed")
    except ValueError as error:
        raise GradeRefused("input_changed", error) from error
    root = _Root.open(private / "relay-delivery")
    try:
        found = {str(path.relative_to(root.path)): [
            "100755" if root.info(path.relative_to(root.path)).st_mode & stat.S_IXUSR else "100644",
            _sha(root.read(path.relative_to(root.path)))] for path in root.files()}
        if _relay_digest(found) != relay["tree_digest"]:
            raise GradeRefused("input_changed", "the pinned Relay delivery image changed")
    finally:
        root.close()


def re_id(value):
    return isinstance(value, str) and len(value) == 32 and all(c in "0123456789abcdef" for c in value)


def _lookup(out, run_id):
    return _Controller(out).load(run_id)[0]


def run_record(run, turns):
    """The run metadata sealed before the first turn. Sealing refuses any later difference except in turns."""
    return {"harness": run.harness, "case": run.case["id"], "skills_at": run.skills_at,
            "project": str(run.project), "timeout_s": run.timeout_s, "turns": turns, "baseline": run.baseline,
            "lead_model": getattr(run, "model", None) or "harness default",
            "lead_effort": getattr(run, "effort", None) or "harness default"}


def _before_turns(run, scratch=()):
    _runtime()
    record = run_record(run, [])
    controller = _Controller(run.root.parent, create=True)
    authorization = controller.issue(run.root, run.project, run.case, record, allocations=(run.project.parent, *scratch))
    if run.case["id"] == RELAY_CASE and run.harness == "codex":
        run._relay_authorization = authorization
    return authorization


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


def _seal(handle, record, trace, *, error=None, write=True):
    _, state = handle._controller.load(handle._id)
    if state["case"]["id"] == RELAY_CASE and state["sealed"]:
        raise GradeRefused("input_changed", "the Relay run is already sealed")
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
    state["error"] = None if error is None else dict(error)
    if "relay_start" in state and error is None:
        state["relay"] = _seal_relay(state, getattr(handle, "_relay_capture", None))
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
    try:
        previous = json.loads(prior)
    except ValueError as error:
        raise GradeRefused("input_changed", "retained prior verdict is not valid JSON") from error
    if not isinstance(previous, dict):
        raise GradeRefused("input_changed", "retained prior verdict must be an object")
    error = previous.get("error")
    if error is not None:
        if not isinstance(error, dict) or set(error) != {"cli", "relogin", "detail"} or any(
                not isinstance(value, str) or not value.strip() for value in error.values()):
            raise GradeRefused("input_changed", "retained error must contain cli, relogin, and detail strings")
        expected = {"case": case["id"], "harness": record["harness"], "skills_at": record["skills_at"]}
        if any(previous.get(key) != value for key, value in expected.items()):
            raise GradeRefused("input_changed", "retained error does not match the reviewed run")
        from live import HARNESSES, adapter
        harness = record["harness"]
        login = getattr(adapter(harness), "LOGIN", None) if harness in HARNESSES else None
        if login is None or (error["cli"], error["relogin"]) != (login.cli, login.relogin):
            raise GradeRefused("input_changed", "retained error does not match the harness login")
        error = dict(error)
    controller = _Controller(out, create=True)
    handle = controller.issue(root, project, case, record, worktrees=worktrees, output=output, original_project=original_project)
    _, state = controller.load(handle._id)
    state["prior_verdict_digest"] = hashlib.sha256(prior).hexdigest()
    controller.save(state)
    _seal(handle, record, trace, error=error, write=False)
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

    def delivery(self, reply):
        ref, sha = _delivery_claim(reply)
        branch_ref = ref.encode("utf-8") + b"\n"
        matches = []
        for path in sorted(self.trees):
            branch = self.git(path, ("symbolic-ref", "--quiet", "--no-recurse", "HEAD"), text=False)
            if branch.returncode == 0 and branch.stdout == branch_ref:
                matches.append(Path(path))
        if len(matches) != 1:
            raise ValueError("the delivery branch does not name one admitted checkout")
        project = matches[0]
        head = self.git(project, ("rev-parse", "HEAD", "HEAD^{commit}"), text=False)
        oid = sha.encode("ascii")
        if head.returncode or head.stdout.splitlines() != [oid, oid]:
            raise ValueError("the delivery commit does not match the checkout HEAD")
        return project, ref, sha

    def check(self, path, command, timeout):
        if str(path) not in self.trees:
            raise GradeRefused("unapproved_worktree", path)
        relay = getattr(self, "relay", None)
        cwd = self.scratch if relay and relay.get("checkout") == str(path) else path
        proc = subprocess.Popen(shlex.split(command), cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
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
            target = output.info("verdict.json")
        except FileNotFoundError:
            target = None
        error = state.get("error")
        if "error" not in state and target is not None and stat.S_ISREG(target.st_mode):
            try:
                error = json.loads(output.read("verdict.json")).get("error")
            except FileNotFoundError:
                pass
        trees = _approved_trees(state)
        _verify_relay(state, trees)
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
        references = Path(state["private"]["path"]) / "references"
        skills = Path(state["private"]["path"]) / "fallback" / "skills"
        relay = state.get("relay")
        relay_grade = relay is not None
        if relay_grade:
            skills = references / "relay-policy"
        elif state["project"]["identity"] is not None:
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
        roots = [_snapshot(references)] if relay_grade else [*trees, _snapshot(references), _snapshot(skills)]
        decision = state.get("relay_decision") or {}
        findings = decision.get("findings") if state.get("relay_packet_digest") == decision.get("packet_digest") else None
        config = {"invocation": uuid.uuid4().hex, "case": state["case"], "record": state["record"],
                  "trace": state["trace"], "project": state["project"]["path"], "roots": roots, "trees": trees,
                  "skills": str(skills), "references": str(references),
                  "scratch": str(scratch), "relay": relay, "relay_decision": findings}
        writes = [scratch] if relay_grade else [*(Path(r["path"]) for r in trees), scratch]
        profile = _policy([Path(state["private"]["path"]) / "code", references, skills], writes)
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
        if error:
            from harnesses.login import error_verdict
            verdict = error_verdict(state["case"], state["record"]["harness"], state["record"]["skills_at"],
                                    error, verdict["promises"])
        if state["case"]["id"] == RELAY_CASE:
            _publish_relay_verdict(controller, state, output, verdict)
        else:
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


def _relay_packet(state, recovery):
    trace = state["trace"]
    start = state["relay_start"]
    private = Path(state["private"]["path"]) / "references/relay-policy"
    events = []
    for event in trace.get("events", []):
        fields = ("seq", "kind", "name", "input", "id", "ok", "output_head", "text")
        record = {name: event[name] for name in fields if name in event}
        if len(_json(record)) > 4096:
            record = {"seq": event.get("seq"), "kind": event.get("kind"),
                      "excerpt": _json(record).decode()[:3900]}
        events.append(record)
    if len(events) > 1200:
        events = [*events[:800], {"omitted": len(events) - 1200}, *events[-400:]]
    worklist = trace.get("worklist") or []
    return {"run": state["id"], "case": RELAY_CASE, "skills_at": state["record"]["skills_at"],
            "sealed_inputs": state["raw_digests"], "start": start, "delivery": state["relay"],
            "prompt": state["case"]["turns"], "policy": {name: read_file(private / name).decode() for name in RELAY_POLICY},
            "worklist": [{"seq": plan.get("seq"), "omitted_items": max(0, len(plan["items"]) - 24), "items": [
                {"text": item["text"][:1500], "state": item.get("state"), "truncated": len(item["text"]) > 1500}
                for item in plan["items"][:24]
            ]} for plan in worklist[:30]], "omitted_worklists": max(0, len(worklist) - 30), "lead_events": events,
            "final_reply": (trace.get("final_reply") or "")[:8000],
            "recovery": recovery, "findings": RELAY_FINDINGS}


@contextmanager
def _relay_lock(controller):
    fcntl.flock(controller.root.fd, fcntl.LOCK_EX)
    try:
        yield
    finally:
        fcntl.flock(controller.root.fd, fcntl.LOCK_UN)


def _publish_relay_verdict(controller, state, output, verdict):
    finding = next(iter(verdict["promises"].values()))
    with _relay_lock(controller):
        _, current = controller.load(state["id"])
        if current.get("relay_decision") != state.get("relay_decision"):
            raise GradeRefused("input_changed", "Relay adjudication changed while grading")
        if finding.get("needs_judge") and "relay_packet_digest" not in current:
            packet = _relay_packet(current, finding["recovery"])
            write_file(Path(current["private"]["path"]) / "relay-packet.json", _json(packet))
            current["relay_packet_digest"] = _relay_digest(packet)
            controller.save(current)
        output.write("verdict.json", _json(verdict))


def _relay_adjudication(authorization, decision=None):
    controller = authorization._controller
    with _relay_lock(controller):
        _, state = controller.load(authorization._id)
        return _record_relay_judgment(controller, state, decision)


def _record_relay_judgment(controller, state, decision):
    digest = state.get("relay_packet_digest")
    if state["case"]["id"] != RELAY_CASE or not digest:
        raise GradeRefused("input_changed", "there is no Relay packet for this authorization")
    packet = json.loads(read_file(Path(state["private"]["path"]) / "relay-packet.json"))
    if _relay_digest(packet) != digest:
        raise GradeRefused("input_changed", "the Relay adjudication packet changed")
    if decision is None:
        return {"packet_digest": digest, "packet": packet}
    if not isinstance(decision, dict) or set(decision) != {"packet_digest", "findings"} or decision["packet_digest"] != digest:
        raise GradeRefused("input_changed", "the Relay decision belongs to another packet")
    findings = decision["findings"]
    if not isinstance(findings, dict) or set(findings) != set(RELAY_FINDINGS):
        raise GradeRefused("input_changed", "the Relay decision must cover every obligation")
    for finding in findings.values():
        if (not isinstance(finding, dict) or set(finding) != {"status", "reason"}
                or finding["status"] not in ("pass", "breach", "unavailable")
                or not isinstance(finding["reason"], str) or not 0 < len(finding["reason"].strip()) <= 800):
            raise GradeRefused("input_changed", "invalid Relay obligation finding")
    if "relay_decision" in state:
        raise GradeRefused("input_changed", "the Relay packet already has an adjudication")
    state["relay_decision"] = decision
    controller.save(state)
    return {"accepted": digest}


def _worker(result_fd):
    os.set_inheritable(result_fd, False)
    config = json.load(sys.stdin)
    result = {"invocation": config["invocation"]}
    try:
        sys.path.insert(0, str(HERE))
        import oracles
        oracles._IO = _Environment(config["roots"], config["trees"], config["skills"], config["scratch"],
                                   config["project"] if not config["trees"] else None)
        oracles._IO.relay = config["relay"]
        oracles._IO.relay_decision = config["relay_decision"]
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
    elif len(sys.argv) == 4 and sys.argv[1] in ("--relay-packet", "--relay-judgment"):
        authorization = _lookup(Path(sys.argv[2]), sys.argv[3])
        decision = None
        if sys.argv[1] == "--relay-judgment":
            decision = json.loads(sys.stdin.read(16385))
            if decision is None:
                raise SystemExit("a Relay decision object is required")
        print(json.dumps(_relay_adjudication(authorization, decision)))
    else:
        raise SystemExit("use live.py grade with a registered run ID")
