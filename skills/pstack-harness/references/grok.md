# Grok Build adapter

Observed circa 2026-09. Verify these hints against the live session and prefer its tools and help.

Resolve with `--harness grok`. Pass `model` only when `spawn_subagent` lists the argument. With subagent model inheritance on and an all-xAI catalog, Grok hides it and rejects a spawn that names one, so the arm runs on the parent model. The spawn takes no effort, so a resolved level runs at the session effort and [role resolution step 5](roles.md#spawn-a-role) reports it.

**Wait for a child.** `spawn_subagent` runs in the background unless you pass `run_in_background: false`, and returns a subagent ID. Its completion wakes you in a new turn.
- When your next step needs the results, call `get_command_or_subagent_output` once with every child's ID in `task_ids` (20 at most) and a positive `timeout_ms`. That call waits until all of them complete, a user message interrupts it, and `timeout_ms` above `3600000` (one hour) is lowered to it. With `timeout_ms` omitted or `0` the call returns a snapshot at once, so never repeat it that way to wait for a child.
- A wait that times out while a child still runs is no reason to stop the child.
- A `grok -p` run waits 10 minutes after its last turn ends for background work, then stops that work and exits `1`, so hold the turn there with the output call, and call it again each time it times out while a child you need still runs.
- The [shared wait rule](delegation.md) says what you may do while a child runs.

## Invocation and effort hints

`spawn_subagent`. On 1.0.41 its schema has no agent type and no argument names a persona, so pass a pstack persona's full briefing in `prompt`, prefix `description` with that persona's name in brackets, such as `[poteto-agent]` or `[comment-sicko]`, so the subagent label shows it, and on `resume_from` keep the tag but skip the briefing because the child already has it. Grok loads the `~/.claude/agents/` wrappers as agent types, and its source honors a `subagent_type` key that arrives, but the schema hides the key and a model told to send it dropped it in a 2026-09 probe, so do not rely on naming the type.
- Only the top-level session spawns, so a delegate cannot fan out. Each spawn starts with its own context window and none of the lead's conversation. `resume_from` carries a completed subagent's transcript, not the lead's, so the [fork restrictions](roles.md#fork-restrictions) have nothing to restrict here.
- Remove a stray copy under `~/.grok/worktrees/`, which `git worktree remove` refuses, with `grok worktree rm --dry-run <path>`, then `grok worktree rm <path>`, which keeps a copy with unsaved work unless you pass `-f`. `grok -p` is the subprocess route

`--effort <value>` on `grok -p`; the spawn takes no effort field

## Writer isolation

Grok Build's `isolation: worktree` can make a standalone clone instead, so a writer there that needs a git worktree gets one from `git worktree add`. On Grok Build, spawn every writer with `isolation: none`, because a Grok role or persona default turns isolation on when the field is omitted. Pass the writer's directory as `cwd` when `spawn_subagent` lists that argument.
