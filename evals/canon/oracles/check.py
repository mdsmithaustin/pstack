"""Grade one answer for one case of one amended rule.

Usage: check.py <rule> <case> <output_dir>

Reads <output_dir>/output.md and exits 0 only when the answer shows the
behavior the case asks for. The grading code is rules/<rule>/oracle.py, whose
CHECKS maps each case id to a function of (answer, project) that returns the
list of failures. For a workspace case, project is a shared.Workspace holding
the pinned checkout and the run's harvested diff. Answer code runs only inside
a networkless, read-only container.
"""
import importlib.util
import json
import sys
import tempfile
from pathlib import Path

ORACLES = Path(__file__).resolve().parent
RULES = ORACLES.parent / "rules"
sys.path.insert(0, str(ORACLES))

from shared import OracleError, Workspace, workspace_diff  # noqa: E402


def load_oracle(rule):
    path = RULES / rule / "oracle.py"
    name = f"canon_oracle_{rule}"
    if name not in sys.modules:
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        sys.modules[name] = module
    return sys.modules[name].CHECKS


def load_project(rule, case):
    root = RULES / rule / "cases" / case / "project"
    return {
        path.relative_to(root).as_posix(): path.read_text(encoding="utf-8")
        for path in sorted(root.rglob("*"))
        if path.is_file() and "__pycache__" not in path.parts
    }


def load_workspace(rule, case, output_dir):
    """The build writes workspace.json, naming the pinned checkout, into a
    workspace case's grader copy."""
    record = RULES / rule / "cases" / case / "workspace.json"
    if not record.is_file():
        return None
    return Workspace(Path(json.loads(record.read_text())["checkout"]), workspace_diff(output_dir))


def evaluate(rule, case, output_dir, workspace=None):
    answer = (Path(output_dir) / "output.md").read_text(encoding="utf-8")
    try:
        project = workspace or load_workspace(rule, case, output_dir) or load_project(rule, case)
        return load_oracle(rule)[case](answer, project)
    except OracleError as exc:
        return [str(exc)]


def grade(rule, case, sample=None, text=None, workspace=None):
    """Grade a sample from the case's samples/ directory, or literal text. A
    workspace case also takes the Workspace its sample diff applies to."""
    if sample is not None:
        text = (RULES / rule / "cases" / case / "samples" / sample).read_text(encoding="utf-8")
    with tempfile.TemporaryDirectory() as directory:
        (Path(directory) / "output.md").write_text(text, encoding="utf-8")
        return evaluate(rule, case, directory, workspace)


def main(argv):
    if len(argv) != 4 or not (RULES / argv[1] / "oracle.py").is_file() or argv[2] not in load_oracle(argv[1]):
        print("usage: check.py <rule> <case> <output_dir>", file=sys.stderr)
        return 2
    failures = evaluate(argv[1], argv[2], argv[3])
    for failure in failures:
        print(f"FAIL: {failure}")
    if not failures:
        print("PASS")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
