---
name: setup-pstack
description: Check installed pstack personas, optionally register native agents, and configure which models pstack uses per role and at what reasoning budget. Detects your available models and writes a config file that overrides the skill defaults. Use for /setup-pstack, "configure pstack models", "pstack budget", or changing pstack's model choices.
---

# Setup pstack

Write the pstack models config, a file that sets pstack's model and reasoning effort per role. Agents resolve it per role with this skill's resolver. A workspace `.agents/pstack-models.md` sits over the user's `~/.agents/pstack-models.md`, a harness section beats a flat line in either file, and a role neither file names falls back to the shipped default in `examples/pstack-models.md`. So this is an override layer, not a requirement.

The inline defaults are written as short model aliases (`fable`, `opus`, `sonnet`, `haiku`), which translate to gpt-6 models on Codex and to `grok-4.7` on Grok Build. Any other value your harness does not accept for subagents means `inherit-parent`: the role runs on the session model, and multi-model panels become same-model panels with differentiated briefs. An entry may pin a reasoning effort as `model@effort`, and `## codex`, `## claude-code`, `## grok`, or `## hermes` sections hold lines that apply to one harness only. The grammar, layering, and effort policy are defined once, in [references/models-config.md](references/models-config.md), and `scripts/check-models-config.py --resolve` applies them.

## Steps

### 0a. Check personas and optional native registration

Read the **pstack-harness** skill's [registration reference](../pstack-harness/references/registration.md). Resolve its logical installed skills root through [portable-paths.md](../pstack-harness/references/portable-paths.md), then run:

```sh
python3 "${PSTACK_SKILLS_ROOT:?}/pstack-harness/scripts/subagents.py" check
```

Failure signal: nonzero exit. Repair missing payloads or sibling skills before reporting persona readiness. A ready payload lets a generic delegate receive the full persona without native registration.

Offer native registration for Claude Code or Codex when the user wants it. Use the already-authorized scope if the session provides one; otherwise ask for project or user scope once. Run the reference's `install` command with the chosen absolute root. Never overwrite a conflict or change model settings to register a persona. For Hermes, use the full briefing through delegation context; do not create native agent files. Grok Build has no registration of its own. It loads the Claude Code wrappers, but its spawn tool cannot name an agent type, so its delegates get the full briefing in the prompt.

For Claude Code, say what registration adds: the two personas and the five `pstack-effort-<level>` agents, which let a written `@effort` apply to subagents here. Before a Claude Code install, read both config layers as step 2 does and list every role whose effort is written for this harness, with that effort. Say those roles run at it once the agents load, and every other role keeps the session effort. Report the `roles` rows and the `efforts` rows separately from live loading. When the install report says `agents_directory: created`, the agents load only in a fresh session, so tell the user to start one. Otherwise a running session picks them up, unless it was started with `--disable-slash-commands` or the directory came from `--add-dir`. In every case check the live catalog before claiming an effort applies.

Report payload readiness, native-file status, and live agent loading separately. Check the requested destination and inspect the live agent catalog before claiming native availability. Filesystem output always leaves activation unverified. Codex project registrations require project trust. Do not edit trust settings automatically. Check a fresh session after registration changes; when a loader requires a restart, say so and use full-brief delegation until loading is confirmed. Keep these observations separate from the model choices below.

### 0b. Check the structured task tools

poteto-mode keeps its worklist in the harness's structured task tool when that tool is on. Whichever CLI runs this skill, check both switches below and report each as on or off. A change applies from the next session. Edit a file only after the user says yes. Then add the key to the existing file and keep every other key.

