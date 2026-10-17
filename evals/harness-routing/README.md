# Inspect six current-Codex routing tasks

This manual study records six one-turn tasks against one frozen source tree and one requested model setting. It checks complete returned file bytes, runtime routing, and task safeguards. It does not compare models or establish token savings, answer quality, causal effects, other runtimes, or general safety.

## Freeze the inputs

Resolve the model and effort through the project's role configuration first. Choose a new persistent parent directory outside the candidate workspaces. The following command creates six neutral workspaces, exact stdin files, source hashes, the private rubric, independent calibration labels, and accepted CLI configuration receipts. It makes no model call.

```sh
python3 evals/harness-routing/study.py freeze \
  --source . --out /persistent/routing/wave-01 \
  --codex /absolute/path/to/codex \
  --model RESOLVED_MODEL --effort RESOLVED_EFFORT
```

Failure means a nonzero exit, fewer than six labels, any calibration mismatch, a missing native option, or introduced disclosure. Read `frozen.json`, all six `inputs/*.txt`, each package inventory, `native.json`, `production-terms.json`, `rubric.json`, and the calibration examples before execution. Existing production wording can include study-related terms. Its source hashes and separate disclosure audit preserve those bytes unchanged.

The initial instruction points only to `skills/pstack-harness/SKILL.md`. Supporting siblings remain available in their normal layout. Parent criteria and controls stay outside the candidate workspaces. Read-only sandboxing does not hide arbitrary host files from a deliberately hostile process. The context review covers saved returned content and supports only a cooperative interpretation claim.

## Collect the six reserved slots

After the internal reviewer approves the exact contract, pass its `frozen.sha256` value explicitly.

```sh
python3 evals/harness-routing/study.py run \
  --study /persistent/routing/wave-01 \
  --approved-contract INSPECTED_SHA256
```

Failure means a nonzero exit or any invocation state other than completed with raw return code zero. The report always accounts for six labels. A process failure is separate from an interpretation failure.

Each slot has one exclusive reservation and one native invocation with a 180-second deadline. Timeout, interruption, spawn failure, and a controller crash consume that slot. Repeating `run` never retries a consumed slot. A separate controller cannot run the same wave concurrently. A possible dispatch, recurring job, workspace change, or observed private disclosure holds the remaining slots for inspection. This hold survives another `run` call.

The collector saves actual argv, cwd, stdin bytes, inventories before and after, raw JSONL, separate stderr, final answer, times, exit status, and hashes. It isolates HOME and CODEX_HOME, copies only the login file, ignores user configuration and rules, disables apps, plugins, child agents, goals, hooks, skill search, and local automations, and enables the CLI's host-skill-discovery disable. The child runs in a read-only sandbox with approval policy `never`. The controller kills and reaps the process group at its deadline. These observations do not prove a network security boundary.

Requested settings, any runtime-reported session fields and their raw position, and provider execution identity are separate. A missing runtime field remains null. Provider execution remains unknown. A local model catalog establishes only the cached configuration. It does not guarantee successful availability.

## Assess retained evidence

```sh
python3 evals/harness-routing/study.py assess \
  --study /persistent/routing/wave-01
```

Failure means a nonzero exit, an altered saved artifact, or a report with fewer than six records. Exit zero means assessment completed. Inspect the three separate axes for each case. No model runs during assessment.

The oracle supports paired `item.started` and `item.completed` Codex command records with the same identity and command. It recognizes explicit `cat` targets and finite `sed -n` line ranges, including a single shell wrapper. Returned UTF-8 bytes must match the frozen file and cover its full byte range. A path, search hit, attempted read, completed-only record, zero exit without bytes, normalized excerpt, or self-report cannot establish a full read. Unsupported commands remain inconclusive. Duplicate identities, missing results, truncated bytes, and ambiguous final-answer binding cannot pass.

`semantic-packet.json` retains every assistant statement and command position under anonymous labels. Give it and the semantic controls to a fresh blinded reviewer. The reviewer must identify each first committed decision and any earlier substantive action, assess safeguards, and distinguish an introductory intention from a decision. Record one object per label in a separate file. Each may also include `safeguards` with a `status` and nonempty `reasons` list:

```json
{
  "A": {"first_committed_decision_line": 9},
  "B": {"first_committed_decision_line": 8},
  "C": {"first_committed_decision_line": 12},
  "D": {"first_committed_decision_line": 7},
  "E": {"first_committed_decision_line": 15, "earlier_action_line": 13},
  "F": {"first_committed_decision_line": 6}
}
```

These line numbers illustrate the input format. They are not expected answers. Run `assess` again with `--decisions /absolute/path/to/decisions.json`. Failure means a nonzero exit, a missing label, or a position that does not identify a saved statement or command. The assessor rechecks complete reads before the reviewed positions. Without semantic review its ordering claim stops at the final answer. Keep the review's safeguard verdict beside the deterministic report. It cannot repair missing read evidence.

Read all six final outputs and their complete returned context yourself. Private content in returned context invalidates affected later observations as blinded evidence. Preserve raw grades and earlier observations with their coverage limits. An exposure does not establish behavioral influence. Missing or unreadable context leaves coverage unverified.

## Run the model-free checks

```sh
python3 -m unittest discover -s tools -p 'test_harness_routing.py' -v
```

Failure means a nonzero exit, `Ran 0 tests`, or absence of the calibration and fake-CLI collector cases. The fake executable proves launcher behavior without a subject call. Native gates and reviewers may run these checks and assess an existing wave. They must not launch extra actual subjects. CI discovers these tests through the existing tools test command and makes no model call.
