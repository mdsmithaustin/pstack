"""Helpers every rule oracle shares: answer parsing, Python source reading,
workspace diffs, and the sandboxed container that runs answer code."""
import ast
import json
import os
import re
import shutil
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

PROBES = Path(__file__).resolve().parent / "probes"
IMAGE = "python:3.12-slim@sha256:229a2c5bfa27522db7815ea81f9bed70af17ccb9de9fc7ad142b1877b5830d36"
PROJECT_IMAGES = Path(__file__).resolve().parent.parent / "images" / "images.json"

FILE_TAG = re.compile(r'<file path="([^"\n]+)">(.*?)</file>', re.DOTALL)
COMMIT_TAG = re.compile(r'<commit message="([^"]*)">(.*?)</commit>', re.DOTALL)


class OracleError(Exception):
    pass


@dataclass(frozen=True)
class Workspace:
    """What a workspace case's oracle receives in place of the project files:
    the pinned checkout with its overlay, and the diff the agent left on it.
    harvest is the directory holding a graded run's diff, where a check may
    write a report beside it; None when the diff did not come from a run."""
    checkout: Path
    diff: str
    harvest: Path | None = None


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


def document_text(answer, document, workspace=None):
    """The text a document case judges, or "" when the run delivered none.

    document is case.json's {"message": true}, which judges the whole final
    message, or {"file": path}. In a workspace case the file is read from the
    checkout after the harvested diff, so a diff that never touches it yields
    the checkout's copy and a deletion yields "". In a pasted-project case it is
    the body of the last <file path="..."> block for that path, with one code
    fence stripped. An unsafe path in some other block does not raise here,
    since an unrelated bad tag must not turn a delivered document into an
    absent one. The judge and calibration cut the document through this one
    function. The precheck receives the whole final message, so a rule's oracle
    calls this function itself when it grades the document alone. The offline
    stand-ins cut nothing: the agent stand-in answers with a whole sample, and
    offline/judge matches the smallest sample that contains the judged text."""
    if document.get("message"):
        return answer
    path = document["file"]
    if isinstance(workspace, Workspace):
        changed = apply_diff(workspace.checkout, workspace.diff)
        if path in changed:
            return changed[path].decode("utf-8", "replace") if changed[path] is not None else ""
        source = Path(workspace.checkout) / path
        return source.read_text(encoding="utf-8", errors="replace") if source.is_file() else ""
    bodies = [body for tagged, body in FILE_TAG.findall(answer) if PurePosixPath(tagged.strip()).as_posix() == path]
    return clean_body(bodies[-1]) if bodies else ""


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
    """Run each job in a container that mounts only its own tree, so answer
    code cannot read another arm's files. Results keep the order of jobs."""
    groups = {}
    for index, job in enumerate(jobs):
        groups.setdefault(job["tree"], []).append(index)
    results = [None] * len(jobs)
    with tempfile.TemporaryDirectory() as directory:
        stage = Path(directory)
        for name in groups:
            for path, body in trees[name].items():
                target = stage / name / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(body, encoding="utf-8")
        with ThreadPoolExecutor() as pool:
            outputs = pool.map(lambda name: run_container(stage / name, name, [jobs[index] for index in groups[name]]), groups)
            for indexes, output in zip(groups.values(), outputs):
                for index, result in zip(indexes, output):
                    results[index] = result
    return results


def run_container(source, name, jobs):
    command = [
        "docker", "run", "--rm", "-i",
        "--network", "none", "--read-only", "--tmpfs", "/tmp:rw,size=64m",
        "--memory", "512m", "--pids-limit", "256", "--cap-drop", "ALL",
        "--security-opt", "no-new-privileges", "--user", "65534:65534",
        "-e", "PYTHONDONTWRITEBYTECODE=1",
        "-v", f"{source}:/work/{name}:ro", "-v", f"{PROBES}:/probes:ro",
        IMAGE, "python3", "/probes/run.py",
    ]
    proc = subprocess.run(command, input=json.dumps({"jobs": jobs}), capture_output=True, text=True, timeout=240, check=False)
    if proc.returncode != 0:
        raise OracleError(f"container probe failed (exit {proc.returncode}): {proc.stderr.strip()[-500:]}")
    return json.loads(proc.stdout)


PLAIN_RUNNER = """import contextlib, importlib, inspect, io, json, sys
failures = []
out = sys.stdout
sys.stdout = io.StringIO()
for name in sys.argv[1:]:
    try:
        module = importlib.import_module(name)
    except BaseException as exc:
        failures.append(f"{name} does not import: {type(exc).__name__}")
        continue
    cases = []
    for key, value in vars(module).items():
        if key.startswith("test") and inspect.isfunction(value) and value.__module__ == name:
            cases.append((f"{name}::{key}", None, value))
        elif key.startswith("Test") and inspect.isclass(value) and value.__module__ == name:
            for attr, method in vars(value).items():
                if attr.startswith("test") and inspect.isfunction(method):
                    cases.append((f"{name}::{key}::{attr}", value, attr))
    if not cases:
        failures.append(f"{name} holds no test functions")
    for label, owner, target in cases:
        try:
            if owner is None:
                target()
            else:
                instance = owner()
                if hasattr(instance, "setup_method"):
                    instance.setup_method()
                getattr(instance, target)()
        except BaseException:
            failures.append(f"{label} failed")
out.write(json.dumps(failures))
"""


