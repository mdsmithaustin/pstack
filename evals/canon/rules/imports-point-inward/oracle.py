"""Point imports inward: the invoice policy imports no adapter, driver, or framework."""
import ast
import json
from decimal import Decimal
from pathlib import PurePosixPath

from shared import is_test_path, parse_files, parse_python, run_jobs

POLICY = "billing.invoices"
ADAPTERS = ("billing.store", "billing.service", "billing.reminders")
OUTSIDE = {
    "sqlite3", "os", "io", "pathlib", "shelve", "dbm", "socket", "subprocess", "importlib",
    "http", "urllib", "requests", "httpx", "flask", "django", "fastapi", "starlette",
    "sqlalchemy", "psycopg", "psycopg2", "pymysql", "peewee",
}
STATEMENT_PROBE = """
import json, os
from datetime import date
os.environ["BILLING_DB"] = "/tmp/billing.sqlite3"
from billing import service, store
store.init_db()
with store.connect() as conn:
    conn.executemany("insert into customers (id, flagged) values (?, ?)", [("c1", 0), ("c2", 1)])
    conn.executemany(
        "insert into invoices (number, customer_id, amount, paid, due) values (?, ?, ?, ?, ?)",
        [
            ("INV-1", "c1", "1000.00", "0.00", "2026-08-01"),
            ("INV-2", "c2", "1000.00", "0.00", "2026-08-01"),
            ("INV-3", "c1", "500.00", "100.00", "2026-09-10"),
            ("INV-4", "c1", "250.00", "0.00", "2026-06-01"),
        ],
    )
today = date(2026, 9, 24)
print(json.dumps({number: str(service.statement(number, today)["amount_due"]) for number in ("INV-1", "INV-2", "INV-3", "INV-4")}))
"""
EXPECTED = {"INV-1": "1020.00", "INV-2": "1000.00", "INV-3": "400.00", "INV-4": "255.00"}


def module_name(path):
    parts = list(PurePosixPath(path).with_suffix("").parts)
    return ".".join(parts[:-1] if parts[-1] == "__init__" else parts)


def imported(name, node):
    """Every module name an import statement in module `name` can bind."""
    if isinstance(node, ast.Import):
        return [alias.name for alias in node.names]
    base = node.module or ""
    if node.level:
        package = name.split(".")[: len(name.split(".")) - node.level]
        base = ".".join(package + ([base] if base else []))
    return [base] + [f"{base}.{alias.name}" for alias in node.names]


def import_graph(tree):
    graph = {}
    for path, body in tree.items():
        if path.endswith(".py") and not is_test_path(path):
            name = module_name(path)
            graph[name] = [
                imported(name, node)
                for node in ast.walk(parse_python(path, body))
                if isinstance(node, (ast.Import, ast.ImportFrom))
            ]
    return graph


def check_inward(answer, project):
    files = parse_files(answer)
    if not files:
        return ["answer changes no file"]
    tree = {**project, **files}
    graph = import_graph(tree)
    failures = []
    seen, queue = set(), [POLICY]
    while queue:
        name = queue.pop()
        if name in seen or name not in graph:
            continue
        seen.add(name)
        for targets in graph[name]:
            leaks = [target for target in targets if target in ADAPTERS or target.split(".")[0] in OUTSIDE]
            if leaks:
                failures.append(f"{name} imports {leaks[0]}")
            queue += [target for target in targets if target in graph and target not in leaks]
    [result] = run_jobs({"answer": tree}, [{"tree": "answer", "argv": ["python3", "-c", STATEMENT_PROBE]}])
    if result["rc"] != 0:
        failures.append(f"statements no longer run: {result['stderr'].strip().splitlines()[-1:]}")
        return sorted(set(failures))
    owed = json.loads(result["stdout"])
    if {number: Decimal(value) for number, value in owed.items()} != {number: Decimal(value) for number, value in EXPECTED.items()}:
        failures.append(f"statement amounts are {owed}, expected {EXPECTED}")
    return sorted(set(failures))


CHECKS = {"billing-late-fees": check_inward}
