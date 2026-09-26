"""Add money through one type that refuses mixed currencies."""
import json

from shared import parse_files, parse_python, run_jobs

PROBE = r"""
import json, numbers, re
from checkout.cart import Cart, CartLine, Price
from checkout.summary import checkout_summary


def subtotal_of(summary):
    if isinstance(summary, dict):
        keys = [key for key in summary if "subtotal" in str(key).lower()]
        return (True, summary[keys[0]]) if keys else (False, None)
    names = [name for name in dir(summary) if "subtotal" in name.lower() and not name.startswith("_")]
    return (True, getattr(summary, names[0])) if names else (False, None)


def single_amount(value):
    if isinstance(value, bool):
        return False
    if isinstance(value, numbers.Number):
        return True
    if isinstance(value, str):
        return len(re.findall(r"\d+(?:[.,]\d+)?", value)) == 1
    fields = value if isinstance(value, dict) else getattr(value, "__dict__", {})
    return isinstance(fields.get("currency"), str)


def probe(cart):
    try:
        found, value = subtotal_of(checkout_summary(cart))
    except Exception as exc:
        return {"raised": f"{type(exc).__name__}: {exc}"}
    return {"found": found, "single": found and single_amount(value), "text": repr(value)}


eur = Cart((CartLine("BOOK", "nordlicht-books", Price(1299, "EUR"), 2), CartLine("MAP", "nordlicht-books", Price(1999, "EUR"), 1)))
mixed = Cart((CartLine("BOOK", "nordlicht-books", Price(1299, "EUR"), 1), CartLine("TEE", "lone-star-tees", Price(2500, "USD"), 1)))
print(json.dumps({"eur": probe(eur), "mixed": probe(mixed)}))
"""


def check_money(answer, project):
    tree = {**project, **parse_files(answer)}
    for path, body in tree.items():
        if path.endswith(".py"):
            parse_python(path, body)
    result = run_jobs({"shop": tree}, [{"tree": "shop", "argv": ["python3", "-c", PROBE]}])[0]
    if result["rc"] != 0:
        return [f"the summary probe crashed: {result['stderr'].strip().splitlines()[-1:]}"]
    outcome = json.loads(result["stdout"])
    eur, mixed = outcome["eur"], outcome["mixed"]
    failures = []
    if "raised" in eur:
        failures.append(f"the summary of a EUR-only cart raises {eur['raised']}")
    elif not eur["found"]:
        failures.append("the summary has no subtotal")
    elif "4597" not in eur["text"] and "45.97" not in eur["text"]:
        failures.append(f"the subtotal of a EUR-only cart is {eur['text']}, expected 45.97 EUR")
    if "raised" not in mixed and mixed["found"] and mixed["single"]:
        failures.append(f"a cart with a EUR line and a USD line gets one amount as its subtotal: {mixed['text']}")
    return failures


CHECKS = {"marketplace-subtotal": check_money}
