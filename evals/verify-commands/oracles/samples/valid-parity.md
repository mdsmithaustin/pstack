Preserve each producer's exit status, then compare successful results.

```bash
EXPECTED=$(python3 tools/reference_total.py) || exit $?
ACTUAL=$(python3 tools/current_total.py) || exit $?
[ "$EXPECTED" = "$ACTUAL" ]
```
