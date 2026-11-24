# Resolve roles and preserve handoffs

Carry delegation roles into plans, checkpoints, and handoffs. Separate the role to resume, prior model history, and explicit human overrides. Record the following for each delegate, including builders and independent verifiers:

| Field | Record |
|---|---|
| Role and panel arm | Exact configured role and one-based arm to resume. |
| Previous resolution | Prior harness, model, and effort returned by the resolver. Label these as historical. |
| Previous execution | Actual prior harness, model, and effort, with the observation or receipt that establishes them. Record unknown values explicitly. |
| Human override | Original explicit human model request and its source, or that no such request is established. |

Record the coordinator's previous execution separately when available. Keep resolver output separate from actual execution, including substitutions and inherited or unknown identities. A resolved model alone does not prove which model ran.

Preserve a specific-model override with its original explicit human request. Model names in defaults, examples, past runs, or agent-written summaries do not establish such a request. If the source is unavailable, report the uncertainty instead of attributing the model choice to the human. A direct human model request still takes precedence.

On pickup, resolve the saved role for the receiving harness and its current configuration, even when the previous harness differs. Keep previous resolutions and execution identities as history, not dispatch requirements. A recovered statement such as "builders require Sonnet" establishes no override without the original human request. When a legacy handoff omits the role, recover it from the original brief or matching playbook, not the prior model name. If the role remains unknown, report that gap. Record the replacement's resolution and observed execution without overwriting the prior history.

For durable recovery, preserve the exact role and one-based panel arm, brief, standing orders, checkout, resolved identity, and any observed native task id or CLI receipt. A missing observation leaves the child's liveness unknown. It does not prove that the child stopped. To recover, spawn the saved role per **Spawn a role** like any other spawn, and use the printed arm whose `arm` matches the saved arm. Do not choose `default`, another panel arm, or a guessed model. Record the harness, model, and effort that the replacement runs on. Recovery keeps the workflow's existing retry allowance.

Retain the exact raw `--work-model` argument from the final successful resolver invocation and its complete printed arm. Keep this pair separate from observed execution identity. In an orch attempt, save it as `resolutionContext: {workModel, resolvedArm}` per the [orch reference](../../poteto-mode/scripts/orch/README.md#optional-durable-attempts). A successful invocation without the flag records `workModel: null`. An unsuccessful resolver invocation supplies no successful context. Keep legacy absence unknown. Later model substitution or effort inheritance does not rewrite the saved arm. To recover a `trail reviewer`, pass a saved string `workModel` as `--work-model`. For a saved null, omit the flag. Without saved context, pass the model the work ran on, as for a new review.

## Spawn a role

Build each spawn in this order.

1. **Name the role and the persona** as the harness skill's **Spawn a role** step 1 says. Neither one picks the model or the effort.
2. **Resolve the role** as the harness skill's **Spawn a role** step 2 says, adding `--work-model '<model>@<effort>'` or `--lead-model '<model>'` where the rules below call for them. Relay each note to the user in the reply. The rules, and the grammar for editing the files, live in setup-pstack's [models config reference](../../setup-pstack/references/models-config.md).
   - For `trail reviewer`:
     - When the exit 2 names `--work-model`, follow its message, drop any `[1m]` suffix, and rerun. If the work ran on another vendor's model, rerun without the flag: every Claude Code arm is a Claude model, so the printed arm is cross-model. Otherwise rerun without the flag and disclose the execution identity per step 5.
     - A `"step": "same-model"` field marks a same-model review, and its note says why. Report that resolution and disclose the execution identity per step 5.
   - If the resolver exits nonzero or cannot run, spawn as the harness skill's step 2 says. For `trail reviewer`, disclose the execution identity per step 5.

   Run a design comparison despite `skip` only when the user asked for the comparison itself in this task: they invoked `arena` by name, asked for candidates, a panel, or a count, or named models. A playbook step, a trigger, or a skill that loads `arena` or `architect` for a design comparison is not that request. Say in the reply that the panel ran at the user's request, and name the model each arm ran on.
3. **Build the spawn call** as the harness skill's step 3 says.
4. **Brief the persona** per the [persona contract](named-roles.md).
5. **Report execution without dropping an arm.** Apply this step to every spawn, including a `trail reviewer` that normally resolves to `inherit-parent` without a fallback or `step` marker.
   - If the spawn rejects a model, or a spawned arm fails on model availability such as exhausted usage credits, omit the model, let the arm inherit the session model, and report the substitution.
   - When either identity is unknown, say the review may be same-model.
   - If no field or agent can carry the effort, the effort alone becomes `inherit-parent`. Keep the model and the arm. Say in the reply which role's effort was inherited and why, such as "`how explainer` ran at the session effort because the spawn tool takes no effort and `pstack-effort-xhigh` is not loaded. Run `/setup-pstack` to register it."

## Fork restrictions

A fork, such as Claude Code's `fork` agent type or a Codex full-history fork, inherits the lead's whole context and runs on the lead's model and effort, ignoring any override. Fork only when the role resolves to `inherit-parent` for both, as `default` ships, and the brief would otherwise restate context the lead already holds, such as drafting from files the lead just read or writing a resume note. Never fork a verdict, a review, a fresh-perspective role, or a role that resolves to a model or an effort.
- Every other spawn starts with a fresh context. Where the spawn tool forks unless told otherwise, as Codex's current one does, the spawn call says which one it wants.
