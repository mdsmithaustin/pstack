# The models config

`~/.agents/pstack-models.md` (user) and `.agents/pstack-models.md` (workspace) map each pstack role to a model and a reasoning effort. setup-pstack writes and lints them. Agents read them only through the resolver, which applies the rules below:

```sh
python3 "${PSTACK_SKILLS_ROOT:?}/setup-pstack/scripts/check-models-config.py" --resolve --harness codex feature
```

Failure signal: nonzero exit. It prints one JSON line per arm with `role`, `arm`, `model`, `effort`, `source`, and `notes` when it substituted a value. Run it from the project root or pass `--project <root>`. With no roles it prints every role.

## Grammar

- A role line is `role: entry`, or `role, role: entry` to bind several roles at once. `reflect judgment, divergent, synthesizer` expands the bare labels to `reflect divergent` and `reflect synthesizer`.
- An entry is `model` or `model@effort`. Efforts are `none`, `low`, `medium`, `high`, `xhigh`, `max`, and `ultra`, which is Codex's maximum reasoning with automatic task delegation. The lint rejects an effort a known model cannot take, such as `none` on `gpt-6.1-sol`, `gpt-6-astra`, `gpt-6-sol`, or `gpt-6-luna`, or `ultra` on `gpt-6-luna`, because Codex's `spawn_agent` rejects both. A gpt-6 model outside that list, such as `gpt-6.1-luna`, is checked only at resolve time, against Codex's model list.
- `inherit-parent` and `auto`, with or without `@effort`, run the arm on the parent chat model.
- Panel roles take a comma list, one arm per entry: `arena runners`, `arena cross-judge pool`, `architect runners`, and `interrogate reviewers`.
- A `## codex`, `## claude-code`, `## grok`, or `## hermes` header starts a section whose lines apply to that CLI only. Lines above any header are flat lines and apply everywhere. Put a CLI's own slug, such as `gpt-6-sol` or `grok-4.7`, under that CLI's section, because Codex, Hermes, and Grok Build each accept any model name from a flat line.
- `trail reviewer` runs the show-me-your-work reviewer and every independent verdict and review, including the audit lanes the **swarm** skill gives it. When it resolves to the model that did the work, the spawn steps down one tier so the review stays cross-model. `default` is the entry for a spawn whose skill names no role, and ships as `inherit-parent`.
- `# budget: <label> (<effort>)` records the budget setup-pstack last applied. Resolution never reads it.
- `# resume-priority: source=destination,...` orders recovery destinations for one source. Names are `codex`, `claude-code`, `grok`, or `hermes`. Reject malformed directives, duplicate source directives, duplicate destinations, self destinations, and unknown names.

## Resume priority

The workspace directive overrides the user directive for the same source. Other sources keep their user setting. Without a directive, Codex prefers Claude Code and Claude Code prefers Codex. Hermes and Grok have no implicit destination. The shipped example shows the reciprocal defaults.

Priority does not change role resolution, dispatch preference, permission settings, or retry allowance. A listed destination still needs a concrete exact role and panel arm resolution and current observed capability evidence. Installing a CLI does not certify it. Preserve every existing priority directive when setup rewrites the file. Change a source only when the user requests it.

## Resolution

