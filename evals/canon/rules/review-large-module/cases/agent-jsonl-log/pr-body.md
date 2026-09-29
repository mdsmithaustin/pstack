## What does this PR do?

Anyone running the gateway on a server ends up parsing `agent.log` with regexes to get it into Loki or Elasticsearch, and multi-line tracebacks break every one of those parsers. This adds an opt-in `logs/agent.jsonl` next to `agent.log`: one JSON object per record, with `ts` (UTC, ms), `level`, `logger`, `message`, `session` when a session is active, and `exc` when a traceback is attached. Vector, Fluent Bit and Promtail can tail it as is.

It goes through the same path as the text logs: the async queue listener, `RedactingFormatter`'s redaction (message and traceback), managed-mode permissions, external-rotation detection, and per-profile routing in a multiplexed process. It rotates on its own size and backup count.

```yaml
logging:
  json:
    enabled: true
    level: INFO
```

## Related Issue

No issue; came up setting up Promtail for a gateway on a VPS.

## Type of Change

- [ ] 🐛 Bug fix (non-breaking change that fixes an issue)
- [x] ✨ New feature (non-breaking change that adds functionality)
- [ ] 🔒 Security fix
- [ ] 📝 Documentation update
- [ ] ✅ Tests (adding or improving test coverage)
- [ ] ♻️ Refactor (no behavior change)
- [ ] 🎯 New skill (bundled or hub)

## Changes Made

- `hermes_logging_json.py`: new sibling with `JsonLinesFormatter` and `json_log_settings`, which reads `logging.json` and falls back to INFO / 10 MB / 3 backups on bad values.
- `hermes_logging.py`: `setup_logging` registers `agent.jsonl` through `_add_rotating_handler` when `logging.json.enabled` is true. `_read_logging_section` returns the whole `logging` section, and `_read_logging_config` reads its three keys from it. The record factory also sets `hermes_session_id`, so the formatter doesn't have to parse `session_tag`.
- `hermes_cli/config_defaults.py`: `logging.json` defaults (off).
- `cli-config.yaml.example`: a File Logging section documenting `logging.*`, including `json`.
- `tests/test_hermes_logging.py`: off by default, one object per record with the session, redaction of message and traceback, the level filter, and fallback on bad settings.

## How to Test

1. `scripts/run_tests.sh tests/test_hermes_logging.py`
2. Set `logging.json.enabled: true`, run `hermes gateway`, send a message, and `tail -f ~/.hermes/logs/agent.jsonl | jq .`

## Checklist

### Code

- [x] I've read the [Contributing Guide](https://github.com/NousResearch/hermes-agent/blob/main/CONTRIBUTING.md)
- [x] My commit messages follow [Conventional Commits](https://www.conventionalcommits.org/) (`fix(scope):`, `feat(scope):`, etc.)
- [x] I searched for [existing PRs](https://github.com/NousResearch/hermes-agent/pulls) to make sure this isn't a duplicate
- [x] My PR contains **only** changes related to this fix/feature (no unrelated commits)
- [x] I've run `pytest tests/ -q` and all tests pass
- [x] I've added tests for my changes (required for bug fixes, strongly encouraged for features)
- [x] I've tested on my platform: Ubuntu 24.04

### Documentation & Housekeeping

- [x] I've updated relevant documentation (README, `docs/`, docstrings) — or N/A
- [x] I've updated `cli-config.yaml.example` if I added/changed config keys — or N/A
- [x] I've updated `CONTRIBUTING.md` or `AGENTS.md` if I changed architecture or workflows — or N/A
- [x] I've considered cross-platform impact (Windows, macOS) per the [compatibility guide](https://github.com/NousResearch/hermes-agent/blob/main/CONTRIBUTING.md#cross-platform-compatibility) — or N/A
- [x] I've updated tool descriptions/schemas if I changed tool behavior — or N/A

## Screenshots / Logs

```
{"ts": "2026-09-27T14:02:11.418+00:00", "level": "INFO", "logger": "gateway.run", "message": "telegram: message from 41... queued", "session": "20260927_140211_9f2c"}
```
