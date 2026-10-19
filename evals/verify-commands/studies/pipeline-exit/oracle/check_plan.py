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
import dataclasses
import hashlib
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


def python_script_index(arguments):
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
        else:
            break
    return script_index


LIFECYCLE_UID = 65533
LIFECYCLE_ATTEMPTS = 8
LIFECYCLE_RECEIPT_BYTES = 32768


class LifecycleProtocolError(ValueError):
    pass


class LifecycleIdentityError(ValueError):
    pass


@dataclasses.dataclass(frozen=True)
class LifecycleIdentity:
    pid: int
    start_ticks: int
    uid: int
    parent: int
    session: int
    group: int
    state: str


@dataclasses.dataclass
class LifecycleSession:
    worker: LifecycleIdentity
    baseline: frozenset[int]
    child: LifecycleIdentity | None = None
    application: bytes | None = None
    frozen: bytes | None = None


def lifecycle_mode(arguments):
    if tuple(arguments) == ():
        return "observe"
    if tuple(arguments) == ("--repair-first",):
        return "repair-first"
    return None


def lifecycle_identity(pid):
    process = Path("/proc") / str(pid)
    tail = (process / "stat").read_text().rsplit(")", 1)[1].split()
    status = (process / "status").read_text().splitlines()
    uid = int(next(line for line in status if line.startswith("Uid:")).split()[1])
    return LifecycleIdentity(pid, int(tail[19]), uid, int(tail[1]), int(tail[3]), int(tail[2]), tail[0])


def lifecycle_children():
    path = Path("/proc/self/task") / str(os.getpid()) / "children"
    return frozenset(map(int, path.read_text().split()))


def lifecycle_remaining(deadline):
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError("lifecycle worker timed out")
    return remaining


def lifecycle_send(channel, value, deadline):
    channel.settimeout(lifecycle_remaining(deadline))
    channel.sendall((json.dumps(value, sort_keys=True) + "\n").encode())


def lifecycle_receive(channel, kind, deadline):
    message = bytearray()
    while not message.endswith(b"\n"):
        channel.settimeout(lifecycle_remaining(deadline))
        byte = channel.recv(1)
        if not byte:
            raise EOFError(f"missing lifecycle {kind}")
        message.extend(byte)
        if len(message) > 4096:
            raise LifecycleProtocolError("lifecycle protocol message is too large")
    value = json.loads(message, object_pairs_hook=unique_object)
    if not isinstance(value, dict) or value.get("kind") != kind:
        raise LifecycleProtocolError(f"invalid lifecycle {kind}")
    return value


def lifecycle_ready(descriptor, deadline):
    if not select.select([descriptor], [], [], lifecycle_remaining(deadline))[0]:
        raise TimeoutError("lifecycle worker timed out")


def lifecycle_wait(pid, pidfd, deadline):
    lifecycle_ready(pidfd, deadline)
    found, status = os.waitpid(pid, os.WNOHANG)
    if found != pid:
        raise ValueError("lifecycle wait did not reap the exact owned process")
    return {"pid": found, "raw_status": status, "exit": os.waitstatus_to_exitcode(status)}


def lifecycle_same_identity(value, original):
    if (value.pid, value.start_ticks, value.uid, value.session, value.group) != (
        original.pid, original.start_ticks, original.uid, original.session, original.group
    ):
        raise LifecycleIdentityError("lifecycle identity changed")


def lifecycle_pipe_closed(reader):
    try:
        value = os.read(reader, 1)
    except BlockingIOError:
        return False
    if value != b"":
        raise ValueError("lifecycle cleanup pipe unexpectedly carried data")
    return True


def lifecycle_snapshot(session, reader):
    worker = lifecycle_identity(session.worker.pid)
    lifecycle_same_identity(worker, session.worker)
    if worker.state == "Z" or session.child is None:
        raise LifecycleIdentityError("lifecycle snapshot requires a live owner and registered child")
    try:
        child = lifecycle_identity(session.child.pid)
    except FileNotFoundError:
        child_state, child_identity = "reaped", None
    else:
        lifecycle_same_identity(child, session.child)
        if child.parent != worker.pid:
            raise LifecycleIdentityError("lifecycle child no longer belongs to the live worker")
        child_state = "zombie" if child.state == "Z" else "running"
        child_identity = dataclasses.asdict(child)
    return {"worker": dataclasses.asdict(worker), "child": child_state,
            "child_identity": child_identity, "writer": "closed" if lifecycle_pipe_closed(reader) else "open"}


