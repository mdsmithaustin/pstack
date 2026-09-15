# Direct-skill evaluation foundation

This tree holds the reusable inputs for evaluating `verify-commands`, `spec-probes`, and `runtime-probes`. It does not hold model answers, traces, judge verdicts, metrics, reports, token ledgers, or private holdbacks.

The baseline is the last synced upstream pstack change at commit `5bf2b1544db739998121a306340631963c2ff3de`. None of the three target skills exists at that revision, so the harness `without_skill` arm represents the upstream feature baseline. During a later improvement climb, `old_skill` represents the shipped incumbent and `with_skill` represents the candidate.

## What is measured

Trigger and behavior are separate populations. Trigger cases measure whether a model loads the skill on relevant requests and stays out of near misses. Behavior cases compare paired `with_skill` and `without_skill` answers on the same fixture.

Deterministic gates own facts that can be executed or recomputed. A judge owns only semantic quality that admits more than one valid answer. A deterministic failure cannot be offset by fluent prose. Missing run evidence, an unavailable judge, an incomplete answer-design attestation, or a missing treatment skill-load event makes the result incomplete rather than passing.

`verify-commands` extracts a structured verification plan from `output.md` and runs its shell artifact against fresh healthy and defective fixture states inside a locked container. Candidate bytes enter the container through standard input; they never become host shell arguments, environment values, image names, or paths. There is no host-execution fallback.

`spec-probes` and `runtime-probes` extract structured records from `output.md`. Their oracles derive counts and promotion states from fixture facts instead of rewarding vocabulary. Runtime execution cases also require evidence that the declared fixture driver ran.

## Model-free checks

Run the repository tests and the pinned harness checks before spending model budget.

```sh
.venv/bin/python -m unittest discover -s tools -p 'test_*.py'
mise run skill-validate
mise run skill-audit
```

The unittest command must discover at least one test and exit zero. `skill-validate` must print an `OK` line for each target manifest. `skill-audit` must name each target manifest and exit zero without blockers. CI repeats the model-free checks and requires at least one manifest.

## Public paired runs

Keep every output below an ignored `runs/` directory. The runner executes one answer-model arm at a time, stops on the first non-zero stage, and requires a judge from the other model family.

```sh
.venv/bin/python tools/run_direct_skill_eval.py --skill verify-commands --agent codex --model gpt-5.6-luna --judge-backend claude --judge-model opus --out evals/verify-commands/runs/luna
.venv/bin/python tools/run_direct_skill_eval.py --skill verify-commands --agent codex --model gpt-5.6-sol --judge-backend claude --judge-model opus --out evals/verify-commands/runs/sol
.venv/bin/python tools/run_direct_skill_eval.py --skill verify-commands --agent codex --model gpt-5.6-terra --judge-backend claude --judge-model opus --out evals/verify-commands/runs/terra
.venv/bin/python tools/run_direct_skill_eval.py --skill verify-commands --agent claude --model opus --judge-backend codex --judge-model gpt-6-astra --out evals/verify-commands/runs/opus
```

Repeat those four commands for `spec-probes` and `runtime-probes`. Use `mise run skill-trigger skills/<skill>` only as a default trigger smoke test. For the promotion matrix, invoke the pinned harness separately for each agent and model so every saved result has one unambiguous model identity:

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

Set `skill` to each of the other two target names for their trigger runs. A non-zero runner exit, a missing matrix file, or fewer than three attempts for any agent-model-query coordinate leaves the trigger run incomplete.

Use cheaper single repetitions to screen instruction candidates. Use three repetitions only for finalists. Rank quality first. Compare tokens and elapsed time only among candidates inside the quality noise band.

## Private holdback

Private cases stay outside the checkout. Copy `private-holdback.template.json` beside an external `payload/` directory, then add four behavior cases and four positive and four negative trigger cases for one skill. Print the four public digests and copy them into the overlay:

```sh
.venv/bin/python tools/compose_eval_holdback.py \
  --skill verify-commands --print-public-digests
```

Compose the public suite and private overlay into a new empty directory outside the repository:

```sh
.venv/bin/python tools/compose_eval_holdback.py \
  --skill verify-commands \
  --overlay /secure/evals/verify-commands/overlay.json \
  --out /secure/runs/verify-commands-shadow
```

The command prints the composed manifest. Capture the source checkout before changing directories, then run each answer-model arm from the shadow repository with `--split holdback`:

```sh
source_repo=$(pwd)
shadow=/secure/runs/verify-commands-shadow
"$source_repo/.venv/bin/python" "$source_repo/tools/run_direct_skill_eval.py" \
  --repo "$shadow" --skill-ci "$source_repo/../skill-ci" --skill verify-commands \
  --split holdback --agent codex --model gpt-5.6-luna \
  --judge-backend claude --judge-model opus --out /secure/results/verify-commands-luna
```

Repeat with the other three answer/judge pairs from the public run block. The composer rejects a changed public manifest, skill file, suite tree, or skill tree; duplicate case IDs; a population other than four behavior, four positive-trigger, and four negative-trigger cases; non-holdback cases; symlinks; payload traversal or collisions; and output paths inside the repository. It never invokes a model.

Run the sealed trigger population separately from the shadow repository:

```sh
(
  cd "$shadow"
  uv run --no-project python "$source_repo/../skill-ci/tools/run_runner.py" skill-trigger-matrix \
    evals/verify-commands/shared-benchmark.json --split holdback \
    --agent codex --model gpt-5.6-luna \
    --codex-cmd "$source_repo/../skill-ci/tools/codex-project-only exec --json --skip-git-repo-check --sandbox read-only" \
    --runs-per-query 3 --trace-runs /secure/results/verify-commands-trigger-luna/traces \
    --out /secure/results/verify-commands-trigger-luna/matrix.json
)
```

Repeat with the other Codex models and the Claude Opus adapter shown in the public trigger block. A non-zero stage, missing artifact, incomplete answer-design attestation, missing skill-load evidence, unavailable judge, or incomplete trigger coordinate makes the run ineligible for scoring. The checked-in runner pairs Claude answers with Codex Astra and Codex answers with Claude Opus so the answer and judge come from different model families.

The holdback lifecycle is an operator-enforced policy; the composer cannot know whether a model answer or verdict has been disclosed. Record the sealed-set identity and disposition outside Git. Infrastructure failures may rerun the same sealed set only if no answer or verdict was disclosed. Candidate failures retire the set. An immediately repairable candidate gets a newly generated sealed holdback. Ambiguous failures count as candidate failures after independent review.

The harness reports a non-zero script assertion as a failed assertion even when an oracle labels the cause `infrastructure` or `missing_measurement`. Before scoring or exposing a holdback verdict, inspect those labels and mark the run incomplete. Do not count them as candidate passes or failures.

## Promotion contract

The frozen operator contract is in `direct-skills-experiment.json`, and repository tests pin every agreed field. Every hard safety and scope gate must pass. No answer model may regress. The numeric improvement threshold comes from repeated incumbent variance before candidate results are inspected.

Trigger and behavior climb independently. Each metric gets at most five cycles and stops after two consecutive no-gain cycles. At most two candidate branches stay live. Complementary changes may be combined, but the combination must beat both parents and consumes one cycle. Compression is a later, separate climb.

Before promotion, show the skill diff, public results, sealed holdback verdict, per-model comparison, and efficiency comparison. Promotion and merge require explicit user approval.
