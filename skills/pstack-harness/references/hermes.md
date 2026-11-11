# Hermes adapter

Observed circa 2026-09. Verify these hints against the live session and prefer its tools and help.

Pass the values through the delegation toolset's fields when it has them, or as `--reasoning` on `hermes -z`.

**Wait for a child.** Unverified on an installed Hermes, so read the live `delegate_task` schema first. Per the Hermes delegation docs read on 2026-11-11, a top-level `delegate_task` returns a handle at once and its children run in the background. Put parallel children in one call's `tasks` array (10 at most by default). One message with every result reaches you between turns, after all of them finish. Finish the work that depends on no child, then end the turn. Never wait by polling a child's transcript or artifacts. Hermes sets no wall-clock limit on a child. It interrupts a child that shows no progress for 450 seconds, or 1200 seconds inside a tool, and reports it to you as a timeout or as `stalled`. If the call returns the results itself, it already waited. The [shared wait rule](delegation.md) says what you may do while a child runs.

## Invocation and effort hints

a delegation toolset when enabled; `hermes -z` for one-shot subprocess runs. `delegate_task` starts every child with a fresh conversation and has no fork option. The child sees only the `goal` and `context` you pass, plus the workspace's project context files, so the brief carries everything else

`--reasoning <value>` on `hermes -z`; config `agent.reasoning_effort` and per-model `agent.reasoning_overrides`. Whether the delegation toolset takes an effort field is unverified: check its schema in session
