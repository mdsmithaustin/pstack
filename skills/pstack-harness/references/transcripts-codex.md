# Codex transcript location and schema

JSONL lives under `$CODEX_HOME/sessions/<year>/<month>/<day>/rollout-*.jsonl`. `CODEX_HOME` defaults to `~/.codex`. A wrapper can select a different store. Verify the active store before reading it, then restrict reads to this workspace as required by [workspace transcripts](transcripts.md).

## Observed schema

Observed on 2026-11-04 in this workspace with Codex CLI 0.165.0. These are local observations, not a version-independent schema. Older or wrapper-generated records can differ.

- `session_meta.payload.cwd` binds the record to its workspace. `thread_source: "user"` identifies the observed human root. `thread_source: "subagent"` and `source.subagent.thread_spawn` identify observed children, including their `parent_thread_id`. Gate invocations can supply their own `--thread-source` value. Classify those from the recorded metadata and the bound gate invocation, not from a filename or the mere use of `exec`.
- `agent_path`, also present under `source.subagent.thread_spawn`, identifies the child's task path. `agent_nickname` is a display label and does not establish its role or scope.
- A `response_item` with `type: "custom_tool_call"` and `name: "exec"` can contain several `tools.exec_command` calls, each with its own `cmd`, inside the string `input`. One outer call is not one shell command. Other tools appear as `function_call` records with JSON in `arguments`. Pair calls and outputs by `call_id`. Forked history can repeat calls, so deduplicate shared call IDs before aggregating across threads.
- Observed `spawn_agent.arguments.message` values are encrypted strings. A missing plaintext brief is not evidence that the child received no brief. Preserve the observable task identity and report unavailable content instead of guessing or attempting decryption.
- Rollout filenames use the observed local wall time. JSON record timestamps ending in `Z` use UTC. Use record timestamps for time comparisons and convert explicitly before grouping by local day.
- `event_msg` records with `payload.type: "token_count"` expose `info.total_token_usage` and `info.last_token_usage`. The former is cumulative, so summing every sample counts earlier usage repeatedly. In the observed records, `input_tokens` includes `cached_input_tokens`, and `total_tokens` equals input plus output. Cached input is not an extra amount to add. `token_usage_record` is another representation of usage, not another bill to sum. Preserve the usage categories and distinguish totals from uncached-input or cost estimates.

For another version, inspect representative root, child, tool-call, output, and usage records before counting. Retain only the metadata needed to justify the schema and counts. Do not publish private prompts or raw session records as fixtures.
