# What `multi_agent_v2` changes on Codex 0.167.0

Evidence for the setup-pstack step 0d change in issue 542. The question is whether turning the `multi_agent_v2` flag on changes whether or how `spawn_agent` reaches a model, and whether `[agents] enabled = false` still removes it with the flag on.

## Method

`run-cell.sh` starts `codex exec` in a fresh `CODEX_HOME` per cell, with only `auth.json` copied in, so the user's own config and feature flags are untouched. A cell sets its flags with `codex features enable|disable`, or appends `[agents] enabled = false`. Then it asks the model to say whether `spawn_agent` is available, spawn one child that answers `PONG`, and print the answer. The prompt tells the model to search deferred tool namespaces before calling the tool missing.

`summarize.py` reduces each cell's rollouts to `results/<cell>.json`. Tool presence and the spawn arguments come from the rollout records, not from what the model said. The twelve original cells ran with the operator's real `HOME`. `luna-v2-disabled` also ran with it, since `run-cell.sh` leaves `HOME` alone. The step 0d sessions below run with `HOME` private too. Raw rollouts carry account identifiers and rate-limit data, so they are not kept here.

The two models are `gpt-6.1-sol` (`multi_agent_version: v2`) and `gpt-5.6-luna` (`v1`), per the model catalog the private home fetched. One run per cell, root effort `low`, on 2026-11-17, except `luna-v2-disabled`, which ran on 2026-11-18. A first pass of the same cells used a prompt that did not tell the model to search deferred namespaces. The v1 model then answered `NO_SPAWN` while the namespace was listed, so the prompt now says to search, and all twelve cells were rerun.

## Results

`default` is `multi_agent` on and `multi_agent_v2` off, as `codex features list` shows here. `v2` runs `codex features enable multi_agent_v2`. `ma-off` runs `codex features disable multi_agent`. `agents-off` sets `[agents] enabled = false`.

| Cell setting | `gpt-6.1-sol` (v2 model) | `gpt-5.6-luna` (v1 model) |
| --- | --- | --- |
| default | `spawn_agent` v2: `task_name`, `fork_turns` | deferred `multi_agent_v1` namespace, called through `exec`: `fork_context` |
| v2 | same as default | `spawn_agent` v2: `task_name`, `fork_turns` |
| ma-off | same as default | same as default (v1 stays) |
| ma-off, v2 | v2 shape | v2 shape |
| agents-off | no `spawn_agent` | no `spawn_agent`, no `multi_agent_v1` namespace |
| agents-off, v2 | v2 shape | v2 shape |
| v2 disabled (`codex features disable multi_agent_v2`) | not run | same as default (`luna-v2-disabled.json`) |

Every cell that had a tool spawned a child on the model the root ran on at effort `low`, and the root received `PONG`. The two `agents-off` cells had no tool, and their root received no child answer.

## What this settles

- On a v2 model the flag changes nothing, except under `[agents] enabled = false`, where it restores `spawn_agent` (`sol-agents-off.json` has no tool, `sol-agents-off-v2.json` has the v2 shape). With the flag off, the model's catalog version picks the shape, and `multi_agent = false` does not remove it either.
- On a v1 model the flag switches the tool from the deferred `multi_agent_v1` namespace with `fork_context` to the direct v2 tool with `task_name` and `fork_turns`. Turning `multi_agent` off did not remove the v1 tool.
- `[agents] enabled = false` removes `spawn_agent` from both models with the flag off, and does not with the flag on. Step 0d's rule to name `multi_agent_v2` as the alternative that overrides the line rests on this.
- Not tested: other Codex releases, other models, a model or effort passed on `spawn_agent` (the spawn matrix in issue 542 covers that), and repeat runs. The v1 spawn goes through code mode, so it shows up as an `exec` custom tool call, not a `spawn_agent` function call.

## How Codex edits the `multi_agent_v2` setting

`config-forms.sh` runs `codex features enable|disable multi_agent_v2` on each form of the setting in a private home, and `results/config-forms.txt` holds its output. Step 0d's edit rules rest on it.

- `codex features disable multi_agent_v2` on an empty file writes a `[features.multi_agent_v2]` table with `enabled = false`.
- `codex features enable multi_agent_v2` edits the setting in place in all three forms: the `[features.multi_agent_v2]` table, `multi_agent_v2 = false` under `[features]`, and a top-level `features.multi_agent_v2 = false`. On a file with `[features]` and no setting it appends the key under that table.
- A second `multi_agent_v2` key beside the table or beside the dotted key, and a second `[features]` table, each make `codex features list` exit 1 with `failed to load bootstrap configuration`.

## Step 0d as a Codex session reads it

