# Claude Code adapter

Observed circa 2026-09. Verify these hints against the live session and prefer its tools and help.

Pass `model`. The spawn tool has no effort field, so the agent type carries the effort. Each `pstack-effort-<level>` agent runs at its level and takes the `model` you pass.

| resolved effort | no persona | a pstack persona |
|---|---|---|
| a level, and `pstack-effort-<level>` is in the live agent catalog | `pstack-effort-<level>` | `pstack-effort-<level>`, with the persona's complete briefing at the top of the prompt |
| a level, but that agent is not in the catalog | `general-purpose` | the persona per the [persona contract](named-roles.md) |
| `inherit-parent` | `general-purpose` | the persona per the persona contract |

Always name an agent type from this table. Fork mode is on by default from Claude Code 2.1.302, and a spawn under any named type other than `fork` starts fresh. Use `fork` only as the [fork restrictions](roles.md#fork-restrictions) allow.

Only the live catalog proves an agent is loaded. A file on disk does not. A delegate's own spawns inherit the delegate's effort, so a nested spawn with an `inherit-parent` effort runs at the delegate's level, not the top session's.

## Invocation and effort hints

`Task` tool (custom agents from `.claude/agents/` spawn by name); `model` takes short aliases

no per-call field; a `pstack-effort-<level>` agent type carries it (see the [effort table above](#claude-code-adapter)). An `inherit-parent` effort, or a session whose catalog lacks the agent, runs at the session effort (`--effort`, `effortLevel`)
