"""Digests of what a live run is graded against, taken when the run starts so a receipt names the bytes it tested."""

import hashlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
GRADER = ("oracles.py", "grade_boundary.py")


def tree_digest(paths, here=HERE):
    """One digest over every file under `paths`, keyed by path relative to `here`."""
    digest = hashlib.sha256()
    for root in paths:
        files = [root] if root.is_file() else sorted(p for p in root.rglob("*") if p.is_file() and "__pycache__" not in p.parts)
        for path in files:
            digest.update(path.relative_to(here).as_posix().encode() + b"\0" + hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def case_paths(case_id, spec, here=HERE):
    """The case's own directory, the case directory it borrows held-out checks from, its fixture, and its history."""
    paths = [here / "cases" / name for name in dict.fromkeys((case_id, spec.get("references", case_id)))]
    paths.append(here / "fixtures" / spec["fixture"])
    if spec.get("history"):
        paths.append(here / "histories" / spec["history"])
    return paths


def case_digest(case_id, spec, here=HERE):
    return tree_digest(case_paths(case_id, spec, here), here)


def grader_digest(here=HERE):
    return hashlib.sha256(b"".join((here / name).read_bytes() for name in GRADER)).hexdigest()


def run_inputs(case, here=HERE):
    """What live.py stores in a run's record before its first turn. The grader is frozen for the run at the same moment."""
    spec = {k: v for k, v in case.items() if k != "id"}
    return {"case": case_digest(case["id"], spec, here), "grader": grader_digest(here)}
