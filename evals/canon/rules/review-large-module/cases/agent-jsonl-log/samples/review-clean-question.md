## Review: `feat/logging-jsonl`

Nice feature, and the implementation reuses the existing handler path instead of building a second one, so rotation, permissions, and redaction all come along.

### Comments

1. **Formatter.** `JsonLinesFormatter` redacts both `message` and `exc`, and the UTC millisecond `ts` sorts correctly in Loki. Good.
2. **Session id.** Adding `hermes_session_id` to the record factory avoids parsing `session_tag`. The name is namespaced, so it won't collide with `extra={...}` keys. Fine.
3. **Settings parsing.** `json_log_settings` falling back to 10 MB and 3 backups on bad input means the file always rotates, which is the right failure mode for a log file.
4. **Question, not blocking.** `hermes_cli/config_defaults.py` is past 3,100 lines now, well beyond the 2,000-line split signal in `AGENTS.md`. I assume that rule is meant for modules with behavior rather than a pure-data defaults table like this one. Is that the intended reading? No change needed in this PR either way.
5. **Multiplex.** Secondary profiles inherit the launch profile's `logging.json` choice. Worth a sentence in the docs.
6. **Level.** An unknown `level` quietly becomes INFO. Consider warning once.
7. **Tests.** Good coverage: off by default, session, redaction, level filter, and bad settings.

Approve.
