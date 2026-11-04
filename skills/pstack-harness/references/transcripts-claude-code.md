# Claude Code transcript location and schema

JSONL lives under `~/.claude/projects/<slug>/`. The slug is the resolved workspace path with every character other than a letter or digit replaced by `-`. Verify the workspace binding before reading it, as required by [workspace transcripts](transcripts.md). A slug usually starts with `-`. Use an absolute path, prefix a relative slug with `./`, or put `--` before path operands where the command supports it.

## Observed schema

Observed on 2026-11-04 in this workspace's retained sessions, including records dated 2026-10-06. These are local observations, not a version-independent schema.

- A root transcript is `<slug>/<session-id>.jsonl`. Its child records live at `<slug>/<session-id>/subagents/agent-<id>.jsonl`. The adjacent `agent-<id>.meta.json` supplies `description` and `agentType`, with optional execution metadata. Use those fields to identify the task and agent type rather than guessing from the opaque ID.
- Message records carry `isSidechain`. The observed child messages set it to `true`. Combine that flag with the path and session identity when separating roots from children. Do not count every JSONL file as a human session.
- A root transcript can contain `type: "cost-state"` records with `totalCostUSD`, duration totals, and per-model `modelUsage`. These are cumulative snapshots. Use the last recorded snapshot for that session instead of summing snapshots. Record a missing snapshot as unavailable, not zero. Per-model usage separates input, output, cache reads, and cache creation. Preserve those categories instead of applying Codex's token formula.
- JSON timestamps ending in `Z` use UTC. Convert explicitly for a local-day report. JSONL includes metadata and system records as well as messages, so line count is not a turn count.

Inspect representative root, child, metadata, and cost records again when the runtime changes. Retain minimal schema evidence privately. Do not commit raw transcripts, task descriptions, or personal data as test fixtures.
