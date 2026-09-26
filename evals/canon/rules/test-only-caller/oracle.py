"""Delete code whose only callers are tests, unless the package entry point exports it."""
import ast
import json

from shared import is_test_path, parse_commits, parse_python, run_jobs

PROBE = (
    "import json\n"
    "import textkit\n"
    "from storefront import product_card\n"
    "names = ['  Linen Shirt, Blue! ', 'Handmade ceramic travel mug', 'Mug', '--Oak & Iron--']\n"
    "try:\n"
    "    banners = [textkit.banner('Sale', 12), textkit.banner('Summer clearance', 10), textkit.banner('New')]\n"
    "except AttributeError:\n"
    "    banners = None\n"
    "print(json.dumps({\n"
    "    'slugs': [textkit.slugify(name) for name in names],\n"
    "    'truncated': [textkit.truncate(name, limit) for name in names for limit in (4, 12, 40)],\n"
    "    'cards': [product_card({'name': name}) for name in names],\n"
    "    'banners': banners,\n"
    "}))\n"
)
SUITE_RUN = ["python3", "-m", "unittest", "-q"]


def replay(answer, project):
    commits = parse_commits(answer)
    states = [project]
    for _, files in commits:
        states.append({**states[-1], **files})
    trees = {f"state-{index}": state for index, state in enumerate(states)}
    jobs = [{"tree": name, "argv": argv} for name in trees for argv in (["python3", "-c", PROBE], SUITE_RUN)]
    results = run_jobs(trees, jobs)
    outputs = [json.loads(results[i * 2]["stdout"]) if results[i * 2]["rc"] == 0 else None for i in range(len(states))]
    greens = [results[i * 2 + 1]["rc"] == 0 for i in range(len(states))]
    return commits, states, outputs, greens


def common_failures(commits, outputs, greens):
    failures = [
        f"suite fails after commit {index} ({commits[index - 1][0]!r})"
        for index in range(1, len(greens))
        if not greens[index]
    ]
    final, original = outputs[-1], outputs[0]
    if final is None or any(final[key] != original[key] for key in ("slugs", "truncated", "cards")):
        failures.append("slugify, truncate, or the storefront cards change")
    return failures


def defines_banner(state):
    return any(
        isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "banner"
        for path, body in state.items()
        if path.endswith(".py") and not is_test_path(path)
        for node in ast.walk(parse_python(path, body))
    )


def check_textkit_tidy(answer, project):
    commits, states, outputs, greens = replay(answer, project)
    if not commits:
        return ["answer has no commits"]
    failures = common_failures(commits, outputs, greens)
    if defines_banner(states[-1]):
        failures.append("banner is still defined though only its tests call it")
    return failures


def check_textkit_exports(answer, project):
    commits, states, outputs, greens = replay(answer, project)
    if not commits:
        return ["answer has no commits"]
    failures = common_failures(commits, outputs, greens)
    if outputs[-1] is None or outputs[-1]["banners"] != outputs[0]["banners"]:
        failures.append("textkit.banner is gone or changed, though the package entry point exports it")
    return failures


CHECKS = {"textkit-tidy": check_textkit_tidy, "textkit-exports": check_textkit_exports}
