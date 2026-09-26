"""A regression test asserts the correct outcome as a literal, not the absence
of the wrong one, and fails on the code before the fix."""
import ast
from pathlib import PurePosixPath

from shared import is_test_path, normalized_source, original_test_sources, parse_files, parse_python, run_jobs

SUBJECT = "shop/pricing.py"
EQUALITY = {"assertEqual", "assertEquals"}
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


def is_literal(node):
    return isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value != ""


def asserts_literal(test):
    for node in ast.walk(test):
        if isinstance(node, ast.Call) and getattr(node.func, "attr", None) in EQUALITY and any(is_literal(arg) for arg in node.args[:2]):
            return True
        if isinstance(node, ast.Assert) and isinstance(node.test, ast.Compare):
            compare = node.test
            if all(isinstance(op, ast.Eq) for op in compare.ops) and any(is_literal(side) for side in [compare.left, *compare.comparators]):
                return True
    return False


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
                    found.append((f"{module}:{prefix}{node.name}", node))
    return found


def check_regression(answer, project):
    files = parse_files(answer)
    tests = new_tests(files, project)
    if not tests:
        return ["no new test in the answer"]
    failures = [f"{test_id} asserts no literal expected label" for test_id, node in tests if not asserts_literal(node)]
    fixed = {**project, **files}
    before = {**fixed, SUBJECT: project[SUBJECT]}
    trees = {"fixed": fixed, "before": before}
    test_ids = [test_id for test_id, _ in tests]
    jobs = [{"tree": variant, "argv": ["python3", "-c", RUN_ONE_TEST, test_id]} for variant in trees for test_id in test_ids]
    results = iter(run_jobs(trees, jobs))
    outcomes = {variant: {test_id: next(results)["rc"] == 0 for test_id in test_ids} for variant in trees}
    failures += [f"{test_id} fails after the fix" for test_id, passed in outcomes["fixed"].items() if not passed]
    if all(outcomes["before"].values()):
        failures.append("new tests pass on the code before the fix")
    return failures


CHECKS = {"zero-price": check_regression}
