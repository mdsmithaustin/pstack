"""Deepen the shallow pricing cluster: replace its layered tests, and test the
owned remote dependency through an in-memory adapter."""
import ast
import re

from shared import apply_diff, functions, is_test_path, normalized_source, original_test_sources, parse_files, parse_python, run_jobs, safe_path

DELETE_TAG = re.compile(r'<delete path="([^"\n]+)"\s*/?>')
IN_MEMORY = re.compile(r"in_?memory|fake|stub", re.IGNORECASE)
MOCKS = re.compile(r"\bunittest\.mock\b|\bfrom unittest import mock\b|\bMagicMock\b|\bmock\.patch\b")
SUITE_RUN = ["python3", "-m", "unittest", "-q"]
PIN_RUN = ["python3", "pin_probe.py"]
PIN_PROBE = '''import io
import json
import urllib.request

PRICES = {
    "mug": {"sku": "mug", "amount": 12.5, "currency": "usd"},
    "tee": {"sku": "tee", "amount": 25, "currency": "eur"},
    "bad": {"sku": "bad", "amount": -1, "currency": "usd"},
}


class Response:
    def __init__(self, body):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        return self.body


def urlopen(url, *args, **kwargs):
    return Response(json.dumps(PRICES[url.rsplit("/", 1)[1]]).encode())


urllib.request.urlopen = urlopen

import catalog_export  # noqa: E402
import checkout  # noqa: E402
import quotes  # noqa: E402

out = io.StringIO()
catalog_export.export(["mug", "bad", "tee"], out=out)
print(json.dumps([checkout.cart_total_cents([("mug", 2), ("tee", 1)]), quotes.quote_line("tee", 3), out.getvalue()]))
'''


def final_tree(answer, project):
    deleted = {safe_path(path) for path in DELETE_TAG.findall(answer)}
    return {path: body for path, body in {**project, **parse_files(answer)}.items() if path not in deleted}


def kept_layered_tests(tree, project):
    originals = original_test_sources(project)
    kept = []
    for path, body in tree.items():
        if path.endswith(".py") and is_test_path(path):
            kept += [node.name for node in functions(parse_python(path, body)) if normalized_source(body, node) in originals]
    return sorted(kept)


def in_memory_adapters(tree):
    return sorted(
        node.name
        for path, body in tree.items() if path.endswith(".py")
        for node in ast.walk(parse_python(path, body))
        if isinstance(node, ast.ClassDef) and IN_MEMORY.search(node.name) and "cache" not in node.name.lower()
    )


def check_deepened(answer, project):
    tree = final_tree(answer, project)
    failures = []
    kept = kept_layered_tests(tree, project)
    if kept:
        failures.append(f"{len(kept)} test(s) on the shallow modules kept: {', '.join(kept)}")
    if not in_memory_adapters(tree):
        failures.append("no in-memory adapter for the pricing service")
    failures += [f"{path} mocks instead of using an adapter" for path, body in sorted(tree.items()) if is_test_path(path) and MOCKS.search(body)]
    if not any(is_test_path(path) and path.endswith(".py") and path not in project for path in tree):
        failures.append("no new tests at the deepened interface")
    trees = {"before": {**project, "pin_probe.py": PIN_PROBE}, "after": {**tree, "pin_probe.py": PIN_PROBE}}
    before_pin, after_pin, suite = run_jobs(trees, [
        {"tree": "before", "argv": PIN_RUN}, {"tree": "after", "argv": PIN_RUN}, {"tree": "after", "argv": SUITE_RUN},
    ])
    if before_pin["rc"] != 0:
        failures.append(f"pin probe fails on the original project: {before_pin['stderr'][-300:]}")
    elif after_pin["rc"] != 0 or after_pin["stdout"] != before_pin["stdout"]:
        failures.append("checkout, quotes, or catalog export behave differently against the same pricing responses")
    if suite["rc"] != 0:
        failures.append("final suite fails")
    return failures


# omnigent's harness-name cluster: the modules that hand-list spellings the
# plugin registry already knows.
HAND_LISTED = ("omnigent/gateway_inference.py", "omnigent/harness_availability.py")
SPELLING_PAIRS = (("codex-native", "native-codex"), ("claude-native", "native-claude"))
ALIASES_MODULE = "omnigent/harness_aliases.py"
NEAR_MISS_SCOPE = (ALIASES_MODULE, "omnigent/harness_plugins.py")


def touched_sources(workspace):
    """{path: (source before, source after)} for each Python file the diff
    touches, None where the file does not exist."""
    touched = {}
    for path, data in apply_diff(workspace.checkout, workspace.diff).items():
        if path.endswith(".py"):
            before = workspace.checkout / path
            touched[path] = (before.read_text(encoding="utf-8") if before.is_file() else None,
                             data.decode("utf-8") if data is not None else None)
    return touched


def head_source(workspace, touched, path):
    if path in touched:
        return touched[path][1]
    source = workspace.checkout / path
    return source.read_text(encoding="utf-8") if source.is_file() else None


