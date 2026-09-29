## Review: `discord-server-actions-deny`

Good addition. An allowlist is the wrong tool for "everything except deletes", and making the deny list win over the allowlist is the rule people will expect.

### Correctness

- `_parse_action_names` is a clean extraction. Both keys get the same comma-string and YAML-list handling and the same unknown-name warning, now with the key in the message, and the typo test covers it.
- The deny list is enforced in the schema filter and again at call time, so a stale cached schema can't sneak a denied action through. That matches how the allowlist already works.
- Denying every core action drops the `discord` tool entirely, like an all-typo allowlist does. Worth a line in the config comment so nobody is surprised when the tool disappears.
- A config load failure still falls back to allowing everything, which is the existing behavior.

### Tests

- The new schema tests assert membership rather than a frozen enum, which fits the repo's no-change-detector rule.
- `test_denylist_leaves_other_actions_running` asserts the PUT that went out, not just that a call happened. Nice.
- Consider one test with a YAML list for `server_actions` too; only the deny key gets one.

### Nits

- The denied-action refusal doesn't list what is still allowed; the allowlist refusal does.
- `Tuple` is imported at the top and again in the plugin-compat block.
- The `server_actions` comment in `config_defaults.py` still omits `delete_message`.

Approve.
