"""Load job configs through the original and the delivered loader, each in a fresh Python process, and report
every config the delivered loader treats differently.

Usage: held_out.py <delivered project>. Prints one JSON report. Exits nonzero only when the original loader
itself misbehaves or a probe cannot run.
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROBE_TIMEOUT_S = 120
BASE = {"source": "/srv/app/data", "destination": "/mnt/copies/nightly"}

# Configs the original loader accepts and no requirement restricts.
KEEP = {
    "nightly": {**BASE, "keep": 14},
    "spec-example-destination": {"source": "/srv/app/data", "destination": "backup://store/nightly"},
    "relative-destination": {**BASE, "destination": "copies/nightly"},
    "other-scheme-destination": {**BASE, "destination": "s3://bucket/nightly"},
    "spaced-destination": {**BASE, "destination": "/mnt/my copies/nightly"},
    "destination-equals-source": {**BASE, "destination": "/srv/app/data"},
    "trailing-slash-source": {**BASE, "source": "/srv/app/data/"},
    "unknown-key": {**BASE, "owner": "ops"},
    "keep-low-bound": {**BASE, "keep": 1},
    "keep-high-bound": {**BASE, "keep": 90},
    "archive-days-alone": {**BASE, "archive_after_days": 30},
    "archive-plain-path": {**BASE, "archive_destination": "/mnt/cold/nightly", "archive_after_days": 30},
    "duplicate-key": '{"source": "/srv/app/data", "destination": "/mnt/a", "destination": "/mnt/copies/nightly"}',
}
# Configs a requirement rejects: SJ-101 missing fields, SJ-102 a source that is not absolute, SJ-104 keep.
REJECT = {
    "missing-source": {"destination": "/mnt/copies/nightly"},
    "missing-destination": {"source": "/srv/app/data"},
    "relative-source": {**BASE, "source": "data/app"},
    "empty-source": {**BASE, "source": ""},
    "keep-zero": {**BASE, "keep": 0},
    "keep-above-range": {**BASE, "keep": 91},
    "keep-string": {**BASE, "keep": "7"},
    "keep-fraction": {**BASE, "keep": 2.5},
    "top-level-array": [],
}
# Configs whose treatment the specs leave arguable. Reported, never graded.
OPEN = {
    "null-destination": {**BASE, "destination": None},
    "empty-destination": {**BASE, "destination": ""},
    "numeric-destination": {**BASE, "destination": 5},
    "keep-true": {**BASE, "keep": True},
    "keep-whole-float": {**BASE, "keep": 14.0},
}
# The reported defect: a null source.
DEFECT = {"null-source": {**BASE, "source": None}}
GROUPS = {"keep": KEEP, "reject": REJECT, "open": OPEN, "defect": DEFECT}

PROBE = r"""
import json, sys
sys.path.insert(0, sys.argv[1])
from sync_job_loader import load_job
out = {}
for name, path in json.loads(sys.argv[2]).items():
    try:
        job = load_job(path)
    except BaseException as error:
        out[name] = {"ok": False, "error": type(error).__name__, "detail": str(error)[:200]}
    else:
        out[name] = {"ok": True, "value": json.dumps(job, sort_keys=True, default=repr) if isinstance(job, dict) else repr(job)}
print(json.dumps(out))
"""


def probe(root, paths):
    run = subprocess.run([sys.executable, "-I", "-B", "-c", PROBE, str(root), json.dumps(paths)],
                         capture_output=True, text=True, timeout=PROBE_TIMEOUT_S, cwd=root)
    if run.returncode:
        return None, (run.stderr.strip().splitlines() or [f"exit {run.returncode}"])[-1]
    return json.loads(run.stdout), None


def main(argv):
    project = Path(argv[1]).resolve()
    with tempfile.TemporaryDirectory(prefix="sync-configs-") as folder:
        paths = {}
        for group in GROUPS.values():
            for name, config in group.items():
                path = Path(folder) / f"{name}.json"
                path.write_text(config if isinstance(config, str) else json.dumps(config), encoding="utf-8")
                paths[name] = str(path)
        original, error = probe(HERE / "reference", paths)
        if error:
            print(f"original loader probe failed: {error}", file=sys.stderr)
            return 2
        delivered, error = probe(project, paths)
    report = {"probe_error": error, "checks": {}}
    for kind, group in GROUPS.items():
        for name in group:
            before = original[name]
            if kind in ("keep", "reject", "defect") and (kind == "keep") != before["ok"]:
                print(f"original loader disagrees with the {kind} group on {name}: {before}", file=sys.stderr)
                return 2
            after = delivered[name] if delivered else None
            report["checks"][name] = {"kind": kind, "original": before, "delivered": after}
    print(json.dumps(report))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
