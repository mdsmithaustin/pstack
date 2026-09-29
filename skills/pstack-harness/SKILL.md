---
name: pstack-harness
description: Maps pstack's delegation and portable resource primitives to the current CLI (Claude Code, Codex, Hermes, or any other harness). Covers how to locate installed skills and fresh trunk resources, spawn a subagent, set a per-subagent model, parallelize arms, go read-only, ask a structured question (AskQuestion), track a worklist, loop, and locate the transcript store. Read whenever a pstack skill says spawn, Task tool, subagent_type, per-subagent model, AskQuestion, or worklist, names a sibling skill you cannot find, or runs a path from a playbook. Every primitive is named differently per harness, so read this before concluding your harness has no such capability or resource.
---

# Harness adapters

pstack skills describe delegation abstractly: "spawn a subagent on model X", "launch N in parallel in one message", "readonly", "AskQuestion". Each is an intent, not a tool name. Satisfy the intent with whatever your session actually provides. Your live tool inventory and your CLI's own help are the authority, not this file. Never invent a tool. Say which mechanism you used when it affects execution or evidence. For worklists, report the item state rather than the carrier.

## Resolve portable resources

When a pstack workflow uses a `PSTACK_SKILLS_ROOT`, `PSTACK_SOURCE_ROOT`, or `PROJECT_ROOT` command, read the [portable resource path contract](references/portable-paths.md) in full. These commands run bundled scripts, address installed resources, read fresh pstack trunk, or read a consumer control skill. Resolve only the roots that the next command needs. Keep the exact command forms in generated plans and restore the recorded roots across owners, delegates, wake-ups, and later ticks.

## Resolve named personas

When a workflow requests `poteto-agent` or `Comment Sicko`, read the [named-role contract](references/named-roles.md) before delegation. The installed bundle supplies the full upstream persona and local skill paths. Confirm a current native registration against the live role catalog, or supply the complete briefing through a generic delegate, own-CLI subprocess, or sequential arm. Persona identity and model-role configuration are separate.

## The primitives

**Spawn a subagent.** In order of preference:

1. Your harness's native subagent or delegation tool, whatever it is called.
2. No such tool → invoke your own CLI non-interactively as a subprocess (its help names the command and flags), one invocation per arm, run concurrently in background shells, each arm's report collected from stdout or a file path named in its brief.
3. No subprocesses either → run the arms sequentially inline, one at a time, each writing its report to a file before the next starts, then synthesize. Keep the configured arm count.

Each writer gets its own git worktree, whichever mechanism spawns it. Keep the location a native isolation option picks. When you run `git worktree add` yourself, never place the worktree beside the repository:

- A throwaway checkout (verify, review, replay, eval arm) goes under `mktemp -d "${TMPDIR:-/tmp}/pstack-<slug>.XXXXXX"`. Remove it with `git worktree remove` when its run ends.
- A worktree that holds unpushed work goes under `.worktrees/<slug>` in the main checkout. If the repository does not ignore `.worktrees/`, append it to `"$(git rev-parse --git-common-dir)/info/exclude"` first.

