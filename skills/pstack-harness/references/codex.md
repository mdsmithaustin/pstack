# Codex adapter

Observed circa 2026-09. Verify these hints against the live session and prefer its tools and help.

**Wait for a child with `wait_agent` and an explicit `timeout_ms` of at least `180000` (three minutes).** Without `close_agent` in your tools, the call returns as soon as any child sends a message or finishes, and as soon as the user sends input, so the timeout is a ceiling, not a delay. Your base instructions say to avoid blocking sleep or wait calls longer than 60 seconds, so that the user can reach you. A user message ends that form of `wait_agent` at once, so that reason does not hold for it, and this rule overrides the 60 seconds. Each wait that times out makes you reread your whole context for nothing. On that form an omitted `timeout_ms` is `30000` by default, a value below `10000` is raised to `10000`, and a value above `3600000` fails the call. When the wait returns while a child still runs, call it again with the same timeout, and repeat until every child has reported. Never call `sleep` in its place, and never loop on `list_agents`. When no child has sent anything across two waits in a row, call `list_agents` once. Wait again for a child that still runs. Report a child that stopped without a result, and spawn its arm again. That form of `wait_agent` takes no target, returns no content because each report arrives as its own message, and blocks until its timeout when no child is running, so call it only while a spawned child is still working. With `close_agent` in your tools, `wait_agent` takes the agent IDs to wait for, returns when one of them reaches a final status, and lowers a `timeout_ms` above the maximum to it. Its own text says to prefer waits of minutes, so keep the three-minute floor. No source read shows that user input ends that wait, so read the live schema before you rely on it. A final status there already tells you that a child stopped. The [shared wait rule](delegation.md) says what you may do while a child runs.

For a review, verdict, or fresh-perspective role, always set `fork_turns: "none"`, even when both model and effort resolve to `inherit-parent`. Pass the original task and file pointers in its brief. This restriction takes precedence over the full-history permission below.

When the configured role is `trail reviewer` and the live catalog lists that exact name, set `agent_type: "trail reviewer"`. Pass the resolved model and effort and the calling workflow's read-only review brief. This native assignment takes precedence over a persona. If the type is unavailable, use the normal fallback below with the same review brief and report the fallback.

Pass `model` and `reasoning_effort` on `spawn_agent`, and whenever you pass either, set `fork_turns` to `"none"`, or to a positive integer to carry the last few turns. A full-history fork, with `fork_turns` omitted or `"all"`, inherits the parent's model and effort and ignores overrides. So a role that resolves to a model or an effort never forks the full history. Only a non-review role that resolves to `inherit-parent` for both may fork full history. Set `agent_type` to the persona's native name when the live agent catalog lists it, and otherwise to `default` with the persona's briefing at the top of the message. When `spawn_agent` shows no `agent_type` parameter, this session loaded no custom agents, so omit the field and put the persona's briefing at the top of the message.

**Codex agent cap.** Codex caps subagents, and a spawn past the cap fails with `agent thread limit reached` and creates nothing. If your tools include `close_agent`, by default at most 6 agents stay open per session and a finished agent holds its slot until closed, so launch at most 6 at once and close each agent once you have read its result. If they do not, by default at most 3 subagents run at once and finished ones free their slots, so launch parallel arms in waves of 3 or fewer. Either limit overrides a skill's "spawn all in one message". The arm count stays the same either way. After a limit error, never wait for the refused arm: spawn it when a slot frees. Run it yourself only when the arm needs no other model, and report it as a substitution. Wait when each remaining task belongs either to a running child or to an arm that waits for a free slot. Spawn each waiting arm as soon as a slot frees. After a child reports, spot-check its claims.

## Invocation and effort hints

`spawn_agent` (the multi-agent feature, stable in 0.152) takes a model and a reasoning effort per spawn, with the [`fork_turns` rule above](#codex-adapter); custom agents use TOML in `~/.codex/agents/` or `.codex/agents/` with `name`, `description`, and `developer_instructions`; generated pstack personas leave model and effort unset; `codex exec` is the subprocess route

the reasoning-effort field on `spawn_agent`; `-c model_reasoning_effort=<value>` on `codex exec`. A model set without an effort gets that model's default effort (low on `gpt-6.1-sol`, medium on the other gpt-6 models), not the parent's, so always pass one

## Injected skills

A `$name` mention in a user prompt injects that skill's `SKILL.md` as a `<skill>` block with its name and path. While that block is in your context, it is your read of the file, so do not read the file again, unless the block was cut. Read the files it references only when a step needs them.

## Writer isolation

Codex's `workspace-write` sandbox keeps `.git` read-only, so `git worktree add` fails there.

## Read skill files

A tool call cuts output that is longer than its cap and keeps the start and the end. An outer `exec` call has one cap for everything its `tools.exec_command` calls return, whatever `max_output_tokens` each of them sets. That outer cap is the `max_output_tokens` in the call's first-line pragma, or 10000 when the pragma sets none. Before you read a skill file, choose the caps for the calls that read it. Set `<n>` to the outer cap, or to the `max_output_tokens` you pass to each `tools.exec_command` call if that is lower. Then print the file's read plan.

```sh
python3 "<installed skills root>/pstack-harness/scripts/read-plan.py" "<file>" --max-output-tokens <n>
```

Each line that the script prints is a command whose output fits `<n>`. Run each command in its own outer call, with the caps you chose. Never batch two commands, or two files, in one outer `exec` call. Run every command in order before you act on the file. If the last line runs `read-plan.py` again, run it after the other lines. It prints the rest of the plan. If an output still warns that it was cut, keep your caps and print a new plan with half of `<n>`. Then run the new plan from its first command.
