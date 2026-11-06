---
name: pstack-harness
description: Maps pstack's delegation and portable resource primitives to the current CLI (Claude Code, Codex, Hermes, Grok Build, or any other harness). Covers how to locate installed skills and fresh trunk resources, spawn a subagent, set a per-subagent model, parallelize arms, go read-only, ask a structured question (AskQuestion), track a worklist, loop, locate the transcript store, write shell commands, and inspect running processes. Read whenever a pstack skill says spawn, Task tool, subagent_type, per-subagent model, AskQuestion, or worklist, names a sibling skill you cannot find, or runs a path from a playbook. Every primitive is named differently per harness, so read this before concluding your harness has no such capability or resource.
---

# Harness adapters

Use this skill when a pstack workflow names a delegation action, worklist, question, loop, transcript, portable resource, shell command, or process inspection.

pstack tool names describe intent. Satisfy that intent with the live session's capabilities. Your tool inventory and CLI help are authoritative. Never invent a tool. Report the mechanism when it affects execution or evidence. For worklists, report item state rather than the carrier.

Before executing shell commands or answering what is running, read [shell commands and running processes](references/shell-and-processes.md). This applies to every action and runtime.

## Select the action

Read each selected reference in full before its action. Select only the actions the next step needs. Combine their files when a step needs several actions. Read a link inside a reference only when its described operation applies. Do not read every reference.

| Action | Required references |
|---|---|
| `worklist` | [Worklist procedure](references/worklist.md) |
| `question` | [Structured questions](references/questions.md) |
| `spawn` | The **Spawn a role** recipe below, [Delegation and isolation](references/delegation.md), and the current runtime adapter below. Read [Role resolution and handoffs](references/roles.md) only for a handoff, a recovery, a `trail reviewer`, or a resolver that fails or prints a note, and [Portable resource path contract](references/portable-paths.md) only when `PSTACK_SKILLS_ROOT` is unset |
| `role-handoff` | [Role resolution and handoffs](references/roles.md) |
| `persona` | [Persona contract](references/named-roles.md) when the spawn names a persona |
| `loop` | [Loops and wake-ups](references/loops.md) |
| `transcript` | [Workspace transcripts](references/transcripts.md) and the current runtime adapter below |
| `portable-paths` | [Portable resource path contract](references/portable-paths.md) when a command uses `PSTACK_SKILLS_ROOT`, `PSTACK_SOURCE_ROOT`, or `PROJECT_ROOT` |

## Runtime adapters

When context compaction, shortened skill content, or skill restoration affects the next action, read [skill retention evidence](references/skill-retention.md). Keep documented limits, runtime observations, and unknown behavior separate.

For spawn or transcript, read only the current runtime column for that action. Other actions need no runtime adapter.

| Runtime | Spawn adapter | Transcript location |
|---|---|---|
| `claude-code` | [Claude Code](references/claude-code.md) | [Transcript location](references/transcripts-claude-code.md) |
| `codex` | [Codex](references/codex.md) | [Transcript location](references/transcripts-codex.md) |
| `hermes` | [Hermes](references/hermes.md) | [Transcript location](references/transcripts-hermes.md) |
| `grok` | [Grok Build](references/grok.md) | [Transcript location](references/transcripts-grok.md) |
| `other` | [Other runtime](references/other-runtime.md) | [Transcript location](references/transcripts-other.md) |

## Resolve portable resources

Read the portable resource path contract selected above. Resolve only the roots that the next command needs. Keep the exact command forms in generated plans and restore the recorded roots across owners, delegates, wake-ups, and later ticks.

## Preserve roles across handoffs

Read the role resolution and handoffs reference selected above before a role handoff or recovery.

## Spawn a role

Every pstack spawn runs a role from the models config, such as `feature` or `how explorer`, sometimes under a persona. Keep the caller's role and panel arm count.

1. Take the role from the skill or playbook step. A step that names none uses `default`. A `subagent_type` of `poteto-agent` or `comment-sicko` names a persona, and `general-purpose` names none.
2. Resolve it once per task, and again after the harness or config changes. Do not read the config files to pick values.

   ```sh
   python3 "${PSTACK_SKILLS_ROOT:?}/setup-pstack/scripts/check-models-config.py" --resolve --harness <claude-code|codex|grok|hermes> <role>
   ```

   Failure signal: nonzero exit. It prints one JSON line per arm with `model`, `effort`, and `source`, plus `notes` to relay in the reply. If it fails or prints a note, or the role is `trail reviewer`, follow **Spawn a role** in [roles.md](references/roles.md#spawn-a-role). Never drop a spawn because the resolver failed. Spawn with model and effort omitted and report it.
3. Build the call from the current runtime adapter. `inherit-parent` in a field means omit that field.
4. For a persona, put its complete briefing at the top of the prompt, from `python3 "${PSTACK_SKILLS_ROOT:?}/pstack-harness/scripts/subagents.py" brief <persona>`, unless the live agent catalog lists the persona's native name.
5. Report the model and effort each arm ran on, and label a review `same-model` when it matches the work's model.

## The primitives

Use the action table above for spawning, parallelism, read-only execution, structured questions, worklists, loops, and transcripts.

## Universal rules

- **Use named sibling skills yourself.** "Call the Skill tool with `architect`" tells you to load the pstack skill `architect` and follow it. A following "follow its" or "use its" names the part of that skill the step needs, after the whole skill loads. The name is a sibling directory under the installed skills root, the directory that holds this skill's own directory. Any other pstack mention of a skill by name, such as "the leaf skill" or "the **arena** skill", names one the same way. On Claude Code, call the Skill tool with the bare name, such as `architect`. The call works when the listing shows the name only, with no description, and a name-only listing never means the skill is missing. Codex, Grok Build, Hermes, and any other harness have no tool named Skill for these skills. There, the same phrase means read `<installed skills root>/<name>/SKILL.md` in full, then read the files it references when its steps need them. On Codex, a `$name` mention in a user prompt [injects](references/codex.md#injected-skills) that skill's `SKILL.md`, so do not read that file again unless the injected copy was cut. Read each other file as the [Codex read rule](references/codex.md#read-skill-files) says. Never ask the user to type a skill that a pstack skill names. Never edit a skill's files or the listing settings to change how it loads.
- **Finish every cut-off read.** If a runtime or tool return is shortened or warns that it was cut, read the missing content before continuing.
- **Load only skills that someone named.** Never read or load a pstack skill that you found by listing or searching a skills directory, unless the user or a loaded skill named it. A skill that the harness lists with its description can still load from that description.
- **Tool names in skill text describe intent, never a required tool.** `Task`, `Glob`, `Grep`, `Read`, a worklist, and Cursor-era parameters like `readonly` name capabilities: realize each with whatever your session provides (a search tool, a shell command, a read-only brief). Capability selection follows live descriptions, not recalled names. A missing optional tool never cancels the step and needs no announcement. A `subagent_type` in skill text names a persona or none, and **Spawn a role** turns it into the concrete type.
