---
name: pstack-harness
description: Maps pstack's delegation primitives to the current CLI (Claude Code, Codex, Hermes, or any other harness) — how to spawn a subagent, set a per-subagent model, parallelize arms, go read-only, ask a structured question (AskQuestion), open a todolist, loop, and locate the transcript store. Read whenever a pstack skill says spawn, Task tool, subagent_type, per-subagent model, AskQuestion, or todolist and you are unsure how to realize that in this harness, or names a sibling skill you cannot find in your tool inventory.
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

**Set an arm's effort.** Every role resolves to a model and a reasoning effort (see **The models config** below). Pass the effort through the spawn mechanism when it has a field or flag for it. When it has none, or the harness rejects the value, the effort alone becomes `inherit-parent`: keep the model, keep the arm, and say in the reply that the effort was inherited. An effort problem never drops a model or an arm.

**Parallelism.** Real where the mechanism allows it (independent tool calls in one message, concurrent subprocesses); otherwise sequential with the same arm count.

**Read-only.** Use an enforcing option if the spawn mechanism has one; otherwise state it plainly in the brief ("read-only: do not edit or write files").

**Structured questions (`AskQuestion`).** Your harness's structured-question tool if it has one; otherwise ask in plain chat.

**Open a todolist.** Your harness's todo or plan-tracking tool if it has one; otherwise keep the list visible another way — a checklist in your reply updated as items land, or a scratch `TODO.md` in the worktree. Missing the tool never cancels the practice: the full plan stated up front, one item in progress at a time, skips marked with a reason, nothing silently dropped.

**Loops and wake-ups.** Your harness's loop or scheduling facility; otherwise a re-invoking wrapper (script, cron, CI).

**Transcripts.** Every harness keeps this workspace's session record somewhere — log files under its data directory, or a database with an export command. Locate yours before reading, and stay inside the current workspace's sessions; other projects' transcripts are private.

## Hints for known harnesses

Observed circa 2026-09. Treat as starting points, not contracts — verify against your live session before relying on any of them, and prefer what you find over what is written here.

| harness | spawn | effort | transcripts |
|---|---|---|---|
| Claude Code | `Task` tool (custom agents from `.claude/agents/` spawn by name); `model` takes short aliases | no per-call field; only the `effort` frontmatter key of a custom agent file. A subagent inherits the session effort (`--effort`, `effortLevel`), so the effort is `inherit-parent` here | JSONL under `~/.claude/projects/<slug>/`, `<slug>` = workspace path with `/` → `-` |
| Codex | `spawn_agent` (the multi-agent feature, stable in 0.152) takes a model and a reasoning effort per spawn; custom roles live in `~/.codex/agents/*.md` or `.codex/agents/*.md` with `model` and `model_reasoning_effort`; `codex exec` is the subprocess route | the reasoning-effort field on `spawn_agent`; `-c model_reasoning_effort=<value>` on `codex exec`. A model set without an effort gets that model's default effort (medium on the GPT-5.6 family), not the parent's, so always pass one | JSONL under `~/.codex/sessions/` by date |
| Hermes | a delegation toolset when enabled; `hermes -z` for one-shot subprocess runs | `--reasoning <value>` on `hermes -z`; config `agent.reasoning_effort` and per-model `agent.reasoning_overrides`. Whether the delegation toolset takes an effort field is unverified: check its schema in session | SQLite store; `hermes sessions` subcommands list and export |

## Universal rules

