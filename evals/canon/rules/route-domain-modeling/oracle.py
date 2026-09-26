"""Name the new operation with the project's glossary term."""
import ast
import re
from pathlib import PurePosixPath

from shared import apply_diff, is_test_path, parse_files, parse_python, run_jobs

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


DEFINITIONS = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
TREE_AVOIDED = re.compile(r"(fork|clone|chain|thread)(s|es|ed|ing)?")
TERM = re.compile(r"^\*\*(.+?)\*\*:", re.MULTILINE)
GLOSSARY_PATH = re.compile(r"(.+/)?CONTEXT(-MAP)?\.md|docs/adr/.+")


def identifier_words(name):
    return [word.lower() for word in re.findall(r"[A-Z]+(?![a-z])|[A-Z]?[a-z]+|\d+", name)]


def scope_names(node):
    """Names bound in node's own scope: arguments, assignment targets, and
    the names of the definitions directly inside it."""
    names, stack = set(), list(ast.iter_child_nodes(node))
    while stack:
        child = stack.pop()
        if isinstance(child, DEFINITIONS):
            names.add(child.name)
            continue
        if isinstance(child, ast.arg):
            names.add(child.arg)
        elif isinstance(child, ast.Name) and isinstance(child.ctx, ast.Store):
            names.add(child.id)
        elif isinstance(child, ast.Attribute) and isinstance(child.ctx, ast.Store):
            names.add(child.attr)
        stack.extend(ast.iter_child_nodes(child))
    return names


def scopes(node, prefix=""):
    """{qualified name: node} for the module and every definition in it."""
    found, stack = {prefix: node}, list(ast.iter_child_nodes(node))
    while stack:
        child = stack.pop()
        if isinstance(child, DEFINITIONS):
            found.update(scopes(child, f"{prefix}.{child.name}"))
        else:
            stack.extend(ast.iter_child_nodes(child))
    return found


def introduced_names(workspace, changed):
    """Names each changed .py scope binds that its version before the diff did
    not, plus the stem of each new module."""
    names = set()
    for path, data in changed.items():
        if not path.endswith(".py") or data is None:
            continue
        before = workspace.checkout / path
        old = scopes(parse_python(path, before.read_text(encoding="utf-8"))) if before.is_file() else {}
        if not old:
            names.add(PurePosixPath(path).stem)
        for qualname, node in scopes(parse_python(path, data.decode("utf-8"))).items():
            names |= scope_names(node) - (scope_names(old[qualname]) if qualname in old else set())
    return names


def glossary_terms(text):
    return {"_".join(term.lower().replace("-", " ").split()) for term in TERM.findall(text)}


def check_session_tree(answer, workspace):
    changed = apply_diff(workspace.checkout, workspace.diff)
    names = introduced_names(workspace, changed)
    before = (workspace.checkout / "CONTEXT.md").read_text(encoding="utf-8")
    after = (changed.get("CONTEXT.md") or b"").decode("utf-8") if "CONTEXT.md" in changed else before
    new_terms = sorted(glossary_terms(after) - glossary_terms(before))
    snake_names = {"_".join(identifier_words(name)) for name in names}
    failures = []
    if not new_terms:
        failures.append("CONTEXT.md gains no term")
    elif not any(term in name for term in new_terms for name in snake_names):
        failures.append(f"no new name carries a term CONTEXT.md gains; new terms are {new_terms}")
    for name in sorted(names):
        failures += [f"new name {name} uses the word {word}" for word in identifier_words(name) if TREE_AVOIDED.fullmatch(word)]
    return failures


def check_paused_reason(answer, workspace):
    changed = apply_diff(workspace.checkout, workspace.diff)
    failures = [f"the diff writes {path}" for path in sorted(changed) if GLOSSARY_PATH.fullmatch(path)]
    before = (workspace.checkout / "hermes_cli/cron.py").read_text(encoding="utf-8").count("paused_reason")
    after = (changed.get("hermes_cli/cron.py") or b"").decode("utf-8").count("paused_reason")
    if "hermes_cli/cron.py" not in changed or after <= before:
        failures.append("hermes_cli/cron.py gains no use of paused_reason")
    return failures


CHECKS = {
    "order-line-items": check_amendment,
    "session-tree": check_session_tree,
    "cron-paused-reason": check_paused_reason,
}
