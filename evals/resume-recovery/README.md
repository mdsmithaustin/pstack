# Certify a recovery destination

Use this suite to test a saved exact role and arm through an existing
execution route. `oracle.py` prepares files and checks evidence. It never
launches an agent. Read [the bounded operator plan](operator-plan.md) before
spending model budget.

## Run the model-free checks

From the repository root, use the main checkout's Python environment.

```sh
recovery_python="$(git rev-parse --path-format=absolute --git-common-dir)/../.venv/bin/python"
"$recovery_python" -m unittest discover -s evals/resume-recovery -v
"$recovery_python" -m unittest discover -s tests/skills/setup-pstack/scripts -v
```

Each command fails on a nonzero exit or zero discovered tests. Synthetic
rollouts in these tests check the oracle and resolver. They certify no
actual destination. The existing tools CI discovery also runs the oracle
cases through `tools/test_resume_recovery.py`.

## Prepare the screen

Keep the run outside the destination workspace. Retain `fixture.json`,
`operator.json`, raw rollouts, process output, and the oracle receipt there.
The destination owns only `project/checkpoint.json` and
`project/published.json`. A trusted operator owns the other run files.
Keep operator evidence outside every destination-writable root, including
temporary directories the sandbox makes writable. Inspect the observed
sandbox policy before treating the evidence directory as protected.
The receipt relies on this existing local trust boundary. It does not
provide cryptographic execution attestation.

Set `saved_project`, `saved_role`, and `saved_arm` from the retained attempt.
Use its recorded role and one-based panel arm. Keep any explicit human model
override attached to its original request. A candidate that contradicts
that request cannot authorize a launch, even when the eval passes.

```sh
source_root="$(pwd -P)"
saved_project="$source_root"
saved_role=feature
saved_arm=1
mkdir -p "$source_root/evals/resume-recovery/runs"
screen_parent="$(mktemp -d "$source_root/evals/resume-recovery/runs/screen.XXXXXX")"
run_root="$screen_parent/run"

"$recovery_python" skills/setup-pstack/scripts/check-models-config.py \
  --resolve --harness codex --project "$saved_project" "$saved_role" \
  > "$screen_parent/resolved.jsonl"
codex --version > "$screen_parent/version.txt"
codex exec --help > "$screen_parent/exec-help.txt"

"$recovery_python" - "$screen_parent" "$saved_arm" <<'PY'
import json
import sys
from pathlib import Path
parent = Path(sys.argv[1]).resolve()
arm = int(sys.argv[2])
rows = [json.loads(line) for line in (parent / 'resolved.jsonl').read_text().splitlines()]
resolution = next(row for row in rows if row['arm'] == arm)
if any(not isinstance(resolution.get(field), str) or not resolution[field].strip()
       or resolution[field] == 'inherit-parent' for field in ('model', 'effort')):
    raise SystemExit('destination identity is not concrete')
version = (parent / 'version.txt').read_text().strip().removeprefix('codex-cli ')
binding = {'harness': 'codex', 'resolution': resolution, 'route': 'codex-cli',
           'version': version, 'permission_context': {'sandbox': 'workspace-write', 'approval': 'never'}}
(parent / 'binding.json').write_text(json.dumps(binding, indent=2) + '\n')
PY

"$recovery_python" evals/resume-recovery/oracle.py prepare \
  --run "$run_root" --binding "$screen_parent/binding.json"
```

The resolver fails on a nonzero exit. The version and help probes fail on a
nonzero exit or missing output. Binding preparation fails if the saved arm
is absent or either identity field inherits. Fixture preparation fails on a
nonzero exit or an existing run directory. Check the retained help before
using the invocation below.

Read the binding's concrete model and effort into shell variables.

```sh
resolved_model="$("$recovery_python" -c 'import json,sys; print(json.load(open(sys.argv[1]))["resolution"]["model"])' "$screen_parent/binding.json")"
resolved_effort="$("$recovery_python" -c 'import json,sys; print(json.load(open(sys.argv[1]))["resolution"]["effort"])' "$screen_parent/binding.json")"
```

Each extraction fails on a nonzero exit or empty output.

## Run, interrupt, and recover

Run the initial invocation through the existing CLI path. This is a direct
operator command, not an adapter. Do not add permission bypass flags.

```sh
codex exec --json -m "$resolved_model" \
  -c "model_reasoning_effort=\"$resolved_effort\"" -c 'approval_policy="never"' \
  --sandbox workspace-write -C "$run_root/project" --skip-git-repo-check - \
  < "$run_root/initial-prompt.md" > "$run_root/initial-events.jsonl" \
  2> "$run_root/initial-stderr.txt" &
initial_pid=$!
```

Failure signals are process exit before a checkpoint and a five-minute
timeout. Observe `checkpoint.json` containing the total, brief token, and
standing-order token. Observe the CLI waiting, with no `published.json`.
From the operator shell, copy the checkpoint before stopping the process.

```sh
cp "$run_root/project/checkpoint.json" "$run_root/interrupted-checkpoint.json"
kill -TERM "$initial_pid"
if wait "$initial_pid"; then
  initial_status=0
else
  initial_status=$?
fi
```

A missing checkpoint, a failed `kill`, or a zero interrupted process status
fails this phase. The conditional retains the status when the shell uses `set -e`.
Record `SIGTERM` and the actual exit status in `operator.json`. Confirm the
process stopped before proceeding. Do not infer death from a missing report.

