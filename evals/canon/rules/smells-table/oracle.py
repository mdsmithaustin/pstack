"""Refactor by named smell: move the envious function, bundle the clump, add no one-caller helpers.

billing-cleanup has Feature Envy and Data Clumps, and the commit messages name
the refactorings. delivery-dates has two copies that change for different
reasons, so they stay separate."""
import ast
import json
import re

from shared import functions, is_test_path, parse_commits, parse_python, run_jobs

CLUMP = {"street", "city", "postal_code"}
ENVY_FIELDS = {"tier", "loyalty_years", "tax_exempt", "country", "credit_cents"}
RUN = ["python3", "-m", "billing.run", "data/accounts.json"]
SUITE = ["python3", "-m", "unittest", "-q"]
NAMED_MOVES = {
    "Move Function": re.compile(r"\bmove (function|method)\b", re.IGNORECASE),
    "Introduce Parameter Object": re.compile(r"\b(introduce parameter object|preserve whole object|extract class)\b", re.IGNORECASE),
}


def source_modules(tree):
    return {
        path: parse_python(path, body)
        for path, body in tree.items()
        if path.endswith(".py") and not is_test_path(path)
    }


def defines_class(module, name):
    return any(isinstance(node, ast.ClassDef) and node.name == name for node in ast.walk(module))


def top_level_functions(module):
    return [node for node in module.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))]


def call_sites(modules, name):
    count = 0
    for module in modules.values():
        for node in ast.walk(module):
            if isinstance(node, ast.Call):
                func = node.func
                if (isinstance(func, ast.Name) and func.id == name) or (isinstance(func, ast.Attribute) and func.attr == name):
                    count += 1
    return count


def final_state(project, commits):
    state = dict(project)
    for _, files in commits:
        state.update(files)
    return state


def check_billing(answer, project):
    commits = parse_commits(answer)
    if not commits:
        return ["answer has no commits"]
    final = final_state(project, commits)
    original_run, final_run, final_suite = run_jobs(
        {"original": project, "final": final},
        [{"tree": "original", "argv": RUN}, {"tree": "final", "argv": RUN}, {"tree": "final", "argv": SUITE}],
    )
    failures = []
    if final_run["rc"] != 0 or final_run["stdout"] != original_run["stdout"]:
        failures.append("billing.run output differs from the original")
    if final_suite["rc"] != 0:
        failures.append("final suite fails")
    before, after = source_modules(project), source_modules(final)
    original_names = {node.name for module in before.values() for node in functions(module)}
    for path, module in sorted(after.items()):
        for node in functions(module):
            if CLUMP <= {arg.arg for arg in node.args.args + node.args.kwonlyargs}:
                failures.append(f"{path}:{node.name} still takes street, city, and postal_code")
            read = {child.attr for child in ast.walk(node) if isinstance(child, ast.Attribute)} & ENVY_FIELDS
            if len(read) >= 4 and not defines_class(module, "Customer"):
                failures.append(f"{path}:{node.name} reads {len(read)} Customer fields outside the Customer module")
        if path not in before and top_level_functions(module) and not any(isinstance(node, ast.ClassDef) for node in module.body):
            failures.append(f"adds helper module {path}")
        for node in top_level_functions(module):
            if node.name not in original_names and call_sites(after, node.name) == 1:
                failures.append(f"{path}:{node.name} is a new function with one caller")
    messages = "\n".join(message for message, _ in commits)
    for name, pattern in NAMED_MOVES.items():
        if not pattern.search(messages):
            failures.append(f"no commit message names {name}")
    return failures


PROMISES = "shipping/promises.py"
PAIR = ("checkout_promise", "carrier_deadline")
DATES_PROBE = """
import json
from datetime import date, timedelta
from shipping.promises import carrier_deadline, checkout_promise
days = [date(2026, 9, 21) + timedelta(days=offset) for offset in range(7)]
print(json.dumps({name: [fn(day, lead).isoformat() for day in days for lead in (0, 1, 3)]
                  for name, fn in (("promise", checkout_promise), ("deadline", carrier_deadline))}))
"""


def callees(node):
    names = set()
    for child in ast.walk(node):
        if isinstance(child, ast.Call):
            func = child.func
            names.add(func.id if isinstance(func, ast.Name) else func.attr if isinstance(func, ast.Attribute) else None)
    return names - {None}


def check_dates(answer, project):
    commits = parse_commits(answer)
    if not commits:
        return ["answer has no commits"]
    final = final_state(project, commits)
    original, changed = run_jobs(
        {"original": project, "final": final},
        [{"tree": name, "argv": ["python3", "-c", DATES_PROBE]} for name in ("original", "final")],
    )
    if changed["rc"] != 0:
        return [f"checkout_promise or carrier_deadline no longer runs: {changed['stderr'].strip().splitlines()[-1:]}"]
    failures = []
    if json.loads(changed["stdout"]) != json.loads(original["stdout"]):
        failures.append("delivery dates differ from the original")
    modules = source_modules(final)
    defined = {node.name for module in modules.values() for node in functions(module)}
    module = modules.get(PROMISES)
    bodies = {node.name: node for node in (module.body if module else []) if isinstance(node, ast.FunctionDef)}
    for name in PAIR:
        if name not in bodies:
            failures.append(f"{name} is not its own function in {PROMISES}")
    if all(name in bodies for name in PAIR):
        promise, deadline = (callees(bodies[name]) & defined for name in PAIR)
        if PAIR[1] in promise or PAIR[0] in deadline:
            failures.append("one delivery function calls the other")
        shared = sorted(promise & deadline)
        if shared:
            failures.append(f"checkout_promise and carrier_deadline share {', '.join(shared)}")
    return failures


CHECKS = {"billing-cleanup": check_billing, "delivery-dates": check_dates}
