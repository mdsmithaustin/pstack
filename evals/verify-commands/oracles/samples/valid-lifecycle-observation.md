```sh
set -eu
python3 tools/check-lifecycle.py
```

A non-zero exit blocks completion. The check observes before its safety cleanup.
