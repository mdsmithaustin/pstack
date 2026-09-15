# Direct-skill evaluation foundation

This directory contains reusable inputs for evaluating `verify-commands`, `spec-probes`, and `runtime-probes`. Model answers, traces, judge verdicts, reports, token ledgers, and private holdbacks stay outside Git.

The experiment has two comparison lanes. Only the integrated lane can support a headline quality claim.

## Terms

- A case is one model request.
- A fixture is the model-visible scenario input or executable synthetic target for a case.
- An oracle is a deterministic grader that checks output, trace, replay, or fixture facts.
- A judge is a separate model that compares semantic quality when several answers can be valid.
- An oracle unit test checks whether a grader accepts valid samples and rejects invalid ones. It does not measure skill quality.

## Comparison lanes

The isolated lane compares `without_skill` with `with_skill`. The harness mounts no skills for `without_skill` and only the selected target for `with_skill`. This lane measures the target's causal effect in isolation. It is diagnostic and is not an upstream pstack baseline.

The integrated lane represents the pinned upstream pstack roster from `cursor/plugins` commit `5bf2b1544db739998121a306340631963c2ff3de`. The control contains the 47 upstream skills in their local CLI-compatible port form. The treatment contains the same 47 skills plus one selected target. The other two targets and all other port-only additions stay out of both arms.

The integrated manifest uses `old_skill` as the harness transport name for the control arm. It does not mean that the target existed upstream or that the control contains a shipped incumbent. The upstream repository, commit, subdirectory, roster, local name map, and target-only file delta are recorded in `direct-skills-experiment.json` and the generated receipt.

The integrated lane copies only Git-tracked files. It reads their current working-tree bytes and records SHA-256 digests. Commit or stage intended skill and eval files before materialization so the receipt covers the candidate you mean to run.

## What the oracles decide

Trigger and behavior use separate case populations. Trigger cases measure whether the model loads the target for relevant requests and stays out of near misses. Behavior cases compare paired answers for the same fixture.

Deterministic gates own facts that the runner can execute or recompute. A fluent answer cannot offset a failed safety, scope, execution, evidence, or exposure gate. Missing run evidence, an unavailable judge, an incomplete answer-design attestation, or a missing expected skill-load event leaves the result incomplete.

The oracles do not require one application-style response schema.

- `verify-commands` accepts a natural answer with one fenced shell artifact and brief prose. It runs the artifact against fresh healthy and defective fixture states inside a locked container. The candidate process has no writable home or shared-memory scratch space and cannot create regular files. An in-container evidence service authenticates each required interpreter, argument vector, and working directory against the root-owned fixture. A hidden operation failure repeats an otherwise passing fixture to prove that the plan propagates the check result. Candidate bytes enter through standard input. They never become host shell arguments, environment values, image names, or paths. There is no host-execution fallback.
- `spec-probes` accepts natural prose and Markdown tables. Its oracle checks source requirement anchors, non-mutation, and arithmetic consistency when the answer includes tagged coverage data. A cross-family comparison judge decides which answer is more complete, grounded, and applicable.
- `runtime-probes` accepts natural prose and findings tables. Its oracle checks that the trusted driver ran as required, the trace contains fresh target-specific evidence, the driver facts match the fixture, the answer cites actual evidence IDs, and the fixture was not mutated. A cross-family comparison judge decides whether the answer's claims agree with those facts and which answer has better diagnostic quality.

Tagged JSON samples remain only in explicitly named importer-integration unit tests. They test parser compatibility and do not contribute to headline behavior results. Metamorphic tests use structurally different valid answers to keep the deterministic gates independent of wording and presentation.

Two runner evidence gaps remain. Normalized path-based skill-read events do not record the temporary workspace root, so a path suffix alone cannot prove that the model read the mounted target. The Claude adapter also permits writes inside its temporary workspace, so command text cannot prove that a runtime driver stayed unchanged before execution. `skill-eval-harness` must record workspace-bound access evidence and post-run fixture integrity before either signal can support promotion.

## Model-free checks

Run repository tests and pinned harness checks before spending model budget.

