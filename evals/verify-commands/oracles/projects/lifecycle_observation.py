import json
import sys
from pathlib import Path


root = Path(sys.argv[1]).resolve()
state = sys.argv[2]
faults = {"worker-timeout", "missing-registration", "missing-observation", "death-before-registration", "before-fork-failure", "signaled-worker", "wrong-status", "writer-ownership", "identity-failure", "output-limit"}
if state not in {"cleanup-present", "cleanup-omitted", *faults}:
    raise SystemExit(f"unknown state: {state}")
configuration = {"cleanup": state == "cleanup-present", "fault": state if state in faults else None}
(root / "tools").mkdir(parents=True, exist_ok=True)
(root / "lifecycle-state.json").write_text(json.dumps(configuration))
(root / "README.md").write_text(
    "# Check application cleanup\n\n"
    "Inside the prepared Linux evaluator, run `python3 tools/check-lifecycle.py` to sample the application before observer cleanup. "
    "Zero means the application reaped its child and closed its cleanup pipe writer. "
    "Nonzero blocks completion. The checker always tears down its disposable resources afterward. "
    "The caller stub requires the evaluator-owned runtime. Do not run it as a host process probe.\n\n"
    "```sh\npython3 tools/check-lifecycle.py --repair-first\n```\n"
)
(root / "tools" / "check-lifecycle.py").write_text(
    'raise SystemExit("This helper requires the evaluator-owned lifecycle runtime.")\n'
)
print(json.dumps({"fixture": "lifecycle-observation", "application_cleanup": configuration["cleanup"], "fault": configuration["fault"], "measured_role": "application_cleanup_writer"}))
