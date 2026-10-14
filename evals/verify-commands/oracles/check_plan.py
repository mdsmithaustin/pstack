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
import time
from pathlib import Path


TRACE_PROLOGUE = """
import os as _pstack_os
import json as _pstack_json
import socket as _pstack_socket
import sys as _pstack_sys
if _pstack_os.getuid() != 65533:
    with _pstack_socket.socket(_pstack_socket.AF_UNIX, _pstack_socket.SOCK_STREAM) as _pstack_client:
        _pstack_client.connect(_pstack_os.environ["PSTACK_EVIDENCE_SOCKET"])
        _pstack_client.sendall(b"ready\\n")
        _pstack_reply = _pstack_client.makefile("rb").readline(16385).decode("ascii", "strict").strip()
    if _pstack_reply.startswith("EXIT "):
        _pstack_os._exit(int(_pstack_reply.split()[1]))
    if _pstack_reply.startswith("{"):
        _pstack_outcome = _pstack_json.loads(_pstack_reply)
        for _pstack_descriptor, _pstack_name in ((1, "stdout"), (2, "stderr")):
            _pstack_data = bytes.fromhex(_pstack_outcome[_pstack_name])
            if _pstack_data:
                _pstack_os.write(_pstack_descriptor, _pstack_data)
        _pstack_os._exit(_pstack_outcome["exit"])
    if _pstack_reply != "OK":
        print(_pstack_reply, file=_pstack_sys.stderr)
        raise SystemExit(125)
"""
TRACE_OBSERVER = """
def _pstack_observe(behavior, cache):
    _pstack_payload = {
        "kind": "observation",
        "behavior": behavior,
        "cache": cache,
        "cache_prefix": _pstack_sys.pycache_prefix,
        "dont_write_bytecode": _pstack_sys.dont_write_bytecode,
        "observer_uid": _pstack_os.getuid(),
    }
    _pstack_message = (_pstack_json.dumps(_pstack_payload) + "\\n").encode("utf-8")
    if len(_pstack_message) > 4096:
        raise SystemExit(125)
    _pstack_os.write(int(_pstack_os.environ["PSTACK_OBSERVATION_FD"]), _pstack_message)
"""
PR_SET_DUMPABLE = 4


def read_message(connection):
    deadline = time.monotonic() + 1
    message = bytearray()
    while True:
        connection.settimeout(max(0.001, deadline - time.monotonic()))
        chunk = connection.recv(4097 - len(message))
        if not chunk or time.monotonic() > deadline:
            raise ValueError("incomplete evidence message")
        message.extend(chunk)
        if len(message) > 4096:
            raise ValueError("evidence message is too large")
        if message.endswith(b"\n"):
            return bytes(message)


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate observation key")
        result[key] = value
    return result


