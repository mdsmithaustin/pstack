# Named pstack roles

When a workflow requests `poteto-agent` or `Comment Sicko`, preserve its complete persona through the delegation mechanism. A built-in generic role does not supply either persona.

## Resolve and dispatch

1. Resolve `PSTACK_SKILLS_ROOT` using the installed-root block in [portable-paths.md](portable-paths.md). Preserve the logical path of the loaded harness skill, including symlinks. This operation needs neither a source checkout nor network access.
2. Read the requested persona with the bundled command below. Use the logical alias `poteto-agent`, `Comment Sicko`, or `comment-sicko`. A missing payload or sibling skill stops the briefing; repair the installation before dispatch.
3. Resolve the task's model and effort through the models config in [pstack-harness](../SKILL.md). Persona identity does not select a model-role label. Keep the caller's role, inline defaults, and arm count.
4. Use the native persona only when the requested destination passes `check` and the live session's role catalog confirms the matching native identifier. Both native identifiers are lowercase, `poteto-agent` and `comment-sicko`. A file check alone never proves a role was loaded. A same-name user-managed role is not proof of the pstack persona.
5. Otherwise pass the complete emitted briefing as instructions or context to a generic native delegate. Include the task scope, worktree ownership, report destination, and model and effort resolved separately. For Hermes, put the persona and installed paths in delegation context alongside the goal. If native delegation is unavailable, pass the same briefing to the own-CLI subprocess route or each sequential arm. Preserve the configured number of arms.

Do not summarize the persona or substitute a pointer that the child cannot read. Native wrappers contain the same full briefing. Poteto reads the complete `poteto-mode` skill and its inline Principles index before work. Comment Sicko edits comments and reports application-code refactor targets; it does not write application code. Do not force Comment Sicko into a read-only mode that prevents its intended comment changes.

```sh
python3 "${PSTACK_SKILLS_ROOT:?}/pstack-harness/scripts/subagents.py" brief 'Comment Sicko'
```

Failure signal: nonzero exit; stdout contains no partial briefing.

## Check the installed payload

```sh
python3 "${PSTACK_SKILLS_ROOT:?}/pstack-harness/scripts/subagents.py" check
```

Failure signal: nonzero exit. Success reports `payload: "ready"` and both roles. All referenced sibling skill files must exist. Python 3.9 or newer runs the installed command.

## Optional native registration

Native registration is independent of model configuration. Choose the caller's explicit project root or user home. Use an absolute existing directory; do not infer a destination from the command's working directory. If the current request already authorizes registration and scope, proceed without another confirmation.

For an authorized Codex project install, set `PSTACK_AGENT_DESTINATION` to the chosen absolute project root and run:

```sh
python3 "${PSTACK_SKILLS_ROOT:?}/pstack-harness/scripts/subagents.py" install --harness codex --project "${PSTACK_AGENT_DESTINATION:?}"
```

Failure signal: nonzero exit. Claude Code uses `--harness claude-code`. For a user install, use `--user` instead of `--project` and set `PSTACK_AGENT_DESTINATION` to the chosen absolute user home. Project roots and user homes both receive `.claude/agents/*.md` or `.codex/agents/*.toml` under that root. Wrappers set neither models nor effort, tools, or sandbox policy. They bind the current logical installed skill paths, so rerun installation after moving the skill installation.

To inspect the same registration without writing:

```sh
python3 "${PSTACK_SKILLS_ROOT:?}/pstack-harness/scripts/subagents.py" check --harness codex --project "${PSTACK_AGENT_DESTINATION:?}"
```

Failure signal: nonzero exit when either requested native file is missing, outdated, conflicting, or invalid.

Hermes supports `check --harness hermes` with an explicit project or user root, reporting ready payloads and unsupported native registration. It has no confirmed arbitrary custom-agent-file loader. `install --harness hermes` rejects the request without writing files. Supply the complete briefing through its delegation context instead.

## Command results

`check` and `install` write JSON. `payload` is `ready` or `invalid`. `native_activation` is always `unverified`. Each row in `roles` has its canonical `id` and `native_file` state:

| State | Meaning |
|---|---|
| `not-requested` | Only payloads were checked. |
| `unsupported` | The harness has no supported native registration format. |
| `missing` | No native file exists at the requested path. |
| `current` | Native bytes match this installation's full briefing. |
| `outdated-generated` | An unchanged generated file can be updated. |
| `conflict` | A user-managed, edited, or symlinked role must remain untouched. |

Native rows also include `path`. Successful installation adds `action`, either `installed` or `unchanged`. Filesystem or payload errors add `error`. Exit 0 means ready payloads and current native files when requested; Hermes's unsupported native registration is an explicit check-only result. Exit 1 means an invalid requested artifact state. Exit 2 means invalid arguments or an unknown role. `brief` writes only persona instructions and installed path guidance to stdout; errors go to stderr.

The installer checks both role destinations before writing either. It refuses unmarked files, symlink destinations, and local edits even when a generated marker remains. A full-content digest identifies unchanged generated wrappers. Identical installs preserve bytes and modification times. Updates use atomic writes in the destination directory. A rerun recovers a partial previous install; the pair of files is not a transaction. There is no force, adoption, removal, or settings-write operation.

Setup reports payload readiness, native-file installation, and live role loading separately. Codex project registrations require a trusted project; setup must not edit trust settings automatically. Inspect the live catalog in a fresh session after registration changes or after any harness-required reload. If loading remains unverified, use the complete briefing with a generic delegate and report that mechanism. Filesystem success must never be presented as activation success.
