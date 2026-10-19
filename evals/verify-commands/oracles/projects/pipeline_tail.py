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
    "import json, pathlib, sys\n"
    "state = json.loads(pathlib.Path('release-state.json').read_text())['state']\n"
    "for number in range(1, 30):\n"
    "    stream = sys.stderr if number == 15 else sys.stdout\n"
    "    print(f'check {number:02d}', file=stream, flush=True)\n"
    "if state == 'broken':\n"
    "    print('ERROR release blocked', file=sys.stderr, flush=True)\n"
    "    raise SystemExit(7)\n"
    "print('OK release ready', flush=True)\n"
)
