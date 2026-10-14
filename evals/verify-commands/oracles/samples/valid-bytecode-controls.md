```sh
set -eu
expected=$(cat expected.txt)
control=$(cat control-name.txt)
observed=$(PYTHONPYCACHEPREFIX="/fresh-$control" python3 tools/observe.py)
[ "$observed" = "$expected" ]
```

See the [bytecode control contract](../../../README.md#what-is-measured).
