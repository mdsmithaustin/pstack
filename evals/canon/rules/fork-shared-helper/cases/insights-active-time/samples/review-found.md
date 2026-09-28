## Review: `insights-platform-active-time`

The feature itself is nice and the insights side is clean. Pulling the drift guard into `_active_seconds` and reusing it for both the overview and the platform breakdown is the right move, and the "per-platform adds up to the overview" test is exactly the kind of invariant test AGENTS.md asks for.

### Blocking: the formatter change leaks into the rate-limit status line

`format_duration_compact` in `agent/usage_pricing.py` is not an insights helper. Its other production caller is `agent/turn_recovery.py:reset_hint`, which renders the provider's reset window on the retry status line and the live wait notice. For a weekly plan usage limit (the Codex `resets_in_seconds` bodies that hint was written for) this PR changes the line from `resets in ~4.5d` to `resets in ~108h`. That's a user-facing regression in a completely different feature, made to serve the insights report, and nothing catches it: `test_rate_limit_reset_hint.py` only covers windows under a day.

The new docstring gives it away too: "summed session time is effort" is an insights reason sitting on a helper the rate-limit path depends on.

Please fork it instead. Give insights its own formatter in `agent/insights.py` (something like `_format_active_time` that keeps counting hours) and use it for the Active column and the overview lines, and leave `format_duration_compact` as it was so `reset_hint` keeps printing days. If you want to be thorough, add a test pinning the multi-day reset hint so the next change to the shared helper has to face it.

### Smaller things

- `_active_label` returns `—` when a platform has no ended sessions. Fine for the terminal table, but in the gateway line you already skip the suffix when `active_seconds` is 0, so the dash never shows there. Formatting inline in the terminal row would be simpler.
- Width 9 on the `Active` column fits `147h 59m` but not much more; probably fine for 30 days.
- `test_platform_lines_show_active_time_on_both_surfaces` finds rows with `startswith("telegram")`; if a platform name ever prefixes another that gets flaky. Not a blocker.

With the formatter split out this is good to merge.