**Set an arm's model.** Pass a model value this session has confirmed the spawn mechanism accepts. If the value is unconfirmed or rejected, omit it and let the arm inherit the session model. Report the substitution. For explicitly requested models, apply [Arena's required-arm rule](../arena/SKILL.md#required-arms).

**Set an arm's effort.** Every role resolves to a model and a reasoning effort (see **The models config** below). Pass the effort through the spawn mechanism when it has a field or flag for it.

Claude Code has no such field. There the agent type carries the effort. pstack registers one generic agent per level: `pstack-effort-low`, `pstack-effort-medium`, `pstack-effort-high`, `pstack-effort-xhigh`, and `pstack-effort-max`. Each sets no model, only a name, a description, and `effort`, so the `model` you pass still governs. Pick the `subagent_type` from the resolved effort and the persona the skill names:

| resolved effort | skill names `general-purpose` | skill names a pstack persona |
|---|---|---|
| a level, and `pstack-effort-<level>` is in the live agent catalog | `pstack-effort-<level>` | `pstack-effort-<level>`, with the persona's complete briefing at the top of the prompt |
| a level, but that agent is not in the catalog | `general-purpose` | the persona per the [named-role contract](references/named-roles.md) |
| no written effort | `general-purpose` | the persona per the named-role contract |

Pass the role's model in every row, or omit it for `inherit-parent`. `none` and `ultra` are not Claude Code levels. Each is a value this harness cannot use, so per the Config rule below the effort alone is `inherit-parent`, and the spawn takes the "no written effort" row. Only the live catalog proves an agent is loaded. A file on disk does not. A delegate's own spawns inherit the delegate's effort, so a nested spawn with no written effort runs at the delegate's level, not the top session's.

When the mechanism has no field and no agent carries the level, or it rejects the value, the effort alone becomes `inherit-parent`. Keep the model and the arm. Say in the reply which role's written effort was inherited and why, such as "`how explainer` ran at the session effort because `pstack-effort-xhigh` is not loaded. Run `/setup-pstack` to register it." When a persona ran as a briefing in an effort agent's prompt instead of under its native identifier, say that too. An effort problem never drops a model or an arm.

**Parallelism.** Real where the mechanism allows it (independent tool calls in one message, concurrent subprocesses); otherwise sequential with the same arm count.

**Read-only.** Use an enforcing option if the spawn mechanism has one; otherwise state it plainly in the brief ("read-only: do not edit or write files").

**Structured questions (`AskQuestion`).** Your harness's structured-question tool if it has one; otherwise ask in plain chat.

**Track a worklist.** The worklist is an ordered collection of items with `pending`, `in progress`, `completed`, or `skipped: <reason>` state. State the complete initial list before starting, keep at most one item in progress, and update it when an item changes state or the list changes.

Choose its carrier by capability, never by a remembered product-specific name:

1. Inspect the tools and channels already exposed in the live session. Prefer a native structured capability whose description says it creates or updates task, plan, or work-item state.
2. If the harness supports deferred capability discovery, make one semantic query for a capability that tracks ordered multi-step work and item status. Do not query product-specific names.
3. If structured tracking is available, use it. If discovery finds none or any call is rejected, stop trying that carrier for the rest of the task. Publish and maintain the same worklist through the harness's normal progress-update channel. Both are native carriers of the same contract. On that channel, post the worklist as a numbered list with each item's state, and re-post it when an item changes state or the list changes.

Do not create a scratch task file solely because structured tracking is unavailable. A durable file is appropriate only when the workflow must resume across sessions; use that workflow's named state or decision-trail artifact. Ordinary capability variation needs no warning, apology, or "fallback" announcement. Report the current worklist, not the plumbing that carries it.

**Loops and wake-ups.** Your harness's loop or scheduling facility; otherwise a re-invoking wrapper (script, cron, CI).

**Transcripts.** Every harness keeps this workspace's session record somewhere — log files under its data directory, or a database with an export command. Locate yours before reading, and stay inside the current workspace's sessions; other projects' transcripts are private.

## Hints for known harnesses

Observed circa 2026-09. Treat as starting points, not contracts — verify against your live session before relying on any of them, and prefer what you find over what is written here.

| harness | spawn | worklist carrier | effort | transcripts |
|---|---|---|---|---|
| Claude Code | `Task` tool (custom agents from `.claude/agents/` spawn by name); `model` takes short aliases | Prefer any exposed structured task-tracking capability; otherwise use normal progress updates. `CLAUDE_CODE_ENABLE_TODO_TOOLS=1`, in the environment or in a settings file's `env` block, switches the task tools on for every model. Without it 2.1.284 ships them only on Claude 3.x, Opus 4 to 4.7, Sonnet 4 to 4.6, and Haiku 4.5. With tool search on, the default, they arrive deferred, so the discovery step in **Track a worklist** applies | no per-call field. A custom agent's `effort` frontmatter overrides the session effort and combines with the per-call `model` (measured on 2.1.284), so pstack's `pstack-effort-<level>` agents carry a written effort (see **Set an arm's effort**). A role with no written effort, or a session whose catalog lacks the agent, inherits the session effort (`--effort`, `effortLevel`) | JSONL under `~/.claude/projects/<slug>/`, `<slug>` = the resolved workspace path with every character other than a letter or digit turned into `-` |
| Codex | `spawn_agent` (the multi-agent feature, stable in 0.152) takes a model and a reasoning effort per spawn; custom roles use TOML in `~/.codex/agents/` or `.codex/agents/` with `name`, `description`, and `developer_instructions`; generated pstack roles leave model and effort unset; `codex exec` is the subprocess route | Prefer any exposed structured plan-tracking capability; otherwise use normal progress updates in the commentary channel. Goal lifecycle tools are not work tracking unless the user explicitly asked to create a goal. The plan tool is off by default. `[tools.update_plan]` with `enabled = true` in `config.toml` switches it on. That key is absent from Codex's published `docs/config.md` and observed on 0.158.0-alpha.2.1 | the reasoning-effort field on `spawn_agent`; `-c model_reasoning_effort=<value>` on `codex exec`. A model set without an effort gets that model's default effort (medium on the GPT-5.6 family), not the parent's, so always pass one | JSONL under `~/.codex/sessions/` by date |
| Hermes | a delegation toolset when enabled; `hermes -z` for one-shot subprocess runs | Prefer any exposed structured task-planning capability; otherwise use normal progress updates | `--reasoning <value>` on `hermes -z`; config `agent.reasoning_effort` and per-model `agent.reasoning_overrides`. Whether the delegation toolset takes an effort field is unverified: check its schema in session | SQLite store; `hermes sessions` subcommands list and export |
| Grok Build | `spawn_subagent`. On 1.0.41 its schema has no agent type and no argument names a persona, so pass a pstack persona's full briefing in `prompt`, prefix `description` with that persona's name in brackets, such as `[poteto-agent]` or `[comment-sicko]`, so the subagent label shows it, and on `resume_from` keep the tag but skip the briefing because the child already has it. Grok loads the `~/.claude/agents/` wrappers as agent types, and its source honors a `subagent_type` key that arrives, but the schema hides the key and a model told to send it dropped it in a 2026-09 probe, so do not rely on naming the type. A `model` argument appears unless subagent model inheritance is on (default off, settable remotely) and every catalog model is xAI. Only the top-level session spawns, so a delegate cannot fan out. `isolation: worktree` makes a full clone under `~/.grok/worktrees/`, and `grok worktree gc --max-age <age>` reclaims it. `grok -p` is the subprocess route | Prefer any exposed structured task-tracking capability; otherwise use normal progress updates | no per-spawn field; `reasoning_effort` on a Grok role or persona, otherwise the session effort, so the effort is `inherit-parent` here. `--effort <value>` on `grok -p` | per-session directories under `~/.grok/sessions/<url-encoded cwd>/<session>/`; each spawn records `subagents/<id>/meta.json` |

