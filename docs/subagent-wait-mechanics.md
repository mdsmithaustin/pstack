# How a lead waits for a subagent on each harness

Read on 2026-11-11 for issues #455, #456, and #451. The question: after a lead spawns a child, what is the cheapest correct way to learn that the child finished, on each harness the suite supports?

Sources, in order of trust:

1. The installed CLI: version output, help, the tool text and bundled docs inside the binary, and the tool schemas a live session shows.
2. The vendor's documentation and public source, fetched on 2026-11-11.
3. This repository's records and this workspace's saved sessions, scanned read-only. Counts below are aggregates. No prompt or transcript text is copied here.

A cell marked **unverified** names what was tried. Nothing about one harness is inferred from another.

## Installed versions

| Harness | Version on this host | How it was read |
| --- | --- | --- |
| Claude Code | 2.1.322 | `claude --version` |
| Codex | codex-cli 0.167.0 | `codex --version` |
| Grok Build | 1.0.70 (stable) | `grok --version` |
| Hermes | **unverified** | `hermes --version` fails: the managed container `hermes-default-gateway` does not exist. No live schema could be read. |

## Summary

| | Claude Code | Codex | Grok Build | Hermes |
| --- | --- | --- | --- | --- |
| How the lead learns a child finished | A completion notification starts a new turn and carries the report. | `wait_agent` returns, and the child's report arrives as its own message. | Completion wakes the lead in a new turn. `get_command_or_subagent_output` can also block for it. | Per docs: the result is posted as a new message between the lead's turns. Unverified on an install. |
| Wait call and parameters | None needed. No wait tool in the live schema. | `wait_agent(timeout_ms)`. Default 30000, minimum 10000 (lower values are raised), maximum 3600000 (higher values fail). | `get_command_or_subagent_output(task_ids, timeout_ms)`. Up to 20 ids. Omitted or `0` is a snapshot. A positive value blocks and is capped at 3600000. | None documented for a top-level lead. `delegate_task` returns a handle. |
| What ends a wait early | Not applicable. | Any child message or final status, or new user input. | All listed ids complete, or a user message. | Not applicable. |
| Cost while waiting | Nothing while the turn is ended. Each wake is one turn over the whole context. | Nothing while blocked. Each return, including a timeout, is one more model request over the whole context. | Nothing while blocked or idle. Each wake or returned call is one turn. | Per docs, each delivered completion unit is one new turn. |
| Default spawn mode | Background. | Background. The spawn returns at once. | Background (`run_in_background` defaults to `true`). | Background for a top-level call, per docs. |
| Several children | One notification per child. | One `wait_agent` call covers every live child and returns on the first update. Call again. | One output call with every id waits for all of them. | One `tasks` array, one consolidated message after all finish. |
| A child that fails or hangs | A failed child still notifies, with the error and last output. `TaskStop` stops one. No stall monitor found. | `list_agents` shows live agents. No stall monitor found. | The wait returns at its timeout with the child still running. Docs say leave it alone. `kill_command_or_subagent` exists. | No wall-clock cap. A stall monitor interrupts after 450 s idle or 1200 s inside a tool and reports `timeout` or `stalled`. |
| Conflict with base guidance | None found. The live tool text agrees with the rule. | Yes. The base instructions cap blocking waits at 60 seconds. | None found. The bundled docs agree with the rule. | None found. The docs agree with the rule. |
| Recommended pattern | Do independent work, then end the turn. | Do independent work, then `wait_agent` with `timeout_ms` of at least 180000, and call it again while a child runs. | Do independent work. End the turn, or block once on the output call when the next step needs the results. In `grok -p`, block. | One batched call, do independent work, end the turn. |

## Claude Code

