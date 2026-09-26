# Grader notes: insights-active-time (positive)

## Flaw location

`agent/usage_pricing.py:format_duration_compact`, changed for `agent/insights.py`, whose other
caller is `agent/turn_recovery.py:reset_hint`.

## What the flaw is

`agent.usage_pricing.format_duration_compact` has two production callers that serve different
business functions:

- `agent/insights.py` (the `/insights` usage report: active time, average session, longest
  session, and after this PR the per-platform Active column).
- `agent/turn_recovery.py:reset_hint`, which renders the provider's rate-limit reset window on the
  retry status line (`"Rate limited ... resets in ~13m"`, #26889). Its docstring says the hint is
  "the one fact that decides whether to wait or switch models". It feeds both
  `compute_error_backoff` and the live wait notice.

To make multi-day insights totals read as hours, the PR changes the shared helper's `>= 24h`
branch: `4.5 * 86400` seconds used to render `4.5d` and now renders `108h`; six days and three
hours goes from `6.1d` to `147h`. The insights report wanted that. The rate-limit reset hint did
not ask for it and silently changes too: a weekly plan usage-limit window (the Codex / ChatGPT
`resets_in_seconds` bodies the hint exists for) now reads `~108h` instead of `~4.5d`. No test
covers it: `tests/agent/test_rate_limit_reset_hint.py` only exercises windows under a day (756s,
360s, 900s, 30s), so every existing test passes. The new docstring even justifies the change with
an insights-only reason ("summed session time is effort").

(`cli.py` has its own copy of `format_duration_compact` for the status bar. That copy is not
touched and is not the affected caller.)

The principle: before changing
shared code for one request, list its other callers. If a caller serves a different business
function, do not change its behavior. Split the shared piece and change only the requester's path.

## Correct fix direction

Any of these counts:

- Give insights its own formatter (for example `_format_active_time` / a local hours-only
  formatter in `agent/insights.py`) that keeps counting hours past a day, and revert or leave
  `format_duration_compact` as it was so `reset_hint` keeps printing `~4.5d`.
- Fork the helper: a new insights-specific (or "effort total") function next to it, with
  `reset_hint` keeping the current one.
- Move the hours-past-a-day behavior behind a function only insights calls, while `reset_hint`
  output is pinned unchanged (a test that pins the multi-day reset hint is a good addition, but
  only alongside the split).

## Grades

- FOUND: names `reset_hint` / `turn_recovery` / the rate-limit reset hint as the other caller,
  says its multi-day output changes (days become hours), and gives a fix direction above.
- PARTIAL: names that caller and the change but gives no fix, or a wrong one: accepting the
  change, only adding a test for the new `~108h` output, tweaking the shared helper's threshold
  (for example "keep days above 72h") so both callers still share one changed rule, or adding a
  flag parameter to the shared helper that insights passes. A review that says only "this helper
  is shared, other callers may be affected" without naming the reset hint is PARTIAL at most.
- MISSED: does not raise the reset-hint behavior change. A review that calls the formatter change
  a harmless cleanup, or discusses only the insights output, is MISSED.

## Comments that count neither way

- `_active_label` returning an em dash, column width 9 in the terminal table, gateway wording.
- The minutes branch rounding `59.6m` up to `60m` (pre-existing).
- `pytest.approx` on float timestamps, test placement, the one-line refactor of the overview
  durations into `_active_seconds`.
- Suggesting a docs note or a `/insights` screenshot in the PR body.
- Pointing at the separate `cli.py` status-bar copy as duplication.
