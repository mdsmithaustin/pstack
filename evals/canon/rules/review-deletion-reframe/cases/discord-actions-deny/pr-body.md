## What does this PR do?

`discord.server_actions` is an allowlist, so the only way to stop the bot from deleting messages or removing roles today is to list every other action by hand, and to remember to extend that list whenever the tool gains an action. This adds `discord.server_actions_deny`: same format (comma string or YAML list), naming actions to switch off. It wins over `server_actions`, so leaving `server_actions` empty and setting `server_actions_deny: "delete_message,remove_role"` gives a read-mostly bot that can still pin and open threads.

Denied actions are dropped from the `discord` / `discord_admin` schemas and refused at call time, the same two places the allowlist is enforced.

## Related Issue

No issue; came up setting up a community server where the bot should manage pins but never delete anything.

## Type of Change

- [ ] 🐛 Bug fix (non-breaking change that fixes an issue)
- [x] ✨ New feature (non-breaking change that adds functionality)
- [ ] 🔒 Security fix
- [ ] 📝 Documentation update
- [ ] ✅ Tests (adding or improving test coverage)
- [ ] ♻️ Refactor (no behavior change)
- [ ] 🎯 New skill (bundled or hub)

## Changes Made

- `tools/discord_tool.py`: `_load_allowed_actions_config` becomes `_load_action_config()`, which returns `(allowlist, denylist)`. Both keys go through `_parse_action_names`, so they share the string/list handling and the unknown-name warning (now naming the key). `_available_actions` takes the denylist, and `_run_discord_action` refuses a denied action with `disabled by config (discord.server_actions_deny)`.
- `hermes_cli/config_defaults.py`: `discord.server_actions_deny: ""` with a comment.
- `tests/tools/test_discord_tool.py`: loader tests updated for the pair; the deny list hides actions from the admin schema, wins over the allowlist, drops the core tool when it covers every core action, blocks a denied action at runtime and leaves the others running, and drops unknown names with a warning.

## How to Test

1. `scripts/run_tests.sh tests/tools/test_discord_tool.py`
2. Set `discord.server_actions_deny: "delete_message"` in `config.yaml`, restart the gateway, and ask the bot to delete a message: `delete_message` is gone from the `discord_admin` schema, and a call from a stale schema comes back `disabled by config`.

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