def plain_test_failures(tree, modules):
    """Failures from running every test function and Test* class method of
    the named modules in the container, pytest-style but with no plugins or
    fixtures. tree is {path: text}; the modules import from it."""
    job = {"tree": "suite", "argv": ["python3", "_plain_runner.py", *modules], "timeout": 60}
    result = run_jobs({"suite": {**tree, "_plain_runner.py": PLAIN_RUNNER}}, [job])[0]
    if result["rc"] != 0:
        raise OracleError(f"the test runner stopped (exit {result['rc']}): {result['stderr'].strip()[-300:]}")
    return json.loads(result["stdout"])


def project_test_results(image, checkout, files, tests):
    """{test id: "passed", "failed", or "skipped"} from running the named test
    files of a real checkout in a dependency image from images/images.json,
    offline. files is apply_diff's {path: bytes or None}, laid over a copy of
    checkout, so the run never writes to the checkout itself."""
    images = json.loads(PROJECT_IMAGES.read_text()) if PROJECT_IMAGES.is_file() else {}
    if image not in images:
        raise OracleError(f"no dependency image {image!r}; build it with images/build.py")
    with tempfile.TemporaryDirectory() as directory:
        stage = Path(directory) / "work"
        shutil.copytree(checkout, stage, symlinks=True, ignore=shutil.ignore_patterns(".git"))
        for path, data in files.items():
            target = stage / safe_path(path)
            if not target.parent.resolve().is_relative_to(stage.resolve()):
                raise OracleError(f"{path} resolves outside the checkout copy")
            if data is None:
                target.unlink(missing_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
        name = f"canon-project-tests-{os.getpid()}-{Path(directory).name}"
        command = [
            "docker", "run", "--rm", "--name", name,
            "--network", "none", "--read-only", "--tmpfs", "/tmp:rw,exec,size=1g",
            "--memory", "4g", "--pids-limit", "1024", "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges", "--user", "65534:65534",
            "-e", "HOME=/tmp", "-e", "PYTHONDONTWRITEBYTECODE=1",
            "-v", f"{stage}:/work", "-v", f"{PROBES}:/probes:ro", "-w", "/work",
            images[image]["id"], "python3", "/probes/project_tests.py", *tests,
        ]
        try:
            proc = subprocess.run(command, capture_output=True, text=True, timeout=900, check=False)
        except subprocess.TimeoutExpired:
            subprocess.run(["docker", "kill", name], capture_output=True, text=True, timeout=60, check=False)
            raise OracleError("project tests timed out after 900s") from None
    if proc.returncode != 0:
        raise OracleError(f"project tests stopped (exit {proc.returncode}): {proc.stderr.strip()[-500:]}")
    return json.loads(proc.stdout)


def harvested_diff(run_dir):
    """The path of the diff harvested from the agent's workspace for one run.
    The harness seals each run dir, so the diff sits in a parallel tree:
    <work>/runs/<run> maps to <work>/harvest/<run>/workspace.diff."""
    run_dir = Path(run_dir).resolve()
    runs = next((parent for parent in run_dir.parents if parent.name == "runs"), None)
    path = runs.parent / "harvest" / run_dir.relative_to(runs) / "workspace.diff" if runs else None
    if path is None or not path.is_file():
        raise OracleError(f"no workspace diff was harvested for {run_dir}")
    return path


def workspace_diff(run_dir):
    return harvested_diff(run_dir).read_bytes().decode("utf-8", "surrogateescape")


def apply_diff(checkout, diff):
    """{path: bytes after the diff, or None when the diff deletes it} for every
    path the diff touches. Paths it leaves alone are read from checkout."""
    data = diff.encode("utf-8", "surrogateescape")
    if not data.strip():
        return {}
    with tempfile.TemporaryDirectory() as directory:
        stage = Path(directory) / "tree"
        stage.mkdir()
        env = {**os.environ, "GIT_CEILING_DIRECTORIES": directory, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}

        def git_apply(*args):
            proc = subprocess.run(["git", "apply", *args], cwd=stage, env=env, input=data, capture_output=True, check=False)
            if proc.returncode != 0:
                raise OracleError(f"workspace diff does not apply to the checkout: {proc.stderr.decode(errors='replace').strip()[-300:]}")
            return proc.stdout

        paths = [safe_path(record.split(b"\t", 2)[2].decode("utf-8", "surrogateescape"))
                 for record in git_apply("--numstat", "-z").split(b"\0") if record]
        root = Path(checkout).resolve()
        for path in paths:
            source = Path(checkout) / path
            if source.is_symlink():
                raise OracleError(f"workspace diff touches a symlink in the checkout: {path}")
            if not source.resolve().is_relative_to(root):
                raise OracleError(f"workspace diff path resolves outside the checkout: {path}")
            if source.is_file():
                (stage / path).parent.mkdir(parents=True, exist_ok=True)
                (stage / path).write_bytes(source.read_bytes())
        git_apply("--binary", "--whitespace=nowarn")
        for path in paths:
            if (stage / path).is_symlink():
                raise OracleError(f"workspace diff leaves a symlink at {path}")
        return {path: (stage / path).read_bytes() if (stage / path).is_file() else None for path in paths}


def review_names(answer, location):
    """Failures unless answer matches one of the location regexes."""
    if any(re.search(pattern, answer, re.IGNORECASE) for pattern in location):
        return []
    return ["the review does not name the file or symbol under review"]
