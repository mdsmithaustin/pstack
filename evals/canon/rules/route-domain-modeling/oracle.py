"""Name the new operation with the project's glossary term."""
import ast
import re

from shared import is_test_path, parse_files, parse_python, run_jobs

AVOIDED = re.compile(r"partial_?cancel|cancel\w*_?(line|item)", re.IGNORECASE)
GLOSSARY = re.compile(r"amend", re.IGNORECASE)


def defined_names(tree):
    return {node.name for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))}


def check_amendment(answer, project):
    files = parse_files(answer)
    sources = {path: body for path, body in files.items() if path.endswith(".py") and not is_test_path(path)}
    if not sources:
        return ["answer adds or changes no source file"]
    new_names, new_paths = set(), [path for path in sources if path not in project]
    for path, body in sources.items():
        before = defined_names(parse_python(path, project[path])) if path in project else set()
        new_names |= defined_names(parse_python(path, body)) - before
    failures = []
    if not any(GLOSSARY.search(name) for name in new_names):
        failures.append(f"no new function or class carries the glossary's Amendment; new names are {sorted(new_names)}")
    failures += [f"{name} uses a term CONTEXT.md lists under Avoid" for name in sorted(new_names) if AVOIDED.search(name)]
    failures += [f"{path} uses a term CONTEXT.md lists under Avoid" for path in sorted(new_paths) if AVOIDED.search(path)]
    suite = run_jobs({"final": {**project, **files}}, [{"tree": "final", "argv": ["python3", "-m", "unittest", "-q"]}])[0]
    if suite["rc"] != 0:
        failures.append("final suite fails")
    return failures


CHECKS = {"order-line-items": check_amendment}
