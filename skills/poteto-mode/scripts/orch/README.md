# Orch recovery reference

`bun skills/poteto-mode/scripts/orch/orch.ts --store <absolute-store-path>` is written below as `orch`. Pass `--json` for structured command results. `inbox drain --receipt` emits JSON even without `--json`.

## Retained delivery and acknowledgment

`units.tsv` and `ledger.tsv` remain canonical. Unit states are caller-defined strings. Existing stores and five-column inbox pointers remain readable. A tracked pointer adds an attempt id as its sixth column.

Every drain retains its completion files in `inbox-batches/<batch-id>/`. The legacy `--json inbox drain` still emits a pointer array. `inbox receipts` exposes retained events and completed decisions for those deliveries. Draining no longer reduces `inbox count`. Count and peek include every event without a completed acknowledgment.

The canonical commands are:

```sh
orch inbox push worker-1 u1 done --report reports/u1.md --attempt <attempt-id>
orch inbox drain --receipt
orch inbox ack <batch-id> --file decisions.json
orch inbox receipts
```

A receipt has `id` and `events`. Each event has its stable filename `id` and `pointer`. A later drain returns the pending events from a retained batch before claiming new arrivals. Arrivals during claim remain in the new inbox.

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

A standalone verdict uses `kind`, `pr`, `sha`, `verdict`, `evidence`, and optional `verifier`. An explicit discard uses `{"kind":"discard","reason":"reviewed duplicate"}`. Discard does not settle an attempt. A coordinator can explicitly settle an abandoned current attempt with `attempt finish` after inspecting evidence.

Acknowledgment applies only the named events. The store saves normalized effects and timestamps before changing TSV rows or attempts, then marks the decision complete last. A later affected read or write repairs an interrupted decision under the existing store lock. Identical retries preserve the saved effects. A different outcome for an acknowledged event exits 1. Earlier decisions in the same call may already have completed when a later decision fails. Pending events remain countable and replayable.

A drain killed between rename and mkdir recovers on the next affected command. Surviving `.inbox-drain-*` directories from an older CLI are adopted as retained batches. Completions already deleted by an older CLI cannot be recovered. Keep completed receipts as the run's evidence. This CLI has no automatic retention cleanup.

## Optional durable attempts

`attempt begin --file request.json` persists a delegation request before the caller dispatches through its existing route. The CLI never launches, schedules, or probes agents. A request has this shape:

```json
{
	"unit": "u1",
	"role": "feature",
	"arm": "sol",
	"authority": "worker",
	"requestId": "u1-worker-1",
	"brief": "briefs/u1.md",
	"checkout": "/absolute/worktree/u1",
	"resolution": {
		"harness": "codex",
		"model": "gpt-6.1-sol",
		"effort": "xhigh"
	}
}
```

Resolve the actual role and exact panel arm through the current resolver before writing the request. Save its concrete resolution. A repeated identical request id returns the same attempt. A different request with that id exits 1. To replace a slot, include `"replace":"<current-attempt-id>"`. A missing or stale predecessor exits 1. Slots use unit, role, arm, and authority, so worker and verifier attempts coexist. `attempt list` includes prior attempts. An attempt is current when no successor names it in `replace`.

`attempt observe <id> --file observation.json` records one available observation:

```json
{"kind":"native","identity":"agent-1"}
```

A CLI observation is `{"kind":"cli","receipt":"logs/agent-1.jsonl"}`. Missing runtime evidence is `{"kind":"unknown"}`. Unknown leaves the attempt pending and is never proof of death. Observing an attempt does not dispatch or settle it. `attempt finish <id> --reason <disposition>` explicitly settles a current attempt. An accepted unit or verdict acknowledgment settles its bound attempt. A direct ledger record also settles its bound attempt. Direct unit updates preserve the attempt disposition because unit states are caller-defined. Replay does not consume retry allowance.

Tracked unit and ledger mutations require the current bound `--attempt`. Inbox publication accepts late and unbound events for inspection, but acknowledgment rejects their unit or verdict effects on tracked work. The attempt must match the unit and stored PR/head. A unit update through a current attempt moves that attempt's head binding. Other attempts bound to the old head must be replaced before their results can advance the new head.

Direct ledger writes and acknowledgment share verifier precedence. Tracked authority comes from the attempt, regardless of a supplied `verifier` field. Untracked callers retain the existing trusted `--verifier <name>` attribution. A worker cannot replace a verifier on the same PR/head. A current verifier may revise either direction. Verdict labels have no strength ranking. Untracked legacy unit and ledger usage remains available.

## Explicit closeout

`requirements check --file requirements.json` checks only declared criteria over existing units, then requires no pending inbox events or current unsettled attempts. Requirements must be nonempty and have unique ids. Each entry requires at least one explicit state list or exact PR/head verdict list:

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

State-only units need no PR verdict. A ledger criterion requires both the unit's current PR/head and the exact ledger row to match. Changed heads and disallowed verdicts fail. Superseded attempts are historical and do not block closeout. Unknown current attempts remain pending until an explicit disposition or accepted result settles them.

The result contains `ok`, `failures`, `pendingEvents`, and `pendingAttempts`. Exit 0 means the explicit criteria pass. Exit 2 means requirements or pending work remain. Exit 1 means invalid input or a store error. These checks do not authorize landing or replace verification against the actual artifact.
