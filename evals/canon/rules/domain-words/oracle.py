"""Name new code with the glossary's word, never a word it lists under Avoid."""
import ast
import re
from pathlib import PurePosixPath

from shared import apply_diff, normalized_source, parse_files, parse_python

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


HERMES_AVOIDED = re.compile(r"(chain|thread|conversation|chat|fork|clone|head|latest)(s|es|ed|ing)?")
HERMES_CODE = re.compile(r"hermes_state_\w+\.py|hermes_cli/sessions_cmd\w*\.py")
PARSER = "hermes_cli/subcommands/sessions.py"
READS_JSON_FLAG = re.compile(r"""args\.json\b|getattr\(\s*args\s*,\s*["']json["']""")


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


def changed_python(workspace):
    """[(path, scopes before, scopes after)] for each .py file the diff touches;
    a new file has no scopes before and a deleted one none after."""
    changed = []
    for path, data in sorted(apply_diff(workspace.checkout, workspace.diff).items()):
        if path.endswith(".py"):
            before = workspace.checkout / path
            old = scopes(parse_python(path, before.read_text(encoding="utf-8"))) if before.is_file() else {}
            new = scopes(parse_python(path, data.decode("utf-8"))) if data is not None else {}
            changed.append((path, old, new))
    return changed


def workspace_names(changed):
    """Names each changed scope binds that its version before the diff did not,
    plus the stem of each new module."""
    names = set()
    for path, old, new in changed:
        if new and not old:
            names.add(PurePosixPath(path).stem)
        for qualname, node in new.items():
            names |= scope_names(node) - (scope_names(old[qualname]) if qualname in old else set())
    return names


def check_lineage_usage(answer, workspace):
    changed = changed_python(workspace)
    names = workspace_names(changed)
    failures = []
    if not any(HERMES_CODE.fullmatch(path) for path, _, new in changed if new):
        failures.append("the diff changes no hermes_state_*.py or hermes_cli/sessions_cmd*.py file")
    for name in sorted(names):
        failures += [f"new name {name} uses the word {word}" for word in identifier_words(name) if HERMES_AVOIDED.fullmatch(word)]
    if not any("lineage" in identifier_words(name) for name in names):
        failures.append("no new name uses the word lineage")
    return failures


def check_stats_json(answer, workspace):
    changed = changed_python(workspace)
    failures = [f"{path} no longer defines {qualname.lstrip('.')}"
                for path, old, new in changed for qualname in sorted(old) if qualname and qualname not in new]
    parser = {path: new for path, _, new in changed}.get(PARSER, {}).get("") or parse_python(
        PARSER, (workspace.checkout / PARSER).read_text(encoding="utf-8"))
    if not takes_json_flag(parser, "stats"):
        failures.append("the stats parser takes no --json flag")
    added = [line for block in re.split(r"^diff --git ", workspace.diff, flags=re.MULTILINE)
             if re.match(r"a/hermes_cli/sessions_cmd\w*\.py ", block)
             for line in block.splitlines() if line.startswith("+") and not line.startswith("+++")]
    if not any(READS_JSON_FLAG.search(line) for line in added):
        failures.append("no added line in hermes_cli/sessions_cmd*.py reads args.json")
    return failures


def takes_json_flag(module, action):
    """True when the subparser for action is bound to a name that gets
    add_json_flag or an add_argument("--json")."""
    bound = {target.id for node in ast.walk(module) if isinstance(node, ast.Assign) and is_add_parser(node.value, action)
             for target in node.targets if isinstance(target, ast.Name)}
    for node in ast.walk(module):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Name) and node.func.id == "add_json_flag" and node.args:
            if isinstance(node.args[0], ast.Name) and node.args[0].id in bound:
                return True
        if (isinstance(node.func, ast.Attribute) and node.func.attr == "add_argument"
                and isinstance(node.func.value, ast.Name) and node.func.value.id in bound
                and any(isinstance(arg, ast.Constant) and arg.value == "--json" for arg in node.args)):
            return True
    return False


def is_add_parser(node, action):
    return (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "add_parser"
            and bool(node.args) and isinstance(node.args[0], ast.Constant) and node.args[0].value == action)


CHECKS = {
    "shipment-tracking": check_shipment_words,
    "session-lineage-usage": check_lineage_usage,
    "session-stats-json": check_stats_json,
}
