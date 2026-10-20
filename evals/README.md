# Direct skill evaluation

This directory holds public development corpora for `verify-commands`,
`spec-probes`, and `runtime-probes`. The corpora compare the harness's isolated
`with_skill` and `without_skill` arms. They do not represent upstream Cursor
pstack and do not prove that a skill improves production work.

For the separate pipeline exit study, follow its
[study protocol](verify-commands/studies/pipeline-exit/README.md) instead of the
generic screen and repeated-tuning examples below.

`promises/` holds a separate suite that checks the user guide's promises on
each harness. See `promises/README.md`.

Model answers, traces, judge transcripts, raw execution reports, and unpublished
cases stay outside Git. A committed case is tuning material, not sealed evidence.
Oracle and login regression fixtures under `promises/testdata/` are an exception.
They are reduced, sanitized traces, CLI error records, and recorded verdicts used by model-free tests.
`promises/reduce_trace.py` reduces raw traces for oracle fixtures. `promises/results/`
is a second exception. It holds aggregated verdict matrices with no model
answers.

The [port-value comparison](port-value/README.md) documents the separate
native, upstream, and current-port application study, including its published
aggregate results and validation receipt. Its committed cases are now exposed.
Raw execution evidence stays outside Git.

## Maintained scope

| Component | Maintained purpose |
| --- | --- |
| `promises/` | Documented instruction, script, installation, and native process regressions. Presence and observed compliance do not guarantee model behavior. |
| `verify-commands/` | Executable false-green controls and public development cases. |
| `runtime-probes/`, `spec-probes/`, `unslop/` | Small development corpora. Findings, scope restraint, and preservation matter more than requested vocabulary or loading alone. |
| `canon/` | Native application capture and supported outcome-grader controls. Historical screens and process census are in the [archive index](archive/README.md). |
| `harness-routing/` | Targeted read/routing instrumentation with separate unresolved validity axes. |
| `port-value/` and pipeline-exit | Completed comparisons and reproducibility records. Exposed ceiling cases can protect regressions, but repeated results are not fresh efficacy evidence. |

Passing instrument tests validates the evaluator, not the skill. Count tasks,
trials, stages, assertions, and guide claims separately. Historical positive
signals remain bounded by their source versions, grading, and sampling limits.
The recent port-value and pipeline-exit comparisons found no acceptance advantage
on their recorded cases. Existing result files and hashes remain historical.

Native regression runs should answer a named skill or runtime change. Wider
manual matrices and paid studies have no new recurring schedule here. Current
maintenance expense and savings from this smaller catalog are unmeasured.

## What is measured

Trigger cases measure whether a model loads a skill for relevant requests and
stays out of near misses. Behavior cases measure whether loading the skill
changes the quality of an answer to the same prompt and fixture.

`verify-commands` has an executable oracle. It extracts one fenced shell
artifact and runs it against healthy and faulty fixture states in a pinned,
networkless container. Its unit tests cover valid alternatives, false-green
commands, and attempts to forge execution evidence.

The bytecode control case seeds timestamp-based Python caches before replacing
equal-size source with the original timestamp. Its baseline, mutation, and
restoration controls require literal imported values. An expected-mismatch
control imports `baseline` successfully while `expected.txt` contains `mutation`.
The outer gate must reject that mismatch despite the zero observer exit. A gate
that only prints fresh imported values fails this control. An authenticated observer
invocation hands execution to an evaluator worker under a separate user ID.
The worker runs the captured CLI arguments and working directory against the
immutable fixture. Its startup environment belongs to the evaluator. Only
`PYTHONPYCACHEPREFIX` and `PYTHONDONTWRITEBYTECODE` environment settings are
copied from the caller, with a 2048-byte limit per value. Other Python startup
settings and loader overrides are rejected. The worker supplies imported values
through a private descriptor. The broker-owned imported literal and actual
operation exit establish behavior, and acceptance requires a zero operation exit.
The evaluator retains the worker's stdout and stderr losslessly with those records.
The original CLI forwards the worker's output and status, then exits before
running its checker body. The outer gate's output and exit remain separate
candidate results. The evaluator checks that exit in every control, including
forced status 97. Candidate output and value reports cannot establish imported
behavior. Source hashes and cache paths do not establish executed behavior.
`PYTHONDONTWRITEBYTECODE` prevents cache writes but still permits reads of valid
prepopulated caches.
The prepared control tree is read-only, and setup commands stay outside the
returned gate. The checker runs as a Python script entrypoint. Equivalent paths,
environment cache prefixes, and native `-B` and `-X pycache_prefix` options are
supported. Loading the checker through stdin, `-c`, or `runpy` does not satisfy
that CLI contract. A controller can launch the checker as its own script process.
The gate has no writable filesystem and cannot create cache directories.
Invocation metadata, worker output, and observation messages have size limits.
Each evaluator execution has a two-second deadline. Missing observations,
unsupported metadata, or exceeded limits prevent acceptance.

