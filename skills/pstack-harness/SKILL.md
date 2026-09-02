---
name: pstack-harness
description: Maps pstack's delegation primitives to the current CLI (Claude Code, Codex, Hermes, or any other harness) — how to spawn a subagent, set a per-subagent model, parallelize arms, go read-only, ask a structured question (AskQuestion), open a todolist, loop, and locate the transcript store. Read whenever a pstack skill says spawn, Task tool, subagent_type, per-subagent model, AskQuestion, or todolist and you are unsure how to realize that in this harness.
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

**Open a todolist.** Your harness's todo or plan-tracking tool if it has one; otherwise keep the list visible another way — a checklist in your reply updated as items land, or a scratch `TODO.md` in the worktree. Missing the tool never cancels the practice: the full plan stated up front, one item in progress at a time, skips marked with a reason, nothing silently dropped.

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

- **Panels degrade by model, never by count.** A four-model panel in a one-model harness is still four arms (parallel or sequential), each with a genuinely different brief; the configured list length sets the count.
- **Tool names in skill text describe intent, never a required tool.** `Task`, `Glob`, `Grep`, `Read`, a todolist, and Cursor-era parameters like `readonly`, `environment: "cloud"`, and `is_background` name capabilities: realize each with whatever your session provides (a search tool, a shell command, a read-only brief, worktree isolation, background execution). A missing tool never cancels the step — find the equivalent, and never report a step blocked on a tool name.
- **Config**: the pstack models config maps roles to models, layered workspace-first — a role line in `.agents/pstack-models.md` (workspace) overrides the same role in `~/.agents/pstack-models.md` (user); roles absent from both fall back to each skill's inline default. Any value not valid in the current harness is `inherit-parent`.
- **Honesty**: never report parallel arms that actually ran sequentially; name the mechanism used.
