# Port value comparison

This controller compares native Codex, the recorded upstream pstack, and the committed port on three application tasks. Each arm has two repetitions per task. The frozen plan contains 18 application lineages and 36 stage opportunities.

The comparison measures cold-start, relevance-driven skill discovery and application outcomes. It does not explicitly activate poteto-mode. Skill availability does not establish skill use. The retained native transcripts need a separate exposure review before anyone claims that a particular workflow caused an outcome.

## Prepare a frozen comparison

Use Python 3.12 or later. The application owner also needs `sbx`, Docker, the prepared native template, and working model credentials. Discover those tools through `PATH`. This repository has no `mise` task for this controller.

Create a runtime receipt after probing the actual template. The required JSON fields are `template`, `observed_template_id`, `cli_version`, and a `capabilities` object containing `skills: true` and `multi_agent: true`. Retain the bootstrap observations with the receipt. The observed template ID may be a short local identifier. It is not a full OCI digest. Record an archive hash separately if one exists.

Run the following command from the repository root. Replace the directory and runtime receipt with new paths outside the checkout. Preparation creates the directory and refuses an existing one. A nonzero exit, missing `seal.json`, or a calibration receipt whose `passed` field is false means preparation failed.

```sh
python3 evals/port-value/study.py prepare ../port-value-run \
	--runtime-receipt ../port-value-runtime.json \
	--model gpt-6.1-sol --effort high --timeout 240 --seed 73129
```

Preparation freezes both requests, complete project files, private checks, controls, runtime settings, controller sources, and complete guidance trees. It exports upstream `1b6d44ff26d4e242f4e8f68c391e6d2f7ca16def` from `pstack/skills` and current port `701c9a6f09ae3b0bd56a4962ff299c21accf8690` from `skills`. The exported trees do not depend on uncommitted working-tree skills.

The upstream compatibility ledger translates `disable-model-invocation: true` into native `agents/openai.yaml` policy with `allow_implicit_invocation: false`. It records exact before and after bytes and hashes for each edit. All remaining upstream bytes stay unchanged. Tool and model fallback instructions remain part of the upstream workflow. Runtime delegation must be available. An absent capability blocks preparation rather than changing that workflow.

The native arm receives no custom skill tree. Every arm receives the same project and organic request, requested model, effort, execution template, tools, network policy, and deadline. Arm names and private acceptance feedback do not enter requests. The initial arm order is randomized within task and repetition blocks using the recorded seed.

Preparation calibrates each oracle against passing initial and maintenance controls, no-op controls at both stages, and named initial and maintenance defects. Every check must return a strict result with a positive assertion count. The frozen `heldout.json` also checks request bytes against committed public `evals` files at the port pin. That exact-byte check supplements the scenario overlap review in [cases/README.md](cases/README.md). It does not prove absence from external training data.

## Execute planned opportunities

The shared [application owner](../canon/application.py) creates an isolated native session, captures the application, removes the candidate sandbox, and returns the result. Acceptance then reconstructs the capture in a separate Docker container. The container has no network, a read-only application mount, a read-only root, resource limits, and only the private oracle and `checks.json` as checker files. The pinned Python image is the same image used by canon's private Python checks.

Use one planned cell to check the complete two-stage flow. A nonzero exit means a preparation or command error. The resulting native states and acceptance fields decide whether the application succeeded.

```sh
python3 evals/port-value/study.py run ../port-value-run --cell p01
```

Limit the next dispatch to one unspent opportunity with this command. A nonzero exit means a command error. Check `report.json` to identify the dispatched stage and its result.

```sh
python3 evals/port-value/study.py run ../port-value-run --limit 1
```

Run remaining opportunities with at most two concurrent lineages. A nonzero exit means a command error. Native failures, missing captures, and oracle errors remain explicit in `report.json` even when dispatch itself exits zero.

```sh
python3 evals/port-value/study.py run ../port-value-run --concurrency 2
```

An existing stage directory is spent, including a directory left by a crash. Repeating `run` selects only unspent stages. It never retries a spent native call. A study dispatch lock prevents simultaneous controller processes from exceeding the two-lineage limit. Missing or invalid initial capture blocks maintenance. A valid initial capture binds the exact maintenance parent even when initial behavior or native completion failed. Maintenance uses a fresh session and the same arm's guidance. It receives only the frozen maintenance request, without acceptance feedback.

The controller checks frozen inputs and source hashes before each application call and before grading. It also checks the observed local template ID before each call, with a 15-second catalog deadline. Changed input makes the comparison invalid. Start a new preparation after an intentional controller or runtime source change.

## Read all planned outcomes

Generate `report.json` and `report.md` with this command. A nonzero exit means the report could not be generated. An `input_integrity_error` value invalidates acceptance even when earlier behavioral checks passed.

```sh
python3 evals/port-value/study.py report ../port-value-run
```

The report keeps all 36 opportunities, including attempted, incomplete, blocked, and never-started stages. It separates native validity from behavioral acceptance. Both-stage acceptance requires each stage to have valid native completion and a passing private grade. The report retains elapsed time, raw observed usage, unknown usage counts, and paired task outcomes per repetition. Requested model settings do not prove served model identity.

Raw native streams, captures, checker logs, and execution receipts stay in the external run directory. Keep them outside Git. Preserve failed preparations as diagnostic receipts. Do not promote findings from this three-task comparison into a general causal claim or count repetitions as independent task diversity.

## Verify the controller without model calls

The controller tests use actual application snapshots and replay. A recording application callable writes native outcome receipts, and local subprocess oracles check their output. These tests validate the controller, not model behavior or Docker isolation. The application owner's tests cover native process handling and capture integrity separately.

Run this command at the repository root. A nonzero exit, a failure summary, or a zero-test summary means verification failed.

```sh
python3 -m unittest discover -s evals/port-value -p test_study.py -v
```

Run the case controls separately with this command. A nonzero exit, a failure summary, or a zero-test summary means verification failed.

```sh
python3 -m unittest discover -s evals/port-value -p test_cases.py -v
```
