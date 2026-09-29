## Review: `discord-server-actions-deny`

Useful setting. An allowlist you have to extend every time the tool grows an action is the wrong shape for "never delete anything", and the new tests go through the schema and the handler instead of poking internals. One design issue before merge, then small things.

### The second `None` should not exist

The PR keeps `None` meaning "no allowlist" and adds a second `None` meaning "nothing denied". So every check site now carries two sentinel branches: `_available_actions` tests `allowlist is None or ...` and `denylist is None or ...`, and `_run_discord_action` grows a second gate guarded by `denylist is not None`. The pair returned by `_load_action_config` and the extra `denylist` parameter exist only to carry those sentinels.

Resolve the config into the permitted actions once, in `_load_action_config`. An unset `server_actions` is `list(_ACTIONS)`, an unset deny key is `[]`, a load failure is `list(_ACTIONS)`, and the result is allowed minus denied. Then `_available_actions(caps, permitted)` filters on `name in permitted`, and the handler has one `if action not in permitted` refusal. That deletes both existing `allowlist is None` checks, both new `denylist` checks, the second gate, and the pair.

Behavior holds. `_available_actions` only walks `_ACTIONS`, and the handler rejects unknown actions before the config gate, so "no allowlist" and "all of `_ACTIONS`" admit the same actions. An all-typo `server_actions` still parses to `[]`, so the tool still drops. Your new schema and handler tests pass as written. Only the asserts on `(None, None)` and `_available_actions(caps, None)` change, to the resolved list.

### Smaller things

- The deny refusal doesn't list what is still allowed. With one gate you get the `Allowed: ...` text for both keys.
- `Tuple` is now imported at the top and again in the plugin-compat block at the bottom. Harmless.
- The `server_actions` comment in `config_defaults.py` still omits `delete_message`, the action most people will deny.

Request changes for the sentinel; the rest is optional.
