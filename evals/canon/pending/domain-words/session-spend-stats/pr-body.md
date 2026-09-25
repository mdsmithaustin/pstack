## What does this PR do?

After a long run gets compressed a few times, its token and cost numbers are spread over several session rows, and nothing in the CLI tells you what the whole run used. `hermes sessions list` shows the tip row only, so the numbers you see there are just the part since the last compression.

This adds an optional session id to `hermes sessions stats`. With an id (or a unique prefix) it walks the compression chain root to tip and prints API calls, input/output tokens (cache and reasoning tokens when there are any) and spend summed over every row. Any session in the chain gives the same answer. A `/branch` copy keeps its own numbers and does not pull in its source's. Without an id the command prints the same store-wide counts as before.

## Related Issue

Fixes #

## Type of Change

- [ ] 🐛 Bug fix (non-breaking change that fixes an issue)
- [x] ✨ New feature (non-breaking change that adds functionality)
- [ ] 🔒 Security fix
- [ ] 📝 Documentation update
- [ ] ✅ Tests (adding or improving test coverage)
- [ ] ♻️ Refactor (no behavior change)
- [ ] 🎯 New skill (bundled or hub)

## Changes Made

- `hermes_state_usage.py`: `SessionUsageMixin.chain_usage(session_id)` sums the token and spend columns over `get_compression_lineage()`. Spend prefers the billed figure over the estimate, same as `usage_totals`.
- `hermes_cli/sessions_cmd.py`: `stats` with an id prints the summed totals; unknown ids get the usual "No session" message and exit 1. An empty profile reports the id as not found instead of printing zero counts.
- `hermes_cli/subcommands/sessions.py`: optional `session_id` positional and a description for `stats`.
- `website/docs/user-guide/sessions.md`: documents the id form under Session Statistics.
- Tests: `tests/hermes_state/test_chain_usage.py` (same totals from every member, branch kept separate, unknown id) and `tests/hermes_cli/test_sessions_stats_chain.py` (through the real parser and `cmd_sessions`).

## How to Test

1. `scripts/run_tests.sh tests/hermes_state/test_chain_usage.py tests/hermes_cli/test_sessions_stats_chain.py`
2. Run a CLI session long enough to compress at least once, then `hermes sessions stats <any id from that run>`.
3. `hermes sessions stats` with no id still prints the store counts.

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

## Screenshots / Logs

```
$ hermes sessions stats 20260918_1412
Session: 20260918_141233_5c1e
Compression chain: 3 sessions (20260918_141233_5c1e -> 20260918_163007_a90d)
API calls: 61
Input tokens: 1,482,915
Output tokens: 38,204
Cache read/write tokens: 1,210,440 / 96,318
Spend: $4.1872
```
