---
name: pstack-harness
description: Maps pstack's delegation and portable resource primitives to the current CLI (Claude Code, Codex, Hermes, Grok Build, or any other harness). Covers how to locate installed skills and fresh trunk resources, spawn a subagent, set a per-subagent model, parallelize arms, go read-only, ask a structured question (AskQuestion), track a worklist, loop, and locate the transcript store. Read whenever a pstack skill says spawn, Task tool, subagent_type, per-subagent model, AskQuestion, or worklist, names a sibling skill you cannot find, or runs a path from a playbook. Every primitive is named differently per harness, so read this before concluding your harness has no such capability or resource.
---

# Harness adapters

pstack skills describe delegation abstractly: "spawn a subagent on model X", "launch N in parallel in one message", "readonly", "AskQuestion". Each is an intent, not a tool name. Satisfy the intent with whatever your session actually provides. Your live tool inventory and your CLI's own help are the authority, not this file. Never invent a tool. Say which mechanism you used when it affects execution or evidence. For worklists, report the item state rather than the carrier.

## Resolve portable resources

When a pstack workflow uses a `PSTACK_SKILLS_ROOT`, `PSTACK_SOURCE_ROOT`, or `PROJECT_ROOT` command, read the [portable resource path contract](references/portable-paths.md) in full. These commands run bundled scripts, address installed resources, read fresh pstack trunk, or read a consumer control skill. Resolve only the roots that the next command needs. Keep the exact command forms in generated plans and restore the recorded roots across owners, delegates, wake-ups, and later ticks.

## Spawn a role

Every pstack spawn runs a role from the models config, such as `feature` or `how explorer`, sometimes under a persona. Build each spawn in this order.

1. **Name the role and the persona.** The skill or playbook step names the role. A spawn whose skill names no role uses `default`. A `subagent_type` of `poteto-agent` or `comment-sicko` in skill text names a persona, and `general-purpose` names none. Neither one picks the model or the effort.
2. **Resolve the role.** Run the resolver once per task, and again after the config changes:

   ```sh
   python3 "${PSTACK_SKILLS_ROOT:?}/setup-pstack/scripts/check-models-config.py" --resolve --harness <claude-code|codex|grok|hermes> [<role>...]
   ```

   Failure signal: nonzero exit. It prints one JSON line per arm with `model`, `effort`, and `source`. Pass the roles the skill names, or none to print every role. Run it from the project root or pass `--project <root>`. Do not read the config files to pick values. The rules, and the grammar for editing the files, live in setup-pstack's [models config reference](../setup-pstack/references/models-config.md). When `trail reviewer` resolves to the model that did the work, step down one tier in the same family (`fable`, `opus`, `sonnet`, `haiku`; `gpt-6-astra`, `gpt-6.1-sol` or `gpt-6-sol`, `gpt-6-luna`), or up one from the lowest tier, so the review stays cross-model. Grok Build has one tier today, so there the review runs on the same model and the reply says so. Every model you pass comes from this output, an explicit request in the task, or that step-down. Never improvise one, and say which role each model came from. If the resolver exits nonzero or cannot run, still spawn the role. Omit the model and effort so the child inherits the session's, except for `trail reviewer`, which takes one tier below the session model per the step-down rule above. When the session model's family has no tier list above, as on Hermes, the `trail reviewer` inherits it, and the verdict says it is a same-model review. For a panel role, keep the arm count that the panel's skill names as its default, and brief each arm the way that skill says. Report the resolver error and the values the child ran on. Never drop a spawn because the resolver failed.
