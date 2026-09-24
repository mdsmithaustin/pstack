"""Loads the shared oracle tests and every rules/<id>/test_oracle.py, so one
`python3 -m unittest` in this directory runs them all."""
import importlib.util
import sys
from pathlib import Path

CANON = Path(__file__).resolve().parent
sys.path.insert(0, str(CANON / "oracles"))


def load_tests(loader, tests, pattern):
    paths = [CANON / "oracles" / "test_shared.py", *sorted((CANON / "rules").glob("*/test_oracle.py"))]
    for path in paths:
        name = f"canon_tests_{path.parent.name}_{path.stem}"
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
        tests.addTests(loader.loadTestsFromModule(module))
    return tests
