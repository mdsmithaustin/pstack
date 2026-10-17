# Grok Build adapter

Observed circa 2026-09. Verify these hints against the live session and prefer its tools and help.

Resolve with `--harness grok`. Pass `model` only when `spawn_subagent` lists the argument. With subagent model inheritance on and an all-xAI catalog, Grok hides it and rejects a spawn that names one, so the arm runs on the parent model. The spawn takes no effort, so a resolved level runs at the session effort and [role resolution step 5](roles.md#spawn-a-role) reports it.

## Invocation and effort hints

`spawn_subagent`. On 1.0.41 its schema has no agent type and no argument names a persona, so pass a pstack persona's full briefing in `prompt`, prefix `description` with that persona's name in brackets, such as `[poteto-agent]` or `[comment-sicko]`, so the subagent label shows it, and on `resume_from` keep the tag but skip the briefing because the child already has it. Grok loads the `~/.claude/agents/` wrappers as agent types, and its source honors a `subagent_type` key that arrives, but the schema hides the key and a model told to send it dropped it in a 2026-09 probe, so do not rely on naming the type. A `model` argument appears unless subagent model inheritance is on (default off, settable remotely) and every catalog model is xAI. Only the top-level session spawns, so a delegate cannot fan out. Per Grok 1.0.52's docs, `isolation: worktree` makes a copy under `~/.grok/worktrees/` whose kind follows `cli.worktree_type` (`linked`, `standalone`, or `git`, and Grok can set it remotely) and the Grove settings, and a spawn that omits `isolation` takes a role or persona default. For a standalone clone, `git worktree list` omits it and `git worktree remove` refuses it. Remove a stray copy with `grok worktree rm --dry-run <path>`, then `grok worktree rm <path>`, which keeps a copy with unsaved work unless you pass `-f`. `grok worktree gc --max-age <age>` also keeps such a copy. [Writer isolation](#writer-isolation) says when to pass `isolation: none` and `cwd`. `grok -p` is the subprocess route

no per-spawn field; `reasoning_effort` on a Grok role or persona, otherwise the session effort, so the effort is `inherit-parent` here. `--effort <value>` on `grok -p`

## Writer isolation

Grok Build's `isolation: worktree` can make a standalone clone instead, so a writer there that needs a git worktree gets one from `git worktree add`. On Grok Build, spawn every writer with `isolation: none`, because a Grok role or persona default turns isolation on when the field is omitted. Pass the writer's directory as `cwd` when `spawn_subagent` lists that argument.