def peer_process(connection):
    pid, _, _ = struct.unpack("3i", connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
    process = Path("/proc") / str(pid)
    lifetime = (process / "stat").read_text().rsplit(")", 1)[1].split()[19]
    raw = (process / "cmdline").read_bytes()
    raw_environment = (process / "environ").read_bytes()
    if len(raw) > 16384 or len(raw_environment) > 32768:
        raise ValueError("operation metadata is too large")
    arguments = tuple(part.decode("utf-8", "strict") for part in raw.removesuffix(b"\0").split(b"\0"))
    entries = []
    for entry in raw_environment.removesuffix(b"\0").split(b"\0"):
        if not entry:
            continue
        name, separator, value = entry.partition(b"=")
        if not separator or not name:
            raise ValueError("invalid operation environment")
        entries.append((name.decode("utf-8", "strict"), value.decode("utf-8", "strict")))
    environment = unique_object(entries)
    cwd = Path(os.readlink(process / "cwd")).resolve()
    executable = Path(os.readlink(process / "exe")).resolve()
    if lifetime != (process / "stat").read_text().rsplit(")", 1)[1].split()[19]:
        raise ValueError("operation process changed during capture")
    return (cwd, executable, arguments), environment


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
    script_index = 1
    while script_index < len(arguments):
        option = arguments[script_index]
        if option == "-B" or option.startswith("-Xpycache_prefix="):
            script_index += 1
        elif (
            option == "-X"
            and script_index + 1 < len(arguments)
            and arguments[script_index + 1].startswith("pycache_prefix=")
        ):
            script_index += 2
        elif option == "--":
            script_index += 1
            break
        else:
            break
    if (
        executable != Path(sys.executable).resolve()
        or not cwd.is_relative_to(root)
        or script_index >= len(arguments)
        or not arguments[script_index]
        or arguments[script_index].startswith("-")
        or tuple(arguments[script_index + 1:]) != tuple(expected_arguments[1:])
    ):
        return False
    actual_script = (cwd / arguments[script_index]).resolve(strict=True)
    return actual_script.is_relative_to(root) and actual_script == expected_script


def execute_observed_operation(receipt, specifications, project):
    event = (Path(receipt["cwd"]), Path(receipt["executable"]), tuple(receipt["arguments"]))
    if not any(
        "expected_behavior" in specification and operation_matches(specification, event, project)
        for specification in specifications
    ):
        raise ValueError("unsupported evaluator operation")
    subject_settings = {"PYTHONPYCACHEPREFIX", "PYTHONDONTWRITEBYTECODE"}
    if any(
        name.startswith(("PYTHON", "LD_")) and name not in subject_settings
        for name in receipt["environment"]
    ):
        raise ValueError("unsupported observer startup environment")
    settings = {name: value for name, value in receipt["environment"].items() if name in subject_settings}
    if any(len(value.encode("utf-8")) > 2048 for value in settings.values()):
        raise ValueError("observer cache setting is too large")
    reader, writer = os.pipe()
    environment = {
        "HOME": str(project.parent / "home"),
        "LANG": "C.UTF-8",
        "PATH": "/usr/local/bin:/usr/bin:/bin",
        **settings,
        "PSTACK_OBSERVATION_FD": str(writer),
    }
    process = None
    try:
        process = subprocess.Popen(
            list(event[2]), executable=str(event[1]), cwd=event[0], env=environment,
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            user=65533, group=65533, extra_groups=[], start_new_session=True,
            pass_fds=(writer,),
            preexec_fn=lambda: resource.setrlimit(resource.RLIMIT_FSIZE, (0, 0)),
        )
        os.close(writer)
        writer = None
        try:
            stdout, stderr = process.communicate(timeout=2)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, 9)
            process.communicate()
            raise ValueError("evaluator operation timed out")
        message = os.read(reader, 4097)
        if len(message) > 4096 or len(stdout) > 2048 or len(stderr) > 2048:
            raise ValueError("evaluator operation output is too large")
        observation = json.loads(message.decode("utf-8"), object_pairs_hook=unique_object) if message else None
        if observation is not None and (
            not isinstance(observation, dict)
            or set(observation) != {"kind", "behavior", "cache", "cache_prefix", "dont_write_bytecode", "observer_uid"}
            or observation["kind"] != "observation"
            or observation["observer_uid"] != 65533
            or not isinstance(observation["behavior"], str)
            or len(observation["behavior"].encode()) > 128
            or not isinstance(observation["cache"], str)
            or len(observation["cache"].encode()) > 2048
            or not (observation["cache_prefix"] is None or isinstance(observation["cache_prefix"], str))
            or not isinstance(observation["dont_write_bytecode"], bool)
        ):
            raise ValueError("invalid evaluator observation")
        return {
            "observation": {key: value for key, value in observation.items() if key != "kind"} if observation else None,
            "stdout": stdout.hex(), "stderr": stderr.hex(),
            "exit": process.returncode if process.returncode >= 0 else 125,
            "failure": "evaluator operation was signaled" if process.returncode < 0 else None,
        }
    finally:
        if writer is not None:
            os.close(writer)
        os.close(reader)
        if process is not None:
            try:
                os.killpg(process.pid, 9)
            except ProcessLookupError:
                pass
            process.wait()


