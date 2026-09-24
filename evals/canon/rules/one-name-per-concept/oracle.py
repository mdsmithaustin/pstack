"""Keep one name for one concept: never Membership beside Subscription."""
import ast
from pathlib import PurePosixPath

from shared import parse_files, parse_python


def names(tree):
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            found.add(node.name)
        elif isinstance(node, ast.arg):
            found.add(node.arg)
        elif isinstance(node, ast.Name):
            found.add(node.id)
        elif isinstance(node, ast.Attribute):
            found.add(node.attr)
        elif isinstance(node, ast.alias):
            found.update(part for part in (node.name.split(".") + [node.asname or ""]) if part)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.update(node.module.split("."))
    return found


def tree_names(tree_files):
    found = set()
    for path, body in tree_files.items():
        if path.endswith(".py"):
            found |= names(parse_python(path, body)) | {PurePosixPath(path).stem}
    return found


def check_one_name(answer, project):
    files = parse_files(answer)
    final = {**project, **files}
    final = {path: body for path, body in final.items() if body.strip()}
    before, after = tree_names(project), tree_names(final)
    failures = []
    membership = sorted(name for name in after if "membership" in name.lower())
    subscription = sorted(name for name in after if "subscription" in name.lower())
    if membership and subscription:
        failures.append(f"the code names one concept twice: {', '.join(membership)} beside {', '.join(subscription)}")
    if not any("pause" in name.lower() for name in after - before):
        failures.append("no new name carries the pause")
    return failures


CHECKS = {"billing-pause": check_one_name}