def lifecycle_freeze(session, observation, actions, failure):
    if session.frozen is not None:
        raise ValueError("lifecycle facts were already frozen")
    session.frozen = json.dumps({"application": json.loads(session.application) if session.application else None,
        "observation": observation, "actions": actions, "failure": failure}, sort_keys=True).encode()


def lifecycle_worker(channel, writer, configuration, mode, deadline):
    os.setsid()
    os.setgroups([])
    os.setgid(LIFECYCLE_UID)
    os.setuid(LIFECYCLE_UID)
    resource.setrlimit(resource.RLIMIT_FSIZE, (0, 0))
    os.environ.clear()
    fault = configuration["fault"]
    lifecycle_send(channel, {"kind": "worker_ready"}, deadline)
    lifecycle_receive(channel, "fork", deadline)
    if fault == "before-fork-failure":
        os._exit(23)
    release_reader, release_writer = os.pipe()
    closure_reader, closure_writer = os.pipe()
    child = os.fork()
    if child == 0:
        keep = {release_reader, closure_writer}
        for name in os.listdir("/proc/self/fd"):
            descriptor = int(name)
            if descriptor not in keep:
                try:
                    os.close(descriptor)
                except OSError:
                    pass
        os.write(closure_writer, b"C")
        os.close(closure_writer)
        lifecycle_ready(release_reader, deadline)
        if os.read(release_reader, 1) != b"R":
            os._exit(24)
        os.close(release_reader)
        os._exit(0)
    os.close(release_reader)
    os.close(closure_writer)
    lifecycle_ready(closure_reader, deadline)
    if os.read(closure_reader, 1) != b"C":
        raise ValueError("lifecycle child did not close inherited descriptors")
    os.close(closure_reader)
    if fault == "death-before-registration":
        os._exit(23)
    if fault == "missing-registration":
        lifecycle_send(channel, {"kind": "missing_registration"}, deadline)
        lifecycle_receive(channel, "cancel", deadline)
        os._exit(24)
    lifecycle_send(channel, {"kind": "register", "pid": os.getpid() if fault == "identity-failure" else child, "inherited_writer_closed": True}, deadline)
    if fault == "worker-timeout":
        time.sleep(3)
    if fault == "writer-ownership":
        lifecycle_receive(channel, "writer_probe", deadline)
        os.close(writer)
        lifecycle_send(channel, {"kind": "writer_closed"}, deadline)
        lifecycle_receive(channel, "cancel", deadline)
        os._exit(24)
    lifecycle_receive(channel, "release", deadline)
    os.write(release_writer, b"R")
    os.close(release_writer)
    lifecycle_send(channel, {"kind": "released"}, deadline)
    lifecycle_receive(channel, "application_cleanup", deadline)
    reaped, opened, application_wait = False, True, None
    if configuration["cleanup"]:
        application_wait = os.waitpid(child, 0)
        reaped = True
        os.close(writer)
        opened = False
    lifecycle_send(channel, {"kind": "application_finished", "waitpid": application_wait,
        "writer_closed": not opened}, deadline)
    lifecycle_receive(channel, "observer", deadline)
    if fault == "missing-observation":
        os._exit(23)
    if mode == "repair-first":
        lifecycle_send(channel, {"kind": "repair_requested"}, deadline)
        lifecycle_receive(channel, "repair", deadline)
        repair_wait = None
        if not reaped:
            repair_wait = os.waitpid(child, 0)
            reaped = True
        if opened:
            os.close(writer)
            opened = False
        lifecycle_send(channel, {"kind": "repair_finished", "waitpid": repair_wait, "writer_closed": True}, deadline)
        lifecycle_receive(channel, "observe", deadline)
    lifecycle_send(channel, {"kind": "observe"}, deadline)
    observation = lifecycle_receive(channel, "observed", deadline)["facts"]
    result = 0 if (observation["child"], observation["writer"]) == ("reaped", "closed") else 1
    lifecycle_receive(channel, "teardown_after_freeze", deadline)
    safety_wait = None if reaped else os.waitpid(child, 0)
    if opened:
        os.close(writer)
    lifecycle_send(channel, {"kind": "teardown_finished", "waitpid": safety_wait, "writer_closed": True}, deadline)
    print(json.dumps({"child": observation["child"], "writer": observation["writer"]}), flush=True)
    if fault == "output-limit":
        print("x" * 2049, flush=True)
    if fault == "signaled-worker":
        os.kill(os.getpid(), 9)
    os._exit(97 if fault == "wrong-status" else result)


