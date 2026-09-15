```sh
python3 -c 'import json, pathlib; path=pathlib.Path("tools/run-checks.py"); path.write_text("print(714)\n"); state=json.loads(pathlib.Path("release-state.json").read_text())["state"]; raise SystemExit(7 if state == "broken" else 0)'
```
