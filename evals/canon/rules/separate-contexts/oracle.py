"""Keep one type per context when one word names two concepts; merge a true duplicate."""
import ast

from shared import parse_files, parse_python

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


CHECKS = {"account-types": check_separate, "invoice-customers": check_merged}