```sh
mise exec -- python3 -m unittest discover -s tools -p 'test_*.py'
mise exec -- python3 -m unittest discover -s evals/verify-commands/oracles -p 'test_*.py'
mise exec -- python3 -m unittest discover -s evals/spec-probes/oracles -p 'test_*.py'
mise exec -- python3 -m unittest discover -s evals/runtime-probes/oracles -p 'test_*.py'
mise run skill-lint
mise run skill-validate
for skill in verify-commands spec-probes runtime-probes; do
  uv run --no-project python ../skill-ci/tools/run_runner.py skill-benchmark audit-manifest \
    --fail-on-blockers --strict-judge "evals/$skill/shared-benchmark.json"
done
```

The unittest commands must discover tests and exit zero. `skill-validate` must print an `OK` line for each target manifest. Each audit command must name its target manifest and exit zero without blockers. These checks prove that the lane, fixtures, manifests, and deterministic graders are internally consistent. They do not prove semantic quality or judge calibration.

Materialize and verify an integrated lane outside the repository before a model run.

```sh
source_repo=$(pwd)
shadow=/secure/evals/verify-commands-integrated
mise exec -- python3 tools/direct_skill_lanes.py materialize \
  --repo "$source_repo" --skill verify-commands --out "$shadow"
mise exec -- python3 tools/direct_skill_lanes.py verify \
  --repo "$source_repo" --skill verify-commands --shadow-repo "$shadow"
```

`verify` rejects a changed source revision, experiment contract, or lane helper, an altered receipt, a roster mismatch, a path escape, a symlink, and any arm difference beyond the selected target. Integrated runs invoke the helper copy recorded in the materialized lane rather than mutable caller-checkout bytes.

## Integrated headline runs

Use `--dry-run` first to inspect the pinned command sequence without invoking a model.

```sh
mise exec -- python3 tools/run_direct_skill_eval.py \
  --repo "$source_repo" --lane integrated --shadow-repo "$shadow" \
  --skill verify-commands --agent codex --model gpt-5.6-luna \
  --out /secure/results/verify-commands-integrated-luna --dry-run
```

Remove `--dry-run` to execute one answer-model arm. Integrated mode validates and audits the generated manifest. It prepares paired `with_skill` and `old_skill` tasks, removes unused variants, and runs the answer model. Before each later stage, it verifies the shadow against the source and its receipt again. It then applies deterministic grades, checks target-specific exposure for every behavior case in the selected split, and exports blinded comparison tasks. The result directory must not be a symlink and must stay outside the shadow repository.

The checked-in runner stops after `compare-tasks`. It does not automate semantic judging. Give `compare-tasks.jsonl` to a judge from the other model family. Save its verdicts as JSON Lines outside Git, then import them.

```sh
uv run --no-project python ../skill-ci/tools/run_runner.py skill-benchmark compare-results \
  --truth /secure/results/verify-commands-integrated-luna/compare-truth.json \
  --results /secure/results/verify-commands-integrated-luna/compare-results.jsonl \
  --out /secure/results/verify-commands-integrated-luna/compare-summary.json
```

Run the same integrated comparison for Codex Luna, Sol, and Terra, and Claude Opus. Codex answers use Claude Opus as the judge. Claude answers use Codex Astra. The answer and judge families must differ.

`compare-results` validates task coverage, comparison hashes, and `A`, `B`, or `TIE` verdicts. It does not record or validate judge identity, model family, prompt, rubric, or calibration. Before using an imported result for promotion, retain an external receipt with the judge backend and model, the comparison-task digest, the judge-prompt and rubric digests, the labeled calibration-set digest, and the calibration outcomes. The current foundation does not generate or validate that receipt. Until that gap is closed, imported pairwise verdicts are diagnostic and cannot support promotion.

## Isolated diagnostic runs

The isolated lane can screen whether a target changes behavior before the integrated matrix. It runs the harness's built-in judge and report stages. Its results cannot support an upstream pstack improvement claim.

```sh
mise exec -- python3 tools/run_direct_skill_eval.py \
  --lane isolated --skill verify-commands \
  --agent codex --model gpt-5.6-luna \
  --judge-backend claude --judge-model opus \
  --out evals/verify-commands/runs/isolated-luna
```