The lifecycle observation case checks whether the application reaped its one
child and closed its cleanup pipe writer. A private worker owns both resources,
and the broker samples their kernel state before observer repair. The generated
CLI stub requires that evaluator runtime and is not a standalone host process
probe. The default
`python3 tools/check-lifecycle.py` command returns zero for a reaped child and
closed writer, or one for omitted cleanup. Its authenticated `--repair-first`
mode performs real owner cleanup before sampling and fails the observation-order
check, even if its exit and final resources are clean. The broker retains frozen
application facts, first-observation facts, observer action order, actual worker
execution, and a separate safety teardown record. It measures writer cleanup,
not application stdout reader cleanup. A failed or missing observation cannot
pass because the outer shell exits nonzero. Lifecycle grading accepts only the
actual fact-derived worker exit, while bytecode grading still requires zero.
Each state retains at most eight attempts of at most 32 KiB each. The existing
16 KiB ceiling on the whole broker response is stricter than the 32 KiB
retained-attempt bound. A ninth attempt
latches failure and launches no worker. Forced status 97 launches no lifecycle
resource and must make the outer gate return nonzero.

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

Fixture bootstraps that create files, including the verify-commands fixtures,
need `--sandbox workspace-write` in the answer invocation. Use it for bootstrap
writes in the disposable model workspace. Use `read-only` for answer tasks that
only inspect attached files. Resolve the adapter's absolute path before the run
because isolated answer workspaces do not contain repository tools.
The executable oracle keeps its prepared tree immutable to candidates.

```sh
tools="$(git rev-parse --show-toplevel)/tools"
skill-ci run skills/verify-commands --agent codex --runs 1 \
  --codex-cmd "$tools/codex-project-only exec --json --skip-git-repo-check --sandbox workspace-write" \
  --codex-model gpt-6.1-sol --out /private/tmp/verify-commands-sol-screen

skill-ci run skills/verify-commands --agent claude --runs 1 \
  --model opus --judge-model sonnet --out /private/tmp/verify-commands-opus-screen
```

The screen checks that fixture execution, exposure events, judge inputs, and
reports exist. It cannot support an improvement claim. Stop if either answer
population is incomplete or if the apparent difference comes only from
exposure assertions.

## Development repeatability

The following example repeats public tuning cases. Its three paired repetitions
can expose unstable answers or grading, but do not establish confirmation,
statistical power, or generalization. Run it only for a separately authorized
research decision after the screen works. It is not a CI or release gate.

Use one grounded judge verdict per answer as an initial development budget.
Inspect the prompt and rationale before repeating threshold-close or disputed
judgments. `skill-ci run` always uses a Claude judge, so invoke the pinned
harness directly when the design requires a cross-family comparison.

