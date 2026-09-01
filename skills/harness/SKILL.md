---
name: harness
description: How pstack's delegation primitives map to whatever CLI is running them — spawning subagents, per-subagent models, parallelism, read-only posture, structured questions, loops, and transcript access. Read whenever a pstack skill says spawn, Task, subagent, or model and you are unsure how to realize that in the current harness.
---

# Harness adapters

pstack skills describe delegation abstractly: "spawn a subagent on model X", "launch N in parallel in one message", "readonly", "AskQuestion". Each is an intent, not a tool name. Satisfy the intent with whatever your session actually provides — your live tool inventory and your CLI's own help are the authority, not this file. Never invent a tool, and say in your reply which mechanism you used.

## The primitives

**Spawn a subagent.** In order of preference:

1. Your harness's native subagent or delegation tool, whatever it is called.
2. No such tool → invoke your own CLI non-interactively as a subprocess (its help names the command and flags), one invocation per arm, run concurrently in background shells, each arm's report collected from stdout or a file path named in its brief.
3. No subprocesses either → run the arms sequentially inline, one at a time, each writing its report to a file before the next starts, then synthesize. Keep the configured arm count.

Each writer gets its own git worktree, whichever mechanism spawns it.

**Set an arm's model.** Pass the model through whatever the spawn mechanism accepts — a tool parameter, a CLI flag. Only pass a value this session has confirmed the mechanism accepts; anything unconfirmed or rejected means `inherit-parent`: omit the model and let the arm run on the session model.

**Parallelism.** Real where the mechanism allows it (independent tool calls in one message, concurrent subprocesses); otherwise sequential with the same arm count.

**Read-only.** Use an enforcing option if the spawn mechanism has one; otherwise state it plainly in the brief ("read-only: do not edit or write files").

**Structured questions (`AskQuestion`).** Your harness's structured-question tool if it has one; otherwise ask in plain chat.

**Loops and wake-ups.** Your harness's loop or scheduling facility; otherwise a re-invoking wrapper (script, cron, CI).

**Transcripts.** Every harness keeps this workspace's session record somewhere — log files under its data directory, or a database with an export command. Locate yours before reading, and stay inside the current workspace's sessions; other projects' transcripts are private.

## Hints for known harnesses

Observed circa 2026-09. Treat as starting points, not contracts — verify against your live session before relying on any of them, and prefer what you find over what is written here.

| harness | spawn | transcripts |
|---|---|---|
| Claude Code | `Task` tool (custom agents from `.claude/agents/` spawn by name); `model` takes short aliases | JSONL under `~/.claude/projects/<slug>/`, `<slug>` = workspace path with `/` → `-` |
| Codex | had no in-session subagent tool; `codex exec` was the subprocess route | JSONL under `~/.codex/sessions/` by date |
| Hermes | a delegation toolset when enabled; `hermes -z` for one-shot subprocess runs | SQLite store; `hermes sessions` subcommands list and export |

## Universal rules

- **Panels degrade by model, never by count.** A four-model panel in a one-model harness is still four arms (parallel or sequential), each with a genuinely different brief; the list length in `~/.agents/pstack-models.md` sets the count.
- **Cursor-era `Task` parameters describe intent.** `readonly`, `environment: "cloud"`, and `is_background` in a skill's text are not literal arguments unless your tool has them: realize them as a read-only brief, worktree isolation, and background execution.
- **Config**: `~/.agents/pstack-models.md` maps roles to models. Any value not valid in the current harness is `inherit-parent`.
- **Honesty**: never report parallel arms that actually ran sequentially; name the mechanism used.
