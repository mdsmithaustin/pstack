"""Deepen the shallow pricing cluster: replace its layered tests, and test the
owned remote dependency through an in-memory adapter."""
import ast
import re

from shared import functions, is_test_path, normalized_source, original_test_sources, parse_files, parse_python, run_jobs, safe_path

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


CHECKS = {"pricing-modules": check_deepened}
