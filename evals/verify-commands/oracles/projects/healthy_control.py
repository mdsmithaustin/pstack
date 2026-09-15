import json
import sys
from pathlib import Path


root = Path(sys.argv[1]).resolve()
state = sys.argv[2]
if state not in {"healthy", "broken"}:
    raise SystemExit(f"unknown state: {state}")
(root / "tools").mkdir(parents=True, exist_ok=True)
(root / "release-state.json").write_text(json.dumps({"state": state}))
(root / "tools" / "verify-release.py").write_text(
    "import json, pathlib, sys, time\n"
    "time.sleep(0.08)\n"
    "state = json.loads(pathlib.Path('release-state.json').read_text())['state']\n"
    "if state == 'broken':\n"
    "    print('release is not ready', file=sys.stderr)\n"
    "    raise SystemExit(5)\n"
    "print('release is ready')\n"
)
