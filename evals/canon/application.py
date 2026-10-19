"""One isolated native application attempt and hash-checked application replay."""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import signal
import stat
import subprocess
import sys
import tarfile
import tempfile
import time

MAX_FILE_BYTES = 16 * 1024 * 1024
MAX_TOTAL_BYTES = 64 * 1024 * 1024
MAX_ENTRIES = 10000
PHASE_TIMEOUT_S = 60
REMOTE = "/tmp/canon-application"
FEATURES = {"multi_agent": True, "hooks": False, "apps": False,
            "enable_mcp_apps": False, "skip_host_skill_discovery": True}
PROVIDER = {"name": "sandboxd", "base_url": "https://chatgpt.com/backend-api/codex",
            "wire_api": "responses", "requires_openai_auth": False}


class ApplicationError(Exception):
    pass


class SpentAttemptError(ApplicationError):
    pass


@dataclass(frozen=True)
class Runtime:
    template: str
    model: str
    effort: str
    timeout_s: int = 240


@dataclass(frozen=True)
class Snapshot:
    directory: Path
    sha256: str

    @classmethod
    def freeze(cls, source: Path, destination: Path) -> Snapshot:
        source, destination = Path(source), Path(destination)
        entries = _scan(source)
        destination.mkdir(parents=True)
        blobs = destination / "blobs"
        blobs.mkdir()
        for entry in entries:
            if entry["kind"] == "file":
                data = _read_file(source / entry["path"])
                if _sha(data) != entry["sha256"]:
                    raise ApplicationError("source changed while freezing")
                blob = blobs / entry["sha256"]
                if not blob.exists():
                    blob.write_bytes(data)
                    blob.chmod(0o444)
        if entries != _scan(source):
            raise ApplicationError("source changed while freezing")
        encoded = _json(entries)
        (destination / "manifest.json").write_bytes(encoded)
        (destination / "manifest.json").chmod(0o444)
        blobs.chmod(0o555)
        destination.chmod(0o555)
        return cls(destination, _sha(encoded))


@dataclass(frozen=True)
class Request:
    runtime: Runtime
    project: Snapshot
    skills: Snapshot | None
    prompt: str


@dataclass(frozen=True)
class Result:
    state: str
    native_valid: bool
    capture: Snapshot | None
    receipt: Path
    elapsed_s: float
    usage: dict | None


