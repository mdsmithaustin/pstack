"""Branch by abstraction ends by deleting the old client and the interface.

http-client-swap spans several PRs, so the plan's last PR deletes httpclient
and any seam the first PR adds. http-client-small fits one PR, so the answer
migrates both callers and deletes httpclient with no seam in between."""
import ast
import re
from pathlib import PurePosixPath

from shared import is_test_path, parse_commits, parse_python, run_jobs

OLD = "app/httpclient.py"
SUITE = ["python3", "-m", "unittest", "-q"]
PLAN = re.compile(r"<plan>(.*?)</plan>", re.DOTALL)
ITEM = re.compile(r"^\s*(\d+)[.)]\s+", re.MULTILINE)
DELETES = re.compile(r"\b(delete[sd]?|deleting|remove[sd]?|removing|drop(s|ped)?)\b", re.IGNORECASE)
OLD_NAME = re.compile(r"httpclient", re.IGNORECASE)


def plan_items(answer):
    match = PLAN.search(answer)
    if not match:
        return []
    starts = list(ITEM.finditer(match.group(1)))
    return [
        match.group(1)[start.end():starts[index + 1].start() if index + 1 < len(starts) else None].strip()
        for index, start in enumerate(starts)
    ]


def apply(state, files):
    state = dict(state)
    for path, body in files.items():
        if body.strip():
            state[path] = body
        else:
            state.pop(path, None)
    return state


def states(project, commits):
    trees = [project]
    for _, files in commits:
        trees.append(apply(trees[-1], files))
    return trees


def new_modules(project, tree):
    return sorted(path for path in tree if path.endswith(".py") and not is_test_path(path) and path not in project)


def imports(tree, module):
    found = []
    for path, body in tree.items():
        if not path.endswith(".py") or is_test_path(path):
            continue
        for node in ast.walk(parse_python(path, body)):
            names = []
            if isinstance(node, ast.ImportFrom):
                names = [node.module or ""] + [f"{node.module}.{alias.name}" for alias in node.names]
            elif isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            if any(name == module or name.startswith(module + ".") for name in names):
                found.append(path)
                break
    return sorted(found)


def seam_names(path, body):
    dotted = path[:-3].replace("/", ".")
    classes = [node.name for node in parse_python(path, body).body if isinstance(node, ast.ClassDef)]
    names = [path, PurePosixPath(path).name, dotted, *classes]
    return re.compile("|".join(rf"(?<![\w./]){re.escape(name)}(?![\w/])" for name in names))


def suite_failures(trees, commits):
    results = run_jobs({f"state-{index}": tree for index, tree in enumerate(trees)}, [{"tree": f"state-{index}", "argv": SUITE} for index in range(1, len(trees))])
    return [f"suite fails after commit {index} ({commits[index - 1][0]!r})" for index, run in enumerate(results, start=1) if run["rc"] != 0]


def check_rollout(answer, project):
    items = plan_items(answer)
    commits = parse_commits(answer)
    if len(items) < 2:
        return [f"plan has {len(items)} PR(s)"]
    if not commits:
        return ["answer has no commits for the first PR"]
    trees = states(project, commits)
    failures = suite_failures(trees, commits)
    last = items[-1]
    if not (DELETES.search(last) and OLD_NAME.search(last)):
        failures.append("final PR in the plan does not delete httpclient")
    for path in new_modules(project, trees[-1]):
        pattern = seam_names(path, trees[-1][path])
        if not any(DELETES.search(item) and pattern.search(item) for item in items):
            failures.append(f"plan never deletes {path}")
    return failures


def check_small(answer, project):
    commits = parse_commits(answer)
    if not commits:
        return ["answer has no commits"]
    trees = states(project, commits)
    final = trees[-1]
    failures = suite_failures(trees, commits)
    if OLD in final:
        failures.append(f"{OLD} still exists")
    for path in imports(final, "app.httpclient"):
        failures.append(f"{path} still imports app.httpclient")
    for path in new_modules(project, final):
        failures.append(f"adds module {path} between the callers and platform_http")
    if not imports(final, "platform_http"):
        failures.append("no module uses platform_http")
    return failures


CHECKS = {"http-client-swap": check_rollout, "http-client-small": check_small}
