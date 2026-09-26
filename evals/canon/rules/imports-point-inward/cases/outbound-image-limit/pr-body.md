## What does this PR do?

Send-path eviction retires the oldest tool-result screenshots once a request would carry more than 20 images or 24 MB of image bytes. 20 is the point where Anthropic applies its stricter per-image dimension cap, which is the right default, but on Gemini and OpenAI a long `computer_use` session throws away frames the model could still have used. I run most of my desktop automation on Gemini and the agent keeps losing track of what it clicked two screens ago.

This adds two `config.yaml` keys under `vision:`:

- `outbound_image_limit` (default 20, clamped 4..100)
- `outbound_image_budget_mb` (default 24, clamped 1..30)

Both passes (`evict_stale_outbound_tool_images` on the OpenAI-shaped list and `_evict_old_screenshots` on the Anthropic wire list) go through `outbound_image_retire_count`, so the configured values are resolved there when a caller doesn't pass `limit`/`budget`. That keeps the two passes on one frontier (#113517) without touching either call site. The upper clamps are the provider hard limits (100 images per request on 200K-context models, 32 MB request size with 2 MB left for text).

## Related Issue

No issue yet. Happy to open one if you'd prefer.

## Type of Change

- [ ] 🐛 Bug fix (non-breaking change that fixes an issue)
- [x] ✨ New feature (non-breaking change that adds functionality)
- [ ] 🔒 Security fix
- [ ] 📝 Documentation update
- [ ] ✅ Tests (adding or improving test coverage)
- [ ] ♻️ Refactor (no behavior change)
- [ ] 🎯 New skill (bundled or hub)

## Changes Made

- `agent/image_eviction_policy.py`: `resolve_outbound_image_limit()` and `resolve_outbound_image_budget_bytes()` read and clamp the new `vision.*` keys; `limit`/`budget` on `outbound_image_retire_count` default to them. Explicit arguments still win.
- `hermes_cli/config_defaults.py`: defaults for the two keys under `vision`.
- `tests/agent/test_image_eviction_policy.py`: one test that both passes move together under a raised limit, one for the clamps.
- `cli-config.yaml.example`, `website/docs/user-guide/features/vision.md`: documented.

## How to Test

1. `scripts/run_tests.sh tests/agent/test_image_eviction_policy.py tests/agent/test_outbound_stale_vision.py tests/tools/test_computer_use.py`
2. Set `vision.outbound_image_limit: 40` and run a `computer_use` session past 20 screenshots on a Gemini model. With `HERMES_DUMP_REQUESTS=1`, the dumped request keeps all frames until the 41st, then one batch of 8 is replaced by `[screenshot removed to save context]`.
3. Leave the keys unset and repeat: retirement starts at 21 as before.

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