- **Claude Code** has the task tools on every model when `CLAUDE_CODE_ENABLE_TODO_TOOLS` is `1` in the environment or in the `env` block of `~/.claude/settings.json`, `.claude/settings.json`, or `.claude/settings.local.json`, or when a launch names one of the task tools in `--allowedTools`. When the switch is off, recommend `"env": {"CLAUDE_CODE_ENABLE_TODO_TOOLS": "1"}` in `~/.claude/settings.json` for every project or in `.claude/settings.local.json` for this one, and say that a `settings.local.json` created by hand needs a `.gitignore` line. Also say that with tool search on, the default, the task tools arrive deferred, and Sonnet then kept no worklist in 4 of 4 `/poteto-mode` runs against one task per playbook step in 2 of 2 runs with `ENABLE_TOOL_SEARCH=false`. That setting raised a trivial first turn from 25,770 to 45,907 input tokens on 2.1.284 in 2026-09, so leave the choice to the user.
- **Codex** has the plan tool when `config.toml` under `$CODEX_HOME` or `~/.codex/` holds `[tools.update_plan]` followed by `enabled = true`. Codex's published config reference omits the key, and its shipped `codex-rs/core/config.schema.json` defines it with `enabled` defaulting to false, as of 0.158.0-alpha.2.1. When the switch is off, recommend those two lines. Codex rejects a bare `update_plan = true`.
- **Hermes** has no known switch. Report nothing to change.
- **Grok Build** ships its `todo_write` tool with no known switch. Report nothing to change.

### 1. Detect available models and efforts

Enumerate the model values your session's spawn mechanism accepts, and the reasoning-effort values it accepts per spawn (find the mechanism per the **pstack-harness** skill). On Claude Code, the per-spawn efforts are the levels whose `pstack-effort-<level>` agent the live catalog lists, and none when no effort agent is loaded. That is the dependable source. If your CLI also exposes a models API or command that lists the user's entitled models, such as `codex debug models` or `grok models`, prefer it for completeness. If you cannot detect any, ask the user to paste the slugs they have access to. Never write a real slug you have not confirmed is available. The aliases `inherit-parent` and `auto` are always valid even though they are not detected slugs.

### 2. Load current state

The default mapping is `examples/pstack-models.md` next to this skill. Read both config layers when they exist, the workspace `.agents/pstack-models.md` and then `~/.agents/pstack-models.md`, including their harness sections, and treat each role's lines and the `# budget` line of the file being configured as the current choices. `--resolve --harness <this CLI>` prints what each role runs as here. Otherwise start from those defaults. Unless the user asked for a per-repo override, the user-level file is the one being configured. A line whose role is not in `examples/pstack-models.md`, such as `how critics`, is from a retired role. Drop it.

### 3. Budget, map, and confirm

**(a) Ask for a budget.** Prefer AskQuestion over free text. Offer these five options with these exact labels, and name the current budget when the file records one. The first is a port addition. `unlimited` is upstream's `keep max` under a port label, and the other three match upstream.

- `default — keep as written`
- `unlimited — max reasoning`
- `large — xhigh reasoning`
- `medium — high reasoning`
- `small — medium reasoning`

On Claude Code, describe `default — keep as written` as "roles without a written effort run at your session effort", and say at the ask that a budget's suffix overrides the session effort in both directions once the effort agents are loaded.

**(b) Apply it.** Build the working table from `examples/pstack-models.md`, and on a re-run keep any role the user changed by model, effort, list, alias (`inherit-parent`, `auto`), or harness section. `default` applies no budget: every written `@effort` suffix stands and unsuffixed entries keep the effort policy in [references/models-config.md](references/models-config.md), which on Claude Code is the session effort. `unlimited`, `large`, `medium`, and `small` set the `@effort` of every real entry, panel entries and harness sections included, to `max`, `xhigh`, `high`, or `medium`, adding the suffix where none was written. If the lint in step 4 rejects that effort for the model, use the model's highest supported effort at or below the target. An entry whose model the lint cannot classify keeps its written effort, or stays unsuffixed, and step (c) names it as untouched. An alias with a written suffix, such as `auto@max`, gets the same rewrite on its suffix, since Codex honors a suffix on an alias. A bare `inherit-parent` or `auto` does not change. No budget changes a model or a list length. So `small` turns `fable` into `fable@medium` and `gpt-6-sol@max` into `gpt-6-sol@medium`, and `unlimited` turns both back into `fable@max` and `gpt-6-sol@max`. On Claude Code, a written suffix applies only while the effort agents are loaded. If the live catalog lacks them, say so. The suffixes still govern Codex and Hermes reading the same file, and subagents here run at the session effort until the agents are registered and the catalog lists them.

