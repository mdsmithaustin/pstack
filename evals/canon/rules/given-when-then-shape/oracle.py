"""One Given, one When, one Then, separated by blank lines, not comments."""
import ast
import re
from pathlib import PurePosixPath

from shared import OracleError, is_test_path, normalized_source, original_test_sources, parse_files, parse_python, run_jobs

SUBJECT = "projects/board.py"
SETUP = {"create_project"}
ACTIONS = {"archive_project", "rename_project"}
MUTANT = ("self._projects[project_id].archived = True", "pass")
PHASE_COMMENT = re.compile(r"#\s*(given|when|then|arrange|act|assert)\b", re.IGNORECASE)
RUN_ONE_TEST = """
import importlib, sys, unittest
module_name, _, qualname = sys.argv[1].partition(":")
module = importlib.import_module(module_name)
owner_name, _, method = qualname.rpartition(".")
if owner_name:
    result = unittest.TextTestRunner(verbosity=0).run(unittest.TestSuite([getattr(module, owner_name)(method)]))
    sys.exit(0 if result.wasSuccessful() else 1)
getattr(module, qualname)()
"""


def new_tests(files, project):
    original = original_test_sources(project)
    found = []
    for path, body in files.items():
        if not (path.endswith(".py") and is_test_path(path)):
            continue
        module = PurePosixPath(path).with_suffix("").as_posix().replace("/", ".")
        tree = parse_python(path, body)
        scopes = [("", tree)] + [(f"{node.name}.", node) for node in tree.body if isinstance(node, ast.ClassDef)]
        for prefix, scope in scopes:
            for node in scope.body:
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test") and normalized_source(body, node) not in original:
                    found.append((f"{module}:{prefix}{node.name}", node, ast.get_source_segment(body, node) or ""))
    return found


def called(statement):
    return {
        getattr(node.func, "attr", getattr(node.func, "id", None))
        for node in ast.walk(statement)
        if isinstance(node, ast.Call)
    }


def is_assertion(statement):
    if isinstance(statement, ast.Assert):
        return True
    return any(name and name.startswith("assert") for name in called(statement))


def shape_failures(test_id, node, source):
    failures = []
    if PHASE_COMMENT.search(source):
        failures.append(f"{test_id} marks its phases with comments")
    statements = node.body
    first_assert = next((index for index, statement in enumerate(statements) if is_assertion(statement)), len(statements))
    if any(called(statement) & (SETUP | ACTIONS) for statement in statements[first_assert:]):
        failures.append(f"{test_id} acts again after asserting")
    last_setup = max((index for index, statement in enumerate(statements) if called(statement) & SETUP), default=-1)
    actions = [statement for statement in statements[last_setup + 1:] if called(statement) & ACTIONS]
    if len(actions) != 1:
        failures.append(f"{test_id} has {len(actions)} actions after its setup, not one")
    return failures


def check_shape(answer, project):
    files = parse_files(answer)
    tests = new_tests(files, project)
    if not tests:
        return ["no new test in the answer"]
    failures = [failure for test_id, node, source in tests for failure in shape_failures(test_id, node, source)]
    tree = {**project, **{path: body for path, body in files.items() if path != SUBJECT}}
    old, new = MUTANT
    if project[SUBJECT].count(old) != 1:
        raise OracleError("mutant does not apply to the fixture")
    trees = {"original": tree, "mutant": {**tree, SUBJECT: project[SUBJECT].replace(old, new)}}
    test_ids = [test_id for test_id, _, _ in tests]
    jobs = [{"tree": variant, "argv": ["python3", "-c", RUN_ONE_TEST, test_id]} for variant in trees for test_id in test_ids]
    results = iter(run_jobs(trees, jobs))
    outcomes = {variant: {test_id: next(results)["rc"] == 0 for test_id in test_ids} for variant in trees}
    failures += [f"{test_id} fails against the working code" for test_id, passed in outcomes["original"].items() if not passed]
    if all(outcomes["mutant"].values()):
        failures.append("new tests still pass when archiving keeps the project on the dashboard")
    return failures


CHECKS = {"projects-dashboard": check_shape}
