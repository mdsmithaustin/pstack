"""Converge types within one context: merge a true duplicate, keep two contexts' types apart."""
import ast
import re

from shared import apply_diff, parse_files, parse_python

BILLING = {"payer_name", "balance_cents"}
SIGN_IN = {"email", "password_hash", "mfa_enabled"}
CUSTOMER = {"id", "name", "email"}


def final_tree(answer, project):
    tree = {**project, **parse_files(answer)}
    return {path: body for path, body in tree.items() if body.strip()}


def class_fields(tree_files):
    """(path, class name, field names) for every class in the tree. Fields are
    annotated class attributes and attributes assigned on self."""
    found = []
    for path, body in tree_files.items():
        if not path.endswith(".py"):
            continue
        for node in ast.walk(parse_python(path, body)):
            if not isinstance(node, ast.ClassDef):
                continue
            fields = set()
            for statement in node.body:
                if isinstance(statement, ast.AnnAssign) and isinstance(statement.target, ast.Name):
                    fields.add(statement.target.id)
            for child in ast.walk(node):
                if isinstance(child, ast.Attribute) and isinstance(child.ctx, ast.Store) and isinstance(child.value, ast.Name) and child.value.id == "self":
                    fields.add(child.attr)
            found.append((path, node.name, fields))
    return found


def check_separate(answer, project):
    classes = class_fields(final_tree(answer, project))
    failures = [
        f"{path}:{name} mixes billing fields with sign-in fields"
        for path, name, fields in classes
        if fields & BILLING and fields & SIGN_IN
    ]
    if not any(BILLING <= fields and not fields & SIGN_IN for _, _, fields in classes):
        failures.append("no type keeps the billing account's fields")
    if not any(SIGN_IN <= fields and not fields & BILLING for _, _, fields in classes):
        failures.append("no type keeps the sign-in account's fields")
    return failures


def check_merged(answer, project):
    holders = sorted(f"{path}:{name}" for path, name, fields in class_fields(final_tree(answer, project)) if CUSTOMER <= fields)
    if len(holders) != 1:
        return [f"{len(holders)} types hold a customer's id, name, and email: {', '.join(holders)}"]
    return []


# The value each omnigent harness-family lookup returns. A function or table
# holding values from two of these merges two concepts that share a word.
FAMILY_SPACES = {
    "provider": ({"anthropic", "openai"}, {"ANTHROPIC_FAMILY", "OPENAI_FAMILY"}),
    "routing": ({"gpt"}, set()),
    "skill-vendor": ({"cursor", "devin"}, {"_SKILL_FAMILIES"}),
}
FAMILY_FIELD_WORDS = {"family", "provider", "routing", "vendor"}
ROUTING_MODULE = "omnigent/runner/subagent_routing.py"


def touched_python(workspace):
    """{path: (source before, source after)} for each Python file the diff
    touches under omnigent/, None where the file does not exist."""
    touched = {}
    for path, data in apply_diff(workspace.checkout, workspace.diff).items():
        if path.startswith("omnigent/") and path.endswith(".py"):
            before = workspace.checkout / path
            touched[path] = (before.read_text(encoding="utf-8") if before.is_file() else None,
                             data.decode("utf-8") if data is not None else None)
    return touched


def words(name):
    return {word.lower() for word in re.split(r"_+|(?<=[a-z0-9])(?=[A-Z])", name) if word}


def direct_spaces(node):
    found = set()
    for child in ast.walk(node):
        name = child.id if isinstance(child, ast.Name) else child.attr if isinstance(child, ast.Attribute) else None
        text = child.value if isinstance(child, ast.Constant) and isinstance(child.value, str) else None
        found |= {space for space, (values, names) in FAMILY_SPACES.items() if text in values or name in names}
    return found


def family_holders(path, source):
    """{name: family spaces} for every function and module-level table in the
    file. A holder also takes the spaces of same-module tables it names."""
    tree = parse_python(path, source)
    tables = {}
    for statement in tree.body:
        targets = statement.targets if isinstance(statement, ast.Assign) else [statement.target] if isinstance(statement, ast.AnnAssign) and statement.value else []
        if any(isinstance(node, (ast.Dict, ast.Set)) for node in ast.walk(statement)):
            for target in targets:
                if isinstance(target, ast.Name):
                    tables[target.id] = statement.value
    table_spaces = {name: direct_spaces(value) for name, value in tables.items()}

    def spaces(node):
        named = {child.id for child in ast.walk(node) if isinstance(child, ast.Name)}
        return direct_spaces(node).union(*(table_spaces[name] for name in named & set(table_spaces)))

    holders = {name: spaces(value) for name, value in tables.items()}

    def visit(node, prefix):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                holders[prefix + child.name] = spaces(child)
                visit(child, prefix + child.name + ".")
            elif isinstance(child, ast.ClassDef):
                visit(child, prefix + child.name + ".")

    visit(tree, "")
    return holders


def class_family_fields(path, source):
    """{class name: fields whose words name a family lookup} for every class."""
    found = {}
    for node in ast.walk(parse_python(path, source)):
        if isinstance(node, ast.ClassDef):
            fields = {statement.target.id for statement in node.body if isinstance(statement, ast.AnnAssign) and isinstance(statement.target, ast.Name)}
            fields |= {child.attr for child in ast.walk(node) if isinstance(child, ast.Attribute) and isinstance(child.ctx, ast.Store)
                       and isinstance(child.value, ast.Name) and child.value.id == "self"}
            found[node.name] = {field for field in fields if words(field) & FAMILY_FIELD_WORDS}
    return found


def merged_families(touched):
    """Failures for each function, table, or new class that the diff leaves
    holding values from two family lookups."""
    failures = []
    for path, (before, after) in sorted(touched.items()):
        if after is None:
            continue
        mixed_before = {name for name, spaces in family_holders(path, before).items() if len(spaces) > 1} if before else set()
        for name, spaces in sorted(family_holders(path, after).items()):
            if len(spaces) > 1 and name not in mixed_before:
                failures.append(f"{path}:{name} mixes {', '.join(sorted(spaces))} family values")
        classes_before = class_family_fields(path, before) if before else {}
        for name, fields in sorted(class_family_fields(path, after).items()):
            if len(fields) > 1 and name not in classes_before:
                failures.append(f"{path}:{name} holds fields from more than one family lookup: {', '.join(sorted(fields))}")
    return failures


def check_families_apart(answer, workspace):
    return merged_families(touched_python(workspace))


def check_wrapper_folded(answer, workspace):
    touched = touched_python(workspace)
    failures = merged_families(touched)
    source = touched[ROUTING_MODULE][1] if ROUTING_MODULE in touched else (workspace.checkout / ROUTING_MODULE).read_text(encoding="utf-8")
    if source is not None and any(isinstance(node, ast.FunctionDef) and node.name == "_harness_family" for node in parse_python(ROUTING_MODULE, source).body):
        failures.append(f"{ROUTING_MODULE} still defines _harness_family")
    return failures


CHECKS = {
    "account-types": check_separate,
    "invoice-customers": check_merged,
    "harness-families": check_families_apart,
    "subagent-routing-wrapper": check_wrapper_folded,
}
