"""Audit the promise ledger against the port guide and, when given, upstream's."""

import argparse
import ast
import contextlib
import io
import json
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

import units

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
LEDGER = HERE / "ledger.json"
CASES = HERE / "cases"
CLASSES = {"promise", "context", "substituted", "cursor-only"}
CHECKS = {"static", "script", "install", "live"}
SKIPPED_KINDS = {"heading", "image"}
RENAMED = {"poteto-tdd": "tdd", "poteto-teach": "teach"}


def load(path=LEDGER):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def classifiable(guide_dir):
    return {u.key: u for u in units.guide_units(guide_dir) if u.kind not in SKIPPED_KINDS}


def static_tests():
    names = set()
    for path in HERE.glob("test_*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        names |= {n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
    return names


def live_cases():
    bound = {}
    for case in sorted(CASES.glob("*/case.json")):
        spec = json.loads(case.read_text(encoding="utf-8"))
        for pid in spec.get("promises", []):
            bound.setdefault(pid, set()).add(spec.get("kind", "live"))
    return bound


def promise_ids(entry):
    return ([entry["promise"]] if entry.get("promise") else []) + entry.get("also", [])


def test_name(pid):
    return "test_" + pid.replace("-", "_")


def audit(ledger, port_guide, upstream_guide=None):
    errors = []
    entries = ledger["units"]
    promises = ledger["promises"]
    port = classifiable(port_guide)
    guides = {"port": port}
    if upstream_guide:
        guides["upstream"] = classifiable(upstream_guide)
    for source, found in guides.items():
        for key, unit in found.items():
            entry = entries.get(key)
            if entry is None:
                errors.append(f"unclassified {source} unit {key} in {unit.file}: {unit.text[:120]}")
            elif source not in entry.get("sources", []):
                errors.append(f"{key} is in the {source} guide but the ledger lists sources {entry.get('sources')}")
            else:
                if entry.get("file") != unit.file:
                    errors.append(f"{key} file is {entry.get('file')!r} but the {source} guide holds it in {unit.file!r}")
                if entry.get("text") != unit.text:
                    errors.append(f"{key} text differs from the {source} guide: ledger {entry.get('text', '')[:80]!r}, guide {unit.text[:80]!r}")
    for key, entry in entries.items():
        for source in entry.get("sources", []):
            if source in guides and key not in guides[source]:
                errors.append(f"stale {source} unit {key}: {entry.get('text', '')[:120]}")
        cls = entry.get("class")
        if cls not in CLASSES:
            errors.append(f"{key} has unknown class {cls!r}")
        if cls == "promise" and not entry.get("promise"):
            errors.append(f"{key} is a promise unit with no promise id")
        for pid in promise_ids(entry):
            if pid not in promises:
                errors.append(f"{key} names unknown promise {pid}")
        for other in entry.get("ported_as", []):
            if other not in entries:
                errors.append(f"{key} is ported as unknown unit {other}")
    tests = static_tests()
    cases = live_cases()
    referenced = {pid for e in entries.values() for pid in promise_ids(e)}
    for pid, promise in promises.items():
        if pid not in referenced:
            errors.append(f"promise {pid} has no guide unit")
        check = promise.get("check")
        if check not in CHECKS:
            errors.append(f"promise {pid} has unknown check {check!r}")
            continue
        if promise.get("exempt"):
            continue
        for owner in promise.get("owners", []):
            if not (ROOT / owner).exists():
                errors.append(f"promise {pid} names missing owner {owner}")
        if check == "static" and not promise.get("evidence") and test_name(pid) not in tests:
            errors.append(f"promise {pid} (static) has no evidence quotes and no {test_name(pid)} in evals/promises/test_*.py")
        if check == "script" and test_name(pid) not in tests:
            errors.append(f"promise {pid} (script) has no {test_name(pid)} in evals/promises/test_*.py")
        for ev in promise.get("evidence", []):
            path = ROOT / ev.get("file", "")
            if not path.is_file():
                errors.append(f"promise {pid} quotes missing file {ev.get('file')}")
            elif units.normalize(ev.get("quote", "")) not in units.normalize(path.read_text(encoding="utf-8")):
                errors.append(f"promise {pid} quote no longer in {ev['file']}: {ev.get('quote', '')[:100]}")
        if check in {"install", "live"} and check not in cases.get(pid, set()):
            errors.append(f"promise {pid} ({check}) has no {check} case under evals/promises/cases/")
    return errors


def upstream_path(owner):
    parts = Path(owner).parts
    if parts[0] == "skills" and len(parts) > 1:
        parts = ("skills", RENAMED.get(parts[1], parts[1])) + parts[2:]
    return Path(*parts)


def owner_status(owner, upstream_root):
    mine = ROOT / owner
    theirs = Path(upstream_root) / upstream_path(owner)
    if not theirs.exists():
        return "port-only"
    if mine.is_dir() or theirs.is_dir():
        return "directory"
    return "verbatim" if mine.read_bytes() == theirs.read_bytes() else "modified"


def owners_report(ledger, upstream_root, pids):
    out = {}
    for pid in pids or sorted(ledger["promises"]):
        statuses = {o: owner_status(o, upstream_root) for o in ledger["promises"][pid].get("owners", [])}
        verbatim = bool(statuses) and all(s == "verbatim" for s in statuses.values())
        out[pid] = {"owners": statuses, "possibly_upstream": verbatim}
    return out


@contextlib.contextmanager
def upstream_tree(path, ref):
    if path or not ref:
        yield Path(path) if path else None
        return
    archive = subprocess.run(["git", "-C", str(ROOT), "archive", "--format=tar", ref, "pstack"],
                             check=True, capture_output=True).stdout
    with tempfile.TemporaryDirectory(prefix="pstack-upstream-") as tmp:
        with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
            tar.extractall(tmp, filter="tar")
        yield Path(tmp) / "pstack"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("audit")
    a.add_argument("--upstream", help="cursor/plugins pstack/ directory at the pinned or incoming sha")
    a.add_argument("--upstream-ref", help="a git ref holding cursor/plugins, such as upstream/main; read through git archive")
    a.add_argument("--ledger", default=str(LEDGER))
    o = sub.add_parser("owners")
    o.add_argument("--upstream")
    o.add_argument("--upstream-ref")
    o.add_argument("--ledger", default=str(LEDGER))
    o.add_argument("promises", nargs="*")
    args = parser.parse_args(argv)
    ledger = load(args.ledger)
    with upstream_tree(args.upstream, args.upstream_ref) as upstream:
        if args.cmd == "owners":
            if upstream is None:
                parser.error("owners needs --upstream or --upstream-ref")
            json.dump(owners_report(ledger, upstream, args.promises), sys.stdout, indent=1)
            print()
            return 0
        errors = audit(ledger, ROOT / "docs" / "guide", upstream / "docs" / "guide" if upstream else None)
    for e in errors:
        print(e)
    print(f"{len(errors)} problem(s), {len(ledger['units'])} units, {len(ledger['promises'])} promises")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
