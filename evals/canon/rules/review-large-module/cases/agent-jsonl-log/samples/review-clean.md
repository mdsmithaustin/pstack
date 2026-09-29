## Review: `feat/logging-jsonl`

Useful and well placed. Routing `agent.jsonl` through `_add_rotating_handler` means it gets the queue listener, managed-mode permissions, external-rotation detection, and per-profile routing for free, and the redaction runs on the listener thread under the record's own home, the same as `agent.log`.

### Where things live

The formatter and the settings parser are a new sibling, `hermes_logging_json.py`, and `hermes_logging.py` only gains the handler registration and the `_read_logging_section` split. That's the facade-plus-siblings shape `AGENTS.md` asks for. `hermes_cli/config_defaults.py` and `cli-config.yaml.example` both grow, but they're the defaults table and the example config: every feature's defaults go in `DEFAULT_CONFIG`, and the new block sits inside the existing `logging` section. Nothing to move there.

### Findings

- `warning`: in a multiplexed process, a secondary profile gets `agent.jsonl` whenever the launch profile enabled it, because the router mirrors the launch handler set. That's also how `agent.log`'s level and size behave, so it's consistent, but the PR body should say so.
- `nit`: an unknown `level` such as `"LOUD"` silently becomes INFO. A one-time warning would save someone a confused afternoon.
- `nit`: `hermes logs` only knows the text files. Letting `hermes logs --json` tail `agent.jsonl` would be a natural follow-up.
- `nit`: the website's configuration page doesn't mention `logging.json` yet.

### Tests

`test_redacts_message_and_traceback` checks the traceback too, which is the part most JSON formatters get wrong. Filtering records by logger name keeps the tests stable against unrelated startup logs.

Approve.
