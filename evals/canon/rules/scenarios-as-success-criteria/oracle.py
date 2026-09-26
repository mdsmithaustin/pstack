"""The spec's examples are the success criteria: the first test goes through
the HTTP handler, and every example has a handler test with its literal Then."""
import ast
from pathlib import PurePosixPath

from shared import is_test_path, normalized_source, original_test_sources, parse_files, parse_python, run_jobs

HANDLER = "handle"
EXAMPLES = (
    ("inside the window", 201, {"CREATED"}, "refund_requested"),
    ("window closed", 422, {"UNPROCESSABLE_ENTITY", "UNPROCESSABLE_CONTENT"}, "refund window closed"),
    ("not delivered yet", 409, {"CONFLICT"}, "order not delivered"),
)
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


def called(node):
    return {
        getattr(call.func, "attr", getattr(call.func, "id", None))
        for call in ast.walk(node)
        if isinstance(call, ast.Call)
    }


def handler_callers(tree):
    """Names of functions in this file that reach the handler, directly or through each other."""
    defined = {node.name: node for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
    reach = {HANDLER}
    grew = True
    while grew:
        grew = False
        for name, node in defined.items():
            if name not in reach and called(node) & reach:
                reach.add(name)
                grew = True
    return reach


def ordered_tests(path, tree):
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            for child in node.body:
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) and child.name.startswith("test"):
                    yield f"{node.name}.{child.name}", child
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test"):
            yield node.name, node


def asserts_then(node, status, status_names, message):
    constants = {child.value for child in ast.walk(node) if isinstance(child, ast.Constant)}
    attributes = {child.attr for child in ast.walk(node) if isinstance(child, ast.Attribute)}
    has_status = any(value == status and type(value) is int for value in constants) or bool(attributes & status_names)
    return has_status and message in constants


def check_scenarios(answer, project):
    files = parse_files(answer)
    original = original_test_sources(project)
    tests = []
    for path, body in files.items():
        if not (path.endswith(".py") and is_test_path(path)):
            continue
        module = PurePosixPath(path).with_suffix("").as_posix().replace("/", ".")
        tree = parse_python(path, body)
        reach = handler_callers(tree)
        for qualname, node in ordered_tests(path, tree):
            if normalized_source(body, node) not in original:
                tests.append((f"{module}:{qualname}", node, bool(called(node) & reach)))
    if not tests:
        return ["no new test in the answer"]
    failures = []
    first_id, _, first_through_handler = tests[0]
    if not first_through_handler:
        failures.append(f"the first new test, {first_id}, does not go through OrdersApi.handle")
    for label, status, status_names, message in EXAMPLES:
        if not any(through and asserts_then(node, status, status_names, message) for _, node, through in tests):
            failures.append(f"no handler test asserts the {label} example's literal {status} and {message!r}")
    trees = {"answer": {**project, **files}}
    jobs = [{"tree": "answer", "argv": ["python3", "-c", RUN_ONE_TEST, test_id]} for test_id, _, _ in tests]
    for (test_id, _, _), result in zip(tests, run_jobs(trees, jobs)):
        if result["rc"] != 0:
            failures.append(f"{test_id} fails against the answer's code")
    return failures


CHECKS = {"refund-window": check_scenarios}
