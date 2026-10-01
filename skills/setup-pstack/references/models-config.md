# The models config

`~/.agents/pstack-models.md` (user) and `.agents/pstack-models.md` (workspace) map each pstack role to a model and a reasoning effort. setup-pstack writes and lints them. Agents read them only through the resolver, which applies the rules below:

```sh
python3 "${PSTACK_SKILLS_ROOT:?}/setup-pstack/scripts/check-models-config.py" --resolve --harness codex feature
```

Failure signal: nonzero exit. It prints one JSON line per arm with `role`, `arm`, `model`, `effort`, `source`, and `notes` when it substituted a value. Run it from the project root or pass `--project <root>`. With no roles it prints every role.

## Grammar

- A role line is `role: entry`, or `role, role: entry` to bind several roles at once. `reflect judgment, divergent, synthesizer` expands the bare labels to `reflect divergent` and `reflect synthesizer`.
- An entry is `model` or `model@effort`. Efforts are `none`, `low`, `medium`, `high`, `xhigh`, and `max`. `ultra` is Codex's Pro mode and is valid only on `gpt-5.6-sol`.
- `inherit-parent` and `auto`, with or without `@effort`, run the arm on the parent chat model.
- Panel roles take a comma list, one arm per entry: `arena runners`, `arena cross-judge pool`, `architect runners`, and `interrogate reviewers`.
- A `## codex`, `## claude-code`, or `## hermes` header starts a section whose lines apply to that CLI only. Lines above any header are flat lines and apply everywhere.
- `trail reviewer` runs the show-me-your-work reviewer and every independent verdict and review. When it resolves to the model that did the work, the spawn steps down one tier so the review stays cross-model. `default` is the entry for a spawn whose skill names no role, and ships as `inherit-parent`.
- `# budget: <label> (<effort>)` records the budget setup-pstack last applied. Resolution never reads it.

## Resolution

1. **Layers.** The first layer that names the role wins: the workspace file's section for this CLI, the user file's section, the workspace file's flat lines, the user file's flat lines, then the shipped default in setup-pstack's `examples/pstack-models.md`, its section for this CLI before its flat lines. The shipped flat lines match every skill's inline default. A section beats a flat line in either file, so a per-repo line written for one CLI never overrides another CLI's section.
2. **One line per role.** The winning line supplies the whole entry. Model and effort come from that line, and a panel's arms all come from it. An unsuffixed line never borrows an effort from another file.
3. **Usable values.** Claude Code takes the aliases `fable`, `opus`, `sonnet`, and `haiku`, and the efforts `low` through `max`. Codex and Hermes take any other model name and also `none`, plus `ultra` on `gpt-5.6-sol`. A model the CLI cannot use becomes `inherit-parent`. An effort the CLI cannot use is dropped, and the effort policy fills it as if the line wrote none.
4. **Codex translation.** On Codex a Claude alias translates instead of inheriting: `fable` to `gpt-5.6-sol@max`, `opus` to `gpt-5.6-sol@xhigh`, `sonnet` to `gpt-5.6-terra@high`, and `haiku` to `gpt-5.6-luna@high`. The translated effort applies only when the line wrote none. Hermes has no translation, so an alias there is `inherit-parent`.
5. **Effort policy.** A line without a usable effort runs at the session effort on Claude Code. On Codex and Hermes a spawn that names a model and no effort gets that model's default effort, so the policy fills it: `xhigh` for `hardest tasks`, `judgment and prose`, `bug-fix`, `perf-issue`, `hillclimb`, `how explainer`, `why synthesizer`, `reflect judgment`, `reflect divergent`, `reflect synthesizer`, `arena cross-judge pool`, `architect runners`, and `trail reviewer`, and `high` for every other role. A line whose model is `inherit-parent` gets no fill, because a full-history fork inherits the parent's effort. Nothing in the policy produces `max` or `ultra`. Those come only from a written suffix, the translation of `fable`, or an explicit escalation in the task.
