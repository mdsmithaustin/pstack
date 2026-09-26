"""Helpers every rule oracle shares: answer parsing, Python source reading,
and the sandboxed container that runs answer code."""
import ast
import json
import re
import subprocess
import tempfile
from pathlib import Path, PurePosixPath

PROBES = Path(__file__).resolve().parent / "probes"
IMAGE = "python:3.12-slim@sha256:229a2c5bfa27522db7815ea81f9bed70af17ccb9de9fc7ad142b1877b5830d36"

FILE_TAG = re.compile(r'<file path="([^"\n]+)">(.*?)</file>', re.DOTALL)
COMMIT_TAG = re.compile(r'<commit message="([^"]*)">(.*?)</commit>', re.DOTALL)


class OracleError(Exception):
    pass


def clean_body(body):
    lines = body.strip("\n").split("\n")
    if len(lines) >= 2 and lines[0].startswith("```") and lines[-1].strip() == "```":
        lines = lines[1:-1]
    return "\n".join(lines) + "\n"


def safe_path(raw):
    path = PurePosixPath(raw.strip())
    if not path.parts or path.is_absolute() or ".." in path.parts:
        raise OracleError(f"unsafe file path in answer: {raw!r}")
    return path.as_posix()


def parse_files(text):
    return {safe_path(path): clean_body(body) for path, body in FILE_TAG.findall(text)}


def parse_commits(text):
    return [(message, parse_files(body)) for message, body in COMMIT_TAG.findall(text)]


def is_test_path(path):
    pure = PurePosixPath(path)
    return pure.parts[0] == "tests" or pure.name.startswith("test_")


def parse_python(path, body):
    try:
        return ast.parse(body)
    except SyntaxError as exc:
        raise OracleError(f"{path} does not parse: {exc.msg} at line {exc.lineno}") from exc


def functions(tree):
    return [node for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))]


def normalized_source(body, node):
    return " ".join((ast.get_source_segment(body, node) or "").split())


def original_test_sources(project):
    sources = set()
    for path, body in project.items():
        if path.endswith(".py") and is_test_path(path):
            tree = parse_python(path, body)
            sources.update(normalized_source(body, node) for node in functions(tree))
    return sources


def run_jobs(trees, jobs):
    with tempfile.TemporaryDirectory() as directory:
        stage = Path(directory)
        # The probe runs as nobody, and TemporaryDirectory makes the stage 0700.
        stage.chmod(0o755)
        for name, files in trees.items():
            for path, body in files.items():
                target = stage / name / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(body, encoding="utf-8")
        command = [
            "docker", "run", "--rm", "-i",
            "--network", "none", "--read-only", "--tmpfs", "/tmp:rw,size=64m",
            "--memory", "512m", "--pids-limit", "256", "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges", "--user", "65534:65534",
            "-e", "PYTHONDONTWRITEBYTECODE=1",
            "-v", f"{stage}:/work:ro", "-v", f"{PROBES}:/probes:ro",
            IMAGE, "python3", "/probes/run.py",
        ]
        proc = subprocess.run(command, input=json.dumps({"jobs": jobs}), capture_output=True, text=True, timeout=240, check=False)
    if proc.returncode != 0:
        raise OracleError(f"container probe failed (exit {proc.returncode}): {proc.stderr.strip()[-500:]}")
    return json.loads(proc.stdout)