3. **Build the spawn call for this CLI**, through the mechanism in **Spawn a subagent** below. `inherit-parent` in a field means omit that field.
   - **Claude Code.** Pass `model`. The spawn tool has no effort field, so the agent type carries the effort. Each `pstack-effort-<level>` agent runs at its level and takes the `model` you pass.

     | resolved effort | no persona | a pstack persona |
     |---|---|---|
     | a level, and `pstack-effort-<level>` is in the live agent catalog | `pstack-effort-<level>` | `pstack-effort-<level>`, with the persona's complete briefing at the top of the prompt |
     | a level, but that agent is not in the catalog | `general-purpose` | the persona per the [persona contract](references/named-roles.md) |
     | `inherit-parent` | `general-purpose` | the persona per the persona contract |

     Only the live catalog proves an agent is loaded. A file on disk does not. A delegate's own spawns inherit the delegate's effort, so a nested spawn with an `inherit-parent` effort runs at the delegate's level, not the top session's.
   - **Codex.** Pass `model` and `reasoning_effort` on `spawn_agent`, and whenever you pass either, set `fork_turns` to `"none"`, or to a positive integer to carry the last few turns. A full-history fork, with `fork_turns` omitted or `"all"`, inherits the parent's model and effort and ignores overrides. So a role that resolves to a model or an effort never forks the full history. Only a role that resolves to `inherit-parent` for both may. Set `agent_type` to the persona's native name when the live agent catalog lists it, and otherwise to `default` with the persona's briefing at the top of the message. When `spawn_agent` shows no `agent_type` parameter, this session loaded no custom agents, so omit the field and put the persona's briefing at the top of the message.
   - **Hermes.** Pass the values through the delegation toolset's fields when it has them, or as `--reasoning` on `hermes -z`.
   - **Grok Build.** Resolve with `--harness grok`. Pass `model` only when `spawn_subagent` lists the argument. With subagent model inheritance on and an all-xAI catalog, Grok hides it and rejects a spawn that names one, so the arm runs on the parent model. The spawn takes no effort, so a resolved level runs at the session effort and step 5 reports it.
   - **Forks.** A fork, such as Claude Code's `fork` agent type or a Codex full-history fork, inherits the lead's whole context and runs on the lead's model and effort, ignoring any override. Fork only when the role resolves to `inherit-parent` for both, as `default` ships, and the brief would otherwise restate context the lead already holds, such as drafting from files the lead just read or writing a resume note. Never fork a verdict, a review, or a role that resolves to a model or an effort. A fork returns the same thin report as any spawn, per **principle-guard-the-context-window**.
