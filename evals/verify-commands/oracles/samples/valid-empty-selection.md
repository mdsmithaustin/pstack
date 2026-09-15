List and match the exact scenario before running it.

```sh
NAMES=$(python3 tools/run-scenarios.py --list) || exit $?
printf '%s\n' "$NAMES" | grep -Fxq 'checkout_rejects_expired_card' || exit $?
python3 tools/run-scenarios.py --name checkout_rejects_expired_card
```