- **Panels degrade by model, never by count.** A four-model panel in a one-model harness is still four arms (parallel or sequential), each with a genuinely different brief; the configured list length sets the count.
- **Named sibling skills are files.** When a pstack skill says "the architect skill" or "read the leaf skill", it names a sibling directory under the same installed skills root. Most pstack skills are gated against model invocation, so they appear in no tool inventory and their descriptions are not in context — that never means missing. Read the named skill's SKILL.md (and any files it references) directly and follow it; record that you applied it by file read. Never edit a skill's gating to make it invocable.
- **Tool names in skill text describe intent, never a required tool.** `Task`, `Glob`, `Grep`, `Read`, a todolist, and Cursor-era parameters like `readonly`, `environment: "cloud"`, and `is_background` name capabilities: realize each with whatever your session provides (a search tool, a shell command, a read-only brief, worktree isolation, background execution). A missing tool never cancels the step — find the equivalent, and never report a step blocked on a tool name.
- **Config**: roles resolve to a model and an effort per **The models config** below. A value the current harness cannot use is `inherit-parent` for that field only.
- **Honesty**: never report parallel arms that actually ran sequentially; name the mechanism used.
- **No improvised models**: every spawn resolves through a named role. A spawn whose skill names no role resolves through the `default` line, then `inherit-parent`. Never pick a model that neither the config nor the skill's inline default names, and say which role the model came from.

## The models config

`~/.agents/pstack-models.md` (user) and `.agents/pstack-models.md` (workspace) map each role to a model and a reasoning effort. `setup-pstack` writes and lints the file; its shipped default is `examples/pstack-models.md` next to that skill.

**Grammar.** `role: entry`, or `role, role: entry` to bind several roles at once. Panel roles (`how critics`, `arena runners`, `arena cross-judge pool`, `architect runners`, `interrogate reviewers`) take a comma list, one arm per entry. An entry is `model` or `model@effort`. Efforts are `none`, `low`, `medium`, `high`, `xhigh`, `max`; `ultra` is Codex's Pro mode and is valid only on `gpt-5.6-sol`. `inherit-parent` and `auto`, with or without `@effort`, run the arm on the parent chat model. A `## codex`, `## claude-code`, or `## hermes` header starts a section whose lines apply to that harness only; lines above any header apply everywhere. Two roles are special. `trail reviewer` is the show-me-your-work reviewer; when it resolves to the model that did the work, show-me-your-work steps down one tier so the review stays cross-model. `default` is the entry for any spawn whose skill names no role; it ships as `inherit-parent`.

**Precedence.** Resolve the model and the effort of a role separately, taking the first level that has a value:

1. workspace file, this harness's section
2. workspace file, flat lines
3. user file, this harness's section
4. user file, flat lines
5. the skill's inline default for the model; the effort policy below for the effort
6. the `default` line, searched through levels 1 to 4, for a spawn whose skill names no role or whose role has no inline default
7. `inherit-parent`: the value is `inherit-parent` or `auto`, the harness has no way to set that field, or the harness rejected the value

A section never leaks into another harness. A workspace flat line beats a user harness line, so the old rule "workspace wins per role" still holds.

**Codex alias translation.** On Codex, a Claude alias that reaches step 7 translates instead of inheriting:

| alias | Codex entry | why |
|---|---|---|
| `fable` | `gpt-5.6-sol@max` | Sol at max is the Fable-parity tier |
| `opus` | `gpt-5.6-sol@xhigh` | Sol at high or xhigh matches Opus |
| `sonnet` | `gpt-5.6-terra@high` | Terra is the balanced, mini-like tier, Sonnet's role |
| `haiku` | `gpt-5.6-luna@high` | Luna is the high-throughput, nano-like tier; the floor keeps it at high |

The translated effort belongs to the alias and stands unless the entry wrote its own `@effort`. Hermes has no translation table yet; an alias there is `inherit-parent`, as before.

**Effort policy.** When no `@effort` is written: floor `high` for every role. `xhigh` for hardest tasks, judgment and prose, bug-fix, perf-issue, hillclimb, how explainer, how critics, why synthesizer, reflect judgment, divergent and synthesizer, arena cross-judge pool, architect runners, and trail reviewer. Nothing in this policy produces `max` or `ultra`; those come only from an explicit `@max` or `@ultra` on a line, from the Codex translation of `fable`, or from an explicit escalation in the task. Effort never changes an arm count or a model choice.
