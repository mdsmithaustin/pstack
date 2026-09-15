import json
import sys
from pathlib import Path


root = Path(sys.argv[1]).resolve()
state = sys.argv[2]
if state not in {"healthy", "package-broken", "root-decoy"}:
    raise SystemExit(f"unknown state: {state}")
for directory in (root / "bin", root / "scripts", root / "packages" / "web" / "scripts"):
    directory.mkdir(parents=True, exist_ok=True)
(root / "package.json").write_text(json.dumps({"scripts": {"verify": "python3 scripts/root-decoy.py"}}))
(root / "packages" / "web" / "package.json").write_text(
    json.dumps({"scripts": {"verify": "python3 scripts/check-release.py"}})
)
(root / "package-state.json").write_text(json.dumps({"state": state}))
(root / "scripts" / "root-decoy.py").write_text("print('root package is healthy')\n")
(root / "packages" / "web" / "scripts" / "check-release.py").write_text(
    "import json, pathlib, sys, time\n"
    "time.sleep(0.08)\n"
    "root = pathlib.Path(__file__).resolve().parents[3]\n"
    "state = json.loads((root / 'package-state.json').read_text())['state']\n"
    "if state == 'package-broken':\n"
    "    print('web release check failed', file=sys.stderr)\n"
    "    raise SystemExit(6)\n"
    "print('web release check passed')\n"
)
(root / "bin" / "npm").write_text(
    "#!/usr/bin/env python3\n"
    "import pathlib, subprocess, sys\n"
    "args = sys.argv[1:]\n"
    "prefix = pathlib.Path('.')\n"
    "if '--prefix' in args:\n"
    "    index = args.index('--prefix')\n"
    "    prefix = pathlib.Path(args[index + 1])\n"
    "    del args[index:index + 2]\n"
    "else:\n"
    "    for arg in list(args):\n"
    "        if arg.startswith('--prefix='):\n"
    "            prefix = pathlib.Path(arg.split('=', 1)[1])\n"
    "            args.remove(arg)\n"
    "if args != ['run', 'verify']:\n"
    "    raise SystemExit(64)\n"
    "target = prefix / 'scripts' / ('check-release.py' if str(prefix).rstrip('/') in {'packages/web', './packages/web'} else 'root-decoy.py')\n"
    "raise SystemExit(subprocess.run([sys.executable, str(target)]).returncode)\n"
)
(root / "bin" / "npm").chmod(0o755)
