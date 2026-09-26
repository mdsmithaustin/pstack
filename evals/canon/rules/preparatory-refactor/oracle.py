"""Land the restructure that makes the feature easy before the feature."""
import ast
import csv
import io
import json
import re
from collections import Counter

from shared import apply_diff, functions, is_test_path, parse_commits, parse_python, run_jobs

REPORT_RUNS = (
    ["python3", "report.py", "data/sample-orders.json", "--since", "2026-09-01"],
    ["python3", "report.py", "data/sample-orders.json", "--since", "2026-09-01", "--region", "eu"],
)
CSV_RUN = ["python3", "report.py", "data/sample-orders.json", "--since", "2026-09-01", "--format", "csv"]
SUITE_RUN = ["python3", "-m", "unittest", "-q"]


def calls(node, predicate):
    return any(isinstance(child, ast.Call) and predicate(child.func) for child in ast.walk(node))


def sorts(node):
    return any(
        isinstance(child, ast.Call)
        and any(keyword.arg == "key" for keyword in child.keywords)
        and ((isinstance(child.func, ast.Name) and child.func.id == "sorted") or (isinstance(child.func, ast.Attribute) and child.func.attr == "sort"))
        for child in ast.walk(node)
    )


def writes_json(node):
    return calls(node, lambda func: (isinstance(func, ast.Attribute) and func.attr in {"dumps", "dump"}) or (isinstance(func, ast.Name) and func.id == "dumps"))


def picks_format(node):
    for child in ast.walk(node):
        if isinstance(child, ast.Constant) and isinstance(child.value, str) and child.value.lower() in {"csv", "json"}:
            return True
        if isinstance(child, ast.Name) and child.id == "csv":
            return True
    return False


def tangled(files, serializes):
    names = []
    for path, body in files.items():
        if not path.endswith(".py") or is_test_path(path):
            continue
        for node in functions(parse_python(path, body)):
            if sorts(node) and serializes(node):
                names.append(f"{path}:{node.name}")
    return names


def csv_lists(stdout, order_ids):
    body = [row for row in csv.reader(io.StringIO(stdout)) if row][1:]
    return len(body) == len(order_ids) and all(sum(order_id in row for row in body) == 1 for order_id in order_ids)


def check_preparatory(answer, project):
    commits = parse_commits(answer)
    if len(commits) < 2:
        return [f"answer has {len(commits)} commit(s); the restructure is not its own commit"]
    states = [project]
    for _, files in commits:
        states.append({**states[-1], **files})
    trees = {f"state-{index}": state for index, state in enumerate(states)}
    jobs = []
    for name in trees:
        jobs.extend({"tree": name, "argv": argv} for argv in (*REPORT_RUNS, CSV_RUN, SUITE_RUN))
    results = run_jobs(trees, jobs)
    per_state = [results[index * 4:(index + 1) * 4] for index in range(len(states))]
    golden = [run["stdout"] for run in per_state[0][:2]]
    order_ids = [row["order_id"] for row in json.loads(golden[0])["rows"]]

    def json_kept(index):
        return all(run["rc"] == 0 for run in per_state[index][:2]) and [run["stdout"] for run in per_state[index][:2]] == golden

    def csv_works(index):
        run = per_state[index][2]
        return run["rc"] == 0 and csv_lists(run["stdout"], order_ids)

    feature = next((index for index in range(1, len(states)) if csv_works(index)), None)
    if feature is None:
        return ["no commit makes --format csv print the report rows"]
    failures = []
    last = len(states) - 1
    if not json_kept(last):
        failures.append("final JSON output differs from the original report")
    if per_state[last][3]["rc"] != 0:
        failures.append("final suite fails")
    for name in tangled(states[last], picks_format):
        failures.append(f"{name} both sorts rows and chooses the output format")
    before = feature - 1
    if before == 0:
        failures.append(f"commit 1 ({commits[0][0]!r}) adds the feature; no restructure lands first")
        return failures
    if states[before]["report.py"] == project["report.py"] and not any(
        path.endswith(".py") and not is_test_path(path) and path not in project for path in states[before]
    ):
        failures.append("commits before the feature leave report.py's structure unchanged")
    if not json_kept(before):
        failures.append("JSON output changes before the feature commit")
    if per_state[before][3]["rc"] != 0:
        failures.append("suite fails before the feature commit")
    for name in tangled(states[before], writes_json):
        failures.append(f"before the feature commit {name} still both sorts rows and writes JSON")
    return failures


# omnigent's PII guardrail spells its category keys out in four literals: the
# pattern dict, the label dict, and the pii_types enum and default in
# POLICY_REGISTRY. A new category is one edit once they come from one table.
SAFETY = "omnigent/policies/builtins/safety.py"
PII_KEYS = {"ssn", "credit_card", "email", "phone"}
IP_KEY = re.compile(r"ip(v4)?(_address(es)?)?", re.IGNORECASE)


def string_items(node):
    items = node.keys if isinstance(node, ast.Dict) else node.elts if isinstance(node, (ast.List, ast.Tuple, ast.Set)) else None
    if items and all(isinstance(item, ast.Constant) and isinstance(item.value, str) for item in items):
        return {item.value for item in items}
    return set()


def category_lists(tree):
    """Each literal that lists every PII category key, named by the
    assignment it sits under and the dict key it is the value of."""
    found = []

    def visit(node, owner, key):
        if PII_KEYS <= string_items(node):
            found.append(" ".join(part for part in (owner, key) if part))
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            owner, key = ast.unparse(node.targets[0] if isinstance(node, ast.Assign) else node.target), None
        if isinstance(node, ast.Dict):
            for item_key, value in zip(node.keys, node.values):
                named = item_key.value if isinstance(item_key, ast.Constant) and isinstance(item_key.value, str) else key
                visit(value, owner, named)
            return
        for child in ast.iter_child_nodes(node):
            visit(child, owner, key)

    visit(tree, None, None)
    return found


def string_constants(tree):
    return Counter(node.value for node in ast.walk(tree) if isinstance(node, ast.Constant) and isinstance(node.value, str))


def schema_keys(tree, field):
    keys = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            for item_key, value in zip(node.keys, node.values):
                if isinstance(item_key, ast.Constant) and item_key.value == field:
                    keys |= {inner.value for child in ast.walk(value) if isinstance(child, ast.Dict)
                             for inner in child.keys if isinstance(inner, ast.Constant)}
    return keys


def check_pii_category(answer, workspace):
    changed = apply_diff(workspace.checkout, workspace.diff)
    paths = sorted({SAFETY} | {path for path in changed if path.startswith("omnigent/") and path.endswith(".py") and changed[path] is not None})
    failures = []
    added = False
    for path in paths:
        before = workspace.checkout / path
        old = before.read_text(encoding="utf-8") if before.is_file() else ""
        new = changed[path].decode("utf-8") if path in changed else old
        tree = parse_python(path, new)
        added |= any(IP_KEY.fullmatch(value) for value in string_constants(tree) - string_constants(parse_python(path, old)))
        lists = category_lists(tree)
        if len(lists) > 1:
            failures.append(f"{path} lists the PII category keys by hand in {len(lists)} places: {', '.join(lists)}")
        if path == SAFETY:
            failures += [f"{SAFETY} drops the pii_types {key} from the policy's params_schema"
                         for key in ("enum", "default") if key not in schema_keys(tree, "pii_types")]
    if not added:
        failures.insert(0, "no PII category key for IP addresses is added")
    return failures


CHECKS = {"csv-export": check_preparatory, "pii-ip-address": check_pii_category}
