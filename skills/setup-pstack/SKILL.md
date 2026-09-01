---
name: setup-pstack
description: Configure which models pstack uses per role. Detects your available models and writes a config file that overrides the skill defaults. Use for /setup-pstack, "configure pstack models", or changing pstack's model choices.
---

# Setup pstack

Write `~/.agents/pstack-models.md`, a config file that sets pstack's model per role. The skills read it on demand and fall back to their inline defaults when a line is absent, so this is an override layer, not a requirement.

The inline defaults (and the shape in step 5) are written as short model aliases (`fable`, `opus`, `sonnet`, `haiku`). Any value your harness does not accept for subagents means `inherit-parent`: the role runs on the session model, and multi-model panels become same-model panels with differentiated briefs.

## Steps

### 1. Detect available models

Enumerate the model values your session's spawn mechanism accepts (find the mechanism per the **pstack-harness** skill); that is the dependable source. If your CLI also exposes a models API or command that lists the user's entitled models, prefer it for completeness. If you cannot detect any, ask the user to paste the slugs they have access to. Never write a real slug you have not confirmed is available. The aliases `inherit-parent` and `auto` are always valid even though they are not detected slugs.

### 2. Load current state

The default role-to-model mapping is the file shape shown in step 5 below. If `~/.agents/pstack-models.md` already exists, read it and treat its values as the current choices. Otherwise start from those defaults.

### 3. Map and confirm

The file is shared across CLIs, so a value this harness cannot validate is not wrong — it is another harness's choice (it reads as `inherit-parent` here). Show every role with its current model, marking values outside the detected set as "(set for another harness — kept unless you change it)" rather than as needing a choice. Ask whether to accept as-is or change specific roles, offering the detected models plus `inherit-parent` and `auto` (both mean: this role runs on the parent chat model, which is how Auto users stay on Auto) as the options. Prefer AskQuestion over free text. For panel roles (how critics, arena runners, architect runners, interrogate reviewers) the value is a list, and one subagent runs per entry, alias entries included, so the list length sets the count. `arena cross-judge pool` is also a list, but Arena selects one value from it whose model family or capability tier differs from the parent's when possible. `swarm workers` is the default model for every worker unless a race or comparison assigns another model per arm.

### 4. Validate

Every *newly chosen* real slug must be in the detected set; `inherit-parent` and `auto` always pass, and preserved values from another harness are exempt. If a chosen real slug is not available, stop and ask again. A config pointing at a model no harness can use breaks every delegation that reads it.

### 5. Write the config

Write `~/.agents/pstack-models.md` with one line per role, using the same labels poteto-mode uses. Rewrite the whole file so re-runs stay idempotent, but carry forward every existing line the user did not change — including values this harness could not validate; overwriting another CLI's choices with `inherit-parent` is the one failure mode to avoid. Shape:

```
---
description: pstack per-role model choices (overrides skill defaults)
---
# pstack model configuration. One line per role. Delete a line to fall back to the skill default.
# `inherit-parent` or `auto` as a value: the role runs on the parent chat model (omit the model). Alias entries in a panel list still count toward its fan-out.
feature, refactoring: sonnet
bug-fix: opus
perf-issue: opus
hillclimb: opus
judgment and prose: fable
hardest tasks: fable
how explorer: sonnet
how explainer: fable
how critics: fable, opus, sonnet, haiku
why investigators: sonnet
why synthesizer: fable
reflect tooling: opus
reflect judgment, divergent, synthesizer: fable
arena runners: fable, opus, sonnet, haiku
arena cross-judge pool: fable, opus, sonnet, haiku
swarm workers: sonnet
architect runners: fable, opus, sonnet, haiku
interrogate reviewers: fable, opus, sonnet, haiku
```

### 6. Confirm

Tell the user the config was written and that skills read it the next time they run. Re-running this skill updates it.

### 7. Offer a verification skill (optional)

Check whether the project has a way to drive the real app for proof (a `verify-*` skill, or an existing harness). If not, offer once: "want a project-local verification skill, so agents can drive the app the way a user does and prove changes work? I can generate one with /create-verification-skill." On yes, invoke `/create-verification-skill` (resolves wherever pstack is installed — workspace, user, or plugin). On no, move on without pushing.
