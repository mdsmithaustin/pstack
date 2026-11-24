# Delegate a playbook unit

Read this reference before spawning, briefing, recovering, or reviewing a delegate.

**Spawn up or out, never sideways.** Spawn a subagent for one of four reasons: independent streams that run in parallel, bulk reading that would fill your context, independent scrutiny, or a hard problem that two runs on its role failed, which goes to `fable` under the exception below. A single stream on your own model tier stays with you. The lightweight route spawns no investigation or implementation delegate. Record the reason for each spawn. Keep a reviewer on a model at or above your own tier.

Before each spawn, read [unattended runs](unattended.md) and carry the run's attended or unattended state into the brief. The delegate takes that state from its brief, not its own tools.

**Use the `poteto-agent` persona for any subagent you spawn inside a playbook step**. The main conversation runs the playbook itself.
- The persona sets the subagent's instructions. The playbook step names a role in the models config, which sets the subagent's model and effort. Call the Skill tool with `pstack-harness`, then follow its **Spawn a role** section to turn the persona, model, and effort into this CLI's spawn call. This skill and `poteto-agent` preserve the same wrapper instructions.
- Routed skills (`how`, `why`, `interrogate`, `reflect`, `swarm`) choose their own persona. Respect it.
- A `poteto-agent` reads this skill's entry before work. It skips that read only when its brief names a narrow role whose output cannot land in the project, such as a judge, a reviewer, or a design runner. In the brief for such a role, name the role and the files it reads, such as its runner prompt or rubric. Put in the brief every rule from this suite that it needs.

On Codex, a configured `trail reviewer` uses the [native review assignment](../../pstack-harness/references/codex.md#codex-adapter) in place of `poteto-agent` when the exact type is live. Give it the same review brief and rubric.

**Defaults for every spawn.** Run it in the background, because a foreground call holds your turn while other reports wait. That holds for a steer or resume of a running agent too. Give the child full tool access, because a read-only mode can remove its MCP tools. Pass file pointers, not inlined context, and ask for a thin return. Call the Skill tool with `principle-guard-the-context-window`.
- Each spawn names one role from the models config. Code delegates take the playbook's role (`feature`, `refactoring`, `bug-fix`, `perf-issue`, or `hillclimb`). Prose and judgment take `judgment and prose`. Trivial mechanical edits take `swarm workers`. Independent verdicts and reviews take `trail reviewer`, except a swarm worker that runs something, which the **swarm** skill puts on `swarm workers`. A read-only scan, parse, or watcher that returns a reduced finding takes `routine`. Any other spawn takes `default`.
- `fable` is an exception. Outside a panel, run a spawn on `fable` at its role's effort only when the user named it for this task or two runs of the same brief on its role failed their check, and say which. Difficulty alone never qualifies. Where `fable` translates to the role's own model, as on Codex, report the two failures instead. No role runs above `xhigh`.

**Pass the source, not a summary.** Every brief names the original task text, spec, or issue by path and tells the delegate to read it in full. Write text that exists only in the conversation verbatim to a file first. Put your notes after the source, each rule or test marked `quoted` with its sentence, `current behavior` with its file or test, or `inferred`.

Start each brief from `python3 "${PSTACK_SKILLS_ROOT:?}/pstack-harness/scripts/subagents.py" clauses`, which prints the required clauses below from its arguments. Pass `--failing-test-first` for a Bug fix delegate that lands the reproducer before the repair. Add the scope and your judgment after them.
- Every brief that authorizes commits requires deslop's [Before each commit](../../deslop/SKILL.md#before-each-commit) check at the run's cleanup cadence, with one evidence reference per checked scope, and the preserve check: `python3 "${PSTACK_SKILLS_ROOT:?}/pstack-harness/scripts/preserve.py" --since <start commit>` with the start commit named in the brief, its last output returned per commit, and each failure fixed or, where the playbook allows an automatic-mode waiver, covered through `--reasons <file>` with the file returned. Follow [preservation modes](#preservation-modes) when a repository command is required. It names the branch off trunk to commit on, and it forbids committing credential files such as `.env` or the user's own notes and data they did not ask to version. A project with no repository yet has no trunk, so its brief names no branch.
- Carry these requirements into nested delegates, replacement owners, and fix rounds. Before accepting a delegate's committed work, inspect those references against the actual commits and cleanup diffs. Missing, truncated, stale, or unsupported evidence leaves the commit check pending. Repair the gap before accepting the work. A later pass does not establish that an earlier commit was checked before it happened.

You own every subagent's work. Review the diff and write your own summary. A second opinion is the same prompt against a different model. After you merge or abandon a delegate's work, follow **Remove a writer's worktree** in [Delegation and isolation](../../pstack-harness/references/delegation.md).

**Fresh subagents by default.** Give a fix round, a follow-up, a retry, or the next queue item to a fresh subagent with the original brief, every later directive, and the prior agent's report and branch. Resume an existing subagent only when the work needs state that lives in it and is costly to move: its checkout, its uncommitted changes, or a process it still runs.

## Preservation modes

The preserve script needs `python3` 3.9 or newer. When the script cannot start for that reason, run the project's own test command, confirm with `git diff --stat <start commit>` that no earlier test file changed, and say in the reply that the preserve gate did not run and why. Never report the gate as passed.

A repository task that requires its own selection or execution setup uses `--command <argv...>`. This mode requires Python test summaries and stays strict. The selected command must pass before a commit, and `--reasons` is unsupported.

A playbook that permits an automatic-mode waiver uses `--reasons <file>`, one block per failure cause. Use this route only when automatic execution already meets the repository's required test task. When a required repository command needs a waiver, keep its selection and report preservation pending. There is no command-mode waiver route. Collection errors remain nonwaivable.
