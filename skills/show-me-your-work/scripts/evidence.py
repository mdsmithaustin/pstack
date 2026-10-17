#!/usr/bin/env python3
"""Save command or imported-file evidence and verify its retained bytes."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
from datetime import datetime, timezone


class EvidenceError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise EvidenceError(message)


def object_keys(value, keys):
    require(isinstance(value, dict) and set(value) == set(keys),
            f"expected object fields {', '.join(keys)}")


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, f"duplicate JSON key: {key}")
        result[key] = value
    return result


def invalid_constant(value):
    raise EvidenceError(f"invalid JSON constant: {value}")


def parse_json(data):
    return json.loads(data, object_pairs_hook=unique_object, parse_constant=invalid_constant)


def encoded(value):
    return (json.dumps(value, ensure_ascii=True, indent=2, allow_nan=False) + "\n").encode()


def timestamp():
    return datetime.now(timezone.utc).isoformat()


def valid_time(value):
    require(isinstance(value, str), "timestamp must be a string")
    parsed = datetime.fromisoformat(value)
    require(parsed.tzinfo is not None and parsed.utcoffset() is not None,
            "timestamp must include a timezone")


def absolute(value):
    require(isinstance(value, str) and os.path.isabs(value) and "\x00" not in value,
            "path must be absolute")
    require(".." not in Path(value).parts, "parent path components are forbidden")
    return Path(value)


def open_directory(path, create=False):
    path = absolute(str(path))
    require(os.name == "posix" and hasattr(os, "O_NOFOLLOW") and hasattr(os, "O_DIRECTORY"),
            "directory-relative no-follow operations require POSIX")
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    descriptor = os.open("/", flags)
    try:
        for part in path.parts[1:]:
            if create:
                try:
                    os.mkdir(part, mode=0o700, dir_fd=descriptor)
                except FileExistsError:
                    pass
            child = os.open(part, flags, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def open_regular(name, directory, write=False):
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL if write else os.O_RDONLY | os.O_NONBLOCK
    descriptor = os.open(name, flags | os.O_NOFOLLOW, 0o600, dir_fd=directory)
    try:
        require(stat.S_ISREG(os.fstat(descriptor).st_mode), "payload must be a regular file")
        return os.fdopen(descriptor, "wb" if write else "rb")
    except BaseException:
        os.close(descriptor)
        raise


def read_source(path):
    path = absolute(str(path))
    directory = open_directory(path.parent)
    try:
        with open_regular(path.name, directory) as stream:
            return stream.read()
    finally:
        os.close(directory)


def write_bytes(directory, name, data):
    with open_regular(name, directory, write=True) as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def descriptor_for(name, data):
    return {"path": name, "byte_length": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def payload_name(name):
    require(isinstance(name, str) and re.fullmatch(
        r"(?:record\.json|stdout\.bin|stderr\.bin|source\.bin|basis-[0-9]{4,}\.bin)", name),
        "unsafe or unknown payload path")
    return name


def read_payload(directory, description):
    object_keys(description, ("path", "byte_length", "sha256"))
    name = payload_name(description["path"])
    require(type(description["byte_length"]) is int and description["byte_length"] >= 0,
            "invalid payload byte length")
    require(isinstance(description["sha256"], str) and
            re.fullmatch(r"[0-9a-f]{64}", description["sha256"]), "invalid SHA-256")
    with open_regular(name, directory) as stream:
        data = stream.read()
    require(descriptor_for(name, data) == description, f"payload integrity mismatch: {name}")
    return data


def selected_field(data, line, pointer):
    require(line is None or type(line) is int and line > 0, "line must be a positive integer or null")
    if line is not None:
        lines = data.split(b"\n")
        require(line <= len(lines), "runtime record line is absent")
        data = lines[line - 1]
    value = parse_json(data)
    require(isinstance(pointer, str) and (pointer == "" or pointer.startswith("/")),
            "invalid JSON Pointer")
    if pointer:
        for token in pointer[1:].split("/"):
            require(re.search(r"~(?![01])", token) is None, "invalid JSON Pointer escape")
            token = token.replace("~1", "/").replace("~0", "~")
            if isinstance(value, dict):
                value = value.get(token)
            elif isinstance(value, list) and re.fullmatch(r"0|[1-9][0-9]*", token):
                index = int(token)
                value = value[index] if index < len(value) else None
            else:
                value = None
    require(value is None or isinstance(value, str), "runtime identity field must be a string or null")
    return value


def identity_capture(path, directory):
    identity = {"requested": None, "resolutionContext": None,
                "model": {"kind": "unknown"}, "effort": {"kind": "unknown"},
                "provider_execution": "unknown"}
    basis_names = []
    if path is None:
        return identity, basis_names
    request = parse_json(read_source(absolute(path)))
    require(isinstance(request, dict) and set(request) <= {"requested", "resolutionContext", "runtimeRecords"},
            "unknown identity request fields")
    identity["requested"] = request.get("requested")
    identity["resolutionContext"] = request.get("resolutionContext")
    validate_configured(identity)
    records = request.get("runtimeRecords", [])
    require(isinstance(records, list), "runtimeRecords must be an array")
    for index, record in enumerate(records):
        require(isinstance(record, dict) and "source" in record and
                set(record) <= {"source", "line", "modelPointer", "effortPointer"} and
                ("modelPointer" in record or "effortPointer" in record), "invalid runtime record selector")
        data = read_source(absolute(record["source"]))
        name = f"basis-{index:04d}.bin"
        write_bytes(directory, name, data)
        basis_names.append(name)
        for field in ("model", "effort"):
            key = field + "Pointer"
            if key not in record:
                continue
            line, pointer = record.get("line"), record[key]
            value = selected_field(data, line, pointer)
            if value is not None:
                require(identity[field]["kind"] == "unknown", f"multiple runtime claims for {field}")
                identity[field] = {"kind": "runtime-reported", "value": value,
                                   "basis": {"payload": name, "line": line, "pointer": pointer}}
    return identity, basis_names


def validate_configured(identity):
    requested = identity["requested"]
    require(requested is None or isinstance(requested, dict) and
            set(requested) <= {"harness", "model", "effort"} and
            all(value is None or isinstance(value, str) for value in requested.values()),
            "invalid requested identity")
    context = identity["resolutionContext"]
    require(context is None or isinstance(context, dict), "resolutionContext must be an object or null")


def validate_identity(identity, basis_names, payloads):
    object_keys(identity, ("requested", "resolutionContext", "model", "effort", "provider_execution"))
    validate_configured(identity)
    require(identity["provider_execution"] == "unknown", "provider execution must remain unknown")
    for field in ("model", "effort"):
        claim = identity[field]
        require(isinstance(claim, dict), "identity claim must be an object")
        if claim.get("kind") == "unknown":
            object_keys(claim, ("kind",))
            continue
        object_keys(claim, ("kind", "value", "basis"))
        require(claim["kind"] == "runtime-reported" and isinstance(claim["value"], str),
                "invalid runtime identity claim")
        basis = claim["basis"]
        object_keys(basis, ("payload", "line", "pointer"))
        require(isinstance(basis["payload"], str) and basis["payload"] in basis_names,
                "identity basis must name a saved basis payload")
        value = selected_field(payloads[basis["payload"]], basis["line"], basis["pointer"])
        require(value == claim["value"], "runtime identity disagrees with saved basis")


def validate_record(record, capture_id, payloads):
    object_keys(record, ("version", "capture_id", "captured", "identity", "basis_payloads"))
    require(type(record["version"]) is int and record["version"] == 1, "unsupported record version")
    require(record["capture_id"] == capture_id, "capture ID mismatch")
    basis = record["basis_payloads"]
    require(isinstance(basis, list) and all(isinstance(name, str) for name in basis) and
            basis == [f"basis-{index:04d}.bin" for index in range(len(basis))],
            "invalid basis payload list")
    captured = record["captured"]
    require(isinstance(captured, dict), "captured must be an object")
    if captured.get("kind") == "command":
        object_keys(captured, ("kind", "execution", "stdout", "stderr"))
        require(captured["stdout"] == "stdout.bin" and captured["stderr"] == "stderr.bin",
                "invalid command payload names")
        execution = captured["execution"]
        object_keys(execution, ("argv", "cwd", "started_at", "ended_at", "raw_returncode"))
        argv = execution["argv"]
        require(isinstance(argv, list) and len(argv) > 0 and
                all(isinstance(arg, str) and "\x00" not in arg for arg in argv), "invalid argv")
        absolute(execution["cwd"])
        valid_time(execution["started_at"])
        valid_time(execution["ended_at"])
        require(type(execution["raw_returncode"]) is int, "invalid raw return code")
        expected = {"stdout.bin", "stderr.bin", *basis}
    else:
        object_keys(captured, ("kind", "source", "saved_file"))
        require(captured["kind"] == "imported-file" and captured["saved_file"] == "source.bin",
                "invalid imported-file record")
        source = captured["source"]
        object_keys(source, ("original_path", "captured_at"))
        absolute(source["original_path"])
        valid_time(source["captured_at"])
        expected = {"source.bin", *basis}
    require(set(payloads) == expected, "payload list disagrees with capture record")
    validate_identity(record["identity"], basis, payloads)


def publish(directory, capture_id, captured, identity, basis):
    record = {"version": 1, "capture_id": capture_id, "captured": captured,
              "identity": identity, "basis_payloads": basis}
    names = (["stdout.bin", "stderr.bin"] if captured["kind"] == "command" else ["source.bin"]) + basis
    payloads, descriptions = {}, []
    for name in names:
        with open_regular(name, directory) as stream:
            payloads[name] = stream.read()
        descriptions.append(descriptor_for(name, payloads[name]))
    validate_record(record, capture_id, payloads)
    data = encoded(record)
    write_bytes(directory, "record.json", data)
    manifest = {"version": 1, "capture_id": capture_id, "record": descriptor_for("record.json", data),
                "payloads": descriptions}
    write_bytes(directory, ".manifest-pending", encoded(manifest))
    os.link(".manifest-pending", "manifest.json", src_dir_fd=directory,
            dst_dir_fd=directory, follow_symlinks=False)
    os.unlink(".manifest-pending", dir_fd=directory)
    os.fsync(directory)


def capture(args):
    store = absolute(args.store)
    require(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,79}", args.id) is not None,
            "invalid capture ID")
    store_fd = open_directory(store, create=True)
    try:
        os.mkdir(args.id, mode=0o700, dir_fd=store_fd)
        directory = os.open(args.id, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=store_fd)
        os.fsync(store_fd)
    finally:
        os.close(store_fd)
    try:
        identity, basis = identity_capture(args.identity, directory)
        if args.operation == "command":
            argv = args.argv[1:] if args.argv[:1] == ["--"] else args.argv
            require(argv and all("\x00" not in arg for arg in argv), "command argv must be nonempty")
            cwd = absolute(args.cwd)
            cwd_fd = open_directory(cwd)
            os.close(cwd_fd)
            started = timestamp()
            with open_regular("stdout.bin", directory, write=True) as stdout, \
                    open_regular("stderr.bin", directory, write=True) as stderr:
                child = subprocess.run(argv, cwd=str(cwd), stdout=stdout, stderr=stderr, check=False)
                for stream in (stdout, stderr):
                    stream.flush()
                    os.fsync(stream.fileno())
            captured = {"kind": "command", "execution": {"argv": argv, "cwd": str(cwd),
                        "started_at": started, "ended_at": timestamp(), "raw_returncode": child.returncode},
                        "stdout": "stdout.bin", "stderr": "stderr.bin"}
        else:
            source = absolute(args.source)
            write_bytes(directory, "source.bin", read_source(source))
            captured = {"kind": "imported-file", "source": {"original_path": str(source),
                        "captured_at": timestamp()}, "saved_file": "source.bin"}
        publish(directory, args.id, captured, identity, basis)
    finally:
        os.close(directory)
    return str(store / args.id / "manifest.json")


def verify(path):
    path = absolute(path)
    require(path.name == "manifest.json", "expected manifest.json")
    directory = open_directory(path.parent)
    try:
        with open_regular(path.name, directory) as stream:
            manifest = parse_json(stream.read())
        object_keys(manifest, ("version", "capture_id", "record", "payloads"))
        require(type(manifest["version"]) is int and manifest["version"] == 1,
                "unsupported manifest version")
        require(isinstance(manifest["capture_id"], str) and
                re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,79}", manifest["capture_id"]) and
                manifest["capture_id"] == path.parent.name, "invalid capture ID")
        require(isinstance(manifest["record"], dict) and manifest["record"].get("path") == "record.json",
                "invalid record descriptor")
        record = parse_json(read_payload(directory, manifest["record"]))
        require(isinstance(manifest["payloads"], list), "payloads must be an array")
        payloads = {}
        for description in manifest["payloads"]:
            data = read_payload(directory, description)
            name = description["path"]
            require(name != "record.json" and name not in payloads, "duplicate payload path")
            payloads[name] = data
        validate_record(record, manifest["capture_id"], payloads)
        return record
    finally:
        os.close(directory)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="operation", required=True)
    for operation in ("command", "file"):
        command = commands.add_parser(operation)
        command.add_argument("--store", required=True)
        command.add_argument("--id", required=True)
        command.add_argument("--identity")
        if operation == "command":
            command.add_argument("--cwd", required=True)
            command.add_argument("argv", nargs=argparse.REMAINDER)
        else:
            command.add_argument("--source", required=True)
    commands.add_parser("verify").add_argument("manifest")
    args = parser.parse_args()
    try:
        if args.operation == "verify":
            print(json.dumps(verify(args.manifest), ensure_ascii=True, allow_nan=False))
        else:
            print(capture(args))
        return 0
    except (OSError, ValueError, TypeError, KeyError, OverflowError) as error:
        print(f"evidence: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
