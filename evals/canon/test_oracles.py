"""Loads the shared oracle tests and every rules/<id>/test_oracle.py, so one
`python3 -m unittest` in this directory runs them all. Without a running
Docker daemon, a test whose oracle runs answer code in the container skips."""
import importlib.util
import subprocess
import sys
import unittest
from pathlib import Path

CANON = Path(__file__).resolve().parent
sys.path.insert(0, str(CANON / "oracles"))


def docker_ready():
    try:
        return subprocess.run(["docker", "info"], capture_output=True, timeout=60, check=False).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def skip_container_jobs():
    import shared

    def skip(trees, jobs):
        raise unittest.SkipTest(f"needs a running Docker daemon for {shared.IMAGE}")

    shared.run_jobs = skip
    # An oracle binds run_jobs when it loads, so drop any loaded before the swap.
    for name in [name for name in sys.modules if name.startswith("canon_oracle_")]:
        del sys.modules[name]


def load_tests(loader, tests, pattern):
    if not docker_ready():
        skip_container_jobs()
    paths = [CANON / "oracles" / "test_shared.py", *sorted((CANON / "rules").glob("*/test_oracle.py"))]
    for path in paths:
        name = f"canon_tests_{path.parent.name}_{path.stem}"
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
        tests.addTests(loader.loadTestsFromModule(module))
    return tests
