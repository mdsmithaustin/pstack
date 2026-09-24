"""Name new code with the glossary's word, never a word it lists under Avoid."""
import ast
import re
from pathlib import PurePosixPath

from shared import normalized_source, parse_files, parse_python

DELIVERY = re.compile(r"deliver(y|ies)", re.IGNORECASE)
DEFINITIONS = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)


def bound_names(node):
    """Names a node binds: definitions, arguments, and assignment targets."""
    names = set()
    for child in ast.walk(node):
        if isinstance(child, DEFINITIONS):
            names.add(child.name)
        elif isinstance(child, ast.arg):
            names.add(child.arg)
        elif isinstance(child, ast.Name) and isinstance(child.ctx, ast.Store):
            names.add(child.id)
        elif isinstance(child, ast.Attribute) and isinstance(child.ctx, ast.Store):
            names.add(child.attr)
    return names


def introduced_names(project, files):
    """Names bound by definitions the answer adds or rewrites, module-level
    names the project did not have, and the stems of new modules."""
    original_defs, original_names = set(), set()
    for path, body in project.items():
        if path.endswith(".py"):
            tree = parse_python(path, body)
            original_defs.update(normalized_source(body, node) for node in ast.walk(tree) if isinstance(node, DEFINITIONS))
            original_names |= bound_names(tree)
    found = set()
    for path, body in files.items():
        if not path.endswith(".py"):
            continue
        tree = parse_python(path, body)
        if path not in project:
            found.add(PurePosixPath(path).stem)
        for node in ast.walk(tree):
            if isinstance(node, DEFINITIONS) and normalized_source(body, node) not in original_defs:
                found |= bound_names(node)
        for statement in tree.body:
            if not isinstance(statement, DEFINITIONS):
                found |= bound_names(statement) - original_names
    return found, original_names


def check_shipment_words(answer, project):
    files = parse_files(answer)
    names, original = introduced_names(project, files)
    if not names:
        return ["the answer adds no Python code"]
    failures = [f"new name {name} uses the word delivery" for name in sorted(names - original) if DELIVERY.search(name)]
    if not any("shipment" in name.lower() for name in names):
        failures.append("no new name uses the word shipment")
    return failures


CHECKS = {"shipment-tracking": check_shipment_words}
