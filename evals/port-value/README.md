# Port value comparison

This controller compares native Codex, the recorded upstream pstack, and the committed port on three application tasks. Each arm has two repetitions per task. The frozen plan contains 18 application lineages and 36 stage opportunities.

The comparison makes skills available for cold-start, relevance-driven discovery and measures executable application acceptance. It does not explicitly activate poteto-mode. Skill availability does not establish skill use. The retained native transcripts need a separate exposure review before anyone claims that a particular workflow caused an outcome. The private oracles do not grade requested README updates or broader task quality.

## Prepare a frozen comparison

Use Python 3.12 or later. The application owner also needs `sbx`, Docker, the prepared native template, and working model credentials. Discover those tools through `PATH`. This repository has no `mise` task for this controller.

Create a runtime receipt after probing the actual template. The required JSON fields are `template`, `observed_template_id`, `cli_version`, and a `capabilities` object containing `skills: true` and `multi_agent: true`. Retain the bootstrap observations with the receipt. The observed template ID may be a short local identifier. It is not a full OCI digest. Record an archive hash separately if one exists.

Run the following command from the repository root. Replace the directory and runtime receipt with new paths outside the checkout. Preparation creates the directory and refuses an existing one. A nonzero exit, missing `seal.json`, or a calibration receipt whose `passed` field is false means preparation failed.

```sh
python3 evals/port-value/study.py prepare ../port-value-run \
	--runtime-receipt ../port-value-runtime.json \
	--model gpt-6.1-sol --effort high --timeout 240 --seed 73129
```

Preparation freezes both requests, complete project files, private checks, controls, runtime settings, controller sources, and complete guidance trees. It exports upstream `1b6d44ff26d4e242f4e8f68c391e6d2f7ca16def` from `pstack/skills` and `pstack/agents`, and current port `701c9a6f09ae3b0bd56a4962ff299c21accf8690` from `skills`. The exported trees do not depend on uncommitted working-tree skills. Separate project and guidance snapshots preserve runtime file modes before preparation seals the input copies read-only. Runtime requests use those prepared manifests so Git cloning preserves the same guidance identity.

The upstream compatibility ledger records 102 invocation-policy edits. It translates `disable-model-invocation: true` into native `agents/openai.yaml` policy with `allow_implicit_invocation: false`. It also records five persona setup entries. Two retain the exact pinned root persona files and their source hashes. The other three contain the registration adapter and the generated `poteto-agent` and `comment-sicko` native TOML files. Each entry retains before and after bytes and hashes.

The upstream registration adapter occupies the existing application owner's `pstack-harness/scripts/subagents.py` installer path. It adds no `pstack-harness/SKILL.md`. The native persona instructions contain the upstream body plus a local skill-loading prefix. All upstream skill workflow bodies and tool and model fallback instructions stay unchanged. This arm is the minimally adapted upstream package, including its required personas. The current arm uses its pinned native port and installer.

The runtime receipt establishes generic delegation capability. Successful file registration does not prove that Codex loaded or invoked the named personas. A separate native preflight must establish that capability before task calls. Registration tests alone cannot establish workflow efficacy.

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

The report keeps all 36 opportunities, including attempted, incomplete, blocked, and never-started stages. It separates native validity from executable application acceptance. Both-stage acceptance requires valid native completion, a replayable retained capture, and a passing strict private grade for each stage.

Report generation validates the capture's blobs and manifest and requires its directory to be the planned stage's `application/harvest/capture`. It binds the application receipt and request claim to the frozen request, arm guidance, and runtime. The initial parent must match the frozen project. The maintenance parent must match the same lineage's validated retained initial capture. It also binds the grade to the stage, oracle, and capture. It compares the retained acceptance receipt and parses the oracle output again.

Invalid records receive an explicit `evidence_error` and cannot pass. Malformed state, native validity, usage, total elapsed, and native duration fields receive safe report values before aggregation. Duration values must be null or nonnegative finite numbers. Native results, usage, and durations require a retained application receipt bound to the frozen stage inputs, including attempts without a capture. Reported usage and durations must match that receipt. Invalid retained evidence makes native results, usage, and both durations unknown for that stage. Correctly bound failed attempts retain their known measurements without passing acceptance. These errors preserve all planned opportunities. Reporting never repeats spent calls.

The report retains two separate durations. `native_elapsed_s` measures the native process inside the sandbox. `elapsed_s` measures the application attempt from its claim through sandbox cleanup and excludes acceptance grading. Each arm reports sums of known values and separate known and unknown opportunity counts for each duration. A sum is null when no duration is known. Unknown durations never become zero. Raw observed usage, unknown usage counts, and paired task outcomes remain separate fields.

The paired sample contains three tasks and two repetitions per arm. Timing results describe this sample and do not establish a winner or general performance. Remote inference capacity and its effect on concurrency are unmeasured. Requested model settings do not prove served model identity. Acceptance does not measure requested README updates, human judgment of task quality, or the efficacy of an explicitly activated poteto workflow.

Raw native streams, captures, checker logs, and execution receipts stay in the external run directory. Keep them outside Git. Preserve failed preparations as diagnostic receipts. Do not promote findings from this three-task comparison into a general causal claim or count repetitions as independent task diversity.

## Verify the controller without model calls

The controller tests use actual application snapshots and replay. A recording application callable writes native outcome receipts, and local subprocess oracles check their output. A real Git clone checks guidance identity after the same Git mode normalization that the native sandbox uses. The tests run the upstream installer, inspect its native TOML files, and exercise report rejection of tampered captures, false grades, and broken evidence bindings. A test also calls the real application API with recorded sandbox command responses, then validates its actual harvest capture layout and retained durations through the report. These tests validate the controller, not named persona activation, model behavior, or Docker isolation. The application owner's tests cover native process handling and capture integrity separately.

Run this command at the repository root. A nonzero exit, a failure summary, or a zero-test summary means verification failed.

```sh
python3 -m unittest discover -s evals/port-value -p test_study.py -v
```

Run the case controls separately with this command. A nonzero exit, a failure summary, or a zero-test summary means verification failed.

```sh
python3 -m unittest discover -s evals/port-value -p test_cases.py -v
```
