# Orch recovery reference

`bun skills/poteto-mode/scripts/orch/orch.ts --store <absolute-store-path>` is written below as `orch`. Pass `--json` for structured command results. `inbox drain --receipt` emits JSON even without `--json`.

## Retained delivery and acknowledgment

`units.tsv` and `ledger.tsv` remain canonical. Unit states are caller-defined strings. Existing stores and five-column inbox pointers remain readable. A legacy tracked pointer adds an attempt id as its sixth column. A bound completion adds the saved binding token, actual report PR, and actual report SHA as columns seven through nine. Missing PR or SHA metadata stays empty.

Every nonempty drain retains its completion files in `inbox-pending/<batch-id>/` until all events are acknowledged. Completed batches remain in `inbox-batches/<batch-id>/`. An empty `inbox drain --receipt` returns `null` without creating a batch. The legacy `--json inbox drain` emits a pointer array and returns `[]` when empty. `inbox receipts` exposes retained events and completed decisions for those deliveries. Draining no longer reduces `inbox count`. Count and peek include every event without a completed acknowledgment.

The canonical commands are:

```sh
orch inbox push worker-1 u1 done --report reports/u1.md --attempt <attempt-id> --binding <saved-binding> --pr 12 --sha head
orch inbox drain --receipt
orch inbox ack <batch-id> --file decisions.json
orch inbox receipts
```

A receipt has `id` and `events`. Each event has its stable filename `id` and `pointer`. A later drain returns the pending events from a claimed batch before claiming new arrivals. Arrivals during claim remain in the new inbox.

`decisions.json` is an array. Each entry names an event id from that batch and one outcome. A unit outcome can also record its exact PR and head verdict in the same replayable decision:

```json
[
	{
		"event": "<event-filename.tsv>",
		"outcome": {
			"kind": "unit",
			"state": "published",
			"branch": "work/u1",
			"pr": 12,
			"sha": "head",
			"ledger": {
				"kind": "verdict",
				"pr": 12,
				"sha": "head",
				"verdict": "unit-test-verified",
				"evidence": "reports/u1.md"
			}
		}
	}
]
```

A standalone verdict uses `kind`, `pr`, `sha`, `verdict`, `evidence`, and optional `verifier`. An explicit discard uses `{"kind":"discard","reason":"reviewed duplicate"}`. Discard does not settle an attempt. A coordinator can record a known terminal disposition for any attempt, including a superseded attempt, with `attempt finish` after inspecting evidence.

Acknowledgment applies only the named events. The store saves normalized effects and timestamps before changing TSV rows or attempts, then marks the decision complete last. A later affected read or write repairs an interrupted decision under the existing store lock. Identical retries preserve the saved effects. A different outcome for an acknowledged event exits 1. Earlier decisions in the same call may already have completed when a later decision fails. Pending events remain countable and replayable.

Direct unit updates and ledger records use the same normalized write-intent effects. The store replays pending `write-intents/` entries before later affected operations. A unit row and its attempt head binding converge after interruption. A ledger row and its attempt settlement also converge. Completed direct intents are removed. TSV files remain authoritative, and consumed inbox receipts remain inspectable.

Claims move the inbox atomically into `inbox-pending/`. Recovery, count, peek, and drain consult that pending collection. After all event decisions complete, the store atomically moves the batch to `inbox-batches/`. Routine operations do not read completed receipt history. `inbox receipts` inspects both collections, and acknowledgment by batch id still accepts identical historical retries after rebind or explicit finish.

On the first affected command, the store scans older `inbox-batches/` directories once and moves unfinished batches into the pending collection. It writes `.inbox-pending-migrated` only after those moves. Interrupted migration, claim, and archival recover under the existing lock. Surviving `.inbox-drain-*` directories from an older CLI are adopted into the pending collection. Completions already deleted by an older CLI cannot be recovered. Keep completed receipts as the run's evidence. This CLI has no automatic retention cleanup.

## Optional durable attempts

`attempt begin --file request.json` persists a delegation request before the caller dispatches through its existing route. The CLI never launches, schedules, or probes agents. A request has this shape:

```json
{
	"unit": "u1",
	"role": "feature",
	"arm": 1,
	"authority": "worker",
	"requestId": "u1-worker-1",
	"brief": "briefs/u1.md",
	"checkout": "/absolute/worktree/u1",
	"resolution": {
		"harness": "codex",
		"model": "gpt-6.1-sol",
		"effort": "xhigh"
	},
	"resolutionContext": {
		"workModel": null,
		"resolvedArm": {
			"role": "feature",
			"arm": 1,
			"model": "gpt-6.1-sol",
			"effort": "xhigh",
			"source": "user ## codex"
		}
	}
}
```

Resolve the actual role and exact panel arm through the current resolver as usual. Normal resolver inheritance remains supported. If model or effort inherits, record the actual value observed in the parent or execution context before saving the request. Do not substitute a made-up model. Saved attempts record concrete execution context. Model and effort reject `inherit-parent` and `auto`, including surrounding whitespace, with exit 1 before allocating an attempt or replacing a slot. Rejected saved records remain unchanged on disk for inspection.

Optional `resolutionContext` pairs the exact raw successful `--work-model` argument with the complete canonical printed arm. A successful no-flag invocation records `workModel: null`. Canonical model and effort may inherit or differ from observed execution after the existing spawn fallback. Preserve `source`, ordered `notes`, optional `step`, and absent versus present optional fields. The parser requires both members and matching role and arm. It validates their structure without implementing model policy.