For an interactive PTY invocation, Ctrl-C can produce exit status 1.
Record `SIGINT` and that observed status. The oracle also requires a runtime
`turn_aborted` record with reason `interrupted` in the checkpoint command's turn.
Its failed `CommandExecution` must match the yielded process and contain the
raw checkpoint JSON in stdout. The waiting command need not exit successfully
before the operator interrupts it. Neither the CLI stream nor the rollout may
record a completed initial turn.

Run a fresh invocation with the same concrete identity and scoped options.
This checks pickup from durable files rather than relying on session memory.

```sh
codex exec --json -m "$resolved_model" \
  -c "model_reasoning_effort=\"$resolved_effort\"" -c 'approval_policy="never"' \
  --sandbox workspace-write -C "$run_root/project" --skip-git-repo-check - \
  < "$run_root/recovery-prompt.md" > "$run_root/recovery-events.jsonl" \
  2> "$run_root/recovery-stderr.txt"
recovery_status=$?
```

A nonzero exit, five-minute timeout, plan-only response, or missing
`published.json` fails this phase.

Use the enforcing read-only option for the refusal control.

```sh
codex exec --json -m "$resolved_model" \
  -c "model_reasoning_effort=\"$resolved_effort\"" -c 'approval_policy="never"' \
  --sandbox read-only -C "$run_root/project" --skip-git-repo-check - \
  < "$run_root/refusal-prompt.md" > "$run_root/refusal-events.jsonl" \
  2> "$run_root/refusal-stderr.txt"
refusal_status=$?
```

A nonzero agent exit, timeout, absent attempted write, absent tool refusal,
or a created `denied.txt` fails the control. A text claim of refusal is
insufficient. Other routes require this control only when their existing
execution path exposes an enforcing permission option.

## Retain observed provenance and grade it

For each phase, get the `thread_id` from its `thread.started` CLI event.
Locate that session's rollout under the active Codex session store, matching
both the id and this fixture's resolved workspace. Copy only that session
to `<phase>-rollout.jsonl`. Do not collect other projects' transcripts.
The oracle requires actual `session_meta`, `turn_context`, user prompt,
and observed execution result records. It accepts paired `function_call`
results and native `event_msg` `CommandExecution` records. For an enforcing
refusal before process launch, it accepts correlated `custom_tool_call` `exec`
outputs only when the whole input consists of literal
`text(await tools.exec_command({...}));` calls. Literal `write_stdin` polls
may share the input. It never executes JavaScript or derives evidence from
assistant prose. Computed commands and ambiguous output pairings fail closed.
The exact prescribed refusal command must have a nonzero result containing
a sandbox refusal, matched without regard to letter case.
It rejects missing metadata and
effort, wrong version, stale sessions, and unrelated tool results.

Create `operator.json` outside `project/` from the observations. Its shape is:

```json
{
  "binding": "replace with the complete binding.json object",
  "interruption": {"signal": "SIGTERM", "exit_code": 143},
  "processes": {
    "initial": {"argv": ["replace with exact argv as separate strings"], "exit_code": 143},
    "recovery": {"argv": ["replace with exact argv as separate strings"], "exit_code": 0},
    "refusal": {"argv": ["replace with exact argv as separate strings"], "exit_code": 0}
  }
}
```

Replace example statuses with the observed values. Preserve `codex`, `exec`,
all options, and the final `-` in each argv. The oracle checks that each argv
matches the direct command above. `oracle.argv` describes the accepted
array. It is not observed evidence. Never use it to invent process success.

```sh
"$recovery_python" evals/resume-recovery/oracle.py check --run "$run_root" \
  > "$run_root/receipt.json"
```

A nonzero exit fails certification. Inspect the receipt's exact binding,
observed invocations, session ids, interruption status, and evidence hashes.
The receipt contains no self-reported pass boolean. Raw evidence and fixture
files must remain available. A new oracle or fixture invalidates old evidence.

## Check candidate eligibility

Create a contexts JSON file with current operator observations keyed by
harness. For this screen, use:

```json
{
  "codex": {
    "available": true,
    "route": "codex-cli",
    "version": "replace with the observed version",
    "permission_context": {"sandbox": "workspace-write", "approval": "never"},
    "eval_run": "/absolute/path/to/the/retained/run"
  }
}
```

Then resolve the original saved role and arm from the original checkout.

```sh
"$recovery_python" skills/setup-pstack/scripts/resolve-resume.py \
  --source claude-code --role "$saved_role" --arm "$saved_arm" \
  --project "$saved_project" --contexts "$screen_parent/contexts.json" \
  --oracle "$source_root/evals/resume-recovery/oracle.py"
```

Exit 0 means at least one candidate is eligible. Exit 1 means none is eligible.
Exit 2 means invalid arguments, configuration, or contexts. The output
preserves priority order and denied candidates with reasons. It never
launches work. The path rechecks the installed Codex CLI version and reruns
the current trusted oracle before accepting its retained receipt.

## Record gaps

The current oracle supports `codex-cli` only. It does not certify native
Codex delegation, Claude Code, Hermes, or Grok. Keep reciprocal priority
configured even when a preferred destination has no certified route.
Record an unavailable destination or missing provenance as a gap. Never
substitute a model, effort, role, or panel arm to make the screen pass.
A Codex-first screen cannot establish cross-harness capability. Each other
route needs its own actual destination screen and independent oracle pass.
