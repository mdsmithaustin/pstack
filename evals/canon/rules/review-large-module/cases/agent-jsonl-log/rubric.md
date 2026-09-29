# Grading guide: JSON-lines log file (near-miss)

## The look-alike

`hermes_cli/config_defaults.py` grows from 3,121 to 3,130 lines with a new `logging.json` block. `cli-config.yaml.example` grows from 2,289 to 2,304 lines with a new "File Logging" section. Both files are far past 1,000 lines, and the PR adds a block for a new feature to each. A reviewer checking file sizes may read this as a very large file taking on another responsibility and ask to split it. The repo's `AGENTS.md` adds a pull the same way: it calls a file passing about 2,000 lines "the signal to split along `<stem>_<topic>` FIRST".

## Why it is correct as written

Both files are data. `config_defaults.py` describes itself in its docstring: "Default configuration data for Hermes Agent: DEFAULT_CONFIG and OPTIONAL_ENV_VARS. Pure-data leaf module ... Comments are the user-facing docs of config.yaml." `DEFAULT_CONFIG` is one dict, a single table holding the default of every setting. Every feature's defaults live there by design, and `hermes_cli/config.py` calls it "the single source of truth for documented roots". The new block is 9 lines inside the existing `logging` section. `cli-config.yaml.example` is the example config users copy, and it is data too.

The behavior is where the repo wants it. It lives in a new 65-line sibling, `hermes_logging_json.py`, and 16 lines of wiring in `hermes_logging.py`, which goes from 820 to 836 lines. `AGENTS.md`'s rule is about behavior ("New behaviour goes in a new or topical sibling — never appended to a facade"), and this PR follows it. No file that holds behavior gets near 1,000 lines.

## Grades

- CLEAN. The review leaves the size of `config_defaults.py` and `cli-config.yaml.example` alone. It says nothing about them, or says they are data or tables and fine to grow, or asks about their size as an open question without asking for a change in this PR.
- FALSE_ALARM. The review flags `config_defaults.py` or `cli-config.yaml.example` as too large, or treats the new block as a new responsibility added to them. Examples: asking to split `config_defaults.py` (per feature, per section, or into `<stem>_<topic>` siblings) before or in this PR; asking to move the `logging.json` defaults out of `DEFAULT_CONFIG` into `hermes_logging_json.py` or another module; holding the PR until the file is split. Citing `AGENTS.md`'s 2,000-line rule against `config_defaults.py` as a problem with this PR also counts.

## Comments that count neither way

- `hermes logs` does not tail `agent.jsonl`, or debug bundles do not include it.
- The choice of JSON fields (no `pid`, thread, component, or profile), the timestamp format, or `ensure_ascii=False`.
- Secondary profiles in a multiplexed process inheriting the launch profile's `logging.json` setting.
- Reading the `logging` section twice, the `_read_logging_config` refactor, or the lazy import in `setup_logging`.
- The `hermes_session_id` attribute name on every record.
- An unknown `level` silently falling back to INFO instead of warning.
- The website configuration docs not being updated.
- Test style, such as writing config with `yaml.dump` or filtering records by logger name.
- `stack_info` not being emitted.
- The size of `hermes_logging.py` (836 lines) or of `tests/test_hermes_logging.py` (874 lines). Both stay under 1,000.
