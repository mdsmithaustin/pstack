# What `multi_agent_v2` changes on Codex 0.167.0

Evidence for the setup-pstack step 0d change in issue 542. The question is whether turning the `multi_agent_v2` flag on changes whether or how `spawn_agent` reaches a model, and whether `[agents] enabled = false` still removes it with the flag on.

## Method

`run-cell.sh` starts `codex exec` in a fresh `CODEX_HOME` per cell, with only `auth.json` copied in, so the user's own config and feature flags are untouched. A cell sets its flags with `codex features enable|disable`, or appends `[agents] enabled = false`. Then it asks the model to say whether `spawn_agent` is available, spawn one child that answers `PONG`, and print the answer. The prompt tells the model to search deferred tool namespaces before calling the tool missing.

`summarize.py` reduces each cell's rollouts to `results/<cell>.json`. Tool presence and the spawn arguments come from the rollout records, not from what the model said. Raw rollouts carry account identifiers and rate-limit data, so they are not kept here.

The two models are `gpt-6.1-sol` (`multi_agent_version: v2`) and `gpt-5.6-luna` (`v1`), per the model catalog the private home fetched. One run per cell, root effort `low`, on 2026-11-17. A first pass of the same cells used a prompt that did not tell the model to search deferred namespaces. The v1 model then answered `NO_SPAWN` while the namespace was listed, so the prompt now says to search, and all twelve cells were rerun.

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

Every cell that had a tool spawned a child on the model the root ran on at effort `low`, and the root received `PONG`. The two `agents-off` cells had no tool, and their root received no child answer.

## What this settles

- On a v2 model the flag changes nothing. With the flag off, the model's catalog version picks the shape, and `multi_agent = false` does not remove it either.
- On a v1 model the flag switches the tool from the deferred `multi_agent_v1` namespace with `fork_context` to the direct v2 tool with `task_name` and `fork_turns`. Turning `multi_agent` off did not remove the v1 tool.
- `[agents] enabled = false` removes `spawn_agent` from both models with the flag off, and does not with the flag on. This confirms the claim in step 0d.
- Not tested: other Codex releases, other models, a model or effort passed on `spawn_agent` (the spawn matrix in issue 542 covers that), and repeat runs. The v1 spawn goes through code mode, so it shows up as an `exec` custom tool call, not a `spawn_agent` function call.

## Rerun

```sh
out=$(mktemp -d)
evals/issue-542-v2-flag/run-cell.sh "$out" luna-v2 gpt-5.6-luna enable:multi_agent_v2
python3 -I evals/issue-542-v2-flag/summarize.py "$out" luna-v2
```

The cell names in `results/` map to the flags in the table: `<model>-default`, `<model>-v2`, `<model>-ma-off`, `<model>-ma-off-v2`, `<model>-agents-off`, `<model>-agents-off-v2`, with `sol` and `luna` for the models.