def execute_lifecycle_operation(receipt, project):
    mode = lifecycle_mode(receipt["arguments"][receipt["script_index"] + 1:])
    configuration = json.loads((project / "lifecycle-state.json").read_text())
    deadline = time.monotonic() + 2
    libc = ctypes.CDLL(None, use_errno=True)
    prior = ctypes.c_int()
    if libc.prctl(37, ctypes.byref(prior), 0, 0, 0) != 0 or libc.prctl(36, 1, 0, 0, 0) != 0:
        raise OSError("lifecycle subreaper setup failed")
    baseline = lifecycle_children()
    monitor, channel = socket.socketpair()
    reader, writer = os.pipe()
    out_reader, out_writer = os.pipe()
    err_reader, err_writer = os.pipe()
    os.set_blocking(reader, False)
    session = None
    child_pidfd = None
    worker_wait = None
    actions, teardown_actions, diagnostics = [], [], {}
    teardown = {"failure": None}
    worker = os.fork()
    if worker == 0:
        monitor.close()
        os.dup2(out_writer, 1)
        os.dup2(err_writer, 2)
        keep = {0, 1, 2, channel.fileno(), writer}
        for name in os.listdir("/proc/self/fd"):
            descriptor = int(name)
            if descriptor not in keep:
                try:
                    os.close(descriptor)
                except OSError:
                    pass
        try:
            lifecycle_worker(channel, writer, configuration, mode, deadline)
        except BaseException:
            os._exit(125)
    channel.close()
    for descriptor in (writer, out_writer, err_writer):
        os.close(descriptor)
    worker_pidfd = os.pidfd_open(worker)
    pipe = {"role": "application_cleanup_writer", "inode": os.fstat(reader).st_ino,
        "reader_owner": os.getpid(), "writer_owner": worker, "broker_writer_copy_closed": True,
        "child_inherited_writer_closed": False, "sole_writer": False}
    phase = "registration"
    try:
        lifecycle_receive(monitor, "worker_ready", deadline)
        worker_identity = lifecycle_identity(worker)
        if (worker_identity.parent, worker_identity.uid, worker_identity.group, worker_identity.session) != (
            os.getpid(), LIFECYCLE_UID, worker, worker
        ):
            raise LifecycleIdentityError("lifecycle worker identity mismatch")
        session = LifecycleSession(worker_identity, baseline)
        lifecycle_send(monitor, {"kind": "fork"}, deadline)
        event = lifecycle_receive(monitor, "register", deadline)
        child = lifecycle_identity(event["pid"])
        if (child.parent, child.uid, child.group, child.session) != (worker, LIFECYCLE_UID, worker, worker) or child.start_ticks < worker_identity.start_ticks:
            raise LifecycleIdentityError("lifecycle child identity mismatch")
        session.child = child
        pipe["child_inherited_writer_closed"] = event["inherited_writer_closed"] is True
        pipe["sole_writer"] = pipe["child_inherited_writer_closed"]
        child_pidfd = os.pidfd_open(child.pid)
        phase = "application"
        if configuration["fault"] == "writer-ownership":
            lifecycle_send(monitor, {"kind": "writer_probe"}, deadline)
            lifecycle_receive(monitor, "writer_closed", deadline)
            live = lifecycle_snapshot(session, reader)
            teardown["sole_writer_control"] = {"worker_alive": live["worker"]["state"] != "Z",
                "child_alive": live["child"] == "running", "pipe_eof": live["writer"] == "closed"}
            raise ValueError("instrument-only writer ownership control has no observation")
        lifecycle_send(monitor, {"kind": "release"}, deadline)
        lifecycle_receive(monitor, "released", deadline)
        lifecycle_ready(child_pidfd, deadline)
        lifecycle_send(monitor, {"kind": "application_cleanup"}, deadline)
        diagnostics["application"] = lifecycle_receive(monitor, "application_finished", deadline)
        session.application = json.dumps(lifecycle_snapshot(session, reader), sort_keys=True).encode()
        actions.append({"sequence": 1, "action": "application_snapshot"})
        phase = "observation"
        lifecycle_send(monitor, {"kind": "observer"}, deadline)
        if mode == "repair-first":
            lifecycle_receive(monitor, "repair_requested", deadline)
            actions.append({"sequence": len(actions) + 1, "action": "observer_repair_requested"})
            lifecycle_send(monitor, {"kind": "repair"}, deadline)
            diagnostics["repair"] = lifecycle_receive(monitor, "repair_finished", deadline)
            actions.append({"sequence": len(actions) + 1, "action": "observer_repair_completed", "facts": lifecycle_snapshot(session, reader)})
            lifecycle_send(monitor, {"kind": "observe"}, deadline)
        lifecycle_receive(monitor, "observe", deadline)
        observation = lifecycle_snapshot(session, reader)
        actions.append({"sequence": len(actions) + 1, "action": "candidate_observation"})
        lifecycle_freeze(session, observation, actions, None)
        teardown_actions.append({"action": "facts_frozen"})
        lifecycle_send(monitor, {"kind": "observed", "facts": observation}, deadline)
        phase = "execution"
        lifecycle_send(monitor, {"kind": "teardown_after_freeze"}, deadline)
        diagnostics["safety"] = lifecycle_receive(monitor, "teardown_finished", deadline)
        worker_wait = lifecycle_wait(worker, worker_pidfd, deadline)
        teardown_actions.append({"action": "reap_exact_worker", "receipt": worker_wait})
    except (OSError, ValueError, EOFError, TimeoutError) as error:
        if session is None:
            value = lifecycle_identity(worker)
            session = LifecycleSession(value, baseline)
        if session.frozen is None:
            cause = ("worker_timeout" if isinstance(error, TimeoutError) else
                "identity" if isinstance(error, LifecycleIdentityError) else
                "protocol" if isinstance(error, LifecycleProtocolError) else f"missing_{phase}")
            lifecycle_freeze(session, None, actions, {"cause": cause, "detail": str(error)})
            teardown_actions.append({"action": "failure_frozen"})
    finally:
        cleanup_deadline = time.monotonic() + 1
        try:
            if session is None or session.frozen is None:
                raise ValueError("lifecycle failure was not frozen")
            frozen_hash = hashlib.sha256(session.frozen).hexdigest()
            if worker_wait is None:
                if (session.worker.group, session.worker.session, session.worker.uid) != (worker, worker, LIFECYCLE_UID):
                    raise ValueError("lifecycle group ownership not established")
                try:
                    os.killpg(worker, 9)
                except ProcessLookupError:
                    pass
                teardown_actions.append({"action": "kill_known_worker_group", "group": worker})
                worker_wait = lifecycle_wait(worker, worker_pidfd, cleanup_deadline)
                teardown_actions.append({"action": "reap_exact_worker", "receipt": worker_wait})
            adopted = lifecycle_children() - baseline
            if len(adopted) > 1:
                raise ValueError("lifecycle recovery exceeded one owned child")
            recovered = None
            if adopted:
                recovered = lifecycle_identity(next(iter(adopted)))
                if (recovered.parent, recovered.uid, recovered.group, recovered.session) != (
                    os.getpid(), LIFECYCLE_UID, session.worker.group, session.worker.session
                ) or recovered.start_ticks < session.worker.start_ticks:
                    raise ValueError("lifecycle adopted child ownership mismatch")
                if session.child is not None:
                    lifecycle_same_identity(recovered, session.child)
                adopted_pidfd = os.pidfd_open(recovered.pid)
                try:
                    child_wait = lifecycle_wait(recovered.pid, adopted_pidfd, cleanup_deadline)
                finally:
                    os.close(adopted_pidfd)
                teardown_actions.append({"action": "reap_exact_adopted_child", "receipt": child_wait})
            if lifecycle_children() != baseline or not lifecycle_pipe_closed(reader):
                raise ValueError("lifecycle teardown left an owned resource")
            if session.child is not None and (Path("/proc") / str(session.child.pid)).exists():
                raise ValueError("lifecycle registered child survived teardown")
            teardown.update({"recovered_child": dataclasses.asdict(recovered) if recovered else None,
                "recovered_identity_use": "teardown_only" if recovered else None,
                "child_absent": True, "writer": "closed", "direct_children_after": sorted(lifecycle_children()),
                "frozen_sha256_after": hashlib.sha256(session.frozen).hexdigest()})
            if teardown["frozen_sha256_after"] != frozen_hash:
                raise ValueError("lifecycle frozen facts changed during teardown")
        except (OSError, ValueError, TimeoutError) as error:
            teardown["failure"] = str(error)
        monitor.close()
        for descriptor in (worker_pidfd, child_pidfd, reader):
            if descriptor is not None:
                os.close(descriptor)
    os.set_blocking(out_reader, False)
    os.set_blocking(err_reader, False)
    try:
        stdout, stderr = os.read(out_reader, 2049), os.read(err_reader, 2049)
    except BlockingIOError:
        stdout, stderr = b"", b""
        teardown["failure"] = teardown["failure"] or "lifecycle output writer survived bounded teardown"
    os.close(out_reader)
    os.close(err_reader)
    if teardown["failure"] is None:
        if libc.prctl(36, prior.value, 0, 0, 0) != 0:
            teardown["failure"] = "lifecycle subreaper restore failed"
        else:
            teardown["subreaper_restored"] = prior.value
    execution = {"exit": worker_wait["exit"] if worker_wait else None,
        "raw_status": worker_wait["raw_status"] if worker_wait else None,
        "stdout_hex": stdout.hex(), "stderr_hex": stderr.hex()}
    record = {"broker_pid": os.getpid(), "worker_identity": dataclasses.asdict(session.worker),
        "registered_child_identity": dataclasses.asdict(session.child) if session.child else None,
        "baseline_direct_children": sorted(baseline), "pipe": pipe, "facts": json.loads(session.frozen),
        "frozen_sha256": hashlib.sha256(session.frozen).hexdigest(),
        "application_sha256": hashlib.sha256(session.application).hexdigest() if session.application else None,
        "owner_diagnostics": diagnostics, "execution": execution, "teardown": {**teardown, "actions": teardown_actions}}
    if len(json.dumps(record).encode()) > LIFECYCLE_RECEIPT_BYTES or len(stdout) > 2048 or len(stderr) > 2048:
        record["receipt_failure"] = "lifecycle evidence exceeded its byte bound"
        stdout, stderr = b"", b""
    actual_exit = execution["exit"]
    return {"lifecycle": record, "observation": None, "stdout": stdout.hex(), "stderr": stderr.hex(),
        "exit": actual_exit if actual_exit is not None and actual_exit >= 0 else 125,
        "failure": record["facts"]["failure"]}


