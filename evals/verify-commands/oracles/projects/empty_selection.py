import json
import sys
from pathlib import Path


root = Path(sys.argv[1]).resolve()
state = sys.argv[2]
if state not in {"present", "absent", "scenario-broken"}:
    raise SystemExit(f"unknown state: {state}")
(root / "tools").mkdir(parents=True, exist_ok=True)
(root / "scenario-state.json").write_text(json.dumps({"state": state}))
(root / "tools" / "run-scenarios.py").write_text(
    "import argparse, json, pathlib, sys, time\n"
    "parser = argparse.ArgumentParser()\n"
    "parser.add_argument('--list', action='store_true')\n"
    "parser.add_argument('--name')\n"
    "args = parser.parse_args()\n"
    "time.sleep(0.08)\n"
    "state = json.loads(pathlib.Path('scenario-state.json').read_text())['state']\n"
    "names = ['checkout_rejects_expired_card', 'invoice_sends_receipt']\n"
    "if state == 'absent':\n"
    "    names = ['checkout_rejects_expired_card_v2', 'invoice_sends_receipt']\n"
    "if args.list:\n"
    "    print('\\n'.join(names))\n"
    "    raise SystemExit(0)\n"
    "if args.name is None:\n"
    "    raise SystemExit(64)\n"
    "selected = [name for name in names if args.name in name]\n"
    "if not selected:\n"
    "    print('0 scenarios selected')\n"
    "    raise SystemExit(0)\n"
    "print('selected ' + ', '.join(selected))\n"
    "if state == 'scenario-broken' and args.name == 'checkout_rejects_expired_card':\n"
    "    print('checkout scenario failed', file=sys.stderr)\n"
    "    raise SystemExit(9)\n"
    "print('scenario passed')\n"
)