1. **Layers.** The first layer that names the role wins: the workspace file's section for this CLI, the user file's section, the workspace file's flat lines, the user file's flat lines, then the shipped default in setup-pstack's `examples/pstack-models.md`, its section for this CLI before its flat lines. The shipped flat lines match every skill's inline default. A section beats a flat line in either file, so a per-repo line written for one CLI never overrides another CLI's section. The resolver prints the winning layer as `source`: `workspace ## <cli>`, `user ## <cli>`, `workspace flat`, `user flat`, `skill default ## <cli>`, or `skill default`.
2. **One line per role.** The winning line supplies the whole entry. Model and effort come from that line, and a panel's arms all come from it. An unsuffixed line never borrows an effort from another file.
3. **Usable values.** Claude Code takes the aliases `fable`, `opus`, `sonnet`, and `haiku`, and the efforts `low` through `max`. Codex, Hermes, and Grok Build take any other model name. Codex and Hermes take every effort the model takes, and Grok Build takes `low` through `xhigh`. A model the CLI cannot use becomes `inherit-parent`. An effort the CLI or the model cannot use is dropped, and the effort policy fills it as if the line wrote none.
4. **Alias translation.** On Codex and Grok Build a Claude alias translates instead of inheriting. Codex maps `fable` to `gpt-6-sol@max`, `opus` to `gpt-6-sol@xhigh`, `sonnet` to `gpt-6-sol@high`, and `haiku` to `gpt-6-luna@high`, and the translated effort applies only when the line wrote none. Grok Build maps every alias to `grok-4.7`, its one model tier today, and keeps the line's own effort. Hermes has no translation, so an alias there is `inherit-parent`.
5. **Effort policy.** A line without a usable effort runs at the session effort on Claude Code and Grok Build. On Codex and Hermes a spawn that names a model and no effort gets that model's default effort, so the policy fills it: `xhigh` for `hardest tasks`, `judgment and prose`, `bug-fix`, `perf-issue`, `hillclimb`, `how explainer`, `why synthesizer`, `reflect judgment`, `reflect divergent`, `reflect synthesizer`, `arena cross-judge pool`, `architect runners`, and `trail reviewer`, and `high` for every other role. A line whose model is `inherit-parent` gets no fill, because a full-history fork inherits the parent's effort. Nothing in the policy produces `max` or `ultra`. Those come only from a written suffix, the translation of `fable`, or an explicit escalation in the task.
6. **Codex's model list.** On Codex the resolver reads the model list Codex keeps at `$CODEX_HOME/models_cache.json`, the catalog `codex debug models` prints. `spawn_agent` accepts only the efforts that list gives a model, so the resolver drops any other effort with a note and the effort policy fills it. When the list lacks the policy's floor too, the arm runs at the model's highest listed effort below the floor, or at its lowest listed effort when none is below, with a note. A `gpt-6-<tier>` or `gpt-6.1-<tier>` model runs as the newest of the two that the list carries with the line's effort among its levels, so the written effort drops only when neither release takes it. After an effort fill, the same pick runs with the filled effort. So `gpt-6-sol@high` runs as `gpt-6.1-sol@high`, and `gpt-6.1-luna` runs as `gpt-6-luna` on an account that lacks it. Without a readable list the lint's table decides the efforts and the model stays as written. A note names each swap.

## Resolve recovery candidates

`resolve-resume.py` is a read-only path for the saved role and one-based panel
arm. It calls the existing `resolve_role` with the current destination's
layers and model catalog. It preserves the full resolved source and notes.
It does not launch, change settings, or consume a retry.

```sh
python3 "${PSTACK_SKILLS_ROOT:?}/setup-pstack/scripts/resolve-resume.py" \
  --source claude-code --role feature --arm 1 --project "${PROJECT_ROOT:?}" \
  --contexts /absolute/path/to/observed-contexts.json \
  --oracle "${PSTACK_SOURCE_ROOT:?}/evals/resume-recovery/oracle.py"
```

Failure signal for eligibility is exit 1. Invalid arguments, configuration,
or context input exit 2. Exit 0 means at least one candidate is eligible.
The result has a `priority` object and ordered `candidates`. Each candidate
has `harness`, exact `resolution`, observed `route` and `version`, retained
`eval_receipt`, `eligible`, and a denial `reason` when ineligible.

`--contexts` names an operator-owned JSON object keyed by destination
harness. Each value records `available`, `route`, `version`,
`permission_context`, and an absolute `eval_run` directory. The canonical
route is `skill-ci-pinned-runner`, with suite `pstack-resume-runner-v2`.
The five binding keys are `harness`, `resolution`, `route`, `version`, and
`permission_context`. Its `runner` object records the exact pin, driver and
wrapper paths and SHA-256 hashes, and existing backend option. Diagnostic
preparation accepts `version: null`. The resolver requires an observed
version for eligibility. Missing observations deny eligibility.

`--oracle` names the trusted current oracle from the source checkout.
Omitting it denies eligibility. The oracle reruns against retained raw
execution provenance and fixture outputs. A changed suite, fixture, oracle,
resolution, source, notes, route, version, or relevant permission context
invalidates the evidence. A saved receipt alone is insufficient. The
receipt retains observed invocation and evidence hashes, not an agent's
self-reported pass boolean. The run directory and oracle share the existing
trusted local operator boundary. Hashes detect changed evidence and do not
provide execution attestation against a malicious local operator.

The source checkout's `evals/resume-recovery/README.md` prepares a case for
the canonical public `tools/run_runner.py` driver. Codex uses `--codex-cmd`.
The resolver destination `claude-code` uses driver backend `claude` and
`--claude-bin`. Preparation prints a command without launching it.
Installed skill packages omit the eval corpus.

Current captures always yield a gap report. Claude's native CLI version and
attributed permission-gate denial can be observed. Applied effort, full
effective permissions, post-wrapper origin, executed pin, and host/archive
authority remain unproven. `check` exits nonzero without a
receipt, so neither destination can currently become eligible through this
oracle. Resolver-unit stub tests exercise receipt rechecking only. They
cannot certify an actual destination, and fake captures never become
production eligible.

Installed but unregistered Hermes and Grok remain a coverage gap. The
canonical consumer has no backend for either. Native routes also need
observed evidence support. Keep explicit human model overrides, native
delegation preference, CLI fallback, and existing retry limits.
