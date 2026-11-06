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

A tool call cuts output that is longer than its cap and keeps the start and the end. An outer `exec` call has one cap for everything its `tools.exec_command` calls return, whatever `max_output_tokens` each of them sets. Before you read a skill file, print its read plan. Set `<n>` no higher than the smallest cap on the call that will return a range, and pass `<n>` as that range's `max_output_tokens`.

```sh
python3 "<installed skills root>/pstack-harness/scripts/read-plan.py" "<file>" --max-output-tokens <n>
```

The script prints one `sed -n` command per line, and each command prints a range of lines that fits `<n>`. Run each command in its own outer call. Never batch two ranges, or two files, in one outer `exec` call. Read every range in order before you act on the file. If a range's output still warns that it was cut, lower `<n>` and print a new plan. If a line is too long for `<n>`, the script exits 1 and names the smallest `<n>` it accepts. Raise `<n>` to that value and print a new plan.
