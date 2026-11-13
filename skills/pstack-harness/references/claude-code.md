# Claude Code adapter

Observed circa 2026-09. Verify these hints against the live session and prefer its tools and help.

Pass `model`. Pass a resolved effort level as `effort` when the spawn tool lists that parameter, as it does from Claude Code 2.1.292. It applies under `general-purpose` and under a native persona, and it overrides an agent's own effort, measured on 2.1.322. A `fork` ignores it. When the tool lists no `effort`, the agent type carries the level: each `pstack-effort-<level>` agent runs at its level and takes the `model` you pass.

| resolved effort | no persona | a pstack persona |
|---|---|---|
| a level, and the spawn tool lists `effort` | `general-purpose`, with `effort` | the persona per the [persona contract](named-roles.md), with `effort` |
| a level, no `effort` parameter, and `pstack-effort-<level>` is in the live agent catalog | `pstack-effort-<level>` | `pstack-effort-<level>`, with the persona's complete briefing at the top of the prompt |
| a level, and neither carrier | `general-purpose` | the persona per the persona contract |
| `inherit-parent` | `general-purpose` | the persona per the persona contract |

Always name an agent type, from this table or `fork`. A spawn under any named type other than `fork` starts fresh. Use `fork` only as the [fork restrictions](roles.md#fork-restrictions) allow.

Only the live catalog proves an agent is loaded. A file on disk does not. A delegate's own spawns inherit the delegate's effort, so a nested spawn with an `inherit-parent` effort runs at the delegate's level, not the top session's.

**Wait for a child.** A spawned agent runs in the background by default. Its completion notification starts your next turn and carries its report. A child that fails notifies you too, with the error and its last output.
- So when every remaining task belongs to a running child, end the turn. If a playbook or skill step orders that turn's reply, as an audit tick does, that step alone decides the reply, whether it names the content or orders no reply text. Otherwise say in one line what is running. Each child notifies you on its own, so handle each notice and end the turn again while others run.
- Never wait for a child with `sleep`, a `Monitor` loop, or a read or grep of its output file or transcript. Never report what a child concluded before its notification arrives. A side effect you read yourself, such as its pushed head or opened PR, is yours to report.
- Stop a child you no longer need with `TaskStop`.
- The [shared wait rule](delegation.md) says what you may do while a child runs.

## Invocation and effort hints

`Task` tool (custom agents from `.claude/agents/` spawn by name); `model` takes short aliases

the `effort` parameter on the spawn when the tool lists it, and otherwise a `pstack-effort-<level>` agent type (see the [effort table above](#claude-code-adapter)). A spawn with an `inherit-parent` effort, or with neither carrier, runs at the session effort (`--effort`, `effortLevel`) only when its model is the session's model. On another model it runs at the level Claude Code keeps for that model, or that model's default, from 2.1.317 and measured on 2.1.322. Report that level as unknown unless you observed it

## Writer isolation

Per the Claude Code worktree docs read on 2026-11-12, a subagent's `isolation: worktree` branches from the repository's default branch unless the `worktree.baseRef` setting is `head`. So whenever a writer must start from any other commit, pushed or not, such as your branch or a parent PR's branch, make its worktree with `git worktree add` at the commit its brief names.
