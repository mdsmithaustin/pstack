## Review: `insights-platform-active-time`

Nice small feature. I read through `agent/insights.py`, the formatter tweak in `agent/usage_pricing.py`, and the tests.

### What's good

- `_active_seconds` consolidates the clock-drift guard that the overview had inline, and the platform breakdown reuses it, so the per-platform numbers are guaranteed to add up to the overview. The test asserting exactly that is the right shape.
- Keeping hours past a day in `format_duration_compact` is a readability win for the report; `52h 10m` next to `3h 15m` in a column is much easier to compare than `2.2d`.
- Both surfaces are covered: terminal table column and gateway suffix.

### Suggestions

1. `_active_label` takes the whole platform row but only reads `active_seconds`. Passing the number would make it reusable for the overview lines too, which still call `format_duration_compact` directly with a leading `~`.
2. In the gateway branch you check `p["active_seconds"]` before calling `_active_label`, so its `—` fallback is unreachable there. Either drop the check or drop the fallback.
3. The terminal header uses `{'Active':>9}`. For a heavy user over 30 days `147h 59m` is 8 chars, so it fits, but a `--days 365` report could overflow. Maybe widen to 10.
4. The `test_platform_lines_show_active_time_on_both_surfaces` test locates rows via `startswith("telegram")`. Fine today; a regex on the row would be sturdier.
5. Minor: the commit message says "same drift guard as the overview", which is accurate; could also mention the per-platform sum invariant.

No blockers from me. Ship it after the small cleanups if you like.
