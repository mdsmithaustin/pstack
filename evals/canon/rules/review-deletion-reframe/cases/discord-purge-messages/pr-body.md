## What does this PR do?

Clearing out a channel (a raid, a runaway bot, test spam) means one `delete_message` call per message today, and every call counts against Discord's per-channel rate limit. This adds `purge_messages(channel_id, limit)` to `discord_admin`: it fetches the channel's newest `limit` messages (max 100) and deletes them with one `POST /channels/{id}/messages/bulk-delete`.

Discord's bulk endpoint has two rules that shape the action. It takes 2 to 100 ids and answers 400 (code 50016) for fewer, so when only one message is deletable the action sends the per-message `DELETE` instead. It also rejects the whole batch if any id is older than 14 days (code 50034), so older messages are left in place and reported as `skipped_older_than_14_days`.

## Related Issue

No issue; came up moderating a server after a spam wave.

## Type of Change

- [ ] 🐛 Bug fix (non-breaking change that fixes an issue)
- [x] ✨ New feature (non-breaking change that adds functionality)
- [ ] 🔒 Security fix
- [ ] 📝 Documentation update
- [ ] ✅ Tests (adding or improving test coverage)
- [ ] ♻️ Refactor (no behavior change)
- [ ] 🎯 New skill (bundled or hub)

## Changes Made

- `tools/discord_tool.py`: `_purge_messages` and its manifest entry (an admin action; the bot needs MANAGE_MESSAGES), a 403 hint, and the `limit` description covering purge.
- `hermes_cli/config_defaults.py`: `purge_messages` added to the action list in the `server_actions` comment.
- `tests/tools/test_discord_tool.py`: recent messages go in one bulk request; a single message, alone or among old ones, uses the per-message DELETE; messages older than two weeks are skipped; nothing is sent when only old messages remain; a 403 names MANAGE_MESSAGES.

## How to Test

1. `scripts/run_tests.sh tests/tools/test_discord_tool.py`
2. In a test server, post three messages and ask the bot to purge the last three; then post one and ask it to purge the last one.

## Checklist

### Code

- [x] I've read the [Contributing Guide](https://github.com/NousResearch/hermes-agent/blob/main/CONTRIBUTING.md)
- [x] My commit messages follow [Conventional Commits](https://www.conventionalcommits.org/) (`fix(scope):`, `feat(scope):`, etc.)
- [x] I searched for [existing PRs](https://github.com/NousResearch/hermes-agent/pulls) to make sure this isn't a duplicate
- [x] My PR contains **only** changes related to this fix/feature (no unrelated commits)
- [x] I've run `pytest tests/ -q` and all tests pass
- [x] I've added tests for my changes (required for bug fixes, strongly encouraged for features)
- [x] I've tested on my platform: macOS 15.5

### Documentation & Housekeeping

- [x] I've updated relevant documentation (README, `docs/`, docstrings) — or N/A
- [x] I've updated `cli-config.yaml.example` if I added/changed config keys — or N/A
- [x] I've updated `CONTRIBUTING.md` or `AGENTS.md` if I changed architecture or workflows — or N/A
- [x] I've considered cross-platform impact (Windows, macOS) per the [compatibility guide](https://github.com/NousResearch/hermes-agent/blob/main/CONTRIBUTING.md#cross-platform-compatibility) — or N/A
- [x] I've updated tool descriptions/schemas if I changed tool behavior — or N/A
