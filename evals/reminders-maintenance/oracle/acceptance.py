import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path


def run(app, phase, prior=None):
    scenarios = json.loads(Path(__file__).with_name("acceptance_cases.json").read_text())
    stages = ["baseline", "requested", "maintenance"]
    enabled = stages[:stages.index(phase) + 1]
    count = 0
    for scenario in scenarios:
        if scenario["phase"] not in enabled:
            continue
        if scenario.get("requires_prior") and prior is None:
            continue
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / "reminders.json"
            if "initial_state" in scenario:
                state.write_text(json.dumps(scenario["initial_state"]))
            for index, step in enumerate(scenario["steps"], 1):
                before = state.read_bytes() if state.exists() else None
                payload = step.get("raw", json.dumps(step.get("request")))
                process = subprocess.run(
                    [sys.executable, "-B", str(prior if step.get("producer") else app), "--state", str(state)],
                    input=payload, text=True, capture_output=True, timeout=5,
                    cwd=(prior if step.get("producer") else app).parent,
                )
                label = f"{scenario['name']} request {index}"
                lines = process.stdout.splitlines()
                if len(lines) != 1 or not process.stdout.endswith("\n"):
                    raise AssertionError(f"{label}: expected one response line, got {process.stdout!r}")
                try:
                    response = json.loads(lines[0])
                except json.JSONDecodeError as error:
                    raise AssertionError(f"{label}: response is not JSON") from error
                expected = step["expected"]
                code = 2 if "error" in expected else 0
                if (process.returncode != code or
                        json.dumps(response, sort_keys=True) != json.dumps(expected, sort_keys=True)):
                    raise AssertionError(
                        f"{label}: expected exit {code} and {expected!r}; "
                        f"got exit {process.returncode} and {response!r}; stderr={process.stderr!r}"
                    )
                after = state.read_bytes() if state.exists() else None
                if code == 2 and after != before:
                    raise AssertionError(f"{label}: persistent state changed")
                count += 1
    if count == 0:
        raise AssertionError("No requests exercised")
    return count


def controls():
    for value in [0, {"occurrences": []}]:
        with tempfile.TemporaryDirectory() as directory:
            app = Path(directory) / "app.py"
            app.write_text(
                "import json, sys\nfrom pathlib import Path\n"
                "sys.stdin.read()\nPath(sys.argv[2]).write_text('{}')\n"
                f"print(json.dumps({value!r}))\n"
            )
            try:
                run(app, "baseline")
            except AssertionError:
                continue
            raise AssertionError(f"Mutation control survived: {value!r}")
    return 2


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("project_path", nargs="?", type=Path)
    parser.add_argument("--app", type=Path)
    parser.add_argument("--phase", choices=["baseline", "requested", "maintenance"])
    parser.add_argument("--stage", choices=["baseline", "build", "design", "maintenance"])
    parser.add_argument("--prior-project", type=Path)
    parser.add_argument("--self-check", "--mutation-checks", action="store_true")
    args = parser.parse_args()
    if args.app is not None and args.project_path is not None:
        parser.error("choose a project path or --app")
    if args.phase is not None and args.stage is not None:
        parser.error("choose --phase or --stage")
    app = args.app or ((args.project_path or Path(__file__).parent / "project") / "app.py")
    phase = args.phase or {"build": "requested", "design": "requested"}.get(args.stage, args.stage) or "baseline"
    prior = (args.prior_project / "app.py").resolve() if args.prior_project is not None else None
    if prior is not None and phase != "maintenance":
        parser.error("--prior-project requires the maintenance stage")
    count = run(app.resolve(), phase, prior)
    print(f"{phase}: {count} requests passed")
    if args.self_check:
        print(f"mutation controls: {controls()} rejected")


if __name__ == "__main__":
    main()
