# Direct skill evaluation

This directory holds public development corpora for `verify-commands`,
`spec-probes`, and `runtime-probes`. The corpora compare the harness's isolated
`with_skill` and `without_skill` arms. They do not represent upstream Cursor
pstack and do not prove that a skill improves production work.

Model answers, traces, judge transcripts, reports, and private cases stay
outside Git. A committed case is tuning material, not sealed evidence.

## What is measured

Trigger cases measure whether a model loads a skill for relevant requests and
stays out of near misses. Behavior cases measure whether loading the skill
changes the quality of an answer to the same prompt and fixture.

`verify-commands` has an executable oracle. It extracts one fenced shell
artifact and runs it against healthy and faulty fixture states in a pinned,
networkless container. Its unit tests cover valid alternatives, false-green
commands, and attempts to forge execution evidence.

`spec-probes` and `runtime-probes` allow several valid response shapes. Their
grader-only expectations name the relevant fixture facts and unacceptable
claims. A cross-family judge scores the response. Process assertions separately
check available trace evidence such as skill loading and required commands.
This is evidence-grounded evaluation, not immutable execution attestation.

`skill_invoked` assertions are exposure diagnostics. They do not independently
prove that a read came from a particular mounted file.

## Model-free checks

Run these before spending model budget:

```sh
docker pull python:3.12-slim@sha256:229a2c5bfa27522db7815ea81f9bed70af17ccb9de9fc7ad142b1877b5830d36
(cd evals/verify-commands/oracles && python3 -m unittest -v test_check_plan)
mise run skill-validate
mise run skill-audit
```

The unittest command must execute the named module and exit zero. A missing
Docker image, rejected valid plan, or accepted false-green plan is a failure.
Validation must print an `OK` result for all three manifests. Audit must exit
without blockers. These checks validate the instrument, not skill quality.

## Paid screen

Start with one paired repetition. Replace the skill name for each corpus.

```sh
AGENTS=codex RUNS=1 CODEX_MODEL=gpt-5.6-sol \
  OUT=/private/tmp/verify-commands-sol-screen \
  mise run skill-run skills/verify-commands

AGENTS=claude RUNS=1 MODEL=opus JUDGE_MODEL=sonnet \
  OUT=/private/tmp/verify-commands-opus-screen \
  mise run skill-run skills/verify-commands
```

The screen checks that fixture execution, exposure events, judge inputs, and
reports exist. It cannot support an improvement claim. Stop if either answer
population is incomplete or if the apparent difference comes only from
exposure assertions.

## Confirmation run

Use three paired answer repetitions only after the screen works. One grounded
judge verdict per answer is the default confirmation budget. Repeat judging
only for threshold-close or disputed answers after inspecting the first
verdict's prompt and rationale. The convenience task always uses a Claude
judge, so invoke the pinned harness directly for a cross-family comparison.

Resolve adapter paths before starting. Answer runs execute in isolated
workspaces, where a repository-relative adapter path does not exist.

```sh
skill=runtime-probes
run_root=/private/tmp/runtime-probes-confirmation
skill_ci="$(cd "$(git rev-parse --path-format=absolute --git-common-dir)/../../skill-ci" && pwd -P)"
manifest="evals/$skill/shared-benchmark.json"
runner() { uv run --no-project python "$skill_ci/tools/run_runner.py" "$@"; }
mkdir -p "$run_root"

runner skill-benchmark audit-manifest "$manifest" --fail-on-blockers --strict-judge
runner skill-benchmark prepare "$manifest" --split tune --runs-per-variant 3 --out "$run_root/tasks.jsonl"

runner skill-benchmark run-agent --agent codex --model gpt-5.6-sol \
  --codex-cmd "$skill_ci/tools/codex-project-only exec --json --skip-git-repo-check --sandbox read-only" \
  --tasks "$run_root/tasks.jsonl" --runs "$run_root/codex" --timeout 240
runner skill-benchmark grade "$manifest" --runs "$run_root/codex" --allow-scripts
runner skill-benchmark judge "$manifest" --runs "$run_root/codex" \
  --judge-backend claude --judge-model opus \
  --claude-bin "$skill_ci/tools/claude-project-only" --judge-runs 1 \
  --transcripts "$run_root/codex-judge-transcripts" \
  --out "$run_root/codex-judge.jsonl"
runner skill-benchmark benchmark "$manifest" --runs "$run_root/codex" --split tune \
  --allow-scripts --judge-results "$run_root/codex-judge.jsonl" \
  --out "$run_root/codex-benchmark.json"
```

Run Claude answers separately and use Codex as their judge:

```sh
runner skill-benchmark run-agent --agent claude --model opus \
  --claude-bin "$skill_ci/tools/claude-project-only" \
  --tasks "$run_root/tasks.jsonl" --runs "$run_root/claude" --timeout 240
runner skill-benchmark grade "$manifest" --runs "$run_root/claude" --allow-scripts
runner skill-benchmark judge "$manifest" --runs "$run_root/claude" \
  --judge-backend codex --judge-model gpt-5.6-sol \
  --codex-cmd "$skill_ci/tools/codex-project-only exec --json --skip-git-repo-check --sandbox read-only" \
  --judge-runs 1 --transcripts "$run_root/claude-judge-transcripts" \
  --out "$run_root/claude-judge.jsonl"
runner skill-benchmark benchmark "$manifest" --runs "$run_root/claude" --split tune \
  --allow-scripts --judge-results "$run_root/claude-judge.jsonl" \
  --out "$run_root/claude-benchmark.json"
```

## Trigger run

Run trigger cases separately for each answer model. The convenience task passes
one `MODEL` value to every selected adapter, so use the pinned harness directly:

```sh
skill=runtime-probes
trigger_root=/private/tmp/runtime-probes-triggers
skill_ci="$(cd "$(git rev-parse --path-format=absolute --git-common-dir)/../../skill-ci" && pwd -P)"
manifest="evals/$skill/shared-benchmark.json"
runner() { uv run --no-project python "$skill_ci/tools/run_runner.py" "$@"; }
mkdir -p "$trigger_root/codex-traces" "$trigger_root/claude-traces"

runner skill-trigger-matrix "$manifest" --agent codex --model gpt-5.6-sol \
  --codex-cmd "$skill_ci/tools/codex-project-only exec --json --skip-git-repo-check --sandbox read-only" \
  --runs-per-query 3 --trace-runs "$trigger_root/codex-traces" \
  --out "$trigger_root/codex.json"

runner skill-trigger-matrix "$manifest" --agent claude --model opus \
  --claude-bin "$skill_ci/tools/claude-project-only" \
  --runs-per-query 3 --trace-runs "$trigger_root/claude-traces" \
  --out "$trigger_root/claude.json"
```

Inspect at least one generated judge prompt before the batch and review all
answer-family disagreements, apparent treatment wins, and a sample of ties.
Report behavior lift and trigger precision or recall separately. Compare token
use only after quality. A hill climb needs a repeatable skill-sensitive
weakness, judge agreement with independently reviewed examples, and fresh
unseen cases.
