---
name: harness
description: How pstack's delegation primitives map to each CLI — spawning subagents, per-subagent models, parallelism, read-only posture, structured questions, loops, and transcript access in Claude Code, Codex, and Hermes. Read whenever a pstack skill says spawn, Task, subagent, or model and you are unsure how to realize that in the current harness.
---

# Harness adapters

pstack skills describe delegation abstractly: "spawn a subagent on model X", "launch N in parallel in one message", "readonly", "AskQuestion". This skill maps each primitive to the harness you are actually running in. Never invent a tool. If the primary mechanism below is not available in your session, use its fallback, and say in your reply which mechanism you used.

## Claude Code

- **Spawn**: the `Task` (Agent) tool, `subagent_type: general-purpose`, or a registered custom agent from `.claude/agents/` by name. Parallelism is real: put every independent `Task` call in a single message.
- **Model**: the tool's `model` parameter takes short aliases (`sonnet`, `opus`, `haiku`; `fable` where entitled). If a configured slug is rejected, fall back per the skill's slug-fallback rule or omit `model` (that is `inherit-parent`).
- **Read-only**: there is no `readonly` parameter. State it in the brief ("read-only: do not edit or write files") and prefer read-only agent types (e.g. Explore) where the session offers them.
- **Isolation / "cloud" workers**: one git worktree per writer; long work via background shells or the harness's background/cloud agents where available.
- **Questions**: `AskUserQuestion`. **Loop**: `/loop`.
- **Transcripts**: `~/.claude/projects/<slug>/*.jsonl`, `<slug>` = the workspace path with every `/` turned into `-` (so `/Users/you/proj` becomes `-Users-you-proj`).

## Codex

- **Spawn**: no in-session subagent tool. Delegate by running the CLI itself as a subprocess: `codex exec "<brief>"`, one process per arm, each arm in its own git worktree, launched concurrently as background shells; collect each arm's report from stdout or a file path named in the brief. Check `codex exec --help` for the model and sandbox flags your version supports.
- **Fallback** when subprocesses are unavailable: run the arms sequentially inline — one arm at a time, its own worktree, its report written to a file before the next arm starts — then synthesize. Keep the configured arm count.
- **Model**: pin per subprocess with the exec model flag when it exists; otherwise everything is `inherit-parent` and panels run same-model with differentiated briefs.
- **Questions**: a plain chat message. **Loop**: re-invoke on an interval (wrapper script, cron, CI).
- **Transcripts**: `~/.codex/sessions/<year>/<month>/<day>/rollout-*.jsonl`.

## Hermes

- **Spawn**: the delegation toolset (Task Delegation), when enabled — treat it as the `Task` equivalent, including any model option it exposes. When it is disabled, subprocess instead: `hermes -z "<brief>" -m <model> --worktree`, one one-shot run per arm, concurrently in background shells.
- **Model**: the delegation tool's model option, or `-m` on the subprocess; a slug Hermes does not serve means `inherit-parent`.
- **Questions**: the clarify toolset when enabled; otherwise a plain chat message. **Loop**: `hermes cron`, or a re-invoking wrapper.
- **Transcripts**: a SQLite store, not files to glob — `hermes sessions list` to find the session, `hermes sessions export` (JSONL or Markdown) to read it.

## Universal rules

- **Panels degrade by model, never by count.** A four-model panel in a one-model harness is still four arms (parallel or sequential), each with a genuinely different brief; the list length in `~/.agents/pstack-models.md` sets the count.
- **Cursor-era `Task` parameters are not real here.** `readonly`, `environment: "cloud"`, and `is_background` in a skill's text describe intent, not literal arguments: realize them as a read-only brief, worktree isolation, and background execution.
- **Config**: `~/.agents/pstack-models.md` maps roles to models. Any value not valid in the current harness is `inherit-parent`. Never pass a model value you have not confirmed this harness accepts.
- **Privacy**: transcript access stays inside the current workspace's sessions, whichever store holds them.
- **Honesty**: never report parallel arms that actually ran sequentially; name the mechanism used.
