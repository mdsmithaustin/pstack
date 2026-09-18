import io
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tarfile
from pathlib import Path


IMAGE = "python:3.12-slim@sha256:229a2c5bfa27522db7815ea81f9bed70af17ccb9de9fc7ad142b1877b5830d36"
SHELL_FENCE = re.compile(r"```(?:bash|sh|shell)\s*\n(.*?)\n```", re.DOTALL | re.IGNORECASE)
CONTAINER_PROGRAM = r'''
import ctypes
import json
import os
import resource
import secrets
import select
import shutil
import socket
import struct
import subprocess
import sys
import tarfile
from pathlib import Path


TRACE_PROLOGUE = """
import os as _pstack_os
import socket as _pstack_socket
import sys as _pstack_sys
with _pstack_socket.socket(_pstack_socket.AF_UNIX, _pstack_socket.SOCK_STREAM) as _pstack_client:
    _pstack_client.connect(_pstack_os.environ["PSTACK_EVIDENCE_SOCKET"])
    _pstack_client.sendall(b"ready\\n")
    _pstack_reply = _pstack_client.recv(1024).decode("ascii", "strict").strip()
if _pstack_reply.startswith("EXIT "):
    raise SystemExit(int(_pstack_reply.split()[1]))
if _pstack_reply != "OK":
    print(_pstack_reply, file=_pstack_sys.stderr)
    raise SystemExit(125)
"""
PR_SET_DUMPABLE = 4


def peer_process(connection):
    pid, _, _ = struct.unpack("3i", connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
    process = Path("/proc") / str(pid)
    raw = (process / "cmdline").read_bytes()
    arguments = tuple(part.decode("utf-8", "replace") for part in raw.split(b"\0") if part)
    cwd = Path(os.readlink(process / "cwd")).resolve()
    executable = Path(os.readlink(process / "exe")).resolve()
    return cwd, executable, arguments


def operation_matches(specification, event, project):
    program = specification.get("program")
    expected_arguments = specification.get("args")
    if (
        program != "python"
        or not isinstance(expected_arguments, list)
        or not expected_arguments
        or not all(isinstance(argument, str) for argument in expected_arguments)
        or not expected_arguments[0]
        or expected_arguments[0].startswith("-")
    ):
        raise RuntimeError("invalid required operation")
    root = project.resolve(strict=True)
    expected_script = (root / expected_arguments[0]).resolve(strict=True)
    if not expected_script.is_relative_to(root):
        raise RuntimeError("invalid required operation")
    cwd, executable, arguments = event
    if (
        executable != Path(sys.executable).resolve()
        or not cwd.is_relative_to(root)
        or len(arguments) < 2
        or not arguments[1]
        or arguments[1].startswith("-")
        or tuple(arguments[2:]) != tuple(expected_arguments[1:])
    ):
        return False
    actual_script = (cwd / arguments[1]).resolve(strict=True)
    return actual_script.is_relative_to(root) and actual_script == expected_script


def serve_evidence(listener, stop_reader, result_writer, specifications, project, forced_exit):
    events = set()
    try:
        while True:
            readable, _, _ = select.select([listener, stop_reader], [], [])
            if stop_reader in readable:
                break
            connection, _ = listener.accept()
            with connection:
                connection.settimeout(1)
                try:
                    connection.recv(64)
                    event = peer_process(connection)
                    trusted = any(operation_matches(specification, event, project) for specification in specifications)
                except (OSError, ValueError):
                    trusted = False
                if trusted:
                    events.add(event)
                    reply = f"EXIT {forced_exit}" if forced_exit is not None else "OK"
                else:
                    reply = "REJECT"
                try:
                    connection.sendall((reply + "\n").encode("ascii"))
                except BrokenPipeError:
                    pass
        payload = {
            "events": [
                {"cwd": str(cwd), "executable": str(executable), "arguments": list(arguments)}
                for cwd, executable, arguments in sorted(events)
            ]
        }
    except BaseException as error:
        payload = {"events": [], "error": f"{type(error).__name__}: {error}"}
    os.write(result_writer, json.dumps(payload).encode("utf-8"))


def start_evidence_server(listener, specifications, project, forced_exit):
    stop_reader, stop_writer = os.pipe()
    result_reader, result_writer = os.pipe()
    server_pid = os.fork()
    if server_pid == 0:
        os.close(stop_writer)
        os.close(result_reader)
        os.setgroups([])
        os.setgid(65534)
        os.setuid(65534)
        if ctypes.CDLL(None).prctl(PR_SET_DUMPABLE, 0, 0, 0, 0) != 0:
            os._exit(126)
        serve_evidence(listener, stop_reader, result_writer, specifications, project, forced_exit)
        os._exit(0)
    os.close(stop_reader)
    os.close(result_writer)
    return server_pid, stop_writer, result_reader


def finish_evidence_server(server_pid, stop_writer, result_reader):
    os.write(stop_writer, b"stop")
    os.close(stop_writer)
    chunks = []
    while True:
        chunk = os.read(result_reader, 4096)
        if not chunk:
            break
        chunks.append(chunk)
    os.close(result_reader)
    _, status = os.waitpid(server_pid, 0)
    payload = json.loads(b"".join(chunks))
    if status != 0 or "error" in payload:
        raise RuntimeError(payload.get("error", f"evidence server exited with status {status}"))
    return {
        (Path(event["cwd"]), Path(event["executable"]), tuple(event["arguments"]))
        for event in payload["events"]
    }


def instrument_operations(project, specifications):
    paths = {specification["args"][0] for specification in specifications}
    for relative in paths:
        target = project / relative
        target.write_text(TRACE_PROLOGUE + target.read_text())


def operation_seen(specification, events, project):
    return any(operation_matches(specification, event, project) for event in events)


def run_case(root, plan, definition, bootstrap):
    results = []
    base_state = next(state for state in definition["states"] if state["exit"] == "zero")
    forced_state = {
        "name": "forced-operation-failure",
        "bootstrap_state": base_state["name"],
        "exit": "nonzero",
        "required_operations": base_state["required_operations"][:1],
        "force_exit": 97,
    }
    states = [*definition["states"], forced_state]
    expected_order = {state["name"]: index for index, state in enumerate(states)}
    secrets.SystemRandom().shuffle(states)
    for state in states:
        run_root = root / "run"
        project = run_root / "project"
        project.mkdir(parents=True)
        home = run_root / "home"
        home.mkdir()
        home.chmod(0o555)
        shared_memory = Path("/dev/shm")
        if shared_memory.exists():
            shared_memory.chmod(0o555)
        setup = subprocess.run(
            [sys.executable, "-c", bootstrap, str(project), state.get("bootstrap_state", state["name"])],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=5,
            check=False,
        )
        if setup.returncode != 0:
            raise RuntimeError(f"setup failed for {state['name']}: {setup.stderr}")
        instrument_operations(project, state["required_operations"])
        evidence_path = run_root / "evidence.sock"
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        listener.bind(str(evidence_path))
        evidence_path.chmod(0o666)
        listener.listen()
        server_pid, stop_writer, result_reader = start_evidence_server(
            listener, state["required_operations"], project, state.get("force_exit")
        )
        environment = {
            "HOME": str(home),
            "LANG": "C.UTF-8",
            "PATH": f"{project / 'bin'}:/usr/local/bin:/usr/bin:/bin",
            "PSTACK_EVIDENCE_SOCKET": str(evidence_path),
            "PYTHONDONTWRITEBYTECODE": "1",
        }
        candidate_cwd = project / plan["workdir"]
        if not candidate_cwd.is_dir():
            results.append({
                "state": state["name"],
                "exit": None,
                "expected": state["exit"],
                "exit_matches": False,
                "timed_out": False,
                "missing_operations": state["required_operations"],
                "stdout": "",
                "stderr": "candidate working directory does not exist",
            })
            finish_evidence_server(server_pid, stop_writer, result_reader)
            listener.close()
            shutil.rmtree(run_root)
            continue
        process = subprocess.Popen(
            ["/bin/sh", str(root / "input" / "plan.sh")],
            cwd=candidate_cwd,
            env=environment,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            user=65534,
            group=65534,
            extra_groups=[],
            start_new_session=True,
            preexec_fn=lambda: resource.setrlimit(resource.RLIMIT_FSIZE, (0, 0)),
        )
        timed_out = False
        try:
            stdout, stderr = process.communicate(timeout=state.get("timeout_seconds", 5))
        except subprocess.TimeoutExpired:
            timed_out = True
            os.killpg(process.pid, 9)
            stdout, stderr = process.communicate()
        try:
            os.killpg(process.pid, 9)
        except ProcessLookupError:
            pass
        seen = finish_evidence_server(server_pid, stop_writer, result_reader)
        listener.close()
        expected_zero = state["exit"] == "zero"
        exit_matches = not timed_out and ((process.returncode == 0) == expected_zero)
        missing_operations = [
            specification
            for specification in state["required_operations"]
            if not operation_seen(specification, seen, project)
        ]
        results.append({
            "state": state["name"],
            "exit": process.returncode,
            "expected": state["exit"],
            "exit_matches": exit_matches,
            "timed_out": timed_out,
            "missing_operations": missing_operations,
            "observed_commands": [list(arguments) for _, _, arguments in sorted(seen)],
            "stdout": stdout[-1000:],
            "stderr": stderr[-1000:],
        })
        shutil.rmtree(run_root)
    return sorted(results, key=lambda result: expected_order[result["state"]])


root = Path("/work")
input_root = root / "input"
input_root.mkdir()
payloads = {}
with tarfile.open(fileobj=sys.stdin.buffer, mode="r|*") as archive:
    for member in archive:
        if member.name not in {"plan.sh", "bootstrap.py", "definition.json"} or not member.isfile():
            raise RuntimeError("unexpected archive member")
        source = archive.extractfile(member)
        if source is None:
            raise RuntimeError("missing archive member")
        payloads[member.name] = source.read()

(input_root / "plan.sh").write_bytes(payloads["plan.sh"])
plan = json.loads(payloads["definition.json"])
bootstrap = payloads["bootstrap.py"].decode("utf-8")
root.chmod(0o711)
results = run_case(root, plan["artifact"], plan["case"], bootstrap)
print(json.dumps({"status": "measured", "states": results}, sort_keys=True))
'''


