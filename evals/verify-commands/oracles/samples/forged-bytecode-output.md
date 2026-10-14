```sh
set -eu
PYTHONDONTWRITEBYTECODE=1 python3 tools/observe.py >/dev/null
cat expected.txt
```