def _json(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _read_file(path):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, "rb") as handle:
        info = os.fstat(handle.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_FILE_BYTES:
            raise ApplicationError(f"unsupported or oversized file: {path}")
        data = handle.read(MAX_FILE_BYTES + 1)
    if len(data) > MAX_FILE_BYTES:
        raise ApplicationError(f"oversized file: {path}")
    return data


def _scan(source):
    if source.is_symlink() or not source.is_dir():
        raise ApplicationError("snapshot source must be a directory")
    entries, total = [], 0
    def fail(error):
        raise error

    for directory, dirs, files in os.walk(source, followlinks=False, onerror=fail):
        for name in sorted(dirs + files):
            path = Path(directory) / name
            rel = path.relative_to(source).as_posix()
            mode = path.lstat().st_mode
            if name == ".git" or not (stat.S_ISDIR(mode) or stat.S_ISREG(mode)):
                raise ApplicationError(f"unsupported snapshot entry: {rel}")
            entry = {"path": rel, "mode": stat.S_IMODE(mode),
                     "kind": "dir" if stat.S_ISDIR(mode) else "file"}
            if entry["mode"] & ~0o777:
                raise ApplicationError(f"unsupported permissions: {rel}")
            if entry["kind"] == "file":
                data = _read_file(path)
                total += len(data)
                entry.update(size=len(data), sha256=_sha(data))
            entries.append(entry)
            if len(entries) > MAX_ENTRIES or total > MAX_TOTAL_BYTES:
                raise ApplicationError("snapshot size limit exceeded")
    return sorted(entries, key=lambda entry: entry["path"])


def _inventory(snapshot):
    directory = Path(snapshot.directory)
    if directory.is_symlink() or not directory.is_dir():
        raise ApplicationError("invalid snapshot directory")
    if (directory / "blobs").is_symlink() or not (directory / "blobs").is_dir():
        raise ApplicationError("invalid snapshot blob directory")
    for path, mode in ((directory, 0o555), (directory / "blobs", 0o555), (directory / "manifest.json", 0o444)):
        if stat.S_IMODE(path.lstat().st_mode) != mode or path.is_symlink():
            raise ApplicationError("snapshot store mode mismatch")
    encoded = _read_file(directory / "manifest.json")
    if _sha(encoded) != snapshot.sha256:
        raise ApplicationError("snapshot manifest digest mismatch")
    entries = json.loads(encoded)
    if not isinstance(entries, list) or len(entries) > MAX_ENTRIES:
        raise ApplicationError("invalid snapshot inventory")
    paths, directories, blobs, total = set(), set(), set(), 0
    for entry in entries:
        if not isinstance(entry, dict):
            raise ApplicationError("invalid inventory entry")
        path = entry.get("path")
        if not isinstance(path, str) or not path or "\\" in path:
            raise ApplicationError("invalid snapshot path")
        rel = PurePosixPath(path)
        if rel.is_absolute() or rel.as_posix() != path or any(p in (".", "..", ".git") for p in rel.parts) or path in paths:
            raise ApplicationError("unsafe or duplicate snapshot path")
        if any(parent.as_posix() not in directories for parent in list(rel.parents)[:-1]):
            raise ApplicationError("snapshot lacks parent directory")
        if type(entry.get("mode")) is not int or not 0 <= entry["mode"] <= 0o777:
            raise ApplicationError("invalid snapshot permissions")
        kind = entry.get("kind")
        if kind == "dir" and set(entry) == {"path", "mode", "kind"}:
            directories.add(path)
        elif kind == "file" and set(entry) == {"path", "mode", "kind", "sha256", "size"}:
            digest = entry["sha256"]
            if not isinstance(digest, str) or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
                raise ApplicationError("invalid blob digest")
            blob = directory / "blobs" / digest
            if stat.S_IMODE(blob.lstat().st_mode) != 0o444:
                raise ApplicationError("snapshot blob mode mismatch")
            data = _read_file(blob)
            if len(data) != entry["size"] or _sha(data) != digest:
                raise ApplicationError("snapshot blob digest mismatch")
            total += len(data)
            blobs.add(digest)
        else:
            raise ApplicationError("invalid inventory fields")
        paths.add(path)
    if total > MAX_TOTAL_BYTES or {p.name for p in (directory / "blobs").iterdir()} != blobs:
        raise ApplicationError("invalid snapshot blobs or size")
    if {p.name for p in directory.iterdir()} != {"manifest.json", "blobs"}:
        raise ApplicationError("invalid snapshot store")
    return entries


def replay(snapshot: Snapshot, destination: Path) -> Path:
    entries = _inventory(snapshot)
    destination = Path(destination)
    destination.mkdir(parents=True)
    for entry in entries:
        path = destination / entry["path"]
        if entry["kind"] == "dir":
            path.mkdir()
        else:
            path.write_bytes(_read_file(Path(snapshot.directory) / "blobs" / entry["sha256"]))
            path.chmod(entry["mode"])
    for entry in reversed(entries):
        if entry["kind"] == "dir":
            (destination / entry["path"]).chmod(entry["mode"])
    return destination


def _write_json(path, value):
    temporary = path.with_suffix(".tmp")
    with temporary.open("wb") as handle:
        handle.write(_json(value))
        handle.flush()
        os.fsync(handle.fileno())
    temporary.replace(path)
    fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _command(argv, *, timeout=PHASE_TIMEOUT_S, cwd=None, input=None, check=True):
    proc = subprocess.Popen(list(map(str, argv)), cwd=cwd, stdin=subprocess.PIPE if input is not None else subprocess.DEVNULL,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
    try:
        stdout, stderr = proc.communicate(input, timeout=timeout)
    except BaseException:
        for sig in (signal.SIGTERM, signal.SIGKILL):
            try:
                os.killpg(proc.pid, sig)
            except ProcessLookupError:
                pass
            try:
                proc.communicate(timeout=2)
                break
            except subprocess.TimeoutExpired:
                pass
        raise
    if check and proc.returncode:
        raise ApplicationError(f"{argv[0]} {argv[1]} exited {proc.returncode}: {stderr.decode(errors='replace')[-600:]}")
    return subprocess.CompletedProcess(argv, proc.returncode, stdout, stderr)


def _unpack(archive, destination):
    total, names = 0, set()
    with tarfile.open(archive) as tar:
        members = tar.getmembers()
        if len(members) > MAX_ENTRIES + 100:
            raise ApplicationError("harvest entry limit exceeded")
        for member in members:
            path = PurePosixPath(member.name)
            if path.is_absolute() or path.as_posix() != member.name or ".." in path.parts or member.name in names:
                raise ApplicationError("unsafe harvest path")
            if not (member.isdir() or member.isfile()) or member.size > MAX_FILE_BYTES or member.mode & ~0o777:
                raise ApplicationError("unsupported harvest entry")
            total += member.size
            if total > MAX_TOTAL_BYTES + MAX_FILE_BYTES:
                raise ApplicationError("harvest size limit exceeded")
            names.add(member.name)
        destination.mkdir()
        for member in sorted(members, key=lambda item: (len(PurePosixPath(item.name).parts), item.name)):
            target = destination / member.name
            if member.isdir():
                target.mkdir(exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(tar.extractfile(member).read())
                target.chmod(member.mode & 0o777)
        for member in sorted(members, key=lambda item: len(PurePosixPath(item.name).parts), reverse=True):
            if member.isdir():
                (destination / member.name).chmod(member.mode & 0o777)


def run_application(request: Request, slot: Path) -> Result:
    slot = Path(slot).absolute()
    try:
        slot.mkdir(parents=True)
    except FileExistsError as exc:
        raise SpentAttemptError(f"attempt slot already spent: {slot}") from exc
    started = time.monotonic()
    spec = {"runtime": asdict(request.runtime), "project": request.project.sha256,
            "skills": request.skills.sha256 if request.skills else None, "prompt_sha256": _sha(request.prompt.encode()),
            "features": FEATURES, "provider": PROVIDER, "owner_sha256": _sha(Path(__file__).read_bytes())}
    digest = _sha(_json(spec))
    name = "canon-app-" + _sha((str(slot) + digest).encode())[:24]
    receipt = slot / "receipt.json"
    facts = {"schema": 1, "spec": spec, "spec_sha256": digest, "sandbox": name,
             "state": "setup_failed", "native_valid": False, "usage": None, "observed_model": None,
             "capture": None, "cleanup_confirmed": False}
    _write_json(slot / "claim.json", facts)
    capture, created, setup, run_error = None, False, False, None
    try:
        runtime = request.runtime
        if not runtime.template or not runtime.model or runtime.effort not in ("low", "medium", "high", "xhigh", "max") or type(runtime.timeout_s) is not int or runtime.timeout_s <= 0:
            raise ApplicationError("invalid runtime")
        project = replay(request.project, slot / "staging" / "project")
        if any((project / p).exists() for p in (".agents", ".codex")):
            raise ApplicationError("application contains reserved native configuration directories")
        staging = project.parent
        if request.skills:
            replay(request.skills, staging / ".agents" / "skills")
        _command(["git", "init", "-q", "--template=", staging])
        _command(["git", "-C", staging, "config", "core.hooksPath", "/dev/null"])
        _command(["git", "-C", staging, "add", "--all"])
        _command(["git", "-C", staging, "-c", "user.name=canon", "-c", "user.email=canon", "commit", "--allow-empty", "-qm", "public application inputs"])
        templates = json.loads(_command(["sbx", "template", "ls", "--json"]).stdout)
        rows = templates if isinstance(templates, list) else templates.get("images", [])
        matches = [row for row in rows if runtime.template in (row.get("id"),
                   row.get("repository", "") + ":" + row.get("tag", ""),
                   row.get("repository", "").rsplit("/", 1)[-1] + ":" + row.get("tag", ""))]
        if len(matches) != 1:
            raise ApplicationError("runtime template is not uniquely present in local inventory")
        facts["template_identity"] = matches[0]
        _write_json(slot / "claim.json", facts)
        created = True
        _command(["sbx", "create", "--skills", "off", "--clone", "--name", name, "-q", "-t", runtime.template, "codex", staging], timeout=120)
        checked_policy = _command(["sbx", "policy", "check", "network", "--sandbox", name, "example.org", "--json"], check=False)
        policy = json.loads(checked_policy.stdout)
        if checked_policy.returncode not in (0, 1) or (policy.get("allowed") is not False and policy.get("decision") != "deny"):
            raise ApplicationError("sandbox lacks default-deny network policy")
        _command(["sbx", "cp", Path(__file__), f"{name}:{REMOTE}.py"])
        payload = {"root": str(staging), "runtime": asdict(runtime), "skills": spec["skills"], "prompt": request.prompt}
        _write_json(slot / "input.json", payload)
        _command(["sbx", "cp", slot / "input.json", f"{name}:{REMOTE}.json"])
        configured = _command(["sbx", "exec", name, "python3", f"{REMOTE}.py", "setup", f"{REMOTE}.json"], timeout=120)
        facts["setup"] = json.loads(configured.stdout)
        setup = True
        try:
            _command(["sbx", "exec", name, "python3", f"{REMOTE}.py", "run", f"{REMOTE}.json"], timeout=runtime.timeout_s + 15)
        except subprocess.TimeoutExpired:
            run_error = "timeout"
            facts["state"] = "timeout"
        except ApplicationError as exc:
            run_error = "native_failed"
            facts.update(state="native_failed", error=str(exc))
    except KeyboardInterrupt:
        facts["state"] = "interrupted"
    except (ApplicationError, OSError, ValueError, subprocess.TimeoutExpired) as exc:
        facts["error"] = str(exc)
    finally:
        if created:
            if setup:
                try:
                    _command(["sbx", "exec", name, "python3", f"{REMOTE}.py", "kill", f"{REMOTE}.json"])
                    _command(["sbx", "exec", name, "python3", f"{REMOTE}.py", "harvest", f"{REMOTE}.json"])
                    _command(["sbx", "cp", f"{name}:{REMOTE}.tar", slot / "harvest.tar"])
                    _unpack(slot / "harvest.tar", slot / "harvest")
                    status = json.loads((slot / "harvest" / "status.json").read_text())
                    facts["native"] = status
                    facts["usage"] = status.get("usage")
                    candidate = Snapshot(slot / "harvest" / "capture", status["capture_sha256"])
                    _inventory(candidate)
                    capture = candidate
                    facts["capture"] = {"directory": str(capture.directory), "sha256": capture.sha256}
                    facts["state"] = run_error or status["state"]
                    facts["native_valid"] = status["native_valid"] and run_error is None
                    _inventory(request.project)
                    if request.skills:
                        _inventory(request.skills)
                    if not status["guidance_valid"]:
                        raise ApplicationError("assigned guidance changed")
                except (ApplicationError, OSError, ValueError, KeyError, subprocess.TimeoutExpired, tarfile.TarError) as exc:
                    facts.update(state="capture_failed", native_valid=False, error=str(exc))
            try:
                _command(["sbx", "rm", "--force", name])
                listing = json.loads(_command(["sbx", "ls", "--json"]).stdout)
                facts["cleanup_confirmed"] = all(row["name"] != name for row in listing["sandboxes"])
                if not facts["cleanup_confirmed"]:
                    raise ApplicationError("sandbox remains after removal")
            except (ApplicationError, OSError, ValueError, KeyError, subprocess.TimeoutExpired) as exc:
                facts.update(state="cleanup_failed", native_valid=False, cleanup_error=str(exc))
                capture = None
        facts["elapsed_s"] = round(time.monotonic() - started, 6)
        _write_json(receipt, facts)
    return Result(facts["state"], facts["native_valid"], capture, receipt, facts["elapsed_s"], facts["usage"])


def _native_command(runtime, root):
    command = ["codex", "exec", "--json", "--ignore-user-config", "--ignore-rules",
               "--dangerously-bypass-approvals-and-sandbox", "--model", runtime["model"], "-C", str(root / "project")]
    overrides = {"model_reasoning_effort": runtime["effort"], "model_provider": "sandboxd",
                 "model_providers.sandboxd": PROVIDER, "mcp_servers": {},
                 "projects." + json.dumps(str(root)) + ".trust_level": "trusted",
                 **{f"features.{key}": value for key, value in FEATURES.items()}}
    for key, value in overrides.items():
        if isinstance(value, dict):
            value = "{" + ",".join(k + "=" + json.dumps(v) for k, v in value.items()) + "}"
        else:
            value = json.dumps(value)
        command += ["-c", key + "=" + value]
    return command + ["-"]


def _inside_setup(payload):
    root = Path(payload["root"])
    home = Path(REMOTE + "-home")
    home.mkdir()
    (home / ".codex").mkdir()
    installer = root / ".agents/skills/pstack-harness/scripts/subagents.py"
    if installer.is_file():
        _command([sys.executable, installer, "install", "--harness", "codex", "--project", root], timeout=45)
    version = _command(["codex", "--version"]).stdout.decode().strip()
    help_text = _command(["codex", "exec", "--help"]).stdout.decode()
    features = _command(["codex", "features", "list"]).stdout.decode()
    for flag in ("--ignore-user-config", "--ignore-rules", "--json"):
        if flag not in help_text:
            raise ApplicationError(f"native runtime lacks {flag}")
    if not any(line.startswith("multi_agent ") for line in features.splitlines()):
        raise ApplicationError("native runtime lacks required delegation capability")
    return {"cli_version": version, "features": FEATURES}


def _kill_native():
    pid_file = Path(REMOTE + ".pid")
    if pid_file.exists():
        pid = int(pid_file.read_text())
        try:
            os.killpg(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


def _inside_run(payload):
    root = Path(payload["root"])
    home = Path(REMOTE + "-home")
    keep = ("PATH", "HTTPS_PROXY", "HTTP_PROXY", "NO_PROXY", "https_proxy", "http_proxy", "no_proxy",
            "SSL_CERT_FILE", "REQUESTS_CA_BUNDLE", "NODE_EXTRA_CA_CERTS", "NODE_USE_ENV_PROXY")
    env = {key: os.environ[key] for key in keep if key in os.environ}
    env.update(HOME=str(home), CODEX_HOME=str(home / ".codex"), GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL="/dev/null")
    status = {"state": "native_failed", "native_valid": False, "usage": None, "observed_model": None}
    with open(REMOTE + ".stdout", "wb") as stdout, open(REMOTE + ".stderr", "wb") as stderr:
        proc = subprocess.Popen(_native_command(payload["runtime"], root), cwd=root / "project", env=env,
                                stdin=subprocess.PIPE, stdout=stdout, stderr=stderr, start_new_session=True)
        Path(REMOTE + ".pid").write_text(str(proc.pid))
        try:
            proc.communicate(payload["prompt"].encode(), timeout=payload["runtime"]["timeout_s"])
            status["exit_code"] = proc.returncode
        except subprocess.TimeoutExpired:
            status["state"] = "timeout"
        finally:
            _kill_native()
            proc.wait(timeout=5)
    terminal, failed, malformed = False, False, False
    for line in _read_file(Path(REMOTE + ".stdout")).splitlines():
        try:
            event = json.loads(line)
            if not isinstance(event, dict) or not isinstance(event.get("type"), str):
                raise ValueError("invalid native event")
            if event["type"] == "turn.completed":
                terminal = True
                if isinstance(event.get("usage"), dict):
                    status["usage"] = event["usage"]
            failed |= event["type"] in ("turn.failed", "error")
        except (ValueError, TypeError):
            malformed = True
    status.update(terminal_completed=terminal, failure_event=failed, malformed_stream=malformed)
    status["native_valid"] = status.get("exit_code") == 0 and terminal and not failed and not malformed
    if status["native_valid"]:
        status["state"] = "completed"
    _write_json(Path(REMOTE + ".status"), status)


def _inside_harvest(payload):
    root = Path(payload["root"])
    out = Path(REMOTE + "-harvest")
    out.mkdir()
    status_file = Path(REMOTE + ".status")
    status = json.loads(status_file.read_text()) if status_file.exists() else {"state": "timeout", "native_valid": False, "usage": None}
    skills = root / ".agents/skills"
    if payload["skills"] is None:
        status["guidance_valid"] = not skills.exists()
    else:
        frozen_skills = Snapshot.freeze(skills, Path(REMOTE + "-guidance"))
        status["guidance_valid"] = frozen_skills.sha256 == payload["skills"]
    capture = Snapshot.freeze(root / "project", out / "capture")
    status["capture_sha256"] = capture.sha256
    _write_json(out / "status.json", status)
    for suffix in ("stdout", "stderr"):
        source = Path(REMOTE + "." + suffix)
        if source.exists():
            shutil.copyfile(source, out / ("native." + suffix))
    with tarfile.open(REMOTE + ".tar", "w") as archive:
        for path in sorted(out.rglob("*")):
            archive.add(path, arcname=path.relative_to(out), recursive=False)


if __name__ == "__main__":
    operation, payload_file = sys.argv[1:]
    payload = json.loads(Path(payload_file).read_text())
    if operation == "setup":
        print(json.dumps(_inside_setup(payload)))
    elif operation == "run":
        _inside_run(payload)
    elif operation == "kill":
        _kill_native()
    elif operation == "harvest":
        _inside_harvest(payload)
    else:
        raise ApplicationError("unknown inside operation")