class InfrastructureFailure(ValueError):
    pass


def canonical_artifact_root(root: Path) -> Path:
    absolute = root.absolute()
    parts = list(absolute.parts[1:])
    current = Path(absolute.anchor)
    if parts and (current / parts[0]).is_symlink():
        alias = current / parts.pop(0)
        resolved = alias.resolve(strict=True)
        if alias.lstat().st_uid != 0 or resolved.stat().st_uid != 0:
            raise InfrastructureFailure(f"output path contains an untrusted symlink: {alias}")
        current = resolved
    for part in parts:
        current /= part
        if current.is_symlink():
            raise InfrastructureFailure(f"output path contains a symlink: {current}")
    return current


def read_output(output_dir: Path) -> str:
    absolute = canonical_artifact_root(output_dir) / "output.md"
    descriptor = -1
    try:
        descriptor = os.open(absolute.anchor, os.O_RDONLY | os.O_DIRECTORY)
        for index, part in enumerate(absolute.parts[1:]):
            final = index == len(absolute.parts) - 2
            flags = os.O_RDONLY | os.O_NOFOLLOW
            flags |= os.O_NONBLOCK if final else os.O_DIRECTORY
            next_descriptor = os.open(part, flags, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = next_descriptor
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise InfrastructureFailure("output.md is not a regular file")
        if metadata.st_nlink != 1:
            raise InfrastructureFailure("output.md must have exactly one hard link")
        stream = os.fdopen(descriptor, "r", encoding="utf-8")
        descriptor = -1
        with stream:
            text = stream.read()
            if os.fstat(stream.fileno()).st_nlink != 1:
                raise InfrastructureFailure("output.md must have exactly one hard link")
            return text
    except (OSError, UnicodeError) as error:
        raise InfrastructureFailure(
            f"output path contains a symlink or unreadable component: {error}"
        ) from error
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def parse_plan(text: str) -> dict:
    fences = SHELL_FENCE.findall(text)
    if len(fences) != 1:
        raise ValueError("output must contain exactly one fenced shell artifact")
    plan = {"script": fences[0], "workdir": "."}
    if not plan["script"].strip():
        raise ValueError("shell artifact must be non-empty")
    if len(plan["script"].encode()) > 16384 or "\0" in plan["script"]:
        raise ValueError("script is too large or contains a NUL byte")
    return plan


def load_case(case_id: str) -> tuple[dict, Path]:
    root = Path(__file__).resolve().parent
    definitions = json.loads((root / "cases.json").read_text(encoding="utf-8"))
    if case_id not in definitions:
        raise ValueError(f"unknown case: {case_id}")
    definition = definitions[case_id]
    bootstrap = root / "projects" / definition["bootstrap"]
    return definition, bootstrap


def docker_command() -> list[str]:
    return [
        "docker", "run", "--rm", "-i", "--pull", "never",
        "--network", "none",
        "--read-only",
        "--cap-drop", "ALL",
        "--cap-add", "SETUID",
        "--cap-add", "SETGID",
        "--cap-add", "KILL",
        "--security-opt", "no-new-privileges",
        "--pids-limit", "64",
        "--memory", "128m",
        "--cpus", "0.5",
        "--ulimit", "nofile=64:64",
        "--tmpfs", "/work:rw,exec,nosuid,nodev,size=64m,mode=1777",
        "--workdir", "/work",
        IMAGE,
        "python3", "-c", CONTAINER_PROGRAM,
    ]


def archive_bytes(plan: dict, definition: dict, bootstrap: Path) -> bytes:
    payloads = {
        "plan.sh": plan["script"].encode(),
        "bootstrap.py": bootstrap.read_bytes(),
        "definition.json": json.dumps({"artifact": plan, "case": definition}).encode(),
    }
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w") as archive:
        for name, payload in payloads.items():
            info = tarfile.TarInfo(name)
            info.size = len(payload)
            info.mode = 0o600
            archive.addfile(info, io.BytesIO(payload))
    return stream.getvalue()


def replay(plan: dict, definition: dict, bootstrap: Path) -> tuple[int, dict]:
    if shutil.which("docker") is None:
        return 2, {"status": "infrastructure", "reason": "docker is unavailable"}
    try:
        completed = subprocess.run(
            docker_command(),
            input=archive_bytes(plan, definition, bootstrap),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=45,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        return 2, {"status": "infrastructure", "reason": str(error)}
    if completed.returncode != 0:
        return 2, {
            "status": "infrastructure",
            "reason": "container replay failed",
            "stderr": completed.stderr.decode("utf-8", "replace")[-2000:],
        }
    try:
        measured = json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        return 2, {"status": "infrastructure", "reason": f"invalid replay output: {error.msg}"}
    failed = [
        state for state in measured["states"]
        if not state["exit_matches"] or state["missing_operations"]
    ]
    if failed:
        return 1, {"status": "candidate_failure", "failed_states": failed}
    return 0, {
        "status": "pass",
        "states": [state["state"] for state in measured["states"]],
        "operation_evidence": "authenticated by the container evidence server",
    }


def evaluate(case_id: str, output_dir: Path) -> tuple[int, dict]:
    try:
        text = read_output(output_dir)
    except InfrastructureFailure as error:
        return 2, {"status": "infrastructure", "reason": str(error)}
    try:
        plan = parse_plan(text)
        definition, bootstrap = load_case(case_id)
    except (OSError, ValueError) as error:
        return 1, {"status": "candidate_failure", "reason": str(error)}
    return replay(plan, definition, bootstrap)


def main() -> int:
    if len(sys.argv) != 3:
        print(json.dumps({"status": "infrastructure", "reason": "usage: check_plan.py CASE_ID OUTPUT_DIR"}))
        return 2
    code, result = evaluate(sys.argv[1], Path(sys.argv[2]))
    print(json.dumps(result, sort_keys=True))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
