# Codex adapter

Observed circa 2026-09. Verify these hints against the live session and prefer its tools and help.

For a review, verdict, or fresh-perspective role, always set `fork_turns: "none"`, even when both model and effort resolve to `inherit-parent`. Pass the original task and file pointers in its brief. This restriction takes precedence over the full-history permission below.

Pass `model` and `reasoning_effort` on `spawn_agent`, and whenever you pass either, set `fork_turns` to `"none"`, or to a positive integer to carry the last few turns. A full-history fork, with `fork_turns` omitted or `"all"`, inherits the parent's model and effort and ignores overrides. So a role that resolves to a model or an effort never forks the full history. Only a non-review role that resolves to `inherit-parent` for both may fork full history. Set `agent_type` to the persona's native name when the live agent catalog lists it, and otherwise to `default` with the persona's briefing at the top of the message. When `spawn_agent` shows no `agent_type` parameter, this session loaded no custom agents, so omit the field and put the persona's briefing at the top of the message.

**Codex agent cap.** Codex caps subagents, and a spawn past the cap fails with `agent thread limit reached` and creates nothing. If your tools include `close_agent`, by default at most 6 agents stay open per session and a finished agent holds its slot until closed, so launch at most 6 at once and close each agent once you have read its result. If they do not, by default at most 3 subagents run at once and finished ones free their slots, so launch parallel arms in waves of 3 or fewer. Either limit overrides a skill's "spawn all in one message". The arm count stays the same either way. After a limit error, never wait for the refused arm: spawn it when a slot frees. Run it yourself only when the arm needs no other model, and report it as a substitution. Without `close_agent`, `wait_agent` takes no target and blocks until its timeout when no child is running, so call it only while a spawned child is still working. Name each child's scope in its brief: the question and the files or areas it owns. Do not read or search a scope that a running child owns, unless a skill step says that read runs in parallel with the child, as arena's Phase C says of the Phase D read. When a new fact changes a child's question, send the fact to that child. Wait with `wait_agent` when each remaining task belongs either to a running child or to an arm that waits for a free slot. Spawn each waiting arm as soon as a slot frees. Pass an explicit `timeout_ms` of at least `180000` (three minutes) to each `wait_agent` call while a child is running. When it returns while a child still runs, call it again with that timeout. After a child reports, spot-check its claims.

## Invocation and effort hints

`spawn_agent` (the multi-agent feature, stable in 0.152) takes a model and a reasoning effort per spawn, with the [`fork_turns` rule above](#codex-adapter); custom agents use TOML in `~/.codex/agents/` or `.codex/agents/` with `name`, `description`, and `developer_instructions`; generated pstack personas leave model and effort unset; `codex exec` is the subprocess route

the reasoning-effort field on `spawn_agent`; `-c model_reasoning_effort=<value>` on `codex exec`. A model set without an effort gets that model's default effort (low on `gpt-6.1-sol`, medium on the other gpt-6 models), not the parent's, so always pass one

## Writer isolation

Codex's `workspace-write` sandbox keeps `.git` read-only, so `git worktree add` fails there.

## Read skill files

`exec_command` cuts output that is longer than its `max_output_tokens`. Read each skill file in its own call with `read-chunk.py`. Set the call's `max_output_tokens` to `<n>`, and pass the same `<n>` to the script.

```sh
python3 "<installed skills root>/pstack-harness/scripts/read-chunk.py" "<file>" --max-output-tokens <n> --chunk 1
```

The last output line names the chunk and the chunk count, such as `chunk 1 of 3`. Read the remaining chunks in order with `--chunk 2`, `--chunk 3`, and so on, before you act on the file. If a chunk's output still warns that it was cut, lower `<n>`. If a line is too long for `<n>`, the script exits 1 without file content and names the smallest `<n>` it accepts. After any change to `<n>`, start again at chunk 1.
