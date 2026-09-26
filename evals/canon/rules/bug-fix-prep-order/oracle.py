"""Refactor (green), failing repro (red), fix (green), and refactor only when it
makes the fix commit smaller."""
import ast
import difflib
import json

from shared import functions, is_test_path, parse_commits, parse_python, run_jobs

SUITE_RUN = ["python3", "-m", "unittest", "-q"]

ITEMS = [
    {"sku": "MUG", "price_cents": 1500, "member_price_cents": 1200, "qty": 2},
    {"sku": "TEE", "price_cents": 2500, "qty": 1},
]
BASKETS = [(member, percent) for member in (False, True) for percent in (None, 10, 25)]
DISCOUNT_PROBE = (
    "import json\n"
    "from cart import cart_summary\n"
    "from checkout import amount_due\n"
    f"items = {ITEMS!r}\n"
    "out = []\n"
    f"for member, percent in {BASKETS!r}:\n"
    "    coupon = None if percent is None else {'code': 'X', 'percent': percent}\n"
    "    out.append([cart_summary([dict(i) for i in items], member=member, coupon=coupon)['total_cents'],\n"
    "                amount_due({'id': 'c-9', 'member': member}, [dict(i) for i in items], coupon=coupon)])\n"
    "print(json.dumps(out))\n"
)
DISCOUNT_SITES = {"member_price_cents", "percent"}

PAGE_PROBE = (
    "import json\n"
    "from pagination import page_count, page_slice\n"
    "from orders_view import orders_page\n"
    "counts = [page_count(total, 20) for total in (1, 20, 21, 40, 45, 60)]\n"
    "print(json.dumps([counts, page_slice(list(range(45)), 3, 20), orders_page(list(range(40)), 2)['pages']]))\n"
)
PAGES_FIXED = [[1, 1, 2, 2, 3, 3], [40, 41, 42, 43, 44], 2]
SMALL_FIX_LINES = 2


def unit_price(item, member, percent):
    price = item["member_price_cents"] if member and item.get("member_price_cents") is not None else item["price_cents"]
    return price if percent is None else price * (100 - percent) // 100


FIXED = [[sum(unit_price(item, member, percent) * item["qty"] for item in ITEMS)] * 2 for member, percent in BASKETS]


def replay(project, commits, probe):
    states = [project]
    for _, files in commits:
        states.append({**states[-1], **files})
    trees = {f"state-{index}": state for index, state in enumerate(states)}
    jobs = [{"tree": name, "argv": argv} for name in trees for argv in (["python3", "-c", probe], SUITE_RUN)]
    results = run_jobs(trees, jobs)
    outputs = [json.loads(results[i * 2]["stdout"]) if results[i * 2]["rc"] == 0 else None for i in range(len(states))]
    greens = [results[i * 2 + 1]["rc"] == 0 for i in range(len(states))]
    return states, outputs, greens


def source(state):
    return {path: body for path, body in state.items() if path.endswith(".py") and not is_test_path(path)}


def touches_tests(before, after):
    return any(is_test_path(path) and before.get(path) != body for path, body in after.items() if path.endswith(".py"))


def discount_sites(state):
    return sum(
        any(isinstance(child, ast.Constant) and child.value in DISCOUNT_SITES for child in ast.walk(node))
        for path, body in source(state).items()
        for node in functions(parse_python(path, body))
    )


def removed_lines(before, after):
    old, new = source(before), source(after)
    return sum(
        1
        for path, body in old.items()
        for line in difflib.ndiff(body.splitlines(), new.get(path, "").splitlines())
        if line.startswith("- ") and line[2:].strip()
    )


def check_member_coupon(answer, project):
    commits = parse_commits(answer)
    if not commits:
        return ["answer has no commits"]
    states, outputs, greens = replay(project, commits, DISCOUNT_PROBE)
    failures = []
    last = len(states) - 1
    if outputs[last] != FIXED:
        failures.append("final totals still take the coupon off twice, or change another total")
    if not greens[last]:
        failures.append("final suite fails")
    fix = next((index for index in range(1, len(states)) if outputs[index] == FIXED), None)
    if fix is None:
        return failures
    before = fix - 1
    sites = discount_sites(states[before])
    if sites > 1:
        failures.append(f"the discount logic is still in {sites} functions when the fix lands")
    merge = next((index for index in range(1, fix) if discount_sites(states[index]) <= 1), None)
    if greens[before]:
        failures.append("the suite is green right before the fix; no failing repro lands first")
    elif before != merge and not touches_tests(states[before - 1], states[before]):
        failures.append("the commit before the fix adds no failing repro")
    if merge is not None:
        message = commits[merge - 1][0]
        if not greens[merge] and touches_tests(states[merge - 1], states[merge]):
            failures.append(f"commit {merge} ({message!r}) lands the refactor and the failing repro together")
        elif outputs[merge] != outputs[0] or not greens[merge]:
            failures.append(f"commit {merge} ({message!r}) refactors but changes totals or leaves the suite red")
    return failures


def check_orders_pagination(answer, project):
    commits = parse_commits(answer)
    if not commits:
        return ["answer has no commits"]
    states, outputs, greens = replay(project, commits, PAGE_PROBE)
    failures = []
    last = len(states) - 1
    if outputs[last] != PAGES_FIXED:
        failures.append("final paging still shows an empty last page, or changes another page")
    if not greens[last]:
        failures.append("final suite fails")
    changing = [index for index in range(1, len(states)) if source(states[index]) != source(states[index - 1])]
    for index in changing:
        message = commits[index - 1][0]
        if outputs[index] == outputs[index - 1]:
            failures.append(f"commit {index} ({message!r}) changes code without changing paging; a refactor ships beside a one-line fix")
        elif removed_lines(states[index - 1], states[index]) > SMALL_FIX_LINES:
            failures.append(f"commit {index} ({message!r}) restructures the code inside the fix")
    return failures


CHECKS = {"member-coupon": check_member_coupon, "orders-pagination": check_orders_pagination}