**(c) Show the roles and confirm.** The file is shared across CLIs, so a value this harness cannot validate is not wrong — it is another harness's choice (it reads as `inherit-parent` here). Show every role with its model and effort for this harness, marking values outside the detected set as "(set for another harness — kept unless you change it)" rather than as needing a choice. On Claude Code, show a role with no written effort as `session`, and mark a written effort "(inactive until the effort agents load)" when the live catalog lacks its agent. Also list each line step 2 dropped. Ask whether to accept as-is or change specific roles, offering the detected models plus `inherit-parent` and `auto` (both mean: this role runs on the parent chat model, which is how Auto users stay on Auto) as the options. Prefer AskQuestion over free text. For panel roles (arena runners, architect runners, interrogate reviewers) the value is a list, and one subagent runs per entry, alias entries included, so the list length sets the count. `arena cross-judge pool` is also a list, but Arena selects one value from it whose model family or capability tier differs from the parent's when possible. `swarm workers` is the default model for every worker unless a race or comparison assigns another model per arm. `trail reviewer` runs the show-me-your-work reviewer and every independent verdict and review; the spawn steps it down one tier whenever it resolves to the model that did the work, so a value that matches the model of another role is fine. `default` is the entry for any spawn whose skill names no role; keep it `inherit-parent` unless the user wants unmapped spawns on a specific model.

### 4. Validate

Run the lint on the file you are about to write, before writing it: `python3 <this skill's directory>/scripts/check-models-config.py <file>`. Any `error:` line (unknown role, bad effort, an effort the model does not support, a duplicate role or section, `none` or `ultra` under `## claude-code`) stops the write; fix the line and re-run. `notice:` lines mark `max` and `ultra` pins, and a flat-line `none` or `ultra` that Claude Code runs at the session effort. Read each one back to the user, so an expensive tier or a Claude Code fallback is a choice. Every *newly chosen* real slug must be in the detected set. `inherit-parent` and `auto` always pass, and preserved values from another harness are exempt. If a chosen real slug is not available, stop and ask again. Once the lint passes, show the user what each role will run as here. For the user file, run `python3 <this skill's directory>/scripts/check-models-config.py --resolve --harness <this CLI> --user-file <file>` from the project root, which also applies any workspace file there. For a per-repo override, copy the draft to `<temp>/.agents/pstack-models.md` and pass `--project <temp>` instead, so the real user file stays underneath.

### 5. Write the config

The target is `~/.agents/pstack-models.md`, or workspace `.agents/pstack-models.md` when the user asked for a per-repo override (only write roles the user actually wants pinned for this repo — every workspace line shadows the user-level one). A workspace file's `# budget` line covers only the roles written in that file. Roles that still resolve from `~/.agents/pstack-models.md` keep that file's budget. If your file tool cannot write the target (a harness that scopes writes to the workspace), fall back in order: write it through your shell tool; else write the workspace file and say the config is project-local until copied to `~/.agents/`; else print the final content for the user to save. Never silently drop the write.

Write the file with a `# budget` line holding the chosen label and its target effort, and one line per role, using the same labels poteto-mode uses. Start from `examples/pstack-models.md` next to this skill and keep its header comments, replacing the value on its budget line. Rewrite the whole file so re-runs stay idempotent, but carry forward every existing line the user did not change — including sections and values this harness could not validate; overwriting another CLI's choices with `inherit-parent` is the one failure mode to avoid. Leave out the retired-role lines step 2 dropped. Put a harness-specific pick under its `## <harness>` section and leave the flat lines for the other CLIs. Shape (excerpt):

```
# budget: default (keep as written)
feature, refactoring: sonnet
bug-fix: sonnet

## codex
feature, refactoring: gpt-6-sol@high
bug-fix: gpt-6-sol@xhigh
```

### 6. Confirm

Tell the user the config was written and that skills read it the next time they run. Re-running this skill updates it.

### 7. Offer a verification skill (optional)

Check whether the project has a way to drive the real app for proof (a `verify-*` skill, or an existing harness). If not, offer once: "want a project-local verification skill, so agents can drive the app the way a user does and prove changes work? I can generate one with /create-verification-skill." On yes, invoke `/create-verification-skill` (resolves wherever pstack is installed: workspace, user, or plugin). On no, move on without pushing.
