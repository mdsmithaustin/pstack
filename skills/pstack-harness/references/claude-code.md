# Claude Code adapter

Observed circa 2026-09. Verify these hints against the live session and prefer its tools and help.

Pass `model`. The spawn tool has no effort field, so the agent type carries the effort. Each `pstack-effort-<level>` agent runs at its level and takes the `model` you pass.

| resolved effort | no persona | a pstack persona |
|---|---|---|
| a level, and `pstack-effort-<level>` is in the live agent catalog | `pstack-effort-<level>` | `pstack-effort-<level>`, with the persona's complete briefing at the top of the prompt |
| a level, but that agent is not in the catalog | `general-purpose` | the persona per the [persona contract](named-roles.md) |
| `inherit-parent` | `general-purpose` | the persona per the persona contract |

Only the live catalog proves an agent is loaded. A file on disk does not. A delegate's own spawns inherit the delegate's effort, so a nested spawn with an `inherit-parent` effort runs at the delegate's level, not the top session's.

**Wait for a child.** A spawned agent runs in the background by default. Its completion notification starts your next turn and carries its report. A child that fails notifies you too, with the error and its last output. So when every remaining task belongs to a running child, say in one line what is running and end the turn. Each child notifies you on its own, so handle each notice and end the turn again while others run. Never wait with `sleep`, a `Monitor` loop, or a read or grep of the child's output file or transcript. Never report a child's result before its notification arrives. Stop a child you no longer need with `TaskStop`. The [shared wait rule](delegation.md) says what you may do while a child runs.

## Invocation and effort hints

`Task` tool (custom agents from `.claude/agents/` spawn by name); `model` takes short aliases

no per-call field; a `pstack-effort-<level>` agent type carries it (see the [effort table above](#claude-code-adapter)). An `inherit-parent` effort, or a session whose catalog lacks the agent, runs at the session effort (`--effort`, `effortLevel`)
