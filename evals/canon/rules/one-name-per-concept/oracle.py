"""Keep one name for one concept: never Membership beside Subscription."""
import ast
import re
from collections import Counter
from pathlib import PurePosixPath

from shared import apply_diff, parse_files, parse_python


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


# omnigent calls a session's key and value a label: the table, the API, the docs.
LIST_ROUTE = "omnigent/server/routes/sessions/routes_core.py"
CLIENT = "sdks/python-client/omnigent_client/_sessions.py"
WIRE_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def words(name):
    return {word.lower() for word in re.split(r"_+|(?<=[a-z0-9])(?=[A-Z])", name) if word}


def deprecated(node):
    """A def marked @deprecated, or a parameter default such as
    Query(deprecated=True): an alias kept for removal, not a second name."""
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        for decorator in node.decorator_list:
            target = decorator.func if isinstance(decorator, ast.Call) else decorator
            name = target.id if isinstance(target, ast.Name) else target.attr if isinstance(target, ast.Attribute) else ""
            if name.lower().endswith("deprecated"):
                return True
        return False
    return isinstance(node, ast.Call) and any(
        keyword.arg == "deprecated" and isinstance(keyword.value, ast.Constant) and keyword.value.value is True for keyword in node.keywords
    )


def introduced_names(tree):
    """Every name the code gives something: defs, classes, parameters,
    assignment targets, attributes set on self, and the wire names a client or
    route sends (params["x"] = ..., {"x": ...}, alias="x"). Keyword arguments
    at call sites are left out: they name the callee's parameters, such as
    FastAPI's own tags=."""
    found = Counter()

    def wire(value):
        if isinstance(value, ast.Constant) and isinstance(value.value, str) and WIRE_NAME.match(value.value):
            found[value.value] += 1

    def visit(node):
        if deprecated(node):
            return
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            found[node.name] += 1
        if isinstance(node, ast.arguments):
            positional = node.posonlyargs + node.args
            defaults = [None] * (len(positional) - len(node.defaults)) + node.defaults
            pairs = [*zip(positional, defaults), *zip(node.kwonlyargs, node.kw_defaults), (node.vararg, None), (node.kwarg, None)]
            for arg, default in pairs:
                if arg is not None and not deprecated(default):
                    found[arg.arg] += 1
        elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            found[node.id] += 1
        elif isinstance(node, ast.Attribute) and isinstance(node.ctx, ast.Store) and isinstance(node.value, ast.Name) and node.value.id == "self":
            found[node.attr] += 1
        elif isinstance(node, ast.Subscript) and isinstance(node.ctx, ast.Store):
            wire(node.slice)
        elif isinstance(node, ast.Dict):
            for key in node.keys:
                wire(key)
        elif isinstance(node, ast.keyword) and node.arg == "alias":
            wire(node.value)
        for child in ast.iter_child_nodes(node):
            visit(child)

    visit(tree)
    return found


def new_names(workspace):
    """{path: names the diff introduces} for each Python file it touches: a
    name counts when the file names it more times after the diff than before."""
    added = {}
    for path, data in apply_diff(workspace.checkout, workspace.diff).items():
        if not path.endswith(".py") or data is None:
            continue
        before = workspace.checkout / path
        old = introduced_names(parse_python(path, before.read_text(encoding="utf-8"))) if before.is_file() else Counter()
        added[path] = set(introduced_names(parse_python(path, data.decode("utf-8"))) - old)
    return added


def check_label_filter(answer, workspace):
    added = new_names(workspace)
    failures = []
    for path, names in sorted(added.items()):
        tagged = sorted(name for name in names if words(name) & {"tag", "tags"})
        if tagged:
            failures.append(f"{path} adds tag names beside the code's labels: {', '.join(tagged)}")
    failures += [f"{path} adds no name that says label" for path in (LIST_ROUTE, CLIENT)
                 if not any(words(name) & {"label", "labels"} for name in added.get(path, ()))]
    return failures


CHECKS = {"billing-pause": check_one_name, "sessions-by-tag": check_label_filter, "sessions-by-label": check_label_filter}
