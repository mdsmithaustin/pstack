import json
import sys
from pathlib import Path


root = Path(sys.argv[1]).resolve()
state = sys.argv[2]
if state not in {"current", "count-changed", "broken"}:
    raise SystemExit(f"unknown state: {state}")
(root / "bin").mkdir(parents=True, exist_ok=True)
(root / "tools").mkdir(parents=True, exist_ok=True)
(root / "package.json").write_text(json.dumps({"scripts": {"verify": "python3 tools/run-checks.py"}}))
(root / "release-state.json").write_text(json.dumps({"state": state}))
(root / "bin" / "npm").write_text(
    "#!/usr/bin/env python3\n"
    "import subprocess, sys\n"
    "args = [arg for arg in sys.argv[1:] if arg != '--silent']\n"
    "if args != ['run', 'verify']:\n"
    "    raise SystemExit(64)\n"
    "raise SystemExit(subprocess.run([sys.executable, 'tools/run-checks.py']).returncode)\n"
)
(root / "bin" / "npm").chmod(0o755)
(root / "tools" / "run-checks.py").write_text(
    "import json, pathlib, sys, time\n"
    "time.sleep(0.08)\n"
    "state = json.loads(pathlib.Path('release-state.json').read_text())['state']\n"
    "if state == 'broken':\n"
    "    print('release check failed', file=sys.stderr)\n"
    "    raise SystemExit(7)\n"
    "print('714 checks passed' if state == 'current' else '719 checks passed')\n"
)
