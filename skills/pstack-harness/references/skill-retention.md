# Skill retention after compaction

Evidence checked on 2026-10-20. Runtime documentation and observed runs answer different questions. A discovery or initial-load contract does not establish post-compaction retention.

| Runtime | Current primary documentation | Runtime observation | Reported or unknown |
|---|---|---|---|
| Claude Code | Compaction reattaches the latest invocation of each skill. It retains the first 5,000 tokens per skill within a combined 25,000-token budget, newest first. Older skills can disappear entirely. [Skill content lifecycle](https://code.claude.com/docs/en/skills#skill-content-lifecycle). | No native Claude compaction observed for this reference. | Issue 265 reports a historical 20,000-character cutoff in one session. Its binary version and raw payload were not inspected. This is not the current documented token contract. |
| Codex | Selection loads the full skill instructions. The initial skill-list budget is separate. Configuration exposes automatic compaction settings. [Build skills](https://learn.chatgpt.com/docs/build-skills), [configuration reference](https://learn.chatgpt.com/docs/config-file/config-reference). | No retention guarantee established by the cited documentation. | Per-skill retained bytes and automatic reinjection after compaction remain unknown. A CLI observation applies to that binary and invocation, not every Codex client. |
| Grok Build | Skills have native discovery and activation settings. [Skills, plugins, and marketplaces](https://docs.x.ai/build/features/skills-plugins-marketplaces). | No native Grok compaction observed for this reference. | The cited page establishes no skill retention budget or automatic restoration contract. |
| Hermes | Skills load through progressive disclosure. Context compression is lossy. [Skills](https://hermes-agent.nousresearch.com/docs/user-guide/features/skills), [configuration](https://hermes-agent.nousresearch.com/docs/user-guide/configuration#context-compression). | No native Hermes compression observed for this reference. | Retained skill bytes, a reinjection budget, and automatic restoration remain unknown. |

The repository limits the whole `skills/poteto-mode/SKILL.md` file, including frontmatter, to 16,000 UTF-8 bytes. The explicit target list is `ENTRY_BUDGETS` in `tools/check-mode-entry-size.py`. This policy leaves headroom below the issue's reported historical character cutoff. Bytes, characters, and tokens are different units. This limit is not a token conversion, a smallest cross-runtime limit, or a retention guarantee.

The [contributor checks](../../../README.md#contributor-checks) describe the gate commands and tier assignments. The existing CI tools unit-test discovery also executes the checker against the repository entry. Failure is a nonzero checker exit. Missing entries and invalid UTF-8 fail too.

For a runtime observation, record the binary version, requested and observed model, invocation route, native compaction event, and inspected payload or transcript. Keep synthetic prefix truncation separate from a native boundary. Without an observed native boundary, a recovery result is `INCONCLUSIVE`. When both parent and head recover, report no demonstrated improvement.

After a known compaction or truncation, follow the recovery rule near the beginning of the mode entry. Recover the active playbook path and current step from the existing task record. A trailing sentinel cannot recover an omitted mode.