**Codex agent cap.** Codex caps subagents, and a spawn past the cap fails with `agent thread limit reached` and creates nothing. If your tools include `close_agent`, by default at most 6 agents stay open per session and a finished agent holds its slot until closed, so launch at most 6 at once and close each agent once you have read its result. If they do not, by default at most 3 subagents run at once and finished ones free their slots, so launch parallel arms in waves of 3 or fewer. Either limit overrides a skill's "spawn all in one message". The arm count stays the same either way. After a limit error, never wait for the refused arm: spawn it when a slot frees. Run it yourself only when the arm needs no other model, and report it as a substitution. Without `close_agent`, `wait_agent` takes no target and blocks until its timeout when no child is running, so call it only while a spawned child is still working.

## Universal rules

- **Panels keep their configured arm count.** Run a three-model panel as three arms even in a one-model harness. Give each arm a different brief and run them in parallel or sequentially. For exact model requests, apply the required-arm rule above.
- **Named sibling skills are files.** When a pstack skill says "the architect skill" or "read the leaf skill", it names a sibling directory under the same installed skills root. Most pstack skills are gated against model invocation, so they appear in no tool inventory and their descriptions are not in context — that never means missing. Read the named skill's SKILL.md (and any files it references) directly and follow it; record that you applied it by file read. Never edit a skill's gating to make it invocable.
- **Tool names in skill text describe intent, never a required tool.** `Task`, `Glob`, `Grep`, `Read`, a worklist, and Cursor-era parameters like `readonly`, `environment: "cloud"`, and `is_background` name capabilities: realize each with whatever your session provides (a search tool, a shell command, a read-only brief, worktree isolation, background execution). Capability selection follows live descriptions, not recalled names. A missing optional tool never cancels the step and needs no announcement. A `subagent_type` of `general-purpose`, `poteto-agent`, or `comment-sicko` in skill text names the delegate's persona, or none. **Set an arm's effort** turns it into the concrete type.
- **Config**: roles resolve to a model and an effort per **The models config** below. A value the current harness cannot use is `inherit-parent` for that field only.
- **Honesty**: never report parallel arms that actually ran sequentially; name the mechanism used.
- **No improvised models**: every spawn resolves through a named role. A spawn whose skill names no role resolves through the `default` line, then `inherit-parent`. Never pick a model that neither the config nor the skill's inline default names, and say which role the model came from.

