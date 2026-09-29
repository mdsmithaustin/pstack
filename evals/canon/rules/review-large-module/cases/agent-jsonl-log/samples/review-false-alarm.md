## Review: `feat/logging-jsonl`

The feature is useful and the formatter itself is clean: redaction on both `message` and `exc`, UTC timestamps, and the handler goes through `_add_rotating_handler`, so rotation and routing come along.

### Blocking: stop growing `config_defaults.py`

`hermes_cli/config_defaults.py` is 3,121 lines on main and this PR makes it 3,130, and `cli-config.yaml.example` goes past 2,300. `AGENTS.md` is explicit that a file passing about 2,000 lines is the signal to split along `<stem>_<topic>` first, and this file has been past that for a long time. Adding another feature's settings block to it is exactly the pattern that rule is meant to stop.

Please keep the new defaults out of it. Either put a `JSON_LOG_DEFAULTS` dict in `hermes_logging_json.py` next to `json_log_settings`, which already knows the fallbacks, or split `config_defaults.py` first and add the block to a `config_defaults_logging.py` sibling. The same goes for the example: a separate `logging` example file would keep `cli-config.yaml.example` from growing further.

### Other notes

- `nit`: an unknown `level` silently becomes INFO. A warning would help.
- `nit`: secondary profiles inherit the launch profile's JSON setting. Document it.
- The tests are good, especially the traceback redaction check.

Requesting changes for the config placement.
