"""Translate a foreign model in one module at the boundary."""
import ast
import re

from shared import is_test_path, parse_files, parse_python

PAYLANE_CODES = ("AUTH_OK", "CAPTURED", "DECLINED", "REFUNDED_PARTIAL")
PAYLANE_CODE = re.compile(r"\b(" + "|".join(PAYLANE_CODES) + r")\b")
DOMAIN_FILES = ("payments/model.py", "payments/orders.py")


def enum_members(body):
    for node in ast.walk(ast.parse(body)):
        if isinstance(node, ast.ClassDef) and node.name == "PaymentStatus":
            members = set()
            for statement in node.body:
                if isinstance(statement, ast.Assign):
                    for target in statement.targets:
                        if isinstance(target, ast.Name):
                            members.add(target.id)
                    if isinstance(statement.value, ast.Constant) and isinstance(statement.value.value, str):
                        members.add(statement.value.value)
            return members
    return set()


def check_translate(answer, project):
    files = parse_files(answer)
    failures = []
    carriers = sorted(path for path, body in files.items() if not is_test_path(path) and PAYLANE_CODE.search(body))
    if not carriers:
        return ["no module in the answer handles Paylane's status codes"]
    for path in carriers:
        if path in DOMAIN_FILES:
            failures.append(f"Paylane codes appear in domain module {path}")
    if len(carriers) > 1:
        failures.append(f"Paylane codes spread across {len(carriers)} modules: {', '.join(carriers)}")
    if "payments/model.py" in files:
        foreign = {re.sub(r"[^a-z]", "", code.lower()) for code in PAYLANE_CODES}
        added = enum_members(files["payments/model.py"]) - enum_members(project["payments/model.py"])
        leaked = sorted(member for member in added if re.sub(r"[^a-z]", "", member.lower()) in foreign)
        if leaked:
            failures.append(f"PaymentStatus gains Paylane values: {', '.join(leaked)}")
    for path, body in files.items():
        if path.endswith(".py"):
            parse_python(path, body)
    return failures


CHECKS = {"paylane-webhooks": check_translate}