## The models config

`~/.agents/pstack-models.md` (user) and `.agents/pstack-models.md` (workspace) map each role to a model and a reasoning effort. `setup-pstack` writes and lints the file; its shipped default is `examples/pstack-models.md` next to that skill.

**Grammar.** `role: entry`, or `role, role: entry` to bind several roles at once. Panel roles (`arena runners`, `arena cross-judge pool`, `architect runners`, `interrogate reviewers`) take a comma list, one arm per entry. An entry is `model` or `model@effort`. Efforts are `none`, `low`, `medium`, `high`, `xhigh`, `max`; `ultra` is Codex's Pro mode and is valid only on `gpt-5.6-sol`. `inherit-parent` and `auto`, with or without `@effort`, run the arm on the parent chat model. A `## codex`, `## claude-code`, or `## hermes` header starts a section whose lines apply to that harness only; lines above any header apply everywhere. A `# budget: <label> (<effort>)` comment records the budget `setup-pstack` last applied to the `@effort` suffixes; resolution reads only the role lines. Two roles are special. `trail reviewer` is the show-me-your-work reviewer; when it resolves to the model that did the work, show-me-your-work steps down one tier so the review stays cross-model. `default` is the entry for any spawn whose skill names no role; it ships as `inherit-parent`.

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

**Effort policy.** The policy fills an effort that would otherwise be a model default. When no `@effort` is written on a harness whose subagents get their model's default effort (Codex, Hermes), the floor is `high` for every role, and `xhigh` for hardest tasks, judgment and prose, bug-fix, perf-issue, hillclimb, how explainer, why synthesizer, reflect judgment, divergent and synthesizer, arena cross-judge pool, architect runners, and trail reviewer. On a harness whose subagents inherit the parent's effort (Claude Code, Grok Build), an unwritten effort stays `inherit-parent`. The policy never overrides a session effort the user set. On Claude Code, only a written `@effort`, including one a setup-pstack budget wrote, or an explicit escalation in the task changes an arm's effort. Nothing in this policy produces `max` or `ultra`; those come only from an explicit `@max` or `@ultra` on a line, from the Codex translation of `fable`, or from an explicit escalation in the task. Effort never changes an arm count or a model choice.
