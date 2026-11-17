# Live spawn matrix for Codex `multi_agent_v2` (issue 542)

Issue 542 asks for live proof that the pstack skills that spawn agents spawn correctly on Codex `multi_agent_v2`. This directory holds that matrix for the nine rows the issue names. It has one live `codex exec` session per attempt on `gpt-6.1-sol`, plus `gpt-5.6-luna` runs with the v2 flag on and off. It covers the issue's work items 3 and 4. Three other skills that spawn, `automate-me`, `no-comments` and `recall`, have no row ([#555](https://github.com/mdsmithaustin/pstack/issues/555)). The setup-pstack step 0d change and its live test are a separate PR.

Ran on 2026-11-17 with `codex-cli 0.167.0` (the `cli_versions` field of every extract), against the skills at commit `a29fb3e84609d92e63fda356bf88ada5aa88b77e`.

## Result

Every row passes on its last attempt. One row failed an attempt for a pstack reason and has issue [#550](https://github.com/mdsmithaustin/pstack/issues/550). No row was blocked by the harness.

Each spawn was checked on four things, read from the rollouts and never from the model's reply.

- `spawn_agent` fired.
- The fork field was set explicitly. On v2 that is `fork_turns`, and a spawn that passes a model must use `"none"`. On v1 it is `fork_context`, and a spawn that passes a model must use `false`.
- The child's own `turn_context` model and effort equal what the spawn asked for. A v2 child is matched to its call by task name. A v1 child has no task name, so it is matched by agent type and passes when it ran a model and effort that some spawn of its agent type asked for.
- That model and effort are an arm of `setup-pstack/scripts/check-models-config.py --resolve --harness codex` for the row's roles, run against the fixture project. The row's roles include the roles of skills it calls, so `architect` also resolves the `how`, `why`, and `arena` roles.

| Row | Lead model | Flag | Spawns | Fork field | Agent type | Resolved vs observed | Attempts | Result |
|---|---|---|---|---|---|---|---|---|
| `how` | gpt-6.1-sol | on | 1 | `fork_turns: "none"` | default | how explainer asked and ran at gpt-6.1-sol medium | 1 | PASS |
| `why` | gpt-6.1-sol | on | 2 | `fork_turns: "none"` | default | investigator gpt-6.1-sol low, synthesizer gpt-6.1-sol medium, both as asked | 1 | PASS |
| `arena` | gpt-6.1-sol | on | 4 | `fork_turns: "none"` | default | runners gpt-6.1-sol, gpt-6-luna and gpt-6.1-terra at low, judge gpt-6-astra low, all as asked | 1 | PASS |
| `architect` | gpt-6.1-sol | on | 7 | `fork_turns: "none"` | default | runners on three models at low, plus the nested `how`, `why` and `arena` roles, all as asked | 1 | PASS |
| `swarm` | gpt-6.1-sol | on | 3 | `fork_turns: "none"` | default | three workers at gpt-6-luna low, as asked | 1 | PASS |
| `interrogate` | gpt-6.1-sol | on | 3 | `fork_turns: "none"` | default | reviewers gpt-6.1-sol, gpt-6-astra and gpt-6.1-terra at low, as asked | 1 | PASS |
| `reflect` | gpt-6.1-sol | on | 4 | `fork_turns: "none"` | default | tooling and judgment lenses at gpt-6.1-sol low, divergent lens at medium, synthesizer at low, as asked | 2 | PASS |
| `poteto-mode` | gpt-6.1-sol | on | 3 | `fork_turns: "none"` | default, `poteto-agent`, `trail reviewer` | feature delegate gpt-6.1-sol low, reviewer gpt-6-astra medium, explainer medium, as asked | 2 | PASS |
| `trail-reviewer` | gpt-6.1-sol | on | 1 | `fork_turns: "none"` | `trail reviewer` | gpt-6-astra medium, as asked | 1 | PASS |
| `how-v1` | gpt-5.6-luna | off | 2 call sites, 4 children | `fork_context` | explorer, default | resolved gpt-6.1-sol low and medium, children asked and ran at those | 2 | PASS on attempt 2 |

`Flag` is `-c features.multi_agent_v2=true`. `how-v1` is the `fork_context` row, so it runs with the flag off. The `extracts/` directory has one file per attempt, and `matrix.py` prints the full per-spawn table from them.

## Earlier attempts

Two attempts did not reach their row and one failed it.

- `reflect` attempt 1 (extract verdict FAIL) spawned nothing. The lead ran the code, answered, and skipped the review panel because `reflect` says to skip a trivial session and the session was one question. That follows the skill, so no issue. Attempt 2 gave the session a real learning, a wrong change, a correction, and a standing instruction. The skill then spawned its panel.
- `poteto-mode` attempt 1 is a scope miss, not a failure. Its extract verdict is PASS, because the one spawn it made, the independent `trail reviewer`, passed every check. The row's point was the feature delegate, which that attempt never spawned. The lead chose the standard route and implemented the small change itself, which the Feature playbook allows for one writer. Attempt 2 asked for two independent pieces and the lead spawned a `poteto-agent` feature delegate at the `feature` role's model and effort.
- `how-v1` attempt 1 (extract verdict FAIL) failed. The lead spawned three explorers with no model, effort, or `fork_context`, and an explainer with no model or effort. Every child ran at the lead's `gpt-5.6-luna` high instead of the resolved `gpt-6.1-sol`. Attempt 2 passed with the same prompt and config. The failure is intermittent and filed as [#550](https://github.com/mdsmithaustin/pstack/issues/550).

## Observations for issue 542

- With `features.multi_agent_v2=true`, a `gpt-5.6-luna` lead (listed `v1` in Codex's model cache) used the v2 `spawn_agent` shape. Its rollout records `multi_agent_version: v2`, it set `fork_turns: "none"`, and its four children ran at the asked model and effort. That run is `extracts/how-v1-flag-on-attempt1.json`. With the flag off, the same model reached `multi_agent_v1__spawn_agent` through code-mode `exec` (the `tool_name` of its spawns in `extracts/how-v1-attempt1.json` and `how-v1-attempt2.json`) and its children record `multi_agent_version: v1`. In these two runs the flag changed the tool shape on a v1 model, which bears on the step 0d change.
- On v1 the lead used the built-in `explorer` agent type for explorers, where `how` and `codex.md` say `default`. The explorers ran read-only at the asked model and effort, so this is a note and no row failed on it.
- The `trail reviewer` role resolved to `gpt-6-astra` medium for a `gpt-6.1-sol` work model because the fixture config names it. The native `trail reviewer` agent type loaded from the fixture's `.codex/agents`.

## How a row runs

`run_row.py ROW --root DIR` builds everything under `DIR`, a fresh directory outside this repository.

- A private `CODEX_HOME` and `HOME`. Only `auth.json` is copied from the real login. The user's `~/.codex/config.toml` and feature flags are never read or changed.
- A throwaway `shop` repository from `fixture.py`, three commits whose messages hold the reasons that `why` asks about.
- The skills from this checkout's `HEAD`, installed to `.agents/skills`, and the personas registered through `subagents.py install --harness codex`, which writes `.codex/agents`.
- `models.md` copied to the project's `.agents/pstack-models.md`. It sets a different low or medium effort per role and spreads panels over `gpt-6.1-sol`, `gpt-6-luna`, `gpt-6.1-terra` and `gpt-6-astra`, so a child that ignores its spawn arguments shows up. The skill defaults would run most roles at max.
- The lead defaults to `gpt-6.1-sol` high, with `approval_policy=never` and a `workspace-write` sandbox. `rows.json` holds each row's roles, models and prompts as of the last attempt. The prompts of `reflect` attempt 1 and `poteto-mode` attempt 1 survive only in the `lead_prompts` of their extracts.

`reduce.py RUN_DIR --out EXTRACT.json` reads the rollouts under `RUN_DIR/codex-home/sessions` and writes the extract. Per spawn the extract keeps the style, tool name, task name, agent type, fork field and value, the model and effort asked for, the spawn's output, and the model and effort of the child's own `turn_context`. It also keeps `cli_versions`, the resolved roles, the lead's prompts, the child threads' ids, roles and contexts, and the verdict with its problems. It holds no spawn message, model answer or credential, and the spawn arguments themselves are not kept. Rollout paths are replaced with `<run>`. `regen.sh RUNS_DIR` rebuilds every extract, and `python3 -m unittest test_reduce` checks the reducer.

## Not covered

- The recorded attempts do not establish reliability. A row that passes once does not show how often the lead gets it right, and #550 shows a lead can differ between two runs of one prompt.
- The spawn briefs are encrypted in the rollouts, so a brief's content is unchecked. Role matching uses the model and effort pair, and two roles that share a pair cannot be told apart.
- A `PASS` does not mean the skill's output was good, only that its spawns were well formed.
- `gpt-5.6-luna` is the only v1 model tried, and only on `how`.
- `gpt-6.1-sol` is the only v2 lead model tried. The other v2 models in Codex's model cache (`gpt-6.1-terra`, `gpt-6-astra`, `gpt-6-sol`, `gpt-6-luna`, `gpt-5.6-sol`, `gpt-5.6-terra`) were not run as leads.
- A v1 child is matched to its spawn by agent type, and the recorded v1 spawns carry no child id. Two v1 spawns of one agent type that ask for different models cannot be told apart, so a child passes if it ran either ask. A v1 spawn that started no child of its type fails.
- The `trail-reviewer` row ran against the skills at `a29fb3e8`, before #549 changed how Codex trail-reviewer resolution reads the session model. The fixture config names the role, so `check-models-config.py --resolve` gives the same pair on current trunk, but no live run covers #549.
- `automate-me`, `no-comments` and `recall` spawn agents and have no row ([#555](https://github.com/mdsmithaustin/pstack/issues/555)).
- The `multi_agent_v2` flag was not tested on a v2 model with the flag off. That belongs to the step 0d test.
