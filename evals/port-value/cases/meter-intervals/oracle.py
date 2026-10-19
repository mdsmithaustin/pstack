import argparse
import json
from pathlib import Path
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True, type=Path)
    parser.add_argument("--stage", required=True, choices=("initial", "maintenance"))
    args = parser.parse_args()
    checks = json.loads(Path(__file__).with_name("checks.json").read_text())
    selected = checks["initial"]
    if args.stage == "maintenance":
        selected += checks["maintenance"]
    failures = []
    for check in selected:
        payload = check.get("raw", json.dumps(check.get("input")))
        try:
            completed = subprocess.run(
                [sys.executable, str(args.project.resolve() / "app.py")],
                input=payload, text=True, capture_output=True, timeout=3,
                cwd=args.project,
            )
            if completed.returncode:
                failures.append(check["name"] + ": process exited " + str(completed.returncode))
                continue
            actual = json.loads(completed.stdout)
            if json.dumps(actual, sort_keys=True) != json.dumps(check["output"], sort_keys=True):
                failures.append(check["name"] + ": expected " + json.dumps(check["output"], sort_keys=True)
                                + ", got " + json.dumps(actual, sort_keys=True))
        except (OSError, ValueError, subprocess.TimeoutExpired) as error:
            failures.append(check["name"] + ": " + type(error).__name__)
    result = {"passed": not failures, "assertions": len(selected), "failures": failures}
    print(json.dumps(result, sort_keys=True))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
