---
name: setup-pstack
description: Configure which models pstack uses per role. Detects your available models and writes a config file that overrides the skill defaults. Use for /setup-pstack, "configure pstack models", or changing pstack's model choices.
---

# Setup pstack

Write the pstack models config, a file that sets pstack's model and reasoning effort per role. The skills read it on demand, layered workspace-first: a role line in `.agents/pstack-models.md` (workspace) overrides the same role in `~/.agents/pstack-models.md` (user), and roles absent from both fall back to each skill's inline default — so this is an override layer, not a requirement.

The inline defaults are written as short model aliases (`fable`, `opus`, `sonnet`, `haiku`); on Codex they translate to the GPT-5.6 tiers per the **pstack-harness** skill. Any other value your harness does not accept for subagents means `inherit-parent`: the role runs on the session model, and multi-model panels become same-model panels with differentiated briefs. An entry may pin a reasoning effort as `model@effort`, and `## codex`, `## claude-code`, or `## hermes` sections hold lines that apply to one harness only. The grammar, precedence, and effort policy are defined once, in the **pstack-harness** skill.

## Steps

### 1. Detect available models and efforts

Enumerate the model values your session's spawn mechanism accepts, and the reasoning-effort values it accepts per spawn (none where it has no such field, which is the Claude Code case) (find the mechanism per the **pstack-harness** skill); that is the dependable source. If your CLI also exposes a models API or command that lists the user's entitled models, prefer it for completeness. If you cannot detect any, ask the user to paste the slugs they have access to. Never write a real slug you have not confirmed is available. The aliases `inherit-parent` and `auto` are always valid even though they are not detected slugs.

### 2. Load current state

The default mapping is `examples/pstack-models.md` next to this skill. Read both config layers when they exist — workspace `.agents/pstack-models.md`, then `~/.agents/pstack-models.md` — including their harness sections, and treat the merged values (workspace winning per role, a harness section winning over flat lines within a file) as the current choices. Otherwise start from those defaults. Unless the user asked for a per-repo override, the user-level file is the one being configured.

### 3. Map and confirm

The file is shared across CLIs, so a value this harness cannot validate is not wrong — it is another harness's choice (it reads as `inherit-parent` here). Show every role with its current model and effort for this harness, marking values outside the detected set as "(set for another harness — kept unless you change it)" rather than as needing a choice. Ask whether to accept as-is or change specific roles, offering the detected models plus `inherit-parent` and `auto` (both mean: this role runs on the parent chat model, which is how Auto users stay on Auto) as the options. Prefer AskQuestion over free text. For panel roles (how critics, arena runners, architect runners, interrogate reviewers) the value is a list, and one subagent runs per entry, alias entries included, so the list length sets the count. `arena cross-judge pool` is also a list, but Arena selects one value from it whose model family or capability tier differs from the parent's when possible. `swarm workers` is the default model for every worker unless a race or comparison assigns another model per arm. `trail reviewer` is the show-me-your-work reviewer; the skill steps it down one tier whenever it resolves to the model doing the work, so a value that matches the model of another role is fine. `default` is the entry for any spawn whose skill names no role; keep it `inherit-parent` unless the user wants unmapped spawns on a specific model.

### 4. Validate

Run the lint on the file you are about to write, before writing it: `python3 <this skill's directory>/scripts/check-models-config.py <file>`. Any `error:` line (unknown role, bad effort, an effort the model does not support, a duplicate role or section) stops the write; fix the line and re-run. `notice:` lines mark `max` and `ultra` pins; read them back to the user so the expensive tiers are a choice. Every *newly chosen* real slug must be in the detected set; `inherit-parent` and `auto` always pass, and preserved values from another harness are exempt. If a chosen real slug is not available, stop and ask again. A config pointing at a model no harness can use breaks every delegation that reads it.

### 5. Write the config

The target is `~/.agents/pstack-models.md`, or workspace `.agents/pstack-models.md` when the user asked for a per-repo override (only write roles the user actually wants pinned for this repo — every workspace line shadows the user-level one). If your file tool cannot write the target (a harness that scopes writes to the workspace), fall back in order: write it through your shell tool; else write the workspace file and say the config is project-local until copied to `~/.agents/`; else print the final content for the user to save. Never silently drop the write.

Write the file with one line per role, using the same labels poteto-mode uses. Start from `examples/pstack-models.md` next to this skill and keep its header comments. Rewrite the whole file so re-runs stay idempotent, but carry forward every existing line the user did not change — including sections and values this harness could not validate; overwriting another CLI's choices with `inherit-parent` is the one failure mode to avoid. Put a harness-specific pick under its `## <harness>` section and leave the flat lines for the other CLIs. Shape (excerpt):

```
feature, refactoring: sonnet
bug-fix: fable
how critics: fable, opus, sonnet, haiku

## codex
feature, refactoring: gpt-5.6-terra@high
bug-fix: gpt-5.6-sol@xhigh
how critics: gpt-5.6-sol@max, gpt-5.6-sol@xhigh, gpt-5.6-terra@high, gpt-5.6-luna@high
```

### 6. Confirm

Tell the user the config was written and that skills read it the next time they run. Re-running this skill updates it.

### 7. Offer a verification skill (optional)

Check whether the project has a way to drive the real app for proof (a `verify-*` skill, or an existing harness). If not, offer once: "want a project-local verification skill, so agents can drive the app the way a user does and prove changes work? I can generate one with /create-verification-skill." On yes, invoke `/create-verification-skill` (resolves wherever pstack is installed — workspace, user, or plugin). On no, move on without pushing.
