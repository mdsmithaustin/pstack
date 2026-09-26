"""Name the test in the glossary's words, not the code's abbreviation."""
import ast
from pathlib import PurePosixPath

from shared import is_test_path, normalized_source, original_test_sources, parse_files, parse_python

GLOSSARY_TERM = "hold"
CODE_TERM = "resv"


def check_names(answer, project):
    files = parse_files(answer)
    original = original_test_sources(project)
    failures = []
    names = []
    for path, body in files.items():
        if not (path.endswith(".py") and is_test_path(path)):
            continue
        module = PurePosixPath(path).with_suffix("").as_posix().replace("/", ".")
        for node in ast.walk(parse_python(path, body)):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test") and normalized_source(body, node) not in original:
                names.append(node.name)
                if GLOSSARY_TERM not in node.name.lower():
                    failures.append(f"{module}:{node.name} does not name the Hold")
                if CODE_TERM in node.name.lower():
                    failures.append(f"{module}:{node.name} uses the code abbreviation resv")
    if not names:
        return ["no new test in the answer"]
    return failures


CHECKS = {"hold-expiry": check_names}
