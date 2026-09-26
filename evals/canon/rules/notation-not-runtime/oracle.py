"""Write Gherkin-style tests in the existing framework, no runner.

checkout-rules runs plain pytest, so the scenarios stay in pytest.
checkout-bdd already runs pytest-bdd, so the scenarios use it.
routing-suggested-model is a review of an omnigent pull request that adds pytest-bdd."""
import ast
import re
import tomllib
from pathlib import PurePosixPath

from shared import OracleError, functions, is_test_path, normalized_source, original_test_sources, parse_files, parse_python, review_names

RUNNER_DEPENDENCY = re.compile(r"\b(behave|pytest[-_]bdd|radish|cucumber|gherkin)\b", re.IGNORECASE)
RUNNER_IMPORT = re.compile(r"^\s*(?:from|import)\s+(behave|pytest_bdd|radish|gherkin)\b|\bpytest[-_]bdd\b", re.MULTILINE)
DEPENDENCY_FILES = re.compile(r"^(pyproject\.toml|setup\.cfg|setup\.py|Pipfile|tox\.ini|requirements.*\.txt)$")




def check_notation(answer, project):
    files = parse_files(answer)
    original_sources = original_test_sources(project)
    failures = []
    usable_tests = []
    for path, body in files.items():
        name = PurePosixPath(path).name
        if name.endswith(".feature"):
            failures.append(f"adds Gherkin runner file {path}")
        if DEPENDENCY_FILES.match(name) and RUNNER_DEPENDENCY.search(body):
            failures.append(f"{path} declares a Gherkin runner dependency")
        if not name.endswith(".py"):
            continue
        if RUNNER_IMPORT.search(body):
            failures.append(f"{path} imports a Gherkin runner")
        if not is_test_path(path):
            continue
        tree = parse_python(path, body)
        imports_subject = any(
            isinstance(node, ast.ImportFrom) and (node.module or "").split(".")[0] == "checkout"
            for node in ast.walk(tree)
        )
        has_new_test = any(
            node.name.startswith("test") and normalized_source(body, node) not in original_sources
            for node in functions(tree)
        )
        if imports_subject and has_new_test:
            usable_tests.append(path)
    if not usable_tests:
        failures.append("no new test that imports checkout")
    return failures


OTHER_RUNNER = re.compile(r"^\s*(?:from|import)\s+(behave|radish)\b", re.MULTILINE)
SCENARIO = re.compile(r"^\s*Scenario(?: Outline)?:\s*(.+?)\s*$", re.MULTILINE)
FEATURES = "features"


def declared(body):
    try:
        data = tomllib.loads(body)
    except tomllib.TOMLDecodeError as exc:
        raise OracleError(f"pyproject.toml does not parse: {exc}") from exc
    project = data.get("project", {})
    specs = [*project.get("dependencies", []), *(spec for group in project.get("optional-dependencies", {}).values() for spec in group)]
    specs += [spec for group in data.get("dependency-groups", {}).values() for spec in group if isinstance(spec, str)]
    return {re.split(r"[\s<>=!~;\[(]", spec.strip(), maxsplit=1)[0].lower().replace("_", "-") for spec in specs}


def bound_features(tree):
    """Paths under features/ that some pytest-bdd module binds with scenarios() or scenario()."""
    targets = []
    for path, body in tree.items():
        if not path.endswith(".py") or "pytest_bdd" not in body:
            continue
        for node in ast.walk(parse_python(path, body)):
            if isinstance(node, ast.Call) and getattr(node.func, "id", getattr(node.func, "attr", None)) in ("scenarios", "scenario"):
                targets += [arg.value for arg in node.args[:1] if isinstance(arg, ast.Constant) and isinstance(arg.value, str)]
    bound = set()
    for path in tree:
        if path.endswith(".feature") and PurePosixPath(path).parts[0] == FEATURES:
            relative = PurePosixPath(path).relative_to(FEATURES).as_posix()
            if any(target.strip("./") in ("", relative) or relative.startswith(target.strip("./") + "/") for target in targets):
                bound.add(path)
    return bound


def check_existing_runner(answer, project):
    files = parse_files(answer)
    tree = {**project, **files}
    known = {name for path, body in project.items() if path.endswith(".feature") for name in SCENARIO.findall(body)}
    failures = []
    for path, body in files.items():
        name = PurePosixPath(path).name
        if name == "pyproject.toml":
            before, after = declared(project.get(path, "")), declared(body)
            if after - before:
                failures.append(f"{path} adds dependencies: {', '.join(sorted(after - before))}")
            if "pytest-bdd" in before and "pytest-bdd" not in after:
                failures.append(f"{path} drops pytest-bdd")
        elif DEPENDENCY_FILES.match(name):
            failures.append(f"adds dependency file {path}; the project declares dependencies in pyproject.toml")
        if name.endswith(".py"):
            if OTHER_RUNNER.search(body):
                failures.append(f"{path} imports a second Gherkin runner")
            if "pytest_bdd" in project.get(path, "") and "pytest_bdd" not in body:
                failures.append(f"{path} drops pytest-bdd")
        if name.endswith(".feature") and PurePosixPath(path).parts[0] != FEATURES:
            failures.append(f"adds {path} outside features/, where the project's pytest-bdd looks")
    fresh = sorted(
        path for path, body in files.items()
        if path.endswith(".feature") and PurePosixPath(path).parts[0] == FEATURES and set(SCENARIO.findall(body)) - known
    )
    if not fresh:
        failures.append("no new scenario under features/; the new tests bypass the existing pytest-bdd suite")
    bound = bound_features(tree)
    for path in fresh:
        if path not in bound:
            failures.append(f"{path} is not bound by scenarios() or scenario()")
    return failures


def check_routing_suggested_model(answer, project):
    """The pytest-bdd dependency, the feature file, or its step module."""
    return review_names(answer, (r"pytest[-_ ]?bdd", r"\.feature\b", r"\bgherkin\b", r"test_suggested_model_scenarios"))


CHECKS = {
    "checkout-rules": check_notation,
    "checkout-bdd": check_existing_runner,
    "routing-suggested-model": check_routing_suggested_model,
}