**Mechanism.** The vendor docs say: "With nothing configured, a subagent that Claude spawns from your main conversation starts in the background", and "A background subagent's results reach Claude as a completion notification in a later turn. Claude waits for that notification before reporting the subagent's results." ([sub-agents](https://code.claude.com/docs/en/sub-agents), section "Run subagents in foreground or background".) The live Agent tool text in a 2.1.322 session says the same: subagents run in the background, the lead is notified when one completes, and the lead must never fabricate or predict a pending agent's results.

**Foreground.** The same page says a foreground subagent blocks the main conversation until it completes. In an interactive session Claude cannot wait in the foreground while fork mode is on, and fork mode is on by default from v2.1.302. In `claude -p` and the Agent SDK "Claude can wait, on its own judgment or when you ask". The live Agent tool schema read in this session has no `run_in_background` field. **Unverified:** which argument asks for a foreground wait in 2.1.322.

**No wait tool.** The tools reference says `TaskOutput` was removed in v2.1.277. `Monitor` "runs a command in the background and feeds each output line back to Claude". The live Bash tool text says a foreground `sleep` is blocked, and says of a background command that the lead is re-invoked when it exits and should not poll its output file. ([tools-reference](https://code.claude.com/docs/en/tools-reference).)

**Failure.** For a background subagent whose run ends on an API error, "the subagent is marked failed, and the message Claude receives when it ends names the API error and includes the subagent's last output". `TaskStop` "stops a running background task by ID" and accepts a named background agent. No timeout or stall monitor for a subagent is documented. **Unverified:** what a lead sees when a child hangs without an API error.

**Headless.** [headless](https://code.claude.com/docs/en/headless), "Background tasks at exit": a `claude -p` run stays open after the turn for background subagents "until that work completes, because its result is part of the final output". The same section says Claude Code stops whatever is still running "after 10 minutes of continuous idle waiting by default", changed with `CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS`. **Unverified:** whether that ceiling can stop a subagent that is still working. No run was made to test it, so the adapter does not state a headless rule.

**Local record.** 15 root transcripts of this workspace from the last 45 days, all on 2.1.x: 1078 spawns, 1045 of them with `run_in_background: true` and 32 with the field omitted. While a child was open, the leads ran 64 shell reads of a child's output or transcript, 11 `sleep` calls or sleep loops on a task output file, and 2 `Monitor` calls. Five of the 15 sessions had at least one.

## Codex

**Mechanism.** Codex 0.167.0 exposes `wait_agent`. Its handler in the public source ([`multi_agents_v2/wait.rs`](https://github.com/openai/codex/blob/main/codex-rs/core/src/tools/handlers/multi_agents_v2/wait.rs)) waits for input activity under a timeout and returns one of three messages: "Wait completed.", "Wait interrupted by new input.", "Wait timed out." The same three strings are in the installed binary. The tool description in [`multi_agents_spec.rs`](https://github.com/openai/codex/blob/main/codex-rs/core/src/tools/handlers/multi_agents_spec.rs) reads: "Wait for a mailbox update from any live agent, including queued messages and final-status notifications. The wait also ends early when new user input is steered into the active turn. Does not return the content". This is the form without `close_agent`, where the only argument is `timeout_ms`.

**Parameters.** In the source, a requested value above the maximum fails with `timeout_ms must be at most <max>`, a value below the minimum is raised to it, and an omitted value takes the default. The defaults are in [`config/mod.rs`](https://github.com/openai/codex/blob/main/codex-rs/core/src/config/mod.rs): minimum 10000, default 30000, maximum 3600000. The installed binary carries the config keys `min_wait_timeout_ms`, `max_wait_timeout_ms`, and `default_wait_timeout_ms` and both error strings. The numbers come from the main branch on the day read, not from the installed binary.

**The older form.** With `close_agent` in the tool list, `wait_agent` takes agent ids and "Completed statuses may include the agent's final message". Its `timeout_ms` text ends "Prefer longer waits (minutes) to avoid busy polling", a string the installed binary also carries. No session in the local record used this form.

**Other tools.** `list_agents` lists "live agents in the current root thread tree". A `sleep` tool exists: "Pause execution for a specified duration. The sleep ends early when new input arrives for the active turn."

**Base-prompt conflict.** All 196 scanned sessions record this line in their base instructions: "Avoid performing blocking sleep or wait calls longer than 60 seconds, as they may prevent you from communicating with the user for their duration". They also record: "should not be left without a commentary update for more than 60 seconds during ongoing work". The reason given is reaching the user. `wait_agent` ends on new user input, so a long wait does not keep the user out. The `spawn_agent` tool text adds "Call wait_agent very sparingly" and "Do not repeatedly wait by reflex", next to "While the subagent is running in the background, do meaningful non-overlapping work immediately". The shared rule agrees with that last line: wait only when every remaining task belongs to a child.

**Cost of a short wait.** Local record: 196 Codex sessions of this workspace from 2026-11-02 to 2026-11-10, on 0.162.0 through 0.167.0-alpha.3.2.

- 605 `wait_agent` calls. 559 passed `timeout_ms` 60000, 35 passed 10000, 4 passed 30000, 4 passed 180000, 3 passed 240000.
- Of 581 with a recorded outcome, 279 timed out (48%).
- The model request after a timed-out wait read a median of about 169,000 input tokens, of which about 167,000 were cached. A timeout is cheap per token and still a full pass over the context that returns nothing.
- In the 26 sessions that spawned, leads made 641 `sleep` calls after their first spawn, with a median of 50 seconds and a maximum of 60, and 72 `list_agents` calls.

**Why 180000.** Measured from a lead's first wait to the wait that completed, 301 waits: 69% ended within 60 seconds, 89% within 180, 94% within 300, 97% within 600. The measure includes time the lead spent on other calls between waits, so it overstates the wait a single call needs. A floor of 180000 would have covered about nine waits in ten with one call. The wait returns the moment a child reports, so a higher value costs nothing when the child is quick.

**A child that never reports.** No stall monitor or child timeout was found in the Codex docs or source read. The adapter's rule, one `list_agents` call after two silent waits, is derived from the tool descriptions. It was not observed in a run. **Unverified:** how `list_agents` shows a child that died.

**Vendor docs.** The [subagents page](https://developers.openai.com/codex/subagents) (served from learn.chatgpt.com) says only that Codex handles "waiting for results" and "waits until all requested results are available". It documents `agents.max_concurrent_threads_per_session` and no wait parameter.

## Grok Build

All quotes are from the documentation bundled in the installed 1.0.70 binary.

**Mechanism.** `spawn_subagent` has `run_in_background`: "Run in the background and return a subagent ID. Defaults to `true`." Background work "can wake the agent for a new turn (commands and subagents on completion, monitors on events, loops on their timer)".

**Wait call.** "Use `get_command_or_subagent_output` to check a background command or subagent. Pass `task_ids` as a list (one id is a one-element array; maximum 20)". "Omit `timeout_ms`, or pass `0`, for a non-blocking snapshot." "A positive `timeout_ms` waits for completion. Several ids wait until **all** complete." "A positive `timeout_ms` is clamped to **1 hour** (`3600000` ms)." A host can lower the cap with `GROK_MAX_WAIT_BLOCK_MS`.

**On timeout.** "If the wait returns while the child is still running, leave it alone: do not kill it or tell it to stop. Completion wakes the parent automatically. Poll again only if you need another snapshot."

**User input.** While a turn is blocked in the output call, "Sending a message interrupts the wait and runs your message right away."

**Polling.** "Do not use sleep loops in normal commands to poll", use the output call with `timeout_ms` instead.

**Headless.** "A headless run waits for the background work it started before it exits, for up to 10 minutes after the latest turn ends." "The wait limit never cuts a running turn short." Work still running when the wait runs out is stopped and the run exits `1`. `--background-wait-timeout <secs>` changes the limit. A lead that blocks inside its turn is therefore not subject to the 10 minutes, which is why the adapter says to hold the turn in a `grok -p` run.

**Unverified.** The bundled docs name a `wait_commands_or_subagents` tool and give no parameters for it. The local store holds six Grok sessions for this workspace, too few to count wait behavior. No stall monitor for a subagent was found.

## Hermes

No installed Hermes could be queried, so every cell here is from the vendor's [delegation docs](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/features/delegation.md) on the main branch, read on 2026-11-11. The adapter says so and tells the lead to read the live schema first.

**Mechanism.** "Top-level model calls run in the background automatically. Hermes returns a handle immediately so the conversation can continue, then posts the result back as a new message. An orchestrator subagent waits for its own workers".

**Several children.** "When a top-level agent provides a `tasks` array, Hermes returns one background handle and runs the subagents in parallel. By default the call returns **one** consolidated message once every task has finished. Results are delivered only between the parent's turns: the parent should finish anything that does not depend on the children, then end its turn rather than polling transcripts, artifacts, or CI while it waits." Maximum concurrency is 10 by default (`delegation.max_concurrent_children`).

**Cost.** Per-completion delivery is opt-in "because every unit is a new turn for the orchestrator: a 15-task call becomes up to 15 wake-ups".

**Timeouts and hangs.** "By default there is **no wall-clock timeout** on subagents." A child with no progress past the stale threshold, "450s idle between turns, 1200s while inside a tool", is interrupted, and the parent gets a `status: "timeout"` entry. A background child that never returns is finalized with a `stalled` completion event.

**Older behavior.** This repository's Hermes harness pairs each `delegate_task` call with a tool result, which matches a call that blocked and returned the results itself. **Unverified:** which behavior the version a user has installed shows. The adapter covers both.

## What holds on every harness

1. A child's completion reaches the lead without the lead asking: a notification, a returned wait, or a posted message. Evidence: each section above.
2. Every wake is a full pass over the lead's context. A wake that brings no result is pure cost. Evidence: Codex token counts above, and the Hermes docs' reason for consolidated delivery.
3. A `sleep`, a status loop, or a read of the child's output adds wakes and no information. Three vendors say so in their own text: the Codex `timeout_ms` text, the Grok best-practice list, and the Hermes completion-delivery paragraph. The Claude Code Bash tool says it of background commands.
4. The lead has useful work only outside the child's scope. Evidence: the Codex `spawn_agent` text, and the race census recorded in `PORTING.md`.

The mechanics differ: end the turn on Claude Code and Hermes, block on Codex, and either on Grok Build. That split is why the shared rule sits in `skills/pstack-harness/references/delegation.md` and each adapter carries its own call, parameters, and numbers.

## Not covered

- No live run tested the rule text. Both "done when" lines in #455 and #456 are transcript observations and stay open.
- The mid-run message rule from #451 rests on the issue's own account. This research did not measure it.
