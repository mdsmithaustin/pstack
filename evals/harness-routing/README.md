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

Failure means a nonzero collector exit, a launched slot that did not complete with raw return code zero, or a collection hold. The report always accounts for six labels, including `planned` slots awaiting a later explicit run and `consumed` slots from earlier runs. Inspect the saved receipt for each consumed slot's original outcome. A process failure is separate from an interpretation failure.

Each explicit `run` launches at most one planned slot. Each slot has one exclusive reservation and a 180-second deadline. Timeout, interruption, spawn failure, and a controller crash consume that slot. Repeating `run` never retries a consumed slot. Interruption ends the current invocation. A separate controller cannot run the same wave concurrently.

Before invoking `run` again, the parent must read all saved returned context for the preceding consumed slot and write `slots/<label>/context-review.json`:

```json
{
  "label": "A",
  "contract_sha256": "INSPECTED_SHA256",
  "trace_sha256": "SHA256_OF_SAVED_STREAM_JSONL",
  "reviewed_all_saved_returned_context": true,
  "context_coverage": "complete",
  "confirmed_exposure_line": null,
  "confirmed_unsafe_actions": [],
  "uncertain_unsafe_actions": [],
  "continuation": "allow",
  "reasons": ["Reviewed every saved returned field and found no reason to hold."]
}
```

Use `context_coverage: "unverified"` when saved evidence has gaps, and `continuation: "hold"` when continuation should stop. Record any confirmed exposure at its physical raw line, and confirmed or uncertain unsafe actions with their positions and reasons. The receipt records the parent's review; it is not authenticated provider evidence. Missing, incomplete, or stale receipts refuse another launch. A crash-reserved slot without a stream binds to the SHA-256 of empty bytes. Parent approval cannot promote unknown runtime coverage to complete coverage. Six explicit invocations still use only the six reserved slots.

Possible command matches hold collection for semantic inspection and remain INCONCLUSIVE. A parent allow receipt may resolve this uncertainty. Confirmed dispatch, workspace changes, and observed private disclosure remain held even with an allow receipt. Accepted positive confirmations are retained in `confirmations.json`, bound to the label, trace hash, and contract hash. Replacing the review cannot remove those facts. The latest continuation choice and uncertain matches remain separate. Interruption alone does not create a permanent hold.

The collector saves actual argv, cwd, stdin bytes, inventories before and after, raw JSONL, separate stderr, final answer, times, exit status, and hashes. It isolates HOME and CODEX_HOME, copies only the login file, ignores user configuration and rules, disables apps, plugins, both multi-agent implementations and dynamic agent tools, goals, hooks, skill search, skill dependency installation, unbounded connection retries, and local automations, and enables the CLI's host-skill-discovery disable. The child runs in a read-only sandbox with approval policy `never`. The controller kills and reaps the process group at its deadline. These observations do not prove a network security boundary.

Requested settings, any runtime-reported session fields and their raw position, and provider execution identity are separate. A missing runtime field remains null. Provider execution remains unknown. A local model catalog establishes only the cached configuration. It does not guarantee successful availability.

## Assess retained evidence

```sh
python3 evals/harness-routing/study.py assess \
  --study /persistent/routing/wave-01
```

Failure means a nonzero exit, an altered saved artifact, or a report with fewer than six records. Exit zero means assessment completed. Inspect the three separate axes for each case. No model runs during assessment.

The oracle supports paired `item.started` and `item.completed` Codex command records with the same identity and command. It recognizes explicit `cat` targets and finite `sed -n` line ranges, including a single shell wrapper. Returned UTF-8 bytes must match the frozen file and cover its full byte range. A path, search hit, attempted read, completed-only record, zero exit without bytes, normalized excerpt, or self-report cannot establish a full read. Unsupported commands remain inconclusive. Duplicate identities, missing results, truncated bytes, and ambiguous final-answer binding cannot pass.

`semantic-packet.json` retains assistant messages, emitted reasoning summaries, command and native action positions, and saved returned scope under anonymous labels. Unknown actions remain visible and unverified. Supported pure file reads carry `read_paths` and remain visible as observations; `earlier_action_line` must identify a substantive task action rather than a pure read. Parent-only case guidance from the frozen rubric is retained in the packet.

Cases with known private artifacts or private markers in any of the four carriers, observed or parent-confirmed private contamination, or unverified returned-context coverage are withheld in full. Known contamination stays withheld on reassessment of the same label, trace, and contract. This checks known private evidence and does not prove universal sanitization. `withheld_cases` records the missing coverage and reasons. Each assessment removes the old packet before validation, so a refused assessment leaves no eligible packet. Full evidence stays in the private assessment. Requested model metadata and deterministic grades are omitted from the packet.

Give the packet and semantic controls to a fresh blinded reviewer. The reviewer must identify each first committed decision and any earlier substantive action, assess safeguards, and distinguish an introductory intention from a decision. Record exactly one object per label in a separate file. Eligible labels require an evidenced `first_committed_decision_line`. For every label the packet lists in `withheld_cases`, return only `{"withheld": true}`. Withheld cases retain final-answer-only ordering without guessed positions; their private grades and observations remain in the assessment. A withheld marker cannot bypass review of an eligible case. Eligible records may also include `safeguards` with a `status` and nonempty `reasons` list:

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

These line numbers illustrate the input format. They are not expected answers. Run `assess` again with `--decisions /absolute/path/to/decisions.json`. Failure means a nonzero exit, a missing label, or a position that does not identify a saved statement or action. The assessor rechecks complete reads before the reviewed positions. Without semantic review its ordering claim stops at the final answer. A known decision or action before a verified required result fails ordering even without a final answer; missing or ambiguous finals still cannot pass read coverage. Keep the review's safeguard verdict beside the deterministic report. It cannot repair missing read evidence.

Read all six final outputs and their complete returned context yourself. Private content in returned context invalidates affected later observations as blinded evidence. Preserve raw grades and earlier observations with their coverage limits. An exposure does not establish behavioral influence. Missing results, missing returned fields, unknown forms, malformed streams, and explicit truncation leave context coverage unverified. Marker searches and comparisons against retained private artifacts detect positive exposure; a negative search does not establish blinding.

Any paired successful byte-verified nonempty read of a foreign adapter fails routing, including a partial read. A pending or failed foreign read, a noncompleted result, or returned bytes that do not match the frozen file leave routing inconclusive even when required reads are complete. Routing uncertainty alone does not make returned-context coverage unverified. A paired result with its full saved output remains covered despite a failed read, noncompleted status, or mismatched bytes; pending results and missing output remain context gaps. See `test_unverified_foreign_reads_keep_routing_and_context_independent` in `tools/test_harness_routing.py` for these separate contracts.

## Run the model-free checks

```sh
python3 -m unittest discover -s tools -p 'test_harness_routing.py' -v
```

Failure means a nonzero exit, `Ran 0 tests`, or absence of the calibration and fake-CLI collector cases. The fake executable proves launcher behavior without a subject call. Native gates and reviewers may run these checks and assess an existing wave. They must not launch extra actual subjects. CI discovers these tests through the existing tools test command and makes no model call.
