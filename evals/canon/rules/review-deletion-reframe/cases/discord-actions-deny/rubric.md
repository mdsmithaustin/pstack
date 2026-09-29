# Grading guide: discord-actions-deny (positive)

## Location

`tools/discord_tool.py`:

- `_parse_action_names` and `_load_action_config`, which return `None` for an unset key and hand back the pair `(allowlist, denylist)`;
- `_available_actions`, whose filter now reads `(allowlist is None or name in allowlist) and (denylist is None or name not in denylist)`;
- `_run_discord_action`, which keeps the allowlist gate (`if allowlist is not None and action not in allowlist`) and adds a second gate (`if denylist is not None and action in denylist`);
- `_get_dynamic_schema`, which unpacks the pair and threads both lists into `_available_actions`.

## The added mode

Before the PR, `None` meant "no allowlist, every action allowed", and two places branched on it: the schema filter in `_available_actions` and the runtime gate in `_run_discord_action`. The PR keeps that sentinel and adds a second one, `None` for "nothing denied". Each check site now carries two `None` branches, the handler has two refusal gates, and the tuple return and the extra `denylist` parameter exist only to carry the second sentinel.

## The deletion the fix must name

Resolve the config once, at load, into the list of permitted actions. An unset `server_actions` is every action in `_ACTIONS` (the full list). An unset `server_actions_deny` is an empty list. The permitted list is the allowed names minus the denied ones, and a config load failure returns the full list. `_parse_action_names` can take the value to use when the key is unset, or `_load_action_config` can substitute it. `_available_actions(caps, permitted)` then filters on `name in permitted`, and the handler has one `if action not in permitted` refusal.

What disappears:

- the two existing `allowlist is None` checks, in `_available_actions` and in `_run_discord_action`;
- the PR's `denylist is None` and `denylist is not None` checks in the same two places;
- the PR's second runtime gate, since one membership check on the resolved list covers both keys;
- the `(allowlist, denylist)` pair and the `denylist` parameter of `_available_actions`.

Why behavior holds:

- `_available_actions` only iterates `_ACTIONS`. `_run_discord_action` answers "Unknown action" for any name outside `valid_actions`, which is a subset of `_ACTIONS`, before it reaches the config gate. So "no allowlist" and "every name in `_ACTIONS`" admit exactly the same actions, and "nothing denied" and an empty deny list exclude nothing.
- Subtracting the deny list at load gives the same set as checking it on every call, and the deny list still wins over the allowlist.
- A `server_actions` value whose names are all unknown still parses to `[]`, not to the full list, so `test_empty_allowlist_with_valid_values_hides_tools` still drops both tools. Only an unset key becomes the full list.
- Every new behavior test in the PR goes through `get_dynamic_schema_admin`, `get_dynamic_schema_core`, or `discord_admin_handler`, and checks the schema enum, the `disabled by config` text, the logged warning, or the request sent. Each one passes unchanged. The only assertions that change are those on the sentinel itself, `_load_action_config() == (None, None)` and `_available_actions(caps, None)`, which would assert the resolved list instead.

This was checked. With the deletion applied and only those sentinel assertions updated, all 47 tests in `tests/tools/test_discord_tool.py` pass.

## Grades

- FOUND: the review points at the `None` handling in `_available_actions`, `_run_discord_action`, or `_load_action_config`/`_parse_action_names`, and gives the deletion. It must say to represent "unrestricted" as the full action list and "nothing denied" as an empty list at load, or to resolve one permitted set once. It must also say what goes: the `None` checks (the new deny ones and the existing allowlist ones, or "all four"), or the two gates collapsing into one membership check on the resolved set. Wording such as "compute the effective allowed set once, as allowed minus denied with an unset allowlist meaning every action, and check membership in both places" counts, because a plain membership check on that set is what replaces the `None` branches. The review does not need to name every test. A review that resolves the set once but still passes an optional allowlist, or still tests for `None` at a check site, is PARTIAL.
- PARTIAL: the review touches the concern but does not name that deletion. Examples:
  - it says the allow/deny checks repeat between the schema filter and the runtime gate, or must stay in sync, but asks only for a shared predicate such as `_is_action_permitted(name, allowlist, denylist)` that keeps both `None` branches;
  - it names Repeated Switches or Duplicated Code but does not say which branches go;
  - it asks for a new class, strategy, or policy object (for example an `ActionPolicy` wrapping the two lists);
  - it says "this could be simpler" or "consider normalizing" without saying what is normalized and what disappears;
  - it applies the resolved-list idea to the deny list only (unset deny becomes `[]`) and keeps the allowlist's `None` branches;
  - it flags the parallel `None` branches but proposes deleting the runtime gates in `_run_discord_action` because the schema already filters. That is the wrong deletion. The gates exist for a stale cached schema (the code comment says so), and `test_denied_action_blocked_at_runtime` and `test_denylisted_action_blocked_at_runtime` pin them. A review that only says "drop the runtime gate as defense in depth" and never raises the `None` branches is MISSED.
- MISSED: the review does not raise the `None` handling or the parallel gates, or it praises them as they stand.

## Comments that count neither way

- Whether the deny list should win over the allowlist, or whether a denied action deserves a different message from one outside the allowlist.
- The deny refusal not listing the allowed actions the way the allowlist refusal does.
- `Tuple` imported at the top of the module while the plugin-compat block at the bottom also imports it.
- Renaming `_load_allowed_actions_config` without a compat alias. It is private, and the compat check passes.
- Docs for the new key beyond the config comment, or the `server_actions` comment's action list omitting `delete_message`.
- Loading the config twice per call (once for the schema build, once for the gate), or caching it.
- Test style: membership asserts compared with a literal enum, the `caplog` use, or the logger-level fixture.
- Proposing a `!name` syntax inside `server_actions` instead of a second key, unless the review also names the deletion above.
- Praise for extracting `_parse_action_names`.