def serve_imports(connection, specifications, project):
    with connection, connection.makefile("rb") as requests:
        while True:
            message = requests.readline(65537)
            if not message:
                return
            try:
                if len(message) > 65536 or not message.endswith(b"\n"):
                    raise ValueError("evaluator request is too large")
                receipt = json.loads(message.decode("utf-8"), object_pairs_hook=unique_object)
                outcome = execute_observed_operation(receipt, specifications, project)
            except (OSError, ValueError) as error:
                outcome = {"observation": None, "stdout": "", "stderr": str(error).encode().hex(), "exit": 125, "failure": str(error)}
            connection.sendall((json.dumps(outcome) + "\n").encode("utf-8"))


def serve_evidence(listener, stop_reader, result_writer, specifications, project, forced_exit, broker):
    events = set()
    observations = {}
    invalid_observations = set()
    responses = broker.makefile("rb")
    try:
        while True:
            readable, _, _ = select.select([listener, stop_reader], [], [])
            if stop_reader in readable:
                break
            connection, _ = listener.accept()
            with connection:
                matching = []
                try:
                    event, environment = peer_process(connection)
                    matching = [
                        index for index, specification in enumerate(specifications)
                        if operation_matches(specification, event, project)
                    ]
                    message = read_message(connection)
                    if not matching or message != b"ready\n":
                        raise ValueError("untrusted operation")
                    if len(events) >= 128 and event not in events:
                        raise ValueError("too many observed operations")
                    events.add(event)
                    required = [index for index in matching if "expected_behavior" in specifications[index]]
                    reply = f"EXIT {forced_exit}" if forced_exit is not None else "OK"
                    if required and forced_exit is None:
                        cwd, executable, arguments = event
                        request = (json.dumps({"cwd": str(cwd), "executable": str(executable),
                            "arguments": list(arguments), "environment": environment}) + "\n").encode("utf-8")
                        if len(request) > 65536:
                            raise ValueError("evaluator request is too large")
                        broker.sendall(request)
                        response = responses.readline(16385)
                        if len(response) > 16384 or not response.endswith(b"\n"):
                            raise RuntimeError("incomplete evaluator response")
                        outcome = json.loads(response.decode("utf-8"))
                        value = outcome["observation"]
                        if outcome["failure"] is not None or value is None or outcome["exit"] != 0:
                            invalid_observations.update(required)
                        if value is not None:
                            value["execution"] = {
                                "exit": outcome["exit"],
                                "stdout_hex": outcome["stdout"],
                                "stderr_hex": outcome["stderr"],
                            }
                        for index in required:
                            if value is None:
                                continue
                            if index in observations:
                                if observations[index]["behavior"] != value["behavior"]:
                                    observations[index]["conflicting_behavior"] = value["behavior"]
                            else:
                                observations[index] = value
                        reply = json.dumps({key: outcome[key] for key in ("stdout", "stderr", "exit")})
                except (OSError, ValueError):
                    invalid_observations.update(
                        index for index in matching if "expected_behavior" in specifications[index]
                    )
                    reply = "REJECT"
                try:
                    connection.sendall((reply + "\n").encode("ascii"))
                except BrokenPipeError:
                    pass
        payload = {
            "events": [
                {"cwd": str(cwd), "executable": str(executable), "arguments": list(arguments)}
                for cwd, executable, arguments in sorted(events)
            ],
            "observations": observations,
            "invalid_observations": sorted(invalid_observations),
        }
    except BaseException as error:
        payload = {"events": [], "error": f"{type(error).__name__}: {error}"}
    responses.close()
    broker.close()
    with os.fdopen(result_writer, "w") as output:
        json.dump(payload, output)


