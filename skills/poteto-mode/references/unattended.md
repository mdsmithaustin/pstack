# Unattended runs

Read this reference before you wait for a human reply, and before you answer a no-mistakes gate.

A run is unattended when any of these is true:

- The operator gave the go for Autopilot-full, Autopilot-stack, or Orchestrate.
- The user said they are stepping away, said not to wait for them, or gave a grant that names no-mistakes.
- The **pstack-harness** skill's `question` action shows that this top-level session cannot reach a human.

A subagent is unattended only when its brief says so. Never infer it from the subagent's own tools.

Follow the [worklist promise rule](../../pstack-harness/references/worklist.md#report-later-promises) before ending with an undelivered report.

In an unattended run, hand blocked work back with [authorization's required final question](authorization.md), then end the turn without waiting for a reply. Apply Autonomy's authorization rule to irreversible writes. An action that the user, the matched playbook, or an enforced approval reserves for the operator stays blocked. Report the gate and continue independent authorized work. When nothing can proceed, report the block and the required decision.

For a gated repository, follow the unattended rules in [gated publish](gated-publish.md).
