## Review: `discord-server-actions-deny`

Nice, small feature, and the tests read well. The deny list hiding actions from the admin schema, winning over the allowlist, and being refused at runtime are the three behaviors that matter, and each has a test.

### The allow/deny rule is written twice

`_available_actions` and `_run_discord_action` each encode the same rule: `allowlist is None or name in allowlist`, then `denylist is None or name not in denylist`. That is a repeated conditional, and the two copies have to stay in sync. The runtime gate already writes the deny half the other way round (`denylist is not None and action in denylist`), which is how these drift.

I'd extract one predicate, say `_is_action_permitted(name, allowlist, denylist) -> bool`, next to `_parse_action_names`, and call it from both the schema filter and the handler. Then the precedence rule lives in one place, and the next list someone adds only touches that function.

### Other notes

- The denied-action error doesn't list the allowed actions the way the allowlist error does. Consider matching.
- Config is loaded twice per call, once for the schema build and once in the gate. Probably fine.
- `Tuple` is imported at the top and again in the plugin-compat block. Harmless.
- A line in the Discord docs page would help people find the new key; right now it only lives in the config comment.
- `test_denylist_wins_over_allowlist` is the most useful test here. Keep it even if the helper lands.

Approve, with the helper extraction as a suggestion.
