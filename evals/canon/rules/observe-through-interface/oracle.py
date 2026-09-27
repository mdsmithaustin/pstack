"""Observe the outcome through the caller's interface, not storage."""
import ast
import re
from pathlib import PurePosixPath

from shared import OracleError, is_test_path, normalized_source, original_test_sources, parse_files, parse_python, run_jobs

SUBJECT = "accounts/users.py"
MUTANTS = {
    "stores-mixed-case": ("normalized = email.strip().lower()", "normalized = email.strip()"),
    "stores-raw-returns-normalized": ("(normalized, name)\n        )", "(email, name)\n        )"),
}
READBACK = re.compile(r"\.(execute|executemany|executescript|cursor|fetchone|fetchall|fetchmany)\(|\bselect\b[^\n]*\bfrom\b", re.IGNORECASE)
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


def new_definitions(path, body, original_sources):
    tree = parse_python(path, body)
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            for child in node.body:
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    found.append((f"{node.name}.{child.name}", child))
        elif isinstance(node, ast.Module):
            for child in node.body:
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    found.append((child.name, child))
    return [
        (qualname, node, ast.get_source_segment(body, node) or "")
        for qualname, node in found
        if normalized_source(body, node) not in original_sources
    ]


def check_observe(answer, project):
    files = parse_files(answer)
    original_sources = original_test_sources(project)
    failures = []
    test_ids = []
    for path, body in files.items():
        if not (path.endswith(".py") and is_test_path(path)):
            continue
        module = PurePosixPath(path).with_suffix("").as_posix().replace("/", ".")
        for qualname, node, source in new_definitions(path, body, original_sources):
            if READBACK.search(source):
                failures.append(f"{module}:{qualname} reads storage directly")
            if node.name.startswith("test"):
                test_ids.append(f"{module}:{qualname}")
    if not test_ids:
        return failures + ["no new test in the answer"]
    tree = {**project, **{path: body for path, body in files.items() if path != SUBJECT}}
    trees = {"original": tree}
    for name, (old, new) in MUTANTS.items():
        subject = project[SUBJECT]
        if subject.count(old) != 1:
            raise OracleError(f"mutant {name} does not apply to the fixture")
        trees[name] = {**tree, SUBJECT: subject.replace(old, new)}
    jobs = [
        {"tree": variant, "argv": ["python3", "-c", RUN_ONE_TEST, test_id]}
        for variant in trees
        for test_id in test_ids
    ]
    results = iter(run_jobs(trees, jobs))
    outcomes = {variant: {test_id: next(results)["rc"] == 0 for test_id in test_ids} for variant in trees}
    for test_id, passed in outcomes["original"].items():
        if not passed:
            failures.append(f"{test_id} fails against the working code")
    for variant in MUTANTS:
        if all(outcomes[variant].values()):
            failures.append(f"new tests still pass when the code {variant.replace('-', ' ')}")
    return failures


CHECKS = {"register-email": check_observe}
