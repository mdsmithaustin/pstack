```sh
python3 tools/run-checks.py || true
python3 -c 'import json, pathlib; state=json.loads(pathlib.Path("release-state.json").read_text())["state"]; raise SystemExit(7 if state == "broken" else 0)'
```
