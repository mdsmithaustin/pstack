## What does this PR do?

`/insights` breaks usage down by platform (sessions, messages, tokens) but says nothing about time, so someone who uses Hermes from Telegram, Discord and the CLI can't see where their hours actually go. This adds an **Active** column to the Platforms table in the terminal report and an "~N active" suffix to the platform lines in the gateway summary.

While testing it on a real 30-day DB, the per-platform and overview totals often passed 24h and rendered as `2.2d` / `1.4d`. For summed session time that reads like calendar days, which it isn't. Durations now keep counting in hours past a day (`52h 10m`, `48h`), which is what you want when reading down the column.

## Related Issue

N/A (came up while looking at my own `/insights` output).

## Type of Change

- [ ] 🐛 Bug fix (non-breaking change that fixes an issue)
- [x] ✨ New feature (non-breaking change that adds functionality)
- [ ] 🔒 Security fix
- [ ] 📝 Documentation update
- [ ] ✅ Tests (adding or improving test coverage)
- [ ] ♻️ Refactor (no behavior change)
- [ ] 🎯 New skill (bundled or hub)

## Changes Made

- `agent/insights.py`: new `_active_seconds(session)` (the overview's existing drift guard, now shared by the overview and the platform breakdown); `_compute_platform_breakdown` sums `active_seconds` per platform; terminal Platforms table gets an `Active` column and the gateway platform lines get `~N active` (via `_active_label`, `—` when no session on that platform has ended).
- `agent/usage_pricing.py`: `format_duration_compact` keeps hours past 24h instead of switching to fractional days.
- `tests/agent/test_insights.py`: per-platform active time adds up to the overview total; both surfaces render it; multi-day totals stay in hours.

## How to Test

1. `scripts/run_tests.sh tests/agent/test_insights.py tests/agent/test_usage_pricing.py`
2. `hermes insights --days 30` with sessions on more than one platform: the Platforms table shows an `Active` column.
3. `/insights` from a gateway chat: each platform line ends with `~Nh Mm active`.

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
