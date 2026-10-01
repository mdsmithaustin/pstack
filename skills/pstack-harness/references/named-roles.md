# pstack personas

When a workflow requests `poteto-agent` or `Comment Sicko`, preserve its complete persona through the delegation mechanism. A built-in generic agent type does not supply either persona.

## Resolve and dispatch

1. Resolve `PSTACK_SKILLS_ROOT` using the installed-root block in [portable-paths.md](portable-paths.md). Preserve the logical path of the loaded harness skill, including symlinks. This operation needs neither a source checkout nor network access.
2. Read the requested persona with the bundled command below. Use the logical alias `poteto-agent`, `Comment Sicko`, or `comment-sicko`. A missing payload or sibling skill stops the briefing. Reinstall the skills with `npx skills add mdsmithaustin/pstack` before dispatch.
3. Resolve the task's model and effort with the resolver in the models config section of [pstack-harness](../SKILL.md). The persona never picks the role. Keep the caller's role and arm count.
4. Use the native persona only when the live agent catalog lists its identifier, `poteto-agent` or `comment-sicko`. A file on disk does not prove the persona is loaded. A native persona wrapper carries no effort. Codex passes the effort on `spawn_agent`, so the native persona keeps its resolved effort there. On Claude Code a native persona runs at the session effort, so apply **Set an arm's effort** in [pstack-harness](../SKILL.md) first. It sends a role whose effort resolves to a level to an effort agent when one is loaded, and to this step otherwise.
5. Otherwise pass the complete emitted briefing as instructions or context to a generic native delegate. Include the task scope, worktree ownership, report destination, and the resolved model and effort. For Hermes, put the persona and installed paths in delegation context alongside the goal. If native delegation is unavailable, pass the same briefing to the own-CLI subprocess route or each sequential arm. Preserve the configured number of arms.

Do not summarize the persona or substitute a pointer that the child cannot read. Native wrappers contain the same full briefing. Poteto reads the complete `poteto-mode` skill and its inline Principles index before work. Comment Sicko edits comments and reports application-code refactor targets; it does not write application code. Do not force Comment Sicko into a read-only mode that prevents its intended comment changes.

```sh
python3 "${PSTACK_SKILLS_ROOT:?}/pstack-harness/scripts/subagents.py" brief 'Comment Sicko'
```

Failure signal: nonzero exit; stdout contains no partial briefing.

Registering native personas and effort agents is setup, not dispatch. setup-pstack does it through [registration.md](registration.md).
