"""A commit changes structure or behavior, never both, and structure lands first."""
import ast
import difflib
import json

from shared import functions, is_test_path, normalized_source, parse_commits, parse_python, run_jobs

ORDERS = [
    {"zone": "domestic", "weight_kg": 1, "subtotal_cents": 2500},
    {"zone": "domestic", "weight_kg": 25, "subtotal_cents": 49999, "express": True},
    {"zone": "canada", "weight_kg": 5, "subtotal_cents": 12000},
    {"zone": "canada", "weight_kg": 24, "subtotal_cents": 18000, "express": True},
    {"zone": "international", "weight_kg": 20, "subtotal_cents": 30000},
    {"zone": "international", "weight_kg": 3, "subtotal_cents": 9000, "express": True},
    {"zone": "domestic", "weight_kg": 12, "subtotal_cents": 50000},
    {"zone": "canada", "weight_kg": 2, "subtotal_cents": 80000, "express": True},
    {"zone": "international", "weight_kg": 30, "subtotal_cents": 120000},
    {"zone": "mars", "weight_kg": 1, "subtotal_cents": 100},
]
FREE_FROM = 50000
PROBE = (
    "import json\n"
    "from shipping import calc_shipping\n"
    "out = []\n"
    f"for order in {ORDERS!r}:\n"
    "    try:\n"
    "        out.append(calc_shipping(dict(order)))\n"
    "    except Exception as exc:\n"
    "        out.append(type(exc).__name__)\n"
    "print(json.dumps(out))\n"
)
PROBE_RUN = ["python3", "-c", PROBE]
SUITE_RUN = ["python3", "-m", "unittest", "-q"]
RESTRUCTURE_LINES = 5


def source_lines(state):
    return {path: body.splitlines() for path, body in state.items() if path.endswith(".py") and not is_test_path(path)}


def removed_source_lines(before, after):
    old, new = source_lines(before), source_lines(after)
    removed = 0
    for path, lines in old.items():
        diff = difflib.ndiff(lines, new.get(path, []))
        removed += sum(1 for line in diff if line.startswith("- ") and line[2:].strip())
    return removed


def branch_count(state):
    return sum(
        isinstance(node, ast.If)
        for path, body in state.items()
        if path.endswith(".py") and not is_test_path(path)
        for node in ast.walk(parse_python(path, body))
    )


def test_sources(state):
    return {
        normalized_source(body, node)
        for path, body in state.items()
        if path.endswith(".py") and is_test_path(path)
        for node in functions(parse_python(path, body))
    }


def check_two_hats(answer, project):
    commits = parse_commits(answer)
    if not commits:
        return ["answer has no commits"]
    states = [project]
    for _, files in commits:
        states.append({**states[-1], **files})
    trees = {f"state-{index}": state for index, state in enumerate(states)}
    jobs = [{"tree": name, "argv": argv} for name in trees for argv in (PROBE_RUN, SUITE_RUN)]
    results = run_jobs(trees, jobs)
    probes = [results[index * 2] for index in range(len(states))]
    suites = [results[index * 2 + 1]["rc"] == 0 for index in range(len(states))]
    charges = [run["stdout"] if run["rc"] == 0 else None for run in probes]
    golden = json.loads(charges[0])
    target = json.dumps([0 if isinstance(value, int) and order["subtotal_cents"] >= FREE_FROM else value for order, value in zip(ORDERS, golden)])

    originals = test_sources(project)
    kept = [originals & test_sources(state) for state in states]

    failures = []
    last = len(states) - 1
    if charges[last] is None or json.loads(charges[last]) != json.loads(target):
        failures.append("final charges are not free from $500 with every other rate unchanged")
    if not suites[last]:
        failures.append("final suite fails")
    if branch_count(states[last]) >= branch_count(project):
        failures.append("the per-zone rate logic is still copy-pasted")

    structure_first = False
    for index in range(1, len(states)):
        message = commits[index - 1][0]
        restructures = removed_source_lines(states[index - 1], states[index]) >= RESTRUCTURE_LINES
        behaves = charges[index] != charges[index - 1]
        edits_expectation = kept[index] != kept[index - 1]
        if restructures and (behaves or edits_expectation):
            failures.append(f"commit {index} ({message!r}) restructures the code and changes behavior or an existing expected value")
        elif restructures and not suites[index]:
            failures.append(f"commit {index} ({message!r}) restructures but the existing suite is not green")
        elif restructures:
            structure_first = True
        if behaves and not structure_first:
            failures.append(f"commit {index} ({message!r}) changes charges before any structure-only commit lands")
            structure_first = True
    return failures


CHECKS = {"free-shipping": check_two_hats}
