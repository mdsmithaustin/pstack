# Hermes adapter

Observed circa 2026-09. Verify these hints against the live session and prefer its tools and help.

Pass the values through the delegation toolset's fields when it has them, or as `--reasoning` on `hermes -z`. Per the Hermes delegation docs read on 2026-11-12, the default `delegate_task` has no per-task model, effort, or toolsets field. Its children run on the parent's model, or on the one `delegation.model` pins, at `delegation.reasoning_effort` or the parent's effort. When the live schema lists no such field, keep the arm, omit the values, and report the arm as inherited per [role resolution step 5](roles.md#spawn-a-role).

**Wait for a child.** Unverified on an installed Hermes, so read the live `delegate_task` schema first. Per the Hermes delegation docs read on 2026-11-11, a top-level `delegate_task` returns a handle at once and its children run in the background. Put parallel children in one call's `tasks` array (10 at most by default). One message with every result reaches you between turns, after all of them finish. Finish the work that depends on no child, then end the turn. Never wait by polling a child's transcript or artifacts. Hermes sets no wall-clock limit on a child. It interrupts a child that shows no progress for 450 seconds, or 1200 seconds inside a tool, and reports it to you as a timeout or as `stalled`. If the call returns the results itself, it already waited. The [shared wait rule](delegation.md) says what you may do while a child runs.

**One-shot runs.** Unverified on an installed Hermes. Per the same docs, a one-shot run (`hermes -z`, `hermes chat -q`, `--oneshot`) may spawn at most `delegation.oneshot_max_children` children in total, 2 by default and unlimited at `0`, and a spawn past the cap returns a tool error. When that error arrives, run each remaining arm by the next route in [Spawn a subagent](delegation.md), keep the arm count, and report the cap and the config key. A one-shot run's skills prompt also asks for domain skills only, so the brief for a `hermes -z` arm names each pstack skill that arm must load.

## Invocation and effort hints

a delegation toolset when enabled; `hermes -z` for one-shot subprocess runs. `delegate_task` starts every child with a fresh conversation and has no fork option. The child sees only the `goal` and `context` you pass, plus the workspace's project context files, so the brief carries everything else

`--reasoning <value>` on `hermes -z`; config `agent.reasoning_effort` and per-model `agent.reasoning_overrides`. Per the delegation docs above the default `delegate_task` takes no effort field, so check its schema in session before you pass one

## Writer isolation

Per the Hermes worktree docs read on 2026-11-12, in a repository where Hermes itself has made a worktree, Hermes sweeps `.worktrees/` at `hermes -w` startup and every 6 hours. It archives and then removes a named tree that has been idle for 72 hours, unless a live process works inside it, and it deletes that tree's local branch when no remote has the branch. `hermes worktree restore <name>` brings an archived tree back, and `worktrees.archive_dirty: false` keeps every tree that holds uncommitted or unpushed work. So push a writer's branch before a pause that long, and after one, check that each recorded worktree still exists before you rely on it.
