```sh
python3 -c 'import json, pathlib, sys, time; marker="tools/run-checks.py"; time.sleep(0.1); state=json.loads(pathlib.Path("release-state.json").read_text())["state"]; raise SystemExit(7 if state == "broken" else 0)'
```
