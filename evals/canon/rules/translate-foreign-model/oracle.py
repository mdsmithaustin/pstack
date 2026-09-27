"""Translate a foreign model in one module at the boundary."""
import ast
import re
from pathlib import PurePosixPath

from shared import is_test_path, parse_files, parse_python

PAYLANE_CODES = ("AUTH_OK", "CAPTURED", "DECLINED", "REFUNDED_PARTIAL")
PAYLANE_CODE = re.compile(r"\b(" + "|".join(PAYLANE_CODES) + r")\b")
DOMAIN_FILES = ("payments/model.py", "payments/orders.py")
DOMAIN_MODULES = ("payments.model", "payments.orders")


def enum_members(body):
    for node in ast.walk(ast.parse(body)):
        if isinstance(node, ast.ClassDef) and node.name == "PaymentStatus":
            members = set()
            for statement in node.body:
                if isinstance(statement, (ast.Assign, ast.AnnAssign)):
                    targets = statement.targets if isinstance(statement, ast.Assign) else [statement.target]
                    for target in targets:
                        if isinstance(target, ast.Name):
                            members.add(target.id)
                    if isinstance(statement.value, ast.Constant) and isinstance(statement.value.value, str):
                        members.add(statement.value.value)
            return members
    return set()


def imported_modules(path, tree):
    package = PurePosixPath(path).parent.parts
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            yield from (alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = package[: len(package) - node.level + 1] if node.level else ()
            prefix = ".".join([*base, *(node.module.split(".") if node.module else [])])
            yield prefix
            yield from (f"{prefix}.{alias.name}" for alias in node.names)


def imports_domain(path, body):
    return any(
        module == domain or module.startswith(domain + ".")
        for module in imported_modules(path, parse_python(path, body))
        for domain in DOMAIN_MODULES
    )


def check_translate(answer, project):
    files = parse_files(answer)
    failures = []
    carriers = sorted(path for path, body in files.items() if not is_test_path(path) and PAYLANE_CODE.search(body))
    if not carriers:
        return ["no module in the answer handles Paylane's status codes"]
    for path in carriers:
        if path in DOMAIN_FILES:
            failures.append(f"Paylane codes appear in domain module {path}")
        elif path.endswith(".py") and not imports_domain(path, files[path]):
            failures.append(f"{path} handles Paylane's codes but imports nothing from payments.model or payments.orders")
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
