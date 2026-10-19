import json
import sys
from pathlib import Path


root = Path(sys.argv[1]).resolve()
state = sys.argv[2]
states = {"equal", "unequal", "reference-unavailable", "current-unavailable", "both-unavailable"}
if state not in states:
    raise SystemExit(f"unknown state: {state}")
(root / "tools").mkdir(parents=True, exist_ok=True)
(root / "total-state.json").write_text(json.dumps({"state": state}))
(root / "tools" / "reference_total.py").write_text(
    "import json, pathlib, sys, time\n"
    "time.sleep(0.08)\n"
    "state = json.loads(pathlib.Path('total-state.json').read_text())['state']\n"
    "if state in {'reference-unavailable', 'both-unavailable'}:\n"
    "    print('reference unavailable', file=sys.stderr)\n"
    "    raise SystemExit(3)\n"
    "print(42)\n"
)
(root / "tools" / "current_total.py").write_text(
    "import json, pathlib, sys, time\n"
    "time.sleep(0.08)\n"
    "state = json.loads(pathlib.Path('total-state.json').read_text())['state']\n"
    "if state in {'current-unavailable', 'both-unavailable'}:\n"
    "    print('current unavailable', file=sys.stderr)\n"
    "    raise SystemExit(4)\n"
    "print(41 if state == 'unequal' else 42)\n"
)