`run-step-0d.sh` starts a session at effort `low` with `CODEX_HOME` and `HOME` both private to the cell, so the host's `~/.codex` and `~/.agents` never reach it, and with `auth.json` and the checkout's `setup-pstack` and `pstack-harness` copied under `skills/`. The prompt tells it to read that copy of the skill, no other, and run only step 0d, ending with an OFFERS list. Step 0d tells the session to run `codex --version` and `codex features list` first, and `check-step-0d.py` fails a run that never ran `codex --version`. It also reads the rollout and fails unless the session read only the checkout's copy, the OFFERS list matches the kind below, no offer is `multi_agent = true`, and the tool list matches the kind. It also fails a run whose `HOME` or `CODEX_HOME` sits outside the cell, or whose tool calls name the host's `~/.codex`. Each record's `isolation` field says which paths the run used. Each record carries `skill_blob`, the git blob hash of the `SKILL.md` the session read, so a record names the text it tested. All runs are Codex 0.167.0 on 2026-11-18.

| Kind | Model | Config | The text says | Result (`step-0d/`) |
| --- | --- | --- | --- | --- |
| `agents-off` | `gpt-6.1-sol` (v2) | `[agents] enabled = false` | delete the line first, then name `multi_agent_v2` as the alternative that overrides the disable | 2 of 2 runs |
| `features-off` | `gpt-6.1-sol` (v2) | `[features] multi_agent = false` and `[agents] enabled = false` | the same two offers, and nothing for `multi_agent = false` | 2 of 2 runs |
| `features-off-flag` | `gpt-6.1-sol` (v2) | `[features] multi_agent = false`, and `-c agents.enabled=false` at launch, which no file shows | no offer: the only key a file shows is inert, so name the unreadable cause | 2 of 2 runs offered none |
| `v1-default` | `gpt-5.6-luna` (v1) | default config | the deferred `multi_agent_v1` tool counts as callable, and `multi_agent_v2` is an optional switch to the direct tool | 6 of 7 runs offered only that; `v1-default-3-failed.json` offered `codex features enable multi_agent`, a slip for `multi_agent_v2`, and its rerun passed |
| `v2-disabled` | `gpt-5.6-luna` (v1) | `codex features disable multi_agent_v2`, which writes `[features.multi_agent_v2]` with `enabled = false` | the optional switch, saying it overrides the disable and changing `enabled` in place, or using the command | 3 of 3 runs |

`main-text-features-off-flag.json`, `main-text-v1-default.json` and `main-text-v2-disabled.json` run the same configs with step 0d from `origin/main` at `a29fb3e8` (`PSTACK_REPO` pointing at an export of that commit). The first offers `multi_agent = true`. The other two offer nothing, and none of the three runs `codex --version`. All three fail the checker, so the scenarios tell the old text from the new one. In the text before this round, the `v2-disabled` config produced a one-line "enable `multi_agent_v2`" offer that never said it overrides the disable.

```sh
out=$(mktemp -d)
evals/issue-542-v2-flag/run-step-0d.sh "$out" v1-default-1 v1-default
python3 -I evals/issue-542-v2-flag/check-step-0d.py "$out" v1-default-1 v1-default
```

What these runs do not show. The sessions ran code mode and shell reads, so the checker reads `custom_tool_call` inputs for the skill path. The older-release rule (`multi_agent = true` before 0.167.0) was not run, because only Codex 0.167.0 was installed, and no run put the key in a project `.codex/config.toml`. A session's reply is graded on its OFFERS list, not on an edit it never made. Replies vary: across the batches of 2026-11-18 on this text, the first `v1-default` runs sometimes offered nothing or left the offer unlabeled, which the wording "begin the offer with the word Optional" fixed. All records here ran on the text that `skill_blob` names. `v2-disabled-2.json` was regraded, not rerun, after the personal-paths lint read a path the model had shortened to `/private/tmp/.../home` as a home path. The checker now scrubs that form. The checker accepts the OFFERS heading with or without `#`, and "no repair is needed" as well as "optional".

The checker has a model-free test, `evals/promises/test_step_0d_checker.py`, in the directory that CI discovers. It runs `run-step-0d.sh` and `check-step-0d.py` against a stub `codex`, from a symlinked directory with a relative output root, and fails when the record names a raw path or the run keeps `auth.json`.

## Rerun

```sh
out=$(mktemp -d)
evals/issue-542-v2-flag/run-cell.sh "$out" luna-v2 gpt-5.6-luna enable:multi_agent_v2
python3 -I evals/issue-542-v2-flag/summarize.py "$out" luna-v2
```

The cell names in `results/` map to the flags in the table: `<model>-default`, `<model>-v2`, `<model>-ma-off`, `<model>-ma-off-v2`, `<model>-agents-off`, `<model>-agents-off-v2`, with `sol` and `luna` for the models. `luna-v2-disabled` runs `run-cell.sh "$out" luna-v2-disabled gpt-5.6-luna disable:multi_agent_v2`.