def lifecycle_match(expected, attempts, attempt_limit_exceeded):
    checks = []
    for record in attempts:
        facts = record.get("facts", {})
        application, observation = facts.get("application"), facts.get("observation")
        application_matches = application is not None and all(application.get(key) == value for key, value in expected.items())
        observation_matches = observation is not None and application is not None and all(
            observation.get(key) == application.get(key) for key in ("child", "writer")
        )
        order_matches = [action["action"] for action in facts.get("actions", [])] == ["application_snapshot", "candidate_observation"]
        expected_exit = 0 if observation is not None and (observation["child"], observation["writer"]) == ("reaped", "closed") else 1
        execution_matches = observation is not None and record.get("execution", {}).get("exit") == expected_exit
        protocol_matches = facts.get("failure") is None and record.get("registered_child_identity") is not None and record.get("pipe", {}).get("sole_writer") is True and "receipt_failure" not in record
        teardown_matches = record.get("teardown", {}).get("failure") is None and record.get("teardown", {}).get("child_absent") is True and record.get("teardown", {}).get("writer") == "closed"
        causes = [name for name, matched in (("application", application_matches), ("observation", observation_matches),
            ("observer_repair_preceded_observation", order_matches), ("execution_status", execution_matches),
            ("protocol_or_identity", protocol_matches), ("teardown", teardown_matches)) if not matched]
        checks.append({"record": record, "application_matches": application_matches, "observation_matches": observation_matches,
            "order_matches": order_matches, "execution_matches": execution_matches, "protocol_matches": protocol_matches,
            "teardown_matches": teardown_matches, "failure_causes": causes, "matches": not causes})
    return {"expected": expected, "attempts": checks, "attempt_limit_exceeded": attempt_limit_exceeded,
        "matches": bool(checks) and not attempt_limit_exceeded and all(check["matches"] for check in checks)}


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
    script_index = python_script_index(arguments)
    if (
        executable != Path(sys.executable).resolve()
        or not cwd.is_relative_to(root)
        or script_index >= len(arguments)
        or not arguments[script_index]
        or arguments[script_index].startswith("-")
        or (lifecycle_mode(arguments[script_index + 1:]) is None if "expected_lifecycle" in specification
            else tuple(arguments[script_index + 1:]) != tuple(expected_arguments[1:]))
    ):
        return False
    actual_script = (cwd / arguments[script_index]).resolve(strict=True)
    return actual_script.is_relative_to(root) and actual_script == expected_script


