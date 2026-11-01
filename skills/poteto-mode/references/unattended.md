# Unattended runs

Read this reference before you wait for a human reply, and before you answer a no-mistakes gate.

A run is unattended when any of these is true:

- The operator gave the go for Autopilot-full, Autopilot-stack, or Orchestrate.
- The user said they are stepping away, said not to wait for them, or gave a grant that names no-mistakes.
- The **pstack-harness** skill's `question` action shows that this top-level session cannot reach a human.

A subagent is unattended only when its brief says so. Never infer it from the subagent's own tools. In an unattended run, say so in every delegate brief.

In an unattended run, never wait for a human reply. When a decision needs the user, make the choice, put the choice and the reason in the final report, and continue. An action that **Always pause** or the matched playbook reserves for the operator stays blocked. Report it as blocked.

For a gated repository, follow the unattended rules in `../playbooks/opening-a-pr.md`.
