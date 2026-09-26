## What does this PR do?

The `💾 Cache:` line tells you how many prompt tokens hit the cache and how many were written, but not what that is worth. A cache read bills at a fraction of the input rate and a cache write at a premium over it, so a 60% hit rate can be a big saving on one route and close to break-even on another.

This adds the net dollar figure. Each priced response computes reads at the gap between the input and cache-read rates, minus writes at the gap between the cache-write and input rates, with context-tier rates applied to the whole request. The per-call line shows it, the session keeps a running total, and `/usage` prints the total.

## Related Issue

No issue; came up while comparing cache behaviour across Anthropic and OpenRouter routes.

## Type of Change

- [ ] 🐛 Bug fix (non-breaking change that fixes an issue)
- [x] ✨ New feature (non-breaking change that adds functionality)
- [ ] 🔒 Security fix
- [ ] 📝 Documentation update
- [ ] ✅ Tests (adding or improving test coverage)
- [ ] ♻️ Refactor (no behavior change)
- [ ] 🎯 New skill (bundled or hub)

## Changes Made

- `agent/cache_savings.py`: new module with `cache_savings_usd`, `estimate_cache_savings`, and the label/line formatters.
- `agent/turn_usage.py`: `record_response_usage` prices the saving for the aggregator's real route (same as the cost estimate), adds it to `session_cache_savings_usd`, and the `💾 Cache:` line uses `format_cache_line`.
- `agent/agent_init.py`, `run_agent.py`: new `session_cache_savings_usd` counter, zeroed by `reset_session_state`.
- `hermes_cli/cli_info_mixin.py`: `/usage` prints `Prompt cache: saved ~$X` when the total is non-zero.
- `tests/agent/test_cache_savings.py`: rate-gap math, tiered rates, unknown and subscription-included routes, and session accumulation plus reset through a real `AIAgent`.

## How to Test

1. `scripts/run_tests.sh tests/agent/test_cache_savings.py tests/agent/test_turn_usage_log_line.py tests/agent/test_usage_pricing.py`
2. Run `hermes` with verbose output on an Anthropic model, send two messages, and check the second `💾 Cache:` line ends with `saved ~$…`.
3. Run `/usage` and check the `Prompt cache:` row.

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
   💾 Cache: 100,000/120,000 tokens (83% hit, 10,000 written, saved ~$0.26)
```