Use cheaper single repetitions to screen instruction candidates. Use three repetitions only for finalists. Rank quality first. Compare tokens and elapsed time only among candidates inside the quality noise band.

## Trigger runs

Use `mise run skill-trigger skills/<skill>` only as a smoke test. Run the pinned harness separately for each agent and model for the promotion matrix. Every saved result must have one answer-model identity.

```sh
skill=verify-commands
for model in gpt-5.6-luna gpt-5.6-sol gpt-5.6-terra; do
  out="evals/$skill/runs/trigger-$model"
  uv run --no-project python ../skill-ci/tools/run_runner.py skill-trigger-matrix \
    "evals/$skill/shared-benchmark.json" --agent codex --model "$model" \
    --codex-cmd "../skill-ci/tools/codex-project-only exec --json --skip-git-repo-check --sandbox read-only" \
    --runs-per-query 3 --trace-runs "$out/traces" --out "$out/matrix.json"
done

out="evals/$skill/runs/trigger-opus"
uv run --no-project python ../skill-ci/tools/run_runner.py skill-trigger-matrix \
  "evals/$skill/shared-benchmark.json" --agent claude --model opus \
  --claude-bin ../skill-ci/tools/claude-project-only \
  --runs-per-query 3 --trace-runs "$out/traces" --out "$out/matrix.json"
```

Set `skill` to each target name. A non-zero runner exit, a missing matrix file, or fewer than three attempts for any agent, model, and query coordinate leaves the trigger run incomplete.

## Private holdback

Private cases stay outside the checkout. Copy `private-holdback.template.json` beside an external `payload/` directory. Add four behavior cases and four positive and four negative trigger cases for one skill. Print the public digests and copy them into the overlay.

```sh
mise exec -- python3 tools/compose_eval_holdback.py \
  --skill verify-commands --print-public-digests
```

Compose the public suite and private overlay into a new empty directory outside the repository.

```sh
mise exec -- python3 tools/compose_eval_holdback.py \
  --skill verify-commands \
  --overlay /secure/evals/verify-commands/overlay.json \
  --out /secure/runs/verify-commands-holdback
```

The holdback composer creates an isolated shadow suite. It does not create the integrated upstream-roster arms. Do not report its `without_skill` arm as an upstream baseline. Integrated holdback use needs a separately verified composition step before it can support a headline claim.

The composer rejects a changed public manifest, skill file, suite tree, or skill tree. It also rejects duplicate case IDs, the wrong population, non-holdback cases, symlinks, payload traversal or collisions, and output paths inside the repository. Every `files` and `prompt_ref` value must be a normalized relative path to an existing public or private payload file. The composer validates these references before creating output and never invokes a model.

The holdback lifecycle is operator-enforced. Record the sealed-set identity and disposition outside Git. An infrastructure failure may rerun the same sealed set only if no answer or verdict was disclosed. A candidate failure retires the set. An immediately repairable candidate gets a newly generated sealed holdback. Ambiguous failures count as candidate failures after independent review.

The harness reports a non-zero script assertion as a failed assertion even when an oracle labels the cause `infrastructure` or `missing_measurement`. Inspect those labels before scoring or exposing a holdback verdict. Mark the run incomplete instead of counting it as a candidate pass or failure.

## Promotion contract

`direct-skills-experiment.json` holds the frozen operator contract. Repository tests pin every agreed field.

The integrated lane supplies the headline behavior comparison. The isolated lane supplies causal diagnostics. Trigger results remain separate. Promotion requires all hard gates, complete target exposure evidence, calibrated cross-family pairwise verdicts, no answer-model regression, and a sealed private holdback. The numeric improvement threshold comes from repeated incumbent variance before candidate results are inspected.

Each trigger and behavior climb gets at most five cycles and stops after two consecutive cycles without gain. At most two candidate branches stay live. Complementary changes may be combined, but the combination must beat both parents and consumes one cycle. Compression is a later, separate climb.

Before promotion, show the skill diff, public results, sealed holdback verdict, per-model comparison, and efficiency comparison. Promotion and merge require explicit user approval.
