```sh
log=$(mktemp "$TMPDIR/release.XXXXXX") || exit 1
trap 'rm -f "$log"' EXIT
status=0
python3 tools/verify-release.py >"$log" 2>&1 || status=$?
tail -n 20 "$log" || exit 1
exit "$status"
```