def hand_lists(workspace, touched):
    """Tuple, set, and list literals in the cluster that still spell a family
    out by hand. Dict literals are the family maps, a separate concern."""
    failures = []
    for path in HAND_LISTED:
        source = head_source(workspace, touched, path)
        if source is None:
            continue
        for node in ast.walk(parse_python(path, source)):
            if isinstance(node, (ast.Tuple, ast.Set, ast.List)):
                values = {element.value for element in node.elts if isinstance(element, ast.Constant)}
                failures += [f"{path}:{node.lineno} hand-lists {', '.join(pair)}" for pair in SPELLING_PAIRS if set(pair) <= values]
    return failures


def base_name(node):
    return node.id if isinstance(node, ast.Name) else node.attr if isinstance(node, ast.Attribute) else ""


def interfaces_without_second_adapter(touched):
    """A new Protocol or ABC in the diff with fewer than two implementations in
    the files the diff touches. A class implements it by subclassing it or, for
    a Protocol, by defining every method it declares."""
    classes = [(path, node) for path, (_, after) in sorted(touched.items()) if after
               for node in ast.walk(parse_python(path, after)) if isinstance(node, ast.ClassDef)]
    failures = []
    for path, node in classes:
        before = touched[path][0]
        existed = before and any(isinstance(old, ast.ClassDef) and old.name == node.name for old in ast.walk(parse_python(path, before)))
        kinds = {base_name(base) for base in node.bases} | {base_name(keyword.value) for keyword in node.keywords if keyword.arg == "metaclass"}
        if existed or not kinds & {"Protocol", "ABC", "ABCMeta"}:
            continue
        declared = {item.name for item in node.body if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and not item.name.startswith("__")}
        implementations = [
            other.name for _, other in classes if other is not node and (
                node.name in {base_name(base) for base in other.bases}
                or ("Protocol" in kinds and declared and declared <= {item.name for item in other.body if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))})
            )
        ]
        if len(implementations) < 2:
            count = len(implementations)
            failures.append(f"{path}:{node.name} is an interface with {count} implementation{'' if count == 1 else 's'}")
    return failures


def forwards_elsewhere(function, imported):
    body = function.body[1:] if function.body and isinstance(function.body[0], ast.Expr) and isinstance(function.body[0].value, ast.Constant) else function.body
    if len(body) != 1 or not isinstance(body[0], ast.Return) or not isinstance(body[0].value, ast.Call):
        return False
    callee = body[0].value.func
    while isinstance(callee, ast.Attribute):
        callee = callee.value
    return isinstance(callee, ast.Name) and callee.id in imported


def pass_through_modules(touched):
    """A new omnigent module that only re-exports names or whose every
    function forwards a call into another omnigent module."""
    failures = []
    for path, (before, after) in sorted(touched.items()):
        if before is not None or after is None or not path.startswith("omnigent/"):
            continue
        tree = parse_python(path, after)
        imported, rest = set(), []
        for statement in tree.body:
            if isinstance(statement, ast.ImportFrom) and (statement.module or "").startswith("omnigent"):
                imported |= {alias.asname or alias.name for alias in statement.names}
            elif isinstance(statement, ast.Import) and any(alias.name.startswith("omnigent") for alias in statement.names):
                imported |= {(alias.asname or alias.name).split(".")[0] for alias in statement.names}
            elif isinstance(statement, (ast.Import, ast.ImportFrom)) or (isinstance(statement, ast.Expr) and isinstance(statement.value, ast.Constant)):
                continue
            elif isinstance(statement, ast.Assign) and [base_name(target) for target in statement.targets] == ["__all__"]:
                continue
            else:
                rest.append(statement)
        if imported and all(isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef)) and forwards_elsewhere(statement, imported) for statement in rest):
            failures.append(f"{path} only passes calls through to other omnigent modules")
    return failures


def check_harness_names(answer, workspace):
    touched = touched_sources(workspace)
    return hand_lists(workspace, touched) + interfaces_without_second_adapter(touched) + pass_through_modules(touched)


def check_terminal_name(answer, workspace):
    touched = touched_sources(workspace)
    failures = [f"the diff reaches beyond {ALIASES_MODULE}: {path}" for path in sorted(touched)
                if path not in NEAR_MISS_SCOPE and not is_test_path(path)]
    failures += interfaces_without_second_adapter(touched)
    source = head_source(workspace, touched, ALIASES_MODULE)
    function = next((node for node in parse_python(ALIASES_MODULE, source).body
                     if isinstance(node, ast.FunctionDef) and node.name == "native_terminal_name"), None)
    if function is None:
        failures.append(f"{ALIASES_MODULE} no longer defines native_terminal_name")
    elif any(isinstance(node, ast.Attribute) and node.attr in ("removesuffix", "removeprefix") for node in ast.walk(function)):
        failures.append("native_terminal_name still strips -native and native- by hand")
    return failures


CHECKS = {"pricing-modules": check_deepened, "harness-names": check_harness_names, "terminal-name": check_terminal_name}