Absent legacy context remains absent on cold reads and replay. It denies reviewer recovery eligibility but does not revoke existing bound completion authority. Legacy feature and panel recovery retains its existing behavior. Project the saved input into `{"workModel": <string-or-null>}` for `resolve-resume.py --resolution-input FILE`. Take source harness from that attempt's `resolution.harness`, and role and arm from the same attempt. The source arm remains historical context while the destination resolver computes its current arm.

The context is immutable request content. Changing raw input, source, notes, step, or optional-field presence conflicts with the same request id, even when concrete execution identity stays the same. Observation, settlement, head rebind, direct intent replay, and acknowledgment replay retain it. Identical begin retries still return the saved attempt after rebind or settlement. A replacement uses a new request id, copies the original input, and saves the new destination arm. Existing completion token and head checks remain authoritative.

`arm` is a positive one-based JSON integer. Single-value roles require arm 1. Panel roles retain their exact ordinal. Model aliases are not arm identifiers. The portable `role-contract.json` catalog derives from setup-pstack's canonical `ROLES`, `PANEL_ROLES`, and reserved `OTHER_ALIASES`, with source parity checked by the tools suite. A repeated identical request id returns the same attempt. A different request with that id exits 1. To replace a slot, include `"replace":"<current-attempt-id>"`. A missing or stale predecessor exits 1. Slots use unit, role, arm, and authority, so worker and verifier attempts coexist. `attempt list` includes prior attempts. An attempt is current when no successor names it in `replace`.

`attempt observe <id> --file observation.json` records one available observation:

```json
{"kind":"native","identity":"agent-1"}
```

A CLI observation is `{"kind":"cli","receipt":"logs/agent-1.jsonl"}`. Missing runtime evidence is `{"kind":"unknown"}`. Unknown leaves an unsettled attempt pending and establishes neither death nor liveness. Replacing it does not settle it. Observing an attempt does not dispatch or settle it. `attempt finish <id> --reason <disposition>` records `settled: {"kind":"finished","reason":"<disposition>"}` for any known attempt. This revokes further unit and ledger effects, including new acknowledgments. An accepted unit or verdict acknowledgment records `settled: {"kind":"accepted","at":"<timestamp>"}`. A direct ledger record does the same. Accepted results remain usable for current verifier revisions and coordinator metadata updates after landing. Direct unit updates preserve settlement because unit states are caller-defined. Legacy settlement strings cannot distinguish accepted results from explicit finish and conservatively revoke effects. Replay does not consume retry allowance.

Tracked unit and ledger mutations require the current bound `--attempt`. The attempt must match the unit and stored PR/head. Direct coordinator metadata updates use that attempt, including after an accepted result, without another worker launch. Changing its PR or SHA also rotates its `binding` token in the same replayable write. A state or branch update keeps the token. Other attempts bound to the old head cannot advance the new head.

Save the attempt's `binding` with its brief and report. Publish tracked reports with `--attempt`, that saved `--binding`, and the report's actual `--pr` and `--sha` when present. Omitted head fields mean absent metadata. Do not obtain an old report's head or token from the attempt's mutable state. A worker may introduce its reported head through a matching unit acknowledgment only when both captured target fields, PR and SHA, are empty. If either target field is populated, the report and unit outcome must match both captured fields exactly, including an empty field. A worker acknowledgment cannot fill or change either field of a partial target. Use the direct coordinator metadata update described above to change that target. Verifiers require the existing target head.

Inbox publication accepts late and unbound events for inspection. Acknowledgment checks the immutable completion binding and report head against the current attempt before applying effects. Legacy six-column tracked pointers lack that binding and cannot authorize effects. Five-column untracked pointers retain their existing behavior. Discard stale or unbound events after inspection. A true identical acknowledgment retry remains valid after rebind or finish because its effects already completed.

Direct ledger writes and acknowledgment share verifier precedence. Tracked authority comes from the attempt, regardless of a supplied `verifier` field. Untracked callers retain the existing trusted `--verifier <name>` attribution. A worker cannot replace a verifier on the same PR/head. A current verifier may revise either direction. Verdict labels have no strength ranking. Untracked legacy unit and ledger usage remains available.

## Explicit closeout

`requirements check --file requirements.json` checks only declared criteria over existing units, then requires no pending inbox events or unsettled attempts, including superseded history. Requirements must be nonempty and have unique ids. Each entry requires at least one explicit state list or exact PR/head verdict list:

```json
[
	{"id":"core","unit":"u1","states":["published"]},
	{
		"id":"review",
		"unit":"u2",
		"ledger":{"pr":12,"sha":"head","verdicts":["unit-test-verified"]}
	}
]
```

State-only units need no PR verdict. A ledger criterion requires both the unit's current PR/head and the exact ledger row to match. Changed heads and disallowed verdicts fail. `verifier-blocked` and `verifier-failed` are invalid successful closeout criteria, even in a mixed allowlist. Passing labels have no strength ranking. Unknown unsettled attempts remain pending after replacement until the coordinator records a known terminal disposition. Superseded ids may be finished for reconciliation, but cannot authorize unit or ledger effects.

The result contains `ok`, `failures`, `pendingEvents`, and `pendingAttempts`. Exit 0 means the explicit criteria pass. Exit 2 means requirements or pending work remain. Exit 1 means invalid input or a store error. These checks do not authorize landing or replace verification against the actual artifact.