def execute_observed_operation(receipt, specifications, project):
    event = (Path(receipt["cwd"]), Path(receipt["executable"]), tuple(receipt["arguments"]))
    if not any(
        ("expected_behavior" in specification or "expected_lifecycle" in specification) and operation_matches(specification, event, project)
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
    if any("expected_lifecycle" in specification and operation_matches(specification, event, project) for specification in specifications):
        receipt["script_index"] = python_script_index(event[2])
        return execute_lifecycle_operation(receipt, project)
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
    lifecycle_attempts = {}
    lifecycle_attempt_count = 0
    lifecycle_limit_exceeded = False
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
                    lifecycle_required = [index for index in matching if "expected_lifecycle" in specifications[index]]
                    reply = f"EXIT {forced_exit}" if forced_exit is not None else "OK"
                    if (required or lifecycle_required) and forced_exit is None:
                        if lifecycle_required:
                            lifecycle_attempt_count += 1
                            if lifecycle_attempt_count > LIFECYCLE_ATTEMPTS:
                                lifecycle_limit_exceeded = True
                                raise ValueError("too many lifecycle attempts")
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
                        if lifecycle_required:
                            record = outcome.get("lifecycle", {"facts": {"failure": {"cause": "protocol", "detail": outcome["failure"]}}})
                            for index in lifecycle_required:
                                lifecycle_attempts.setdefault(index, []).append(record)
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
            "lifecycle_attempts": lifecycle_attempts,
            "lifecycle_limit_exceeded": lifecycle_limit_exceeded,
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
        "lifecycle_attempts": {int(index): value for index, value in payload["lifecycle_attempts"].items()},
        "lifecycle_limit_exceeded": payload["lifecycle_limit_exceeded"],
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
            {key: value for key, value in base_state["required_operations"][0].items() if key not in {"expected_behavior", "expected_lifecycle"}}
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
        lifecycle_checks = [
            lifecycle_match(specification["expected_lifecycle"], seen["lifecycle_attempts"].get(index, []), seen["lifecycle_limit_exceeded"])
            for index, specification in enumerate(state["required_operations"]) if "expected_lifecycle" in specification
        ]
        results.append({
            "state": state["name"],
            "exit": process.returncode,
            "expected": state["exit"],
            "exit_matches": exit_matches,
            "timed_out": timed_out,
            "missing_operations": missing_operations,
            "observed_commands": [list(arguments) for _, _, arguments in sorted(seen["events"])],
            "behavior_checks": behavior_checks,
            "lifecycle_checks": lifecycle_checks,
            "fixture_receipt": json.loads(setup.stdout) if behavior_checks or lifecycle_checks else None,
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
        or any(not check["matches"] for check in state.get("lifecycle_checks", []))
    ]
    control_evidence = [state for state in measured["states"] if state.get("behavior_checks") or state.get("lifecycle_checks")]
    infrastructure = any(
        attempt["record"].get("teardown", {}).get("failure") is not None
        for state in control_evidence for check in state.get("lifecycle_checks", []) for attempt in check["attempts"]
    )
    if infrastructure:
        result = {"status": "infrastructure", "reason": "lifecycle cleanup infrastructure failed", "failed_states": failed}
    elif failed:
        result = {"status": "candidate_failure", "failed_states": failed}
    else:
        result = {
            "status": "pass",
            "states": [state["state"] for state in measured["states"]],
            "operation_evidence": "authenticated by the container evidence server",
        }
    if control_evidence:
        result["control_evidence"] = control_evidence
    return (2 if infrastructure else 1 if failed else 0), result


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
