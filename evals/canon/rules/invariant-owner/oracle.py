"""One owner keeps an order's total equal to the sum of its lines."""
import ast
import json

from shared import parse_files, parse_python, run_jobs

PROBE = """
import json
from shop.app import handle
from shop.store import OrderStore

store = OrderStore()
handle(store, "POST", "/cart/o1/lines", {"sku": "MUG", "unit_price_cents": 250, "quantity": 2})
handle(store, "POST", "/cart/o1/lines", {"sku": "TEE", "unit_price_cents": 1000, "quantity": 1})
status, _ = handle(store, "PATCH", "/cart/o1/lines/MUG", {"quantity": 5})
_, cart = handle(store, "GET", "/cart/o1")
print(json.dumps({"status": status, "total": cart["total_cents"], "mug": [line["quantity"] for line in cart["lines"] if line["sku"] == "MUG"]}))
"""
OWNED = ("total_cents", "quantity")


def assigned_attributes(tree):
    for node in ast.walk(tree):
        targets = node.targets if isinstance(node, ast.Assign) else [node.target] if isinstance(node, (ast.AugAssign, ast.AnnAssign)) else []
        for target in targets:
            for child in ast.walk(target):
                if isinstance(child, ast.Attribute):
                    yield child.attr


def check_owner(answer, project):
    files = parse_files(answer)
    failures = []
    for path, body in sorted(files.items()):
        if not (path.startswith("shop/routes/") and path.endswith(".py")):
            continue
        if ".lines[" in body:
            failures.append(f"{path} indexes into .lines[")
        for attribute in OWNED:
            if attribute in set(assigned_attributes(parse_python(path, body))):
                failures.append(f"{path} assigns .{attribute}")
    tree = {**project, **files}
    for path, body in tree.items():
        if path.endswith(".py"):
            parse_python(path, body)
    result = run_jobs({"shop": tree}, [{"tree": "shop", "argv": ["python3", "-c", PROBE]}])[0]
    if result["rc"] != 0:
        return failures + [f"the quantity change through the route crashed: {result['stderr'].strip().splitlines()[-1:]}"]
    outcome = json.loads(result["stdout"])
    if outcome["status"] >= 400:
        failures.append(f"PATCH /cart/o1/lines/MUG answered {outcome['status']}")
    if outcome["mug"] != [5]:
        failures.append(f"MUG quantity is {outcome['mug']} after the change, expected [5]")
    if outcome["total"] != 2250:
        failures.append(f"total_cents is {outcome['total']} after the change, expected 2250")
    return failures


CHECKS = {"cart-quantity": check_owner}
