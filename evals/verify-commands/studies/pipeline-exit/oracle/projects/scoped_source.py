import json
import sys
from pathlib import Path


root = Path(sys.argv[1]).resolve()
state = sys.argv[2]
if state not in {"migrated", "target-regressed", "compatibility-retained"}:
    raise SystemExit(f"unknown state: {state}")
for directory in (root / "bin", root / "packages" / "api" / "src", root / "packages" / "api" / "tools"):
    directory.mkdir(parents=True, exist_ok=True)
(root / "source-state.json").write_text(json.dumps({"state": state}))
(root / "packages" / "api" / "package.json").write_text(
    json.dumps({"scripts": {"verify": "python3 tools/verify-scenario.py"}})
)
legacy_fetch = "return legacyClient.get(path)" if state == "target-regressed" else "return newClient.get(path)"
(root / "packages" / "api" / "src" / "client.py").write_text(
    f"def legacy_fetch(path):\n    {legacy_fetch}\n\n"
    "def compatibility_probe(path):\n    return legacyClient.get(path)\n"
)
(root / "packages" / "api" / "tools" / "verify-scenario.py").write_text(
    "import pathlib, sys, time\n"
    "time.sleep(0.08)\n"
    "if sys.argv[1:] != ['legacy_fetch_uses_new_client']:\n"
    "    raise SystemExit(64)\n"
    "source = (pathlib.Path(__file__).parents[1] / 'src' / 'client.py').read_text()\n"
    "target = source.split('def compatibility_probe', 1)[0]\n"
    "if 'newClient.get' not in target or 'legacyClient.get' in target:\n"
    "    print('legacy_fetch uses the wrong client', file=sys.stderr)\n"
    "    raise SystemExit(8)\n"
    "print('legacy_fetch scenario passed')\n"
)
(root / "bin" / "npm").write_text(
    "#!/usr/bin/env python3\n"
    "import pathlib, subprocess, sys\n"
    "args = sys.argv[1:]\n"
    "if args[:2] != ['--prefix', 'packages/api'] or args[2:5] != ['run', 'verify', '--'] or len(args) != 6:\n"
    "    raise SystemExit(64)\n"
    "target = pathlib.Path('packages/api/tools/verify-scenario.py')\n"
    "raise SystemExit(subprocess.run([sys.executable, str(target), args[5]]).returncode)\n"
)
(root / "bin" / "npm").chmod(0o755)
