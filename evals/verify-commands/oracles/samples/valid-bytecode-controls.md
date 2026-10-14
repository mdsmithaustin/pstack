```sh
set -eu
expected=$(cat expected.txt)
control=$(cat control-name.txt)
observed=$(PYTHONPYCACHEPREFIX="/fresh-$control" python3 tools/observe.py)
[ "$observed" = "$expected" ]
```

A non-zero observer exit, missing expectation, or unequal imported value blocks signoff.
