"""Land the restructure that makes the feature easy before the feature."""
import ast
import csv
import io
import json

from shared import functions, is_test_path, parse_commits, parse_python, run_jobs

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


CHECKS = {"csv-export": check_preparatory}