Follow the [paid-screen sandbox and adapter guidance](#paid-screen) when
adapting this example to another corpus.

```sh
skill=runtime-probes
run_root=/private/tmp/runtime-probes-repeatability
tools="$(git rev-parse --show-toplevel)/tools"
manifest="evals/$skill/shared-benchmark.json"
runner() { skill-ci harness "$@"; }
mkdir -p "$run_root"

runner skill-benchmark audit-manifest "$manifest" --fail-on-blockers --strict-judge
runner skill-benchmark prepare "$manifest" --split tune --runs-per-variant 3 --out "$run_root/tasks.jsonl"

runner skill-benchmark run-agent --agent codex --model gpt-6.1-sol \
  --codex-cmd "$tools/codex-project-only exec --json --skip-git-repo-check --sandbox read-only" \
  --tasks "$run_root/tasks.jsonl" --runs "$run_root/codex" --timeout 240
runner skill-benchmark grade "$manifest" --runs "$run_root/codex" --allow-scripts
runner skill-benchmark judge "$manifest" --runs "$run_root/codex" \
  --judge-backend claude --judge-model opus \
  --claude-bin "$tools/claude-project-only" --judge-runs 1 \
  --transcripts "$run_root/codex-judge-transcripts" \
  --out "$run_root/codex-judge.jsonl"
runner skill-benchmark benchmark "$manifest" --runs "$run_root/codex" --split tune \
  --allow-scripts --judge-results "$run_root/codex-judge.jsonl" \
  --out "$run_root/codex-benchmark.json"
```

Run Claude answers separately and use Codex as their judge:

```sh
runner skill-benchmark run-agent --agent claude --model opus \
  --claude-bin "$tools/claude-project-only" \
  --tasks "$run_root/tasks.jsonl" --runs "$run_root/claude" --timeout 240
runner skill-benchmark grade "$manifest" --runs "$run_root/claude" --allow-scripts
runner skill-benchmark judge "$manifest" --runs "$run_root/claude" \
  --judge-backend codex --judge-model gpt-6.1-sol \
  --codex-cmd "$tools/codex-project-only exec --json --skip-git-repo-check --sandbox read-only" \
  --judge-runs 1 --transcripts "$run_root/claude-judge-transcripts" \
  --out "$run_root/claude-judge.jsonl"
runner skill-benchmark benchmark "$manifest" --runs "$run_root/claude" --split tune \
  --allow-scripts --judge-results "$run_root/claude-judge.jsonl" \
  --out "$run_root/claude-benchmark.json"
```

## Separate confirmation decision

A confirmation comparison needs a frozen decision contract and new task instances
that were not used to write or tune the skill. A public split name does not make
its cases unseen. Name the intended outcome, the smallest useful gain or quality
floor, acceptable resource use, and the complete assigned population before calls.
Choose task counts and repetitions for that decision, accounting for paired tasks
and shared lineages. Three repetitions are not a universal confirmation budget.

Match the native runtime, tools, permissions, and resource limits across default
and guided conditions. Cold discovery and explicit workflow activation answer
different questions. Retain non-loading, failures, and incomplete attempts in the
assigned population; report exposure-only analysis separately. Grade outcomes
with executable controls where possible and calibrated review for subjective
quality. Report task-level uncertainty, token use, elapsed time, and available
cost without substituting them for human productivity.

These instructions authorize no model calls. Closed studies retain their own
once-only slot and confirmation restrictions.

## Trigger run

Run trigger cases separately for each answer model. `skill-ci trigger` passes
one `--model` value to both agents, so use the pinned harness directly:

```sh
skill=runtime-probes
trigger_root=/private/tmp/runtime-probes-triggers
tools="$(git rev-parse --show-toplevel)/tools"
manifest="evals/$skill/shared-benchmark.json"
runner() { skill-ci harness "$@"; }
mkdir -p "$trigger_root/codex-traces" "$trigger_root/claude-traces"

runner skill-trigger-matrix "$manifest" --agent codex --model gpt-6.1-sol \
  --codex-cmd "$tools/codex-project-only exec --json --skip-git-repo-check --sandbox read-only" \
  --runs-per-query 3 --trace-runs "$trigger_root/codex-traces" \
  --out "$trigger_root/codex.json"

runner skill-trigger-matrix "$manifest" --agent claude --model opus \
  --claude-bin "$tools/claude-project-only" \
  --runs-per-query 3 --trace-runs "$trigger_root/claude-traces" \
  --out "$trigger_root/claude.json"
```

Inspect at least one generated judge prompt before the batch and review all
answer-family disagreements, apparent treatment wins, and a sample of ties.
Report behavior lift and trigger precision or recall separately. Compare token
use only after quality. A hill climb needs a repeatable skill-sensitive
weakness, judge agreement with independently reviewed examples, and fresh
unseen cases.