def start_evidence_server(listener, specifications, project, forced_exit):
    stop_reader, stop_writer = os.pipe()
    result_reader, result_writer = os.pipe()
    broker_client, broker_server = socket.socketpair()
    broker_pid = os.fork()
    if broker_pid == 0:
        broker_client.close()
        listener.close()
        for descriptor in (stop_reader, stop_writer, result_reader, result_writer):
            os.close(descriptor)
        try:
            serve_imports(broker_server, specifications, project)
        except BaseException:
            os._exit(126)
        os._exit(0)
    broker_server.close()
    server_pid = os.fork()
    if server_pid == 0:
        os.close(stop_writer)
        os.close(result_reader)
        os.setgroups([])
        os.setgid(65534)
        os.setuid(65534)
        if ctypes.CDLL(None).prctl(PR_SET_DUMPABLE, 0, 0, 0, 0) != 0:
            os._exit(126)
        serve_evidence(listener, stop_reader, result_writer, specifications, project, forced_exit, broker_client)
        os._exit(0)
    os.close(stop_reader)
    os.close(result_writer)
    broker_client.close()
    return server_pid, stop_writer, result_reader, broker_pid


def finish_evidence_server(server_pid, stop_writer, result_reader, broker_pid):
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
    _, broker_status = os.waitpid(broker_pid, 0)
    payload = json.loads(b"".join(chunks))
    if status != 0 or broker_status != 0 or "error" in payload:
        raise RuntimeError(payload.get("error", f"evidence server exited with status {status}"))
    return {
        "events": {
            (Path(event["cwd"]), Path(event["executable"]), tuple(event["arguments"]))
            for event in payload["events"]
        },
        "observations": {int(index): value for index, value in payload["observations"].items()},
        "invalid_observations": set(payload["invalid_observations"]),
    }


def instrument_operations(project, specifications):
    paths = {specification["args"][0] for specification in specifications}
    for relative in paths:
        target = project / relative
        observer = TRACE_OBSERVER if any(
            specification["args"][0] == relative and "expected_behavior" in specification
            for specification in specifications
        ) else ""
        target.write_text(TRACE_PROLOGUE + observer + target.read_text())


def operation_seen(specification, events, project):
    return any(operation_matches(specification, event, project) for event in events)


def run_case(root, plan, definition, bootstrap):
    results = []
    base_state = next(state for state in definition["states"] if state["exit"] == "zero")
    forced_state = {
        "name": "forced-operation-failure",
        "bootstrap_state": base_state["name"],
        "exit": "nonzero",
        "required_operations": [
            {key: value for key, value in base_state["required_operations"][0].items() if key != "expected_behavior"}
        ],
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
        server_pid, stop_writer, result_reader, broker_pid = start_evidence_server(
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
            finish_evidence_server(server_pid, stop_writer, result_reader, broker_pid)
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
        seen = finish_evidence_server(server_pid, stop_writer, result_reader, broker_pid)
        listener.close()
        expected_zero = state["exit"] == "zero"
        exit_matches = not timed_out and ((process.returncode == 0) == expected_zero)
        missing_operations = [
            specification
            for specification in state["required_operations"]
            if not operation_seen(specification, seen["events"], project)
        ]
        behavior_checks = []
        for index, specification in enumerate(state["required_operations"]):
            if "expected_behavior" not in specification:
                continue
            observation = seen["observations"].get(index)
            behavior_checks.append({
                "operation": specification,
                "expected": specification["expected_behavior"],
                "observation": observation,
                "matches": observation is not None
                and observation["behavior"] == specification["expected_behavior"]
                and "conflicting_behavior" not in observation
                and index not in seen["invalid_observations"],
            })
        results.append({
            "state": state["name"],
            "exit": process.returncode,
            "expected": state["exit"],
            "exit_matches": exit_matches,
            "timed_out": timed_out,
            "missing_operations": missing_operations,
            "observed_commands": [list(arguments) for _, _, arguments in sorted(seen["events"])],
            "behavior_checks": behavior_checks,
            "fixture_receipt": json.loads(setup.stdout) if behavior_checks else None,
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
        or any(not check["matches"] for check in state.get("behavior_checks", []))
    ]
    control_evidence = [state for state in measured["states"] if state.get("behavior_checks")]
    if failed:
        result = {"status": "candidate_failure", "failed_states": failed}
    else:
        result = {
            "status": "pass",
            "states": [state["state"] for state in measured["states"]],
            "operation_evidence": "authenticated by the container evidence server",
        }
    if control_evidence:
        result["control_evidence"] = control_evidence
    return (1 if failed else 0), result


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
