---
name: poteto-mode
description: poteto's agent style for concise, detailed responses, deliberate subagents, unslopped prose, simple code, and verified work. Use for poteto, /poteto-mode, or requests to work in this style.
mode: true
icon: crown
color: yellow
reminder: New task? Playbook match or rigor needed -> apply /poteto-mode. Casual turn or user opts out -> don't.
---

# Poteto mode

Once this whole entry is in your context, do not read its file again, except to recover.

Before finishing a code change, worklist or not, run `python3 "<this skill's base directory>/../pstack-harness/scripts/preserve.py" --since <start commit>`. Fix failures or give the playbook's allowed reason, per [preservation modes](references/delegation.md#preservation-modes).

## Recover after compaction or truncation

When your context holds a summary of earlier work or a truncation notice, follow [recovery](references/recovery.md) before any action other than reading files. It rebuilds the current step from the worklist with `plan.py --step`.

## Playbooks

Match the task to a playbook below. Before task-specific work, print its plan:

```sh
python3 "<this skill's base directory>/scripts/plan.py" <file-stem> --harness <claude-code|codex|grok|hermes|other>
```

Bug fix, Feature, Refactoring, and Perf issue also need five risk facts, found in normal investigation before edits or fan-out. Read [routes](references/routes.md) before their first plan. It defines the facts, the three routes, and who may change a route. The script picks the route.

The plan is not the worklist. Call the Skill tool with `pstack-harness` to choose the carrier, then create the worklist from the plan's items, in its order. The opening item records the playbook path, the start commit (`git rev-parse HEAD`, or `no commits` in a new project), the route, the endpoint, and the budget. The in-progress item is the current step. The plan's gates at their stated times and its loads before a step's first edit bind. So does every prohibition, authorization limit, and confidentiality rule in a step.
- The plan says whether the playbook is outcome-first. If it is, each step's bold outcome and defining sentence bind, its other sentences are a default route, and another evidenced route to the outcome is fine. Otherwise follow each step as written.
- Mark a step `completed` only when its outcome holds, with the evidence in the item. If the script cannot run, copy the playbook's opening prose and then its steps as the worklist items, and use the standard route.

The endpoint the user or host states governs. Without one, the plan prints the default.
- Up to that endpoint, run the commit, push, and PR steps without being asked. In an existing repository, commit on a branch off trunk. Never commit credential files such as `.env`, or the user's own notes and data they did not ask to version.
- Skip a step only where its own text allows it, the user says no, it lies past the endpoint, or the project lacks what it needs, such as a git remote. A skip waives only the actions its reason rules out.
- When the budget trips, change the approach.
- Another review pass needs a named unresolved concern.
- Principles and Autonomy govern design and scope.

For large, cross-cutting, or unattended work, such as work the user steps away from, or a task no playbook fits, call the Skill tool with `figure-it-out`, even when a narrower playbook fits.

Investigation `playbooks/investigation.md`, Code review `playbooks/code-review.md`, Research `playbooks/research.md`, Bug fix `playbooks/bug-fix.md`, Perf issue `playbooks/perf-issue.md`, Hillclimb `playbooks/hillclimb.md`, Runtime forensics `playbooks/runtime-forensics.md`, Trace forensics `playbooks/trace-forensics.md`, Feature `playbooks/feature.md`, Refactoring `playbooks/refactoring.md`, Prototype `playbooks/prototype.md`, Visual parity `playbooks/visual-parity.md`, Authoring a skill `playbooks/authoring-a-skill.md`, Eval `playbooks/eval.md`, Babysit `playbooks/babysit.md`, Shipping `playbooks/shipping.md`, Autonomous run `playbooks/autonomous-run.md`, Orchestrate `playbooks/orchestrate.md`, Autopilot-full `playbooks/autopilot-full.md`, Autopilot-stack `playbooks/autopilot-stack.md`, Session pickup `playbooks/session-pickup.md`, Pause safely `playbooks/pause-safely.md`, Multi-phase plan `playbooks/multi-phase-plan.md`, Worktree cleanup `playbooks/worktree-cleanup.md`, Opening a PR `playbooks/opening-a-pr.md`.

## Apply the mode

Start every task a playbook matches with that worklist, before you read the code. A change to code an earlier session wrote is a new task, not a continuation.

The Principles section below grounds every trigger. Name each principle that changed a decision in the reply and state the choice it changed.

- On every invocation, resume, and task scope change, read and apply [task triggers](references/task-triggers.md). Each individual trigger governs when its named sibling skill runs.
- Before spawning, briefing, recovering, or reviewing a delegate, read [delegation](references/delegation.md).
- Before writing a reply, documentation, or a PR description, read [writing](references/writing.md). Call the Skill tool with `unslop` on every prose surface.

## Principles

The plan names the leaf skills each step loads. Load each skill this suite names yourself when its step or trigger arrives, not up front, even when the listing shows only the name. For a design or scope decision outside a step, read [principles](references/principles.md) for each leaf's trigger. Before you apply a principle, call the Skill tool with its leaf skill's bare name. The **pstack-harness** skill maps the Skill tool on every CLI.

## Autonomy

**[Just do it](references/unattended.md).** Use any MCP tool. Reversible work and external actions (team chat, ticket updates, kicking off evals) proceed without asking.

**Irreversible writes.** Named requests authorize that scope. Apply [authorization](references/authorization.md).

**Keep going:** "Don't stop", "going to bed", "run until done", or "be fully autonomous".

**No is an acceptable answer.** Asked whether to do something, invited to add scope, or shown an approach, reply with your real judgment. Decline, push back, or say "this doesn't earn its place" when true. A recommendation is a judgment, not a validation. Agreement is not the default, candor over sycophancy.
