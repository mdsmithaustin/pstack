import io
import json
import re
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path


IMAGE = "python:3.12-slim@sha256:229a2c5bfa27522db7815ea81f9bed70af17ccb9de9fc7ad142b1877b5830d36"
SHELL_FENCE = re.compile(r"```(?:bash|sh|shell)\s*\n(.*?)\n```", re.DOTALL | re.IGNORECASE)
CONTAINER_PROGRAM = r'''
import json
import os
import re
import subprocess
import sys
import tarfile
import threading
import time
from pathlib import Path


def descendants(root_pid):
    parents = {}
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        try:
            fields = (entry / "stat").read_text().split()
            parents[int(entry.name)] = int(fields[3])
        except (FileNotFoundError, PermissionError, ValueError, IndexError):
            continue
    found = {root_pid}
    changed = True
    while changed:
        changed = False
        for pid, parent in parents.items():
            if parent in found and pid not in found:
                found.add(pid)
                changed = True
    return found - {root_pid}


def observe_processes(process, sink):
    while process.poll() is None:
        for pid in descendants(process.pid) | {process.pid}:
            try:
                raw = (Path("/proc") / str(pid) / "cmdline").read_bytes()
                command = raw.replace(b"\0", b" ").decode("utf-8", "replace").strip()
                cwd = os.readlink(Path("/proc") / str(pid) / "cwd")
            except (FileNotFoundError, PermissionError, ProcessLookupError):
                continue
            if command:
                sink.add(f"{cwd} :: {command}")
        time.sleep(0.002)


def run_case(root, plan, definition, bootstrap):
    results = []
    for state in definition["states"]:
        project = root / "runs" / state["name"] / "project"
        project.mkdir(parents=True)
        setup = subprocess.run(
            [sys.executable, str(bootstrap), str(project), state["name"]],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=5,
            check=False,
        )
        if setup.returncode != 0:
            raise RuntimeError(f"setup failed for {state['name']}: {setup.stderr}")
        seen = set()
        environment = {
            "HOME": "/work/home",
            "LANG": "C.UTF-8",
            "PATH": f"{project / 'bin'}:/usr/local/bin:/usr/bin:/bin",
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
            continue
        process = subprocess.Popen(
            ["/bin/sh", str(root / "input" / "plan.sh")],
            cwd=candidate_cwd,
            env=environment,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        watcher = threading.Thread(target=observe_processes, args=(process, seen))
        watcher.start()
        timed_out = False
        try:
            stdout, stderr = process.communicate(timeout=state.get("timeout_seconds", 5))
        except subprocess.TimeoutExpired:
            timed_out = True
            process.kill()
            stdout, stderr = process.communicate()
        watcher.join()
        expected_zero = state["exit"] == "zero"
        exit_matches = not timed_out and ((process.returncode == 0) == expected_zero)
        missing_operations = [
            pattern
            for pattern in state["required_operations"]
            if not any(re.search(pattern, event) for event in seen)
        ]
        results.append({
            "state": state["name"],
            "exit": process.returncode,
            "expected": state["exit"],
            "exit_matches": exit_matches,
            "timed_out": timed_out,
            "missing_operations": missing_operations,
            "stdout": stdout[-1000:],
            "stderr": stderr[-1000:],
        })
    return results


root = Path("/work")
input_root = root / "input"
input_root.mkdir()
with tarfile.open(fileobj=sys.stdin.buffer, mode="r|*") as archive:
    for member in archive:
        if member.name not in {"plan.sh", "bootstrap.py", "definition.json"} or not member.isfile():
            raise RuntimeError("unexpected archive member")
        source = archive.extractfile(member)
        if source is None:
            raise RuntimeError("missing archive member")
        (input_root / member.name).write_bytes(source.read())

plan = json.loads((input_root / "definition.json").read_text())
results = run_case(root, plan["artifact"], plan["case"], input_root / "bootstrap.py")
print(json.dumps({"status": "measured", "states": results}, sort_keys=True))
'''


def parse_plan(text: str) -> dict:
    fences = SHELL_FENCE.findall(text)
    if len(fences) != 1:
        raise ValueError("output must contain exactly one fenced shell artifact")
    plan = {"script": fences[0], "workdir": "."}
    if not isinstance(plan["script"], str) or not plan["script"].strip():
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
        "--security-opt", "no-new-privileges",
        "--user", "65534:65534",
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
        "operation_evidence": "observed in container process table",
    }


def evaluate(case_id: str, output_dir: Path) -> tuple[int, dict]:
    output = output_dir / "output.md"
    if not output.is_file():
        return 1, {"status": "candidate_failure", "reason": f"missing {output.name}"}
    try:
        plan = parse_plan(output.read_text(encoding="utf-8"))
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
