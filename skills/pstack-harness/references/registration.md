# Register pstack personas and effort agents

setup-pstack reads this file. A spawn never needs it. The spawn-time rules are in the [persona contract](named-roles.md) and in **Spawn a role** in [pstack-harness](../SKILL.md).

## Check the installed payload

```sh
python3 "${PSTACK_SKILLS_ROOT:?}/pstack-harness/scripts/subagents.py" check
```

Failure signal: nonzero exit. Success reports `payload: "ready"` and both personas. All referenced sibling skill files must exist. Python 3.9 or newer runs the installed command.

## Optional native registration

Native registration is independent of model configuration. Choose the caller's explicit project root or user home. Use an absolute existing directory; do not infer a destination from the command's working directory. If the current request already authorizes registration and scope, proceed without another confirmation.

For an authorized Codex project install, set `PSTACK_AGENT_DESTINATION` to the chosen absolute project root and run:

```sh
python3 "${PSTACK_SKILLS_ROOT:?}/pstack-harness/scripts/subagents.py" install --harness codex --project "${PSTACK_AGENT_DESTINATION:?}"
```

Failure signal: nonzero exit. Claude Code uses `--harness claude-code`. For a user install, use `--user` instead of `--project` and set `PSTACK_AGENT_DESTINATION` to the chosen absolute user home. Project roots and user homes both receive `.claude/agents/*.md` or `.codex/agents/*.toml` under that root. Persona wrappers set neither models nor effort, tools, or sandbox policy. They bind the logical installed skill paths of the root that installed them. A check or install from another alias of the same installation, such as a directory of per-skill symlinks, keeps those wrappers. It reports the wrappers current when their bytes match the briefing rendered from the installed root and every named `SKILL.md` resolves to the same file under both roots. Install then reports `unchanged`, and the wrapper keeps its original root. Rerun installation after moving the skill installation.

A wrapper that runs Codex with its own `CODEX_HOME` never reads `~/.codex/agents/`, so a user install does not reach it. A project install does: on Codex 0.159.2 under a private `CODEX_HOME`, `.codex/agents/` in the project loaded into the live catalog whether the project had a `trusted` entry or none, since `codex exec` under a config that never prompts adds one. An explicit `untrusted` entry hid it. For such a wrapper, register with `--project` at the repository it runs in.

A Claude Code install also writes five effort agents, `.claude/agents/pstack-effort-<level>.md` for `low`, `medium`, `high`, `xhigh`, and `max`. Claude Code's spawn tool has no per-call effort, and a custom agent's `effort` frontmatter overrides the session effort while the per-call `model` still applies, measured on 2.1.284. Each effort agent sets `name`, `description`, and `effort` in its frontmatter and carries one generic delegate body from this skill's `references/subagents/effort-delegate.md` template. It sets no model, tools, persona, or skills path, so its bytes are the same for every skills root and every destination. Codex takes the effort per spawn and gets no effort agents. Personas and effort agents preflight as separate groups. A conflict in one group writes nothing in that group and never blocks the other.

To inspect the same registration without writing:

```sh
python3 "${PSTACK_SKILLS_ROOT:?}/pstack-harness/scripts/subagents.py" check --harness codex --project "${PSTACK_AGENT_DESTINATION:?}"
```

Failure signal: nonzero exit when either requested native file is missing, outdated, conflicting, or invalid.

Hermes supports `check --harness hermes` with an explicit project or user root, reporting ready payloads and unsupported native registration. It has no confirmed arbitrary custom-agent-file loader. `install --harness hermes` rejects the request without writing files. Supply the complete briefing through its delegation context instead. Grok Build has no `--harness grok` registration. It loads the Claude Code wrappers from `~/.claude/agents/` as agent types, but its spawn tool cannot name one, so a Grok delegate gets the complete briefing in its prompt.

## Command results

`check` and `install` write JSON. `payload` is `ready` or `invalid`. `native_activation` is always `unverified`. Each row in `roles` has its canonical persona `id` and `native_file` state:

| State | Meaning |
|---|---|
| `not-requested` | Only payloads were checked. |
| `unsupported` | The harness has no supported native registration format. |
| `missing` | No native file exists at the requested path. |
| `current` | Native bytes match this installation's full briefing, or the briefing of another skills root whose named `SKILL.md` files resolve to the same files. |
| `outdated-generated` | An unchanged generated file can be updated. |
| `conflict` | A user-managed, edited, or symlinked wrapper must remain untouched. |

Native rows also include `path`. Successful installation adds `action`, either `installed` or `unchanged`. Filesystem or payload errors add `error`. Exit 0 means ready payloads and current native files when requested; Hermes's unsupported native registration is an explicit check-only result. Exit 1 means an invalid requested artifact state. Exit 2 means invalid arguments or an unknown persona. `brief` writes only persona instructions and installed path guidance to stdout; errors go to stderr.

A Claude Code destination also reports `efforts`, one row per level with `id`, `effort`, `native_file`, and `path`, using the same states and the same `action` values. Other destinations report an empty `efforts` list. Exit 0 requires every requested row in both lists to be `current`. An install report also carries `agents_directory`, `created` when the install made the agents directory and `existing` otherwise. When it is `created`, the new agents appear in the live agent catalog only in a fresh session, so tell the user to start one. A running session also misses them when it was started with `--disable-slash-commands` or when the agents directory sits under a directory added with `--add-dir`.

The installer checks every destination in a group before writing any file in that group. It refuses unmarked files, symlink destinations, and local edits even when a generated marker remains. A full-content digest identifies unchanged generated wrappers. Identical installs preserve bytes and modification times. Updates use atomic writes in the destination directory. A rerun recovers a partial previous install; the files are not a transaction. There is no force, adoption, removal, or settings-write operation.

Setup reports payload readiness, native-file installation, and live agent loading separately. Codex project registrations require a trusted project; setup must not edit trust settings automatically. Inspect the live agent catalog in a fresh session after registration changes or after any harness-required reload. If loading remains unverified, use the complete briefing with a generic delegate and report that mechanism. Filesystem success must never be presented as activation success.
