"""Keep request construction in helpers, out of the test body."""
import ast
import re
from pathlib import PurePosixPath

from shared import is_test_path, normalized_source, original_test_sources, parse_files, parse_python

RAW_REQUEST = {
    "environ": re.compile(r"\benviron\b"),
    "REQUEST_METHOD": re.compile(r"REQUEST_METHOD"),
    "PATH_INFO": re.compile(r"PATH_INFO"),
    "HTTP_ header": re.compile(r"\bHTTP_[A-Z_]+"),
    "wsgi.input": re.compile(r"wsgi\.input"),
    "setup_testing_defaults": re.compile(r"\bsetup_testing_defaults\b"),
    "start_response": re.compile(r"\bstart_response\b"),
    "Bearer token": re.compile(r"\bBearer\b"),
    "direct app call": re.compile(r"(?<![\w.])app\("),
    "http client": re.compile(r"\burllib\b|\bhttp\.client\b|\brequests\.(get|post)\b"),
}


def check_declarative(answer, project):
    files = parse_files(answer)
    original = original_test_sources(project)
    failures = []
    found = False
    for path, body in files.items():
        if not (path.endswith(".py") and is_test_path(path)):
            continue
        module = PurePosixPath(path).with_suffix("").as_posix().replace("/", ".")
        for node in ast.walk(parse_python(path, body)):
            if not (isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test")):
                continue
            if normalized_source(body, node) in original:
                continue
            found = True
            source = ast.get_source_segment(body, node) or ""
            raw = sorted(name for name, pattern in RAW_REQUEST.items() if pattern.search(source))
            if raw:
                failures.append(f"{module}:{node.name} builds the request inline: {', '.join(raw)}")
    if not found:
        return ["no new test in the answer"]
    return failures


CHECKS = {"paid-articles": check_declarative}