4. **Brief the persona.** A persona that runs as a briefing gets its complete text from the [persona contract](references/named-roles.md). Never summarize it.
5. **Fall back without dropping an arm.** If the spawn rejects a model, omit it, let the arm inherit the session model, and report the substitution. For explicitly requested models, apply [Arena's required-arm rule](../arena/SKILL.md#required-arms). If no field or agent can carry the effort, the effort alone becomes `inherit-parent`. Keep the model and the arm. Say in the reply which role's effort was inherited and why, such as "`how explainer` ran at the session effort because `pstack-effort-xhigh` is not loaded. Run `/setup-pstack` to register it." When a persona ran as a briefing in an effort agent's prompt instead of under its native name, say that too.

## The primitives

**Spawn a subagent.** In order of preference:

1. Your harness's native subagent or delegation tool, whatever it is called.
2. No such tool → invoke your own CLI non-interactively as a subprocess (its help names the command and flags), one invocation per arm, run concurrently in background shells, each arm's report collected from stdout or a file path named in its brief.
3. No subprocesses either → run the arms sequentially inline, one at a time, each writing its report to a file before the next starts, then synthesize. Keep the configured arm count. A verdict or review that runs inline is not independent. Label it `self-review` in the verdict and in the reply, and never count it as an independent verdict.

Each writer gets its own git worktree, whichever mechanism spawns it. Keep the location a native isolation option picks. When you run `git worktree add` yourself, never place the worktree beside the repository:

- A throwaway checkout (verify, review, replay, eval arm) goes under `mktemp -d "${TMPDIR:-/tmp}/pstack-<slug>.XXXXXX"`. Remove it with `git worktree remove` when its run ends.
- A worktree that holds unpushed work goes under `.worktrees/<slug>` in the main checkout. If the repository does not ignore `.worktrees/`, append it to `"$(git rev-parse --git-common-dir)/info/exclude"` first.

If `git worktree add` fails, spawn the writer in the current checkout. Run one writer at a time. Codex's `workspace-write` sandbox keeps `.git` read-only, so `git worktree add` fails there. Never take the writer's work back into the lead.

**Parallelism.** Real where the mechanism allows it (independent tool calls in one message, concurrent subprocesses); otherwise sequential with the same arm count.

**Read-only.** Use an enforcing option if the spawn mechanism has one; otherwise state it plainly in the brief ("read-only: do not edit or write files").

**Structured questions (`AskQuestion`).** Your harness's structured-question tool if it has one; otherwise ask in plain chat.

**Track a worklist.** The worklist is an ordered collection of items with `pending`, `in progress`, `completed`, or `skipped: <reason>` state. State the complete initial list before starting, keep at most one item in progress, and update it when an item changes state or the list changes.

Choose its carrier by capability, never by a remembered product-specific name:

1. Inspect the tools and channels already exposed in the live session. Prefer a native structured capability whose description says it creates or updates task, plan, or work-item state.
2. If the harness supports deferred capability discovery, make one semantic query for a capability that tracks ordered multi-step work and item status. Do not query product-specific names.
3. If structured tracking is available, use it. If discovery finds none or any call is rejected, stop trying that carrier for the rest of the task. Publish and maintain the same worklist through the harness's normal progress-update channel. Both are native carriers of the same contract. On that channel, post the worklist as a numbered list with each item's state, and re-post it when an item changes state or the list changes.

Do not create a scratch task file solely because structured tracking is unavailable. A durable file is appropriate only when the workflow must resume across sessions; use that workflow's named state or decision-trail artifact. Ordinary capability variation needs no warning, apology, or "fallback" announcement. Report the current worklist, not the plumbing that carries it.

**Loops and wake-ups.** Your harness's loop or scheduling facility; otherwise a re-invoking wrapper (script, cron, CI). If neither exists, end each reply with the next tick's due time and its checklist, run that tick on the next turn, and report that the cadence is manual. Never skip a tick silently.

**Transcripts.** Every harness keeps this workspace's session record somewhere — log files under its data directory, or a database with an export command. Locate yours before reading, and stay inside the current workspace's sessions; other projects' transcripts are private.

## Hints for known harnesses

Observed circa 2026-09. Treat as starting points, not contracts — verify against your live session before relying on any of them, and prefer what you find over what is written here.

| harness | spawn | worklist carrier | effort | transcripts |
|---|---|---|---|---|
| Claude Code | `Task` tool (custom agents from `.claude/agents/` spawn by name); `model` takes short aliases | Prefer any exposed structured task-tracking capability; otherwise use normal progress updates. When the task tools are off, setup-pstack step 0b names the switch. With tool search on, the default, they arrive deferred, so the discovery step in **Track a worklist** applies | no per-call field; a `pstack-effort-<level>` agent type carries it (see **Spawn a role**). An `inherit-parent` effort, or a session whose catalog lacks the agent, runs at the session effort (`--effort`, `effortLevel`) | JSONL under `~/.claude/projects/<slug>/`, `<slug>` = the resolved workspace path with every character other than a letter or digit turned into `-` |
| Codex | `spawn_agent` (the multi-agent feature, stable in 0.152) takes a model and a reasoning effort per spawn, with the `fork_turns` rule in **Spawn a role**; custom agents use TOML in `~/.codex/agents/` or `.codex/agents/` with `name`, `description`, and `developer_instructions`; generated pstack personas leave model and effort unset; `codex exec` is the subprocess route | Prefer any exposed structured plan-tracking capability; otherwise use normal progress updates in the commentary channel. Goal lifecycle tools are not work tracking unless the user explicitly asked to create a goal. When the plan tool is off, setup-pstack step 0b names the switch | the reasoning-effort field on `spawn_agent`; `-c model_reasoning_effort=<value>` on `codex exec`. A model set without an effort gets that model's default effort (low on `gpt-6.1-sol`, medium on the other gpt-6 models), not the parent's, so always pass one | JSONL under `~/.codex/sessions/` by date |
| Hermes | a delegation toolset when enabled; `hermes -z` for one-shot subprocess runs | Prefer any exposed structured task-planning capability; otherwise use normal progress updates | `--reasoning <value>` on `hermes -z`; config `agent.reasoning_effort` and per-model `agent.reasoning_overrides`. Whether the delegation toolset takes an effort field is unverified: check its schema in session | SQLite store; `hermes sessions` subcommands list and export |
| Grok Build | `spawn_subagent`. On 1.0.41 its schema has no agent type and no argument names a persona, so pass a pstack persona's full briefing in `prompt`, prefix `description` with that persona's name in brackets, such as `[poteto-agent]` or `[comment-sicko]`, so the subagent label shows it, and on `resume_from` keep the tag but skip the briefing because the child already has it. Grok loads the `~/.claude/agents/` wrappers as agent types, and its source honors a `subagent_type` key that arrives, but the schema hides the key and a model told to send it dropped it in a 2026-09 probe, so do not rely on naming the type. A `model` argument appears unless subagent model inheritance is on (default off, settable remotely) and every catalog model is xAI. Only the top-level session spawns, so a delegate cannot fan out. `isolation: worktree` makes a full clone under `~/.grok/worktrees/`, and `grok worktree gc --max-age <age>` reclaims it. `grok -p` is the subprocess route | Prefer any exposed structured task-tracking capability; otherwise use normal progress updates | no per-spawn field; `reasoning_effort` on a Grok role or persona, otherwise the session effort, so the effort is `inherit-parent` here. `--effort <value>` on `grok -p` | per-session directories under `~/.grok/sessions/<url-encoded cwd>/<session>/`; each spawn records `subagents/<id>/meta.json` |

**Codex agent cap.** Codex caps subagents, and a spawn past the cap fails with `agent thread limit reached` and creates nothing. If your tools include `close_agent`, by default at most 6 agents stay open per session and a finished agent holds its slot until closed, so launch at most 6 at once and close each agent once you have read its result. If they do not, by default at most 3 subagents run at once and finished ones free their slots, so launch parallel arms in waves of 3 or fewer. Either limit overrides a skill's "spawn all in one message". The arm count stays the same either way. After a limit error, never wait for the refused arm: spawn it when a slot frees. Run it yourself only when the arm needs no other model, and report it as a substitution. Without `close_agent`, `wait_agent` takes no target and blocks until its timeout when no child is running, so call it only while a spawned child is still working.

## Universal rules

- **Panels keep their configured arm count.** Run a three-model panel as three arms even in a one-model harness. Give each arm a different brief and run them in parallel or sequentially. For exact model requests, apply the required-arm rule above.
- **Named sibling skills are files.** When a pstack skill says "the architect skill" or "read the leaf skill", it names a sibling directory under the same installed skills root. Most pstack skills are gated against model invocation, so they appear in no tool inventory and their descriptions are not in context — that never means missing. Read the named skill's SKILL.md (and any files it references) directly and follow it; record that you applied it by file read. Never edit a skill's gating to make it invocable.
- **Tool names in skill text describe intent, never a required tool.** `Task`, `Glob`, `Grep`, `Read`, a worklist, and Cursor-era parameters like `readonly` name capabilities: realize each with whatever your session provides (a search tool, a shell command, a read-only brief). Capability selection follows live descriptions, not recalled names. A missing optional tool never cancels the step and needs no announcement. A `subagent_type` in skill text names a persona or none, and **Spawn a role** turns it into the concrete type.
- **Honesty**: never report parallel arms that actually ran sequentially; name the mechanism used.
