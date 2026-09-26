## Review: `insights-platform-active-time`

Looks good overall. The per-platform breakdown is straightforward and the new tests assert relations rather than snapshots, which matches how the rest of `test_insights.py` is moving.

### The duration formatter change also hits the rate-limit hint

Heads up that `format_duration_compact` is also called from `agent/turn_recovery.py:reset_hint`. With this change a long reset window renders in hours, so a weekly plan limit shows `resets in ~108h` on the retry status line where it used to say `~4.5d`. That's a behavior change for rate-limited users that the PR body doesn't mention.

I think hours past a day is probably acceptable for most windows, but 108h is hard to read. Maybe switch back to days only above 72h so both reports stay readable, and add a case to `test_rate_limit_reset_hint.py` for a multi-day `resets_in_seconds` so the output is pinned either way.

### Other notes

- `_active_seconds` is a nice extraction; the overview now reads much better.
- `_active_label`'s em dash only appears in the terminal table; the gateway branch filters zero before calling it, so that path is dead there.
- The Active column header is right-aligned at width 9 while the other numeric columns use wider fields. Cosmetic.
- Consider mentioning the new column in the `/insights` docs page if there is one.

Approving once the reset-hint output question is settled.
